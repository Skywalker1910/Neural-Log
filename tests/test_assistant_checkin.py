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


# --- goals and tasks -----------------------------------------------------------
#
# Deliberately outside the weighted ranking. `init_goals` is registered with no
# recompute function because a goal is an intention rather than evidence, so
# giving these a priority beside sleep and training would invent an analytical
# weight the engine does not give them. They close the check-in instead.

def seed_work(ctx, overdue=False):
    ctx.conn.execute(
        "INSERT INTO goals (user_id, title, status, metric_name, target_value, current_value) "
        "VALUES (1, 'Read 12 books', 'active', 'books', 12, 3)"
    )
    goal_id = ctx.conn.execute('SELECT id FROM goals LIMIT 1').fetchone()['id']
    ctx.conn.execute(
        'INSERT INTO tasks (user_id, goal_id, title, due_date) VALUES (1, ?, ?, ?)',
        (goal_id, 'Finish chapter 4', '2026-09-01' if overdue else '2026-12-01'),
    )
    ctx.conn.commit()
    return goal_id


def test_open_work_is_not_part_of_the_weighted_order(app_module, client):
    """The honest bit. Goals feed no attribute, so ranking them next to sleep
    would claim an analytical weight the scoring engine does not give them."""
    register(client)
    ctx = context(app_module)
    seed_work(ctx)

    plan = checkin.plan(ctx.conn, 1, '2026-09-20')

    assert 'goals' not in topics(plan) and 'tasks' not in topics(plan)
    assert plan['follow_up']['affects_scores'] is False
    assert plan['follow_up']['active_goals'] == 1
    assert plan['follow_up']['open_tasks'] == 1


def test_nothing_outstanding_means_nothing_to_ask(app_module, client):
    """No commitments, no closing question - rather than a limp "anything else?"."""
    register(client)
    ctx = context(app_module)

    assert checkin.plan(ctx.conn, 1, '2026-09-20')['follow_up']['ask'] is None


def test_an_overdue_task_is_flagged_rather_than_left_as_arithmetic(app_module, client):
    register(client)
    ctx = context(app_module)
    seed_work(ctx, overdue=True)

    work = tools.get_open_work(ctx)

    assert work['tasks'][0]['overdue'] is True
    assert work['tasks'][0]['goal'] == 'Read 12 books'


def test_a_completed_task_drops_out_of_open_work(app_module, client):
    register(client)
    ctx = context(app_module)
    seed_work(ctx)
    task_id = tools.get_open_work(ctx)['tasks'][0]['id']

    tools.apply_action(ctx, {'type': 'tasks_done', 'date': '2026-09-20',
                             'tasks': [{'task_id': task_id, 'title': 'Finish chapter 4'}]})

    assert tools.get_open_work(ctx)['tasks'] == []


def test_proposing_a_finished_task_writes_nothing(app_module, client):
    register(client)
    ctx = context(app_module)
    seed_work(ctx)
    task_id = tools.get_open_work(ctx)['tasks'][0]['id']

    tools.propose_tasks_done(ctx, tasks=[{'task_id': task_id, 'title': 'Finish chapter 4'}])

    assert len(ctx.queued) == 1
    assert ctx.conn.execute(
        'SELECT completed_on FROM tasks WHERE id = ?', (task_id,)
    ).fetchone()['completed_on'] is None


def test_a_task_that_is_already_done_cannot_be_proposed_again(app_module, client):
    """Otherwise a second check-in re-closes it and the card promises nothing."""
    register(client)
    ctx = context(app_module)
    seed_work(ctx)
    task_id = tools.get_open_work(ctx)['tasks'][0]['id']
    tools.apply_action(ctx, {'type': 'tasks_done', 'date': '2026-09-20',
                             'tasks': [{'task_id': task_id, 'title': 'x'}]})

    try:
        tools.propose_tasks_done(ctx, tasks=[{'task_id': task_id, 'title': 'x'}])
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'get_open_work' in str(error)


def test_somebody_elses_task_is_invisible(app_module, client):
    """Ids are sequential integers."""
    register(client, username='owner')
    ctx = context(app_module)
    seed_work(ctx)
    task_id = tools.get_open_work(ctx)['tasks'][0]['id']

    stranger = context(app_module, user_id=2)
    try:
        tools.propose_tasks_done(stranger, tasks=[{'task_id': task_id, 'title': 'x'}])
        assert False, 'expected a ToolError'
    except tools.ToolError:
        pass


def test_goal_progress_is_the_new_total_not_the_increment(app_module, client):
    """The tool description says so, and the applier assumes it. A model that
    sent the delta would silently reset a goal to today's reading."""
    register(client)
    ctx = context(app_module)
    goal_id = seed_work(ctx)

    tools.apply_action(ctx, {'type': 'goal_progress', 'date': '2026-09-20',
                             'goal_id': goal_id, 'title': 'Read 12 books',
                             'current_value': 4})

    assert ctx.conn.execute(
        'SELECT current_value FROM goals WHERE id = ?', (goal_id,)
    ).fetchone()['current_value'] == 4


def test_a_goal_without_a_metric_cannot_take_progress(app_module, client):
    """"Be more consistent" has no number to move, and inventing one would be
    worse than saying so."""
    register(client)
    ctx = context(app_module)
    ctx.conn.execute(
        "INSERT INTO goals (user_id, title, status) VALUES (1, 'Be more consistent', 'active')"
    )
    ctx.conn.commit()
    goal_id = ctx.conn.execute('SELECT id FROM goals LIMIT 1').fetchone()['id']

    try:
        tools.propose_goal_progress(ctx, goal_id=goal_id, title='Be more consistent',
                                    current_value=5)
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'no metric' in str(error)
