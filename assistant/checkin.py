"""What is worth asking about today, and why - derived, not hardcoded.

The obvious way to build a guided check-in is a fixed script: wake time, then
breakfast, then training, then study. It works until the third day, when it asks
about the workout you logged from the gym two hours ago and you stop using it.

So the order comes from the scoring engine instead. Two numbers already in
`scoring/config.py` decide it, and both are decisions this project made long
before there was an assistant:

**`measured_weight = 3.0` against `self_report_weight = 1.0`.** A logged set of
80 kg x 8 is better evidence than a ticked box, so it dominates the blend. One
answer about what you actually ate is worth three checklist ticks.

**`self_report_ceiling = 0.5`.** An attribute in `MEASURABLE_ATTRIBUTES` with no
measured evidence is capped at half, no matter what the checklist claims. This is
the strong one: if nothing fed Recovery today, then Recovery *cannot go above
0.5* until something does. Asking about sleep does not merely add evidence, it
lifts a ceiling.

Which gives a priority rule nobody had to invent:

1. A workspace whose attribute is currently **capped** - highest. Three times the
   weight, and it unblocks a score that is otherwise stuck.
2. A workspace with no data today whose attribute is already evidenced by
   something else - still measured, still 3x.
3. The checklist - 1x, but the only direct evidence of Discipline, and the thing
   that marks the day logged at all.
4. Anything already recorded - not asked about.

The assistant is told the order and the reason. It still chooses the wording, and
it can depart from the order if the person volunteers something else - the plan is
advice about what matters, not a script to read out.
"""
from scoring.config import DEFAULT_CONFIG, MEASURABLE_ATTRIBUTES


def _listed(names):
    """'Strength, Stamina and Agility' rather than 'a and b and c'.

    These sentences are read by the model and can be repeated to the person when
    they ask why something is being asked, so they have to read like English.
    """
    names = list(names)
    if len(names) <= 1:
        return names[0] if names else ''
    return f'{", ".join(names[:-1])} and {names[-1]}'


#: Which workspace can produce measured evidence for which attributes.
#:
#: Read off `scoring/producers.py` rather than guessed: `sleep_ratios` feeds
#: Recovery and Discipline, `training_ratios` feeds the three physical
#: attributes, `learning_ratios` feeds Knowledge and Focus, and steps feed
#: Stamina through `steps_ratios`.
WORKSPACE_ATTRIBUTES = {
    'sleep': ('Recovery', 'Discipline'),
    'training': ('Strength', 'Stamina', 'Agility'),
    'food': ('Recovery',),
    'study': ('Knowledge', 'Focus'),
    'steps': ('Stamina',),
}

#: What to say when asking. Deliberately about the person's day rather than
#: about the app's data model - nobody thinks of sleep as "a Recovery signal".
PROMPTS = {
    'sleep': 'when they went to bed and got up',
    'training': 'whether they trained, and what',
    'food': 'what they ate today',
    'study': 'whether they studied or read anything',
    'steps': 'roughly how active they were - steps, a walk',
    'checkin': "the daily check-in questions they have not answered",
}


def _measured_today(conn, user_id, date):
    """Which workspaces have any measured evidence on this date."""
    present = set()

    checks = (
        ('sleep', 'SELECT 1 FROM sleep_entries WHERE user_id = ? AND date = ?'),
        ('training', 'SELECT 1 FROM workout_sessions WHERE user_id = ? AND date = ?'),
        ('food', 'SELECT 1 FROM food_entries WHERE user_id = ? AND date = ?'),
        ('study', 'SELECT 1 FROM learning_sessions WHERE user_id = ? AND date = ?'),
        ('steps', 'SELECT 1 FROM lifestyle_days WHERE user_id = ? AND date = ? '
                  'AND steps IS NOT NULL AND steps > 0'),
    )
    for workspace, sql in checks:
        if conn.execute(sql + ' LIMIT 1', (user_id, date)).fetchone():
            present.add(workspace)

    return present


