"""Conversations and proposals on disk.

Two halves. The conversation half is bookkeeping. The proposal half is the
security boundary, and the function worth reading is `apply`.

## The boundary

A proposal is created by the model and confirmed by a person, and in between it
travels to a browser and back. The person is allowed to edit it - that is the
point of the confirmation card; "45 minutes" they actually meant as 35 should be
fixable without another round of conversation.

So the payload that comes back cannot simply be trusted, and it cannot simply be
ignored either. `apply` takes the edited copy and checks it against the stored
one: same number of actions, same types, in the same order. Only values may
differ.

That is what stops an edited payload turning "log a 300 kcal breakfast" into
"delete every workout". The client is the user's own browser, so this is not
really defence against them - it is defence against anything that gets to speak
as that browser, and against a future version of the client with a bug in it.
"""
import json

from . import config, tools


# --- conversations -------------------------------------------------------------

def open_conversation(conn, user_id, kind='general', subject_date=None):
    """The person's live conversation of this kind, created if there is none.

    A daily check-in is resumed rather than restarted: people close the tab
    halfway through one, and being asked about breakfast twice is the fastest
    way to make the feature not worth using.
    """
    if kind == 'today' and subject_date:
        row = conn.execute(
            "SELECT id FROM ai_conversations WHERE user_id = ? AND kind = 'today' "
            "AND subject_date = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (user_id, subject_date),
        ).fetchone()
        if row:
            return row['id']

    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO ai_conversations (user_id, kind, subject_date) VALUES (?, ?, ?)',
        (user_id, kind, subject_date),
    )
    conn.commit()
    return cursor.lastrowid


def history(conn, conversation_id, limit=None):
    """Prior turns, oldest first, in the shape the provider wants.

    Only user and assistant text is replayed - tool calls and their results are
    dropped. Replaying them would double the token count of every turn to tell
    the model things it can look up again in one call, and a stale `get_day`
    from an hour ago is worse than no `get_day` at all.
    """
    limit = limit or config.MAX_HISTORY_MESSAGES
    rows = conn.execute(
        'SELECT role, content FROM ai_messages WHERE conversation_id = ? '
        'ORDER BY id DESC LIMIT ?',
        (conversation_id, limit),
    ).fetchall()

    out = []
    for row in reversed(rows):
        try:
            content = json.loads(row['content'])
        except ValueError:
            content = row['content']
        if isinstance(content, str) and content.strip():
            out.append({'role': row['role'], 'content': content})
    return out


def add_message(conn, conversation_id, role, content):
    conn.execute(
        'INSERT INTO ai_messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conversation_id, role, json.dumps(content)),
    )
    conn.execute(
        'UPDATE ai_conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (conversation_id,),
    )
    conn.commit()


# --- proposals -----------------------------------------------------------------

def create_proposal(conn, user_id, conversation_id, actions):
    """Store a change-set and retire any older one still waiting.

    Superseding matters: without it, a conversation that proposes twice leaves
    two live Save buttons, and pressing the older one logs something the person
    already talked past.
    """
    conn.execute(
        "UPDATE ai_proposals SET status = 'superseded', resolved_at = CURRENT_TIMESTAMP "
        "WHERE user_id = ? AND status = 'pending'",
        (user_id,),
    )
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO ai_proposals (conversation_id, user_id, actions) VALUES (?, ?, ?)',
        (conversation_id, user_id, json.dumps(actions)),
    )
    conn.commit()
    return cursor.lastrowid


def get_proposal(conn, user_id, proposal_id):
    """Scoped to the owner, so an id from somewhere else finds nothing."""
    return conn.execute(
        'SELECT * FROM ai_proposals WHERE id = ? AND user_id = ?',
        (proposal_id, user_id),
    ).fetchone()


class ProposalRejected(Exception):
    """The confirmed change-set is not a version of the proposed one."""


def _reconcile(stored, submitted):
    """The edited change-set, checked against what was actually proposed.

    Values may change. Shape may not: same count, same types, same order. An
    edit is a correction to a number, not a new instruction.
    """
    if submitted is None:
        return stored

    if not isinstance(submitted, list):
        raise ProposalRejected('The confirmed actions were not a list.')

    if len(submitted) != len(stored):
        raise ProposalRejected(
            f'This proposal had {len(stored)} action(s); {len(submitted)} came back.'
        )

    for index, (original, edited) in enumerate(zip(stored, submitted)):
        if not isinstance(edited, dict):
            raise ProposalRejected(f'Action {index + 1} was not an object.')
        if edited.get('type') != original.get('type'):
            raise ProposalRejected(
                f'Action {index + 1} changed from "{original.get("type")}" '
                f'to "{edited.get("type")}". Only values may be edited.'
            )

    return submitted


def apply(conn, user_id, proposal_id, submitted_actions=None, recompute=None, today=None):
    """Confirm a proposal and execute it.

    Actions run in order and stop at the first failure, with everything done so
    far kept. Half-applying is the honest outcome: the alternative is unwinding
    writes that have already moved attribute scores and XP, and a rollback that
    has to un-award a streak is a worse bug than a partial save the person can
    see and finish by hand.
    """
    row = get_proposal(conn, user_id, proposal_id)
    if row is None:
        raise ProposalRejected('No such proposal.')
    if row['status'] != 'pending':
        raise ProposalRejected(f'This proposal was already {row["status"]}.')

    stored = json.loads(row['actions'])
    actions = _reconcile(stored, submitted_actions)

    ctx = tools.ToolContext(conn, user_id, today=today)
    applied, failed = [], None

    for action in actions:
        try:
            applied.append(tools.apply_action(ctx, dict(action), recompute=recompute))
        except Exception as error:  # noqa: BLE001 - recorded, not swallowed
            failed = f'{action.get("type")}: {error}'
            break

    result = {'applied': applied, 'failed': failed}
    conn.execute(
        'UPDATE ai_proposals SET status = ?, result = ?, resolved_at = CURRENT_TIMESTAMP '
        'WHERE id = ?',
        ('applied' if failed is None else 'partial', json.dumps(result), proposal_id),
    )
    conn.commit()
    return result


def discard(conn, user_id, proposal_id):
    row = get_proposal(conn, user_id, proposal_id)
    if row is None:
        raise ProposalRejected('No such proposal.')
    if row['status'] != 'pending':
        raise ProposalRejected(f'This proposal was already {row["status"]}.')

    conn.execute(
        "UPDATE ai_proposals SET status = 'discarded', resolved_at = CURRENT_TIMESTAMP "
        'WHERE id = ?',
        (proposal_id,),
    )
    conn.commit()
