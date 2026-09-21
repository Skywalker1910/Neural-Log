"""The guided check-in: what gets asked, in what order, and why.

The ordering is the feature. A fixed script - wake time, breakfast, training,
study - works until the third day, when it asks about the workout you logged
from the gym two hours ago and you stop using it.

So these tests are mostly about *not* asking: that a recorded topic drops out,
that the remaining ones rank by what the scoring engine says is worth most, and
that the reason given is the real one rather than a label.

The other half is `_apply_checkin`, which must go through `record_checklist_day`
rather than writing `daily_log` itself. A second implementation there would be
the drift that function's docstring warns about, and it would surface weeks
later as a streak wrong by a day.
"""
import assistant.checkin as checkin
import assistant.tools as tools
from conftest import register
from scoring.config import DEFAULT_CONFIG


def context(app_module, user_id=1, today='2026-09-20', username='alice'):
    import app as app_module_ref
    return tools.ToolContext(
        app_module.get_db_connection(), user_id, today=today, username=username,
        record_checklist=app_module_ref.record_checklist_day,
    )


def topics(plan):
    return plan['ask_about_in_this_order']


def item(plan, topic):
    return next(entry for entry in plan['items'] if entry['topic'] == topic)


# --- what gets asked -----------------------------------------------------------

def test_an_empty_day_asks_about_everything(app_module, client):
    register(client)
    ctx = context(app_module)

    plan = checkin.plan(ctx.conn, 1, '2026-09-20')

    assert set(topics(plan)) == {'sleep', 'training', 'food', 'study', 'steps', 'checkin'}


def test_a_recorded_topic_drops_out_entirely(app_module, client):
    """The whole point. Asking about the workout they logged two hours ago is
    how a tool like this stops being worth opening."""
    register(client)
    ctx = context(app_module)
    ctx.conn.execute(
        "INSERT INTO workout_sessions (user_id, date, name, total_sets) "
        "VALUES (1, '2026-09-20', 'Upper body', 12)"
    )
    ctx.conn.commit()

    plan = checkin.plan(ctx.conn, 1, '2026-09-20')

    assert 'training' not in topics(plan)
    assert item(plan, 'training')['status'] == 'recorded'
    assert 'do not ask' in item(plan, 'training')['reason']


def test_a_capped_attribute_outranks_an_already_evidenced_one(app_module, client):
    """The ordering rule, from the scoring engine rather than a developer's list.

    Training evidences Strength, Stamina and Agility. Once it is logged, steps -
    which only feed Stamina - stop unlocking anything and drop below sleep and
    study, whose attributes are still capped at half.
    """
    register(client)
    ctx = context(app_module)
    ctx.conn.execute(
        "INSERT INTO workout_sessions (user_id, date, name) VALUES (1, '2026-09-20', 'Legs')"
    )
    ctx.conn.commit()

    plan = checkin.plan(ctx.conn, 1, '2026-09-20')

    assert item(plan, 'steps')['priority'] < item(plan, 'sleep')['priority']
    assert item(plan, 'steps')['priority'] < item(plan, 'study')['priority']
    assert topics(plan).index('sleep') < topics(plan).index('steps')


def test_the_reason_names_the_actual_ceiling(app_module, client):
    """Not a label. The number in the sentence is the one the engine enforces,
    so the assistant can explain itself truthfully if asked."""
    register(client)
    ctx = context(app_module)

    plan = checkin.plan(ctx.conn, 1, '2026-09-20')
    reason = item(plan, 'sleep')['reason']

    assert 'Recovery' in reason
    assert f'{int(DEFAULT_CONFIG.self_report_ceiling * 100)}%' in reason


def test_the_checklist_ranks_below_measured_data(app_module, client):
    """`self_report_weight` 1 against `measured_weight` 3, made operational."""
    register(client)
    ctx = context(app_module)

    plan = checkin.plan(ctx.conn, 1, '2026-09-20')

    assert item(plan, 'checkin')['priority'] < item(plan, 'sleep')['priority']
    assert topics(plan)[-1] == 'checkin'


def test_the_checklist_still_ranks_when_everything_else_is_logged(app_module, client):
    """It is the only direct evidence of Discipline, and it marks the day logged
    at all - so it never disappears just because the measured data is in."""
    register(client)
    ctx = context(app_module)
    for sql in (
        "INSERT INTO workout_sessions (user_id, date, name) VALUES (1, '2026-09-20', 'x')",
        "INSERT INTO sleep_entries (user_id, date, duration_minutes) VALUES (1, '2026-09-20', 420)",
        "INSERT INTO learning_sessions (user_id, date, duration_minutes) VALUES (1, '2026-09-20', 60)",
        "INSERT INTO lifestyle_days (user_id, date, steps) VALUES (1, '2026-09-20', 9000)",
    ):
        ctx.conn.execute(sql)
    ctx.conn.commit()

    plan = checkin.plan(ctx.conn, 1, '2026-09-20')

    assert topics(plan) == ['food', 'checkin']


