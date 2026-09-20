"""The assistant's endpoints.

Its own blueprint for the same reasons every other workspace has one: app.py is
long enough, and the auth and database helpers are injected at registration so
this module never imports app back.

## Why the chat endpoint streams

A turn can take twenty seconds - several round trips to the provider, with tool
calls in between. Three things go wrong with returning that as one response.

The person watches a spinner with nothing behind it. The request is long enough
to argue with a proxy or a worker timeout. And when it does fail, it fails after
twenty seconds of silence with nothing to show for it.

So the turn is streamed as server-sent events: a `status` event each time a tool
runs, then `done`. The client can say "checking what you logged today" instead of
nothing, and a long turn is a sequence of short writes rather than one long
silence.

## Why a GET endpoint decides whether the feature exists

`/api/assistant/state` reports whether there is an API key at all. The SPA hides
the assistant entirely when there is not, which is what keeps it genuinely
optional: an instance with no key is not a broken instance, it is an instance
without a chat button.
"""
import json
from datetime import date as _date

from flask import Blueprint, Response, jsonify, request, session, stream_with_context

from assistant import agent, config, store, usage

assistant_bp = Blueprint('assistant', __name__)

_get_db = None
_login_required = None
_admin_required = None
_recompute = None


def init_assistant(app, get_db_connection, login_required, admin_required, recompute=None):
    global _get_db, _login_required, _admin_required, _recompute
    _get_db = get_db_connection
    _login_required = login_required
    _admin_required = admin_required
    _recompute = recompute
    app.register_blueprint(assistant_bp)


def _auth(view):
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _admin(view):
    def wrapper(*args, **kwargs):
        return _admin_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _today():
    return _date.today().strftime('%Y-%m-%d')


# --- is this thing on ----------------------------------------------------------

@assistant_bp.route('/api/assistant/state')
@_auth
def state():
    """What the client needs to decide whether to show a chat button at all."""
    conn = _get_db()
    try:
        budget = usage.budget_state(conn, session.get('user_id'))
        pending = conn.execute(
            "SELECT id, actions, created_at FROM ai_proposals "
            "WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (session.get('user_id'),),
        ).fetchone()
    finally:
        conn.close()

    return jsonify({
        'configured': config.is_configured(),
        'model': config.CHAT_MODEL,
        'budget': budget,
        # A proposal survives a reload. Somebody who closed the tab mid-check-in
        # should find their Save button still there.
        'pending_proposal': {
            'id': pending['id'],
            'actions': json.loads(pending['actions']),
            'created_at': pending['created_at'],
        } if pending else None,
    })


# --- talking -------------------------------------------------------------------

@assistant_bp.route('/api/assistant/chat', methods=['POST'])
@_auth
def chat():
    data = request.json or {}
    message = (data.get('message') or '').strip()
    kind = 'today' if data.get('kind') == 'today' else 'general'
    subject_date = (data.get('date') or '').strip() or _today()

    if not message:
        return jsonify({'error': 'Say something.'}), 400
    if len(message) > 2000:
        return jsonify({'error': 'That message is too long.'}), 400

    user_id = session.get('user_id')

    def events():
        # The generator outlives the view, so it owns its own connection rather
        # than borrowing one that is about to be closed.
        conn = _get_db()
        try:
            conversation_id = store.open_conversation(
                conn, user_id, kind, subject_date if kind == 'today' else None
            )
            prior = store.history(conn, conversation_id)
            store.add_message(conn, conversation_id, 'user', message)

            queued, reply = [], ''
            for event in agent.run_turn(
                conn, user_id, prior, message,
                feature=kind, today=_today(), recompute=_recompute,
            ):
                if event['type'] == 'done':
                    queued = event['queued']
                    reply = event['reply']
                yield f'data: {json.dumps(event)}\n\n'

            if reply:
                store.add_message(conn, conversation_id, 'assistant', reply)

            if queued:
                proposal_id = store.create_proposal(conn, user_id, conversation_id, queued)
                yield 'data: ' + json.dumps({
                    'type': 'proposal', 'id': proposal_id, 'actions': queued,
                }) + '\n\n'

            yield 'data: ' + json.dumps({'type': 'end'}) + '\n\n'
        except Exception:  # noqa: BLE001 - a stream cannot raise a 500 at the client
            # Headers went out with the 200. The only way to report a failure now
            # is in the stream itself, which is why this is caught rather than
            # left to the app's error handler.
            conn.rollback()
            yield 'data: ' + json.dumps({
                'type': 'error', 'kind': 'server',
                'message': 'Something went wrong. Nothing was saved.',
            }) + '\n\n'
        finally:
            conn.close()

    response = Response(stream_with_context(events()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    # Tells nginx not to buffer. Caddy streams event-streams already; this costs
    # nothing and means the deployment can change without this going quiet.
    response.headers['X-Accel-Buffering'] = 'no'
    return response


# --- confirming ----------------------------------------------------------------

@assistant_bp.route('/api/assistant/proposals/<int:proposal_id>/apply', methods=['POST'])
@_auth
def apply_proposal(proposal_id):
    """Save a proposal, optionally with the person's edits.

    `actions` in the body is the edited copy. It is reconciled against what was
    stored - same types in the same order, values only - so an edit is a
    correction and never a new instruction.
    """
    data = request.json or {}
    conn = _get_db()
    try:
        result = store.apply(
            conn, session.get('user_id'), proposal_id,
            submitted_actions=data.get('actions'),
            recompute=_recompute, today=_today(),
        )
    except store.ProposalRejected as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    finally:
        conn.close()

    return jsonify({
        'success': result['failed'] is None,
        'applied': result['applied'],
        'failed': result['failed'],
    })


@assistant_bp.route('/api/assistant/proposals/<int:proposal_id>/discard', methods=['POST'])
@_auth
def discard_proposal(proposal_id):
    conn = _get_db()
    try:
        store.discard(conn, session.get('user_id'), proposal_id)
    except store.ProposalRejected as error:
        return jsonify({'success': False, 'message': str(error)}), 400
    finally:
        conn.close()
    return jsonify({'success': True})


# --- what it costs -------------------------------------------------------------

@assistant_bp.route('/api/admin/ai-usage')
@_admin
def ai_usage():
    """Spend across everyone. Admin only - who talked to the assistant how much
    stays with whoever pays the bill."""
    try:
        days = max(1, min(365, int(request.args.get('days', 30))))
    except (TypeError, ValueError):
        days = 30

    conn = _get_db()
    try:
        return jsonify(usage.report(conn, days))
    finally:
        conn.close()