def plan(conn, user_id, date, survey_items=None, answered=None):
    """An ordered list of what to ask about, each with the reason it ranks there.

    `answered` is the set of survey question ids already answered for the day, so
    a half-finished check-in is not restarted from the top.
    """
    recorded = _measured_today(conn, user_id, date)

    # Which measurable attributes have nothing behind them today. An attribute
    # evidenced by any workspace is not capped, so a second workspace feeding it
    # is worth less than the first one feeding something else.
    evidenced = set()
    for workspace in recorded:
        evidenced.update(WORKSPACE_ATTRIBUTES.get(workspace, ()))
    capped = {attribute for attribute in MEASURABLE_ATTRIBUTES if attribute not in evidenced}

    items = []
    for workspace, attributes in WORKSPACE_ATTRIBUTES.items():
        if workspace in recorded:
            items.append({
                'topic': workspace,
                'status': 'recorded',
                'priority': 0,
                'ask': None,
                'reason': 'Already logged today - do not ask about this.',
            })
            continue

        unlocks = sorted(set(attributes) & capped)
        if unlocks:
            items.append({
                'topic': workspace,
                'status': 'missing',
                'priority': 3,
                'ask': PROMPTS[workspace],
                'unlocks': unlocks,
                'reason': (
                    f'{_listed(unlocks)} '
                    f'{"have" if len(unlocks) > 1 else "has"} no measured evidence '
                    f'today, so {"they are" if len(unlocks) > 1 else "it is"} capped at '
                    f'{int(DEFAULT_CONFIG.self_report_ceiling * 100)}% until something '
                    f'is logged.'
                ),
            })
        else:
            items.append({
                'topic': workspace,
                'status': 'missing',
                'priority': 2,
                'ask': PROMPTS[workspace],
                'unlocks': [],
                'reason': (
                    f'Nothing logged, though {_listed(sorted(attributes))} '
                    f'{"are" if len(attributes) > 1 else "is"} already evidenced by '
                    f'something else today. Measured data still counts '
                    f'{DEFAULT_CONFIG.measured_weight:g}x a checklist answer.'
                ),
            })

    unanswered = []
    if survey_items is not None:
        answered = answered or set()
        unanswered = [item for item in survey_items if item.get('id') not in answered]

    if survey_items is None or unanswered:
        items.append({
            'topic': 'checkin',
            'status': 'partial' if (answered and unanswered) else 'missing',
            'priority': 1,
            'ask': PROMPTS['checkin'],
            'reason': (
                f'{len(unanswered)} question(s) unanswered. '
                if survey_items is not None else ''
            ) + (
                'Self-reported, so it counts '
                f'{DEFAULT_CONFIG.self_report_weight:g}x - but it is the only direct '
                'evidence of Discipline, and it is what marks the day as logged.'
            ),
            'questions': [
                {'id': item.get('id'), 'name': item.get('name'), 'type': item.get('type'),
                 'options': item.get('options') or None}
                for item in unanswered
            ],
        })
    else:
        items.append({
            'topic': 'checkin', 'status': 'recorded', 'priority': 0, 'ask': None,
            'reason': 'Every question is answered - do not ask about this.',
        })

    # Within a priority band, the topic that unblocks the most capped
    # attributes comes first: training unlocks three, study two, sleep one. The
    # name is only the final tiebreak, so the order is stable rather than
    # arbitrary.
    items.sort(key=lambda entry: (
        -entry['priority'], -len(entry.get('unlocks') or []), entry['topic'],
    ))

    return {
        'date': date,
        'ask_about_in_this_order': [i['topic'] for i in items if i['priority'] > 0],
        'already_recorded': sorted(recorded),
        'items': items,
        'follow_up': follow_up(conn, user_id, date),
    }


def follow_up(conn, user_id, date):
    """Open commitments to close the check-in on - not part of the ranking.

    Goals and tasks feed no attribute. `init_goals` is registered without a
    recompute function precisely because a goal is an intention rather than
    evidence, so giving them a priority alongside sleep and training would mean
    inventing an analytical weight the engine does not give them.

    They are worth asking about anyway, which is why they are here and not
    omitted - just at the end, briefly, and declared as affecting nothing.
    """
    overdue = conn.execute(
        'SELECT COUNT(*) AS n FROM tasks WHERE user_id = ? AND completed_on IS NULL '
        'AND COALESCE(archived, 0) = 0 AND due_date IS NOT NULL AND due_date < ?',
        (user_id, date),
    ).fetchone()['n']

    open_tasks = conn.execute(
        'SELECT COUNT(*) AS n FROM tasks WHERE user_id = ? AND completed_on IS NULL '
        'AND COALESCE(archived, 0) = 0',
        (user_id,),
    ).fetchone()['n']

    goals = conn.execute(
        "SELECT COUNT(*) AS n FROM goals WHERE user_id = ? AND status = 'active' "
        'AND COALESCE(archived, 0) = 0',
        (user_id,),
    ).fetchone()['n']

    return {
        'open_tasks': int(open_tasks),
        'overdue_tasks': int(overdue),
        'active_goals': int(goals),
        'ask': (
            'Close with anything outstanding - call get_open_work for the detail. '
            'Keep it to one question; these affect no score.'
            if open_tasks or goals else None
        ),
        'affects_scores': False,
    }
