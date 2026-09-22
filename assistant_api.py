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

from assistant import agent, cards, config, label, store, tools, usage

assistant_bp = Blueprint('assistant', __name__)

_get_db = None
_login_required = None
_admin_required = None
_recompute = None
_record_checklist = None


def init_assistant(app, get_db_connection, login_required, admin_required,
                   recompute=None, record_checklist=None):
    global _get_db, _login_required, _admin_required, _recompute, _record_checklist
    _get_db = get_db_connection
    _login_required = login_required
    _admin_required = admin_required
    _recompute = recompute
    # app.record_checklist_day. Answering the check-in has to run the same
    # code the Today page runs, and the tool layer cannot import app.
    _record_checklist = record_checklist
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


def _queue_structured(conn, user_id, payload, today):
    """Turn a filled-in card into queued actions, through the ordinary tools.

    ## Why this does not go through the model

    Every other card answers by composing a sentence and sending it as a normal
    chat turn, which is a good rule: one validated path, and the model can catch
    nonsense on the way past.

    A filled-in workout defeats it. Six exercises with their own sets, reps,
    weights and units flatten into a paragraph that costs a round trip to write,
    another to re-parse, and loses the exercise ids the card already had - so the
    model searches every name back up by hand and occasionally picks the wrong
    Bench Press.

    So the card submits what it already knows, and it is queued by calling the
    *same tool function* the model would have called. Same validation, same
    plausibility checks, same proposal for the person to confirm. It is not a
    second path into the database; it is the same path with a different caller.

    Returns queued actions, or raises ToolError with something the person can act
    on.
    """
    if not isinstance(payload, dict) or payload.get('type') != 'workout':
        raise tools.ToolError('That card is not one this version understands.')

    ctx = tools.ToolContext(conn, user_id, today=today)
    exercises = [
        entry for entry in (payload.get('exercises') or [])
        # An untouched row is not a claim that they did nothing - it is a row
        # they did not fill in, and dropping it is the honest reading.
        if entry.get('sets')
    ]
    if not exercises:
        raise tools.ToolError('Nothing was filled in, so there is nothing to log.')

    built = []
    for entry in exercises:
        count = int(entry.get('sets') or 0)
        if not 0 < count <= 20:
            raise tools.ToolError(f'{entry.get("name")}: {count} sets is not plausible.')
        # The card collects one line per exercise and expands it here, rather
        # than asking somebody to type the same numbers three times. Per-set
        # variation still arrives intact when the model builds the payload.
        built.append({
            'exercise_id': entry.get('exercise_id'),
            'name': entry.get('name') or '',
            'sets': [{
                'reps': entry.get('reps'),
                'weight': entry.get('weight'),
                'weight_unit': entry.get('weight_unit') or payload.get('weight_unit') or 'kg',
                'duration_minutes': entry.get('duration_minutes'),
            } for _ in range(count)],
        })

    tools.propose_workout(
        ctx, date=payload.get('date'), name=payload.get('name'), exercises=built,
    )
    return ctx.queued