def test_a_half_finished_checkin_is_not_restarted(app_module, client):
    """People close the tab. The unanswered questions are what comes back."""
    register(client)
    ctx = context(app_module)
    survey = __import__('habits').load_survey(ctx.conn, 1)
    first = survey[0]['id']

    plan = checkin.plan(ctx.conn, 1, '2026-09-20', survey_items=survey, answered={first})

    entry = item(plan, 'checkin')
    assert entry['status'] == 'partial'
    assert first not in [q['id'] for q in entry['questions']]
    assert len(entry['questions']) == len(survey) - 1


def test_a_finished_checkin_is_not_asked_about(app_module, client):
    register(client)
    ctx = context(app_module)
    survey = __import__('habits').load_survey(ctx.conn, 1)

    plan = checkin.plan(
        ctx.conn, 1, '2026-09-20', survey_items=survey,
        answered={entry['id'] for entry in survey},
    )

    assert 'checkin' not in topics(plan)


def test_the_plan_tool_reads_what_was_already_answered(app_module, client):
    """End to end through the tool, since that is what the model calls."""
    register(client)
    ctx = context(app_module)
    survey = __import__('habits').load_survey(ctx.conn, 1)

    tools.apply_action(ctx, {
        'type': 'checkin', 'date': '2026-09-20',
        'answers': [{'question_id': survey[0]['id'], 'question': survey[0]['name'], 'value': 'yes'}],
    })

    plan = tools.get_checkin_plan(ctx, '2026-09-20')

    assert item(plan, 'checkin')['status'] == 'partial'


# --- answering it --------------------------------------------------------------

def test_proposing_a_checkin_writes_nothing(app_module, client):
    register(client)
    ctx = context(app_module)
    survey = __import__('habits').load_survey(ctx.conn, 1)

    tools.propose_checkin(ctx, date='2026-09-20', answers=[
        {'question_id': survey[0]['id'], 'question': survey[0]['name'], 'value': 'yes'},
    ])

    assert len(ctx.queued) == 1
    assert ctx.conn.execute('SELECT COUNT(*) AS n FROM daily_log').fetchone()['n'] == 0


def test_an_invented_question_id_is_refused(app_module, client):
    register(client)
    ctx = context(app_module)

    try:
        tools.propose_checkin(ctx, date='2026-09-20', answers=[
            {'question_id': 'not-a-real-question', 'question': '?', 'value': 'yes'},
        ])
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'get_checkin_plan' in str(error)


def test_applying_a_checkin_goes_through_the_same_path_as_the_page(app_module, client):
    """The one that matters.

    `record_checklist_day` writes the activity row, the daily_log row and the
    audit trail, and scores the day. A tool that wrote daily_log itself would
    look correct and quietly skip all of that.
    """
    register(client)
    ctx = context(app_module)
    survey = __import__('habits').load_survey(ctx.conn, 1)

    note = tools.apply_action(ctx, {
        'type': 'checkin', 'date': '2026-09-20',
        'answers': [
            {'question_id': entry['id'], 'question': entry['name'], 'value': 'yes'}
            for entry in survey[:3]
        ],
    })

    assert 'complete' in note
    assert ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM activities WHERE activity_name = 'Daily Checklist'"
    ).fetchone()['n'] == 1
    row = ctx.conn.execute('SELECT completion_pct FROM daily_log').fetchone()
    assert row is not None and row['completion_pct'] > 0


def test_answers_merge_rather_than_replacing(app_module, client):
    """Somebody answers three questions on the Today page, then talks about the
    rest. Sending only what the assistant heard would erase the first three."""
    register(client)
    ctx = context(app_module)
    survey = __import__('habits').load_survey(ctx.conn, 1)

    tools.apply_action(ctx, {
        'type': 'checkin', 'date': '2026-09-20',
        'answers': [{'question_id': survey[0]['id'], 'question': survey[0]['name'], 'value': 'yes'}],
    })
    tools.apply_action(ctx, {
        'type': 'checkin', 'date': '2026-09-20',
        'answers': [{'question_id': survey[1]['id'], 'question': survey[1]['name'], 'value': 'no'}],
    })

    # Read the way the app reads them: keyed by question name, out of
    # daily_log.payload_json rather than a column.
    responses = tools._existing_responses(ctx.conn, 1, '2026-09-20')
    assert responses[survey[0]['name']] == 'yes', 'the first answer was erased'
    assert responses[survey[1]['name']] == 'no'


