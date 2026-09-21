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

#: How long a free-form chat stays the same conversation.
#:
#: Long enough that stepping away mid-thought and coming back is continuous,
#: short enough that tomorrow morning's "what did I eat" is not answered in the
#: context of last night's. A check-in ignores this and is bounded by its date
#: instead, which is the more natural boundary for it.
CHAT_RESUME_HOURS = 6


def open_conversation(conn, user_id, kind='general', subject_date=None):
    """The person's live conversation of this kind, created if there is none.

    Resumed rather than restarted, and that is the whole of it: without this,
    every message starts a fresh conversation with no history, so the assistant
    cannot answer "make that 120 grams instead" because it has already forgotten
    what "that" was.

    A check-in resumes by date - people close the tab halfway through one, and
    being asked about breakfast twice is the fastest way to make this not worth
    using. Free chat resumes by recency.
    """
    if kind == 'today' and subject_date:
        row = conn.execute(
            "SELECT id FROM ai_conversations WHERE user_id = ? AND kind = 'today' "
            "AND subject_date = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (user_id, subject_date),
        ).fetchone()
        if row:
            return row['id']
    elif kind != 'today':
        row = conn.execute(
            "SELECT id FROM ai_conversations WHERE user_id = ? AND kind = ? "
            "AND status = 'open' AND updated_at >= datetime('now', ?) "
            'ORDER BY id DESC LIMIT 1',
            (user_id, kind, f'-{CHAT_RESUME_HOURS} hours'),
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

#: Action types where a second one replaces the first rather than adding to it.
#:
#: The rule mirrors what the appliers actually do. `_apply_sleep` deletes and
#: reinserts, `_apply_lifestyle` and `_apply_checkin` merge - one row per day
#: either way - while meals, workouts and study sessions legitimately happen more
#: than once. So a corrected bedtime overwrites the earlier one in the queue, and
#: a second meal joins it.
ONE_PER_DAY = frozenset({'sleep', 'lifestyle', 'checkin'})


def _merge(existing, incoming):
    """Accumulate a turn's actions onto what the conversation already queued."""
    merged = list(existing)

    for action in incoming:
        if action.get('type') in ONE_PER_DAY:
            for index, current in enumerate(merged):
                if (current.get('type') == action.get('type')
                        and current.get('date') == action.get('date')):
                    merged[index] = action
                    break
            else:
                merged.append(action)
        else:
            merged.append(action)

    return merged


def create_proposal(conn, user_id, conversation_id, actions):
    """Add a turn's actions to this conversation's pending card.

    ## Why this accumulates rather than replaces

    It used to replace, and that was right when a turn was the whole
    interaction: "I had oats" in, one card out. A guided check-in is not that. It
    asks about sleep, then training, then food, queueing as it goes - and
    replacing meant the card at the end held only the last thing discussed, with
    everything earlier marked superseded and silently dropped. The person presses
    Save on a card that looks right and loses two thirds of what they just said.

    So a pending proposal from the *same* conversation is extended. One from a
    different conversation is still superseded, which keeps the property that
    mattered: there are never two live Save buttons.
    """
    pending = conn.execute(
        "SELECT id, conversation_id, actions FROM ai_proposals "
        "WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()

    if pending and pending['conversation_id'] == conversation_id:
        try:
            existing = json.loads(pending['actions'])
        except ValueError:
            existing = []
        conn.execute(
            'UPDATE ai_proposals SET actions = ? WHERE id = ?',
            (json.dumps(_merge(existing, actions)), pending['id']),
        )
        conn.commit()
        return pending['id']

    if pending:
        conn.execute(
            "UPDATE ai_proposals SET status = 'superseded', "
            'resolved_at = CURRENT_TIMESTAMP WHERE id = ?',
            (pending['id'],),
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


def apply(conn, user_id, proposal_id, submitted_actions=None, recompute=None,
          today=None, username=None, record_checklist=None):
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

    ctx = tools.ToolContext(conn, user_id, today=today, username=username,
                            record_checklist=record_checklist)
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