@assistant_bp.route('/api/assistant/chat', methods=['POST'])
@_auth
def chat():
    data = request.json or {}
    message = (data.get('message') or '').strip()
    kind = 'today' if data.get('kind') == 'today' else 'general'
    subject_date = (data.get('date') or '').strip() or _today()
    auto_apply = data.get('auto_apply') is True

    if not message:
        return jsonify({'error': 'Say something.'}), 400
    if len(message) > 2000:
        return jsonify({'error': 'That message is too long.'}), 400

    user_id = session.get('user_id')
    username = session.get('username') or f'user_{user_id}'
    structured = data.get('structured')

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

            if structured:
                # A filled-in card knows exactly what it means, so it is queued
                # directly rather than described to the model and read back.
                try:
                    queued = _queue_structured(conn, user_id, structured, _today())
                    reply = 'Ready to save that session.'
                except tools.ToolError as error:
                    yield 'data: ' + json.dumps({
                        'type': 'error', 'kind': 'card', 'message': str(error),
                    }) + '\n\n'
                    yield 'data: ' + json.dumps({'type': 'end'}) + '\n\n'
                    return
                yield 'data: ' + json.dumps({
                    'type': 'done', 'reply': reply, 'queued': queued,
                    'budget': usage.budget_state(conn, user_id),
                }) + '\n\n'

            for event in ([] if structured else agent.run_turn(
                conn, user_id, prior, message,
                feature=kind, today=_today(), recompute=_recompute,
                username=username, record_checklist=_record_checklist,
                # A guided check-in is a different job from free chat, so it
                # gets its own instructions rather than a paragraph bolted on.
                instructions=agent.TODAY_PROMPT if kind == 'today' else None,
            )):
                if event['type'] == 'done':
                    queued = event['queued']
                    reply = event['reply']
                yield f'data: {json.dumps(event)}\n\n'

            if reply:
                store.add_message(conn, conversation_id, 'assistant', reply)

            if queued:
                proposal_id = store.create_proposal(conn, user_id, conversation_id, queued)
                # The merged set, not just this turn's. A check-in accumulates
                # across turns, and the card has to show all of it.
                merged = store.get_proposal(conn, user_id, proposal_id)
                actions = json.loads(merged['actions'])
                if auto_apply:
                    result = store.apply(
                        conn, user_id, proposal_id, recompute=_recompute, today=_today(),
                        username=session.get('username'), record_checklist=_record_checklist,
                    )
                    yield 'data: ' + json.dumps({
                        'type': 'applied', 'id': proposal_id, 'actions': actions, **result,
                    }) + '\n\n'
                else:
                    yield 'data: ' + json.dumps({
                        'type': 'proposal', 'id': proposal_id, 'actions': actions,
                    }) + '\n\n'

            # A card is a faster answer to the next routine check-in question,
            # not a second saving path. The client turns it into a normal chat
            # message and the assistant still queues a proposal for review.
            input_card = cards.input_card(
                conn, user_id, kind, subject_date, message, prior, queued
            )
            if input_card:
                yield 'data: ' + json.dumps({
                    'type': 'input_card', 'card': input_card,
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
            username=session.get('username'), record_checklist=_record_checklist,
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


# --- reading a label -----------------------------------------------------------

#: What a browser will actually produce from a camera, and nothing else.
#:
#: Checked against the file's own first bytes rather than the declared
#: content-type, because the content-type is whatever the client said it was.
IMAGE_SIGNATURES = (
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'RIFF', 'image/webp'),
)


def _sniff_image(data):
    """The media type these bytes really are, or None.

    A photograph is the one thing this app accepts that it did not generate, so
    it is the one place worth looking at the bytes. `RIFF` also fronts .wav, so
    webp gets a second check at offset 8.
    """
    for signature, media_type in IMAGE_SIGNATURES:
        if data.startswith(signature):
            if media_type == 'image/webp' and data[8:12] != b'WEBP':
                continue
            return media_type
    return None


@assistant_bp.route('/api/assistant/label', methods=['POST'])
@_auth
def read_label():
    """Turn a photo of a nutrition panel into a food the person can confirm.

    Returns the payload, and writes nothing. Saving goes through `POST /api/foods`
    like any other custom food - the scanner is an input method, not a second way
    into the catalogue, and a person edits the numbers in between.

    The image is held in memory for this request and never written to disk. It is
    a picture of a packet; once the numbers are out there is nothing left to want.
    """
    upload = request.files.get('image')
    if upload is None:
        return jsonify({'error': 'No image was sent.'}), 400

    data = upload.read()
    if not data:
        return jsonify({'error': 'That image was empty.'}), 400

    media_type = _sniff_image(data)
    if media_type is None:
        return jsonify({
            'error': 'That file is not a JPEG, PNG or WebP image.',
        }), 400

    conn = _get_db()
    try:
        food = label.read_label(conn, session.get('user_id'), data, media_type)
    except label.LabelError as error:
        # A refusal the person can act on - "retake with the headings visible" -
        # rather than a 500. Every branch in label.py says what to do next.
        return jsonify({'error': str(error)}), 422
    finally:
        conn.close()

    return jsonify(food)


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