def test_the_checkin_refuses_rather_than_half_writing_when_unwired(app_module, client):
    """Without the injected writer there is no honest way to record a day."""
    register(client)
    ctx = tools.ToolContext(app_module.get_db_connection(), 1, today='2026-09-20')

    try:
        tools.apply_action(ctx, {'type': 'checkin', 'date': '2026-09-20', 'answers': []})
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'not wired up' in str(error)
    assert ctx.conn.execute('SELECT COUNT(*) AS n FROM daily_log').fetchone()['n'] == 0


# --- training ------------------------------------------------------------------

def exercise_id(ctx, name='Bench'):
    return ctx.conn.execute(
        'SELECT id FROM exercises WHERE name LIKE ? LIMIT 1', (f'%{name}%',)
    ).fetchone()['id']


def test_proposing_a_workout_writes_nothing(app_module, client):
    register(client)
    ctx = context(app_module)

    tools.propose_workout(ctx, date='2026-09-20', name='Push', exercises=[{
        'exercise_id': exercise_id(ctx), 'name': 'Bench Press',
        'sets': [{'reps': 8, 'weight_kg': 60, 'duration_minutes': None}] * 3,
    }])

    assert ctx.conn.execute('SELECT COUNT(*) AS n FROM workout_sessions').fetchone()['n'] == 0
    assert '3 sets' in ctx.queued[0]['summary']


def test_applying_a_workout_computes_the_same_totals_as_the_workspace(app_module, client):
    """Volume is weight times reps with warm-ups excluded - the Training
    workspace's rule, not a second one."""
    register(client)
    ctx = context(app_module)

    tools.apply_action(ctx, {
        'type': 'workout', 'date': '2026-09-20', 'name': 'Push',
        'exercises': [{
            'exercise_id': exercise_id(ctx), 'name': 'Bench Press',
            'sets': [
                {'reps': 8, 'weight_kg': 60, 'duration_minutes': None},
                {'reps': 8, 'weight_kg': 60, 'duration_minutes': None},
            ],
        }],
    })

    row = ctx.conn.execute('SELECT total_sets, total_volume FROM workout_sessions').fetchone()
    assert row['total_sets'] == 2
    assert row['total_volume'] == 2 * 8 * 60


def test_a_cardio_set_records_a_duration_rather_than_a_load(app_module, client):
    register(client)
    ctx = context(app_module)

    tools.apply_action(ctx, {
        'type': 'workout', 'date': '2026-09-20', 'name': 'Run',
        'exercises': [{
            'exercise_id': exercise_id(ctx, 'Run'), 'name': 'Running',
            'sets': [{'reps': None, 'weight_kg': None, 'duration_minutes': 30}],
        }],
    })

    row = ctx.conn.execute('SELECT duration_seconds, weight FROM exercise_sets').fetchone()
    assert row['duration_seconds'] == 1800
    assert row['weight'] is None


def test_an_implausible_load_is_refused(app_module, client):
    register(client)
    ctx = context(app_module)

    try:
        tools.propose_workout(ctx, date='2026-09-20', name='Push', exercises=[{
            'exercise_id': exercise_id(ctx), 'name': 'Bench Press',
            'sets': [{'reps': 8, 'weight_kg': 5000, 'duration_minutes': None}],
        }])
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'plausible' in str(error)


def test_an_invented_exercise_id_is_refused(app_module, client):
    register(client)
    ctx = context(app_module)

    try:
        tools.propose_workout(ctx, date='2026-09-20', name='Push', exercises=[{
            'exercise_id': 999999, 'name': 'Imaginary Press',
            'sets': [{'reps': 8, 'weight_kg': 60, 'duration_minutes': None}],
        }])
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'search_exercises' in str(error)


def test_logging_training_removes_it_from_the_next_plan(app_module, client):
    """The loop closing: what the assistant saves is what it stops asking about."""
    register(client)
    ctx = context(app_module)

    assert 'training' in topics(checkin.plan(ctx.conn, 1, '2026-09-20'))

    tools.apply_action(ctx, {
        'type': 'workout', 'date': '2026-09-20', 'name': 'Push',
        'exercises': [{
            'exercise_id': exercise_id(ctx), 'name': 'Bench Press',
            'sets': [{'reps': 8, 'weight_kg': 60, 'duration_minutes': None}],
        }],
    })

    assert 'training' not in topics(checkin.plan(ctx.conn, 1, '2026-09-20'))
