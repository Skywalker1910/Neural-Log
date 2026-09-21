"""The assistant's tool layer, and the money guard around it.

No model is called anywhere in this file. That is deliberate and it is most of
the point: the tool registry is ordinary Python over the ordinary database, so
the part that decides what happens to somebody's data can be tested exhaustively
and for free. Only the thin layer that turns text into tool calls needs a
provider, and that is the layer with the least logic in it.

The property every write test here is really checking is the same one: **a
proposal changed nothing.** If any of these start passing while also writing
rows, the safety model is gone.
"""
import assistant.config as config
import assistant.tools as tools
import assistant.usage as usage
from conftest import register


def context(app_module, user_id=1, today='2026-09-20'):
    return tools.ToolContext(app_module.get_db_connection(), user_id, today=today)


def food_id(ctx, name):
    row = ctx.conn.execute('SELECT id FROM foods WHERE name LIKE ? LIMIT 1', (f'%{name}%',)).fetchone()
    assert row is not None, f'no food matching {name!r} in the seeded library'
    return row['id']


# --- the shape the provider is given ------------------------------------------

def test_every_tool_is_strict_with_a_closed_schema():
    """`strict` is what makes arguments arrive valid rather than merely plausible.

    These arguments become database rows, so a model that improvises a field name
    should fail at the provider rather than halfway through an applier.
    """
    for spec in tools.schema_for_provider():
        assert spec['strict'] is True, spec['name']
        assert spec['parameters']['additionalProperties'] is False, spec['name']


def test_strict_mode_requires_every_property_to_be_listed_required():
    """The provider rejects a strict schema whose `required` omits any property.

    Optional arguments are expressed as nullable types instead - which is why the
    date parameters read `['string', 'null']` rather than simply being left out.
    """
    for spec in tools.schema_for_provider():
        params = spec['parameters']
        assert set(params['required']) == set(params['properties']), spec['name']


def test_the_write_tools_are_the_ones_we_think_they_are():
    """A read tool that quietly becomes a write tool is the regression to catch.

    Spelled out rather than derived, so adding one is a deliberate act that
    shows up in a diff next to this list.
    """
    writes = {name for name, spec in tools.TOOLS.items() if spec['writes']}
    assert writes == {
        'propose_meal', 'propose_sleep', 'propose_lifestyle', 'propose_study',
        'propose_checkin', 'propose_workout', 'propose_tasks_done',
        'propose_goal_progress',
    }


def test_every_write_tool_has_an_applier():
    """A proposal whose type nothing can apply is a Save button that 400s."""
    proposers = {name for name, spec in tools.TOOLS.items() if spec['writes']}
    # propose_meal -> 'meal', propose_checkin -> 'checkin', and so on.
    assert {name.removeprefix('propose_') for name in proposers} <= set(tools._APPLIERS)


# --- reading ------------------------------------------------------------------

def test_an_empty_day_reports_everything_as_missing(app_module, client):
    """`still_missing` is the field the whole guided check-in hangs off."""
    register(client)
    ctx = context(app_module)

    day = tools.get_day(ctx, '2026-09-20')

    assert day['still_missing'] == ['food', 'sleep', 'training', 'study', 'daily check-in']
    assert day['total_kcal'] == 0


def test_a_logged_meal_drops_out_of_missing(app_module, client):
    """The point of the tool: stop asking about what is already answered."""
    register(client)
    ctx = context(app_module)
    oats = food_id(ctx, 'Oat')

    tools.apply_action(ctx, {
        'type': 'meal', 'date': '2026-09-20', 'meal': 'breakfast',
        'items': [{'food_id': oats, 'name': 'Oats', 'grams': 80}],
    })

    day = tools.get_day(ctx, '2026-09-20')
    assert 'food' not in day['still_missing']
    assert day['total_kcal'] > 0


def test_food_search_will_not_return_somebody_elses_recipe(app_module, client):
    """Custom dishes are per-account, and the assistant must not leak them.

    The catalogue is shared; a recipe someone saved is not. Getting this wrong
    would mean one friend's assistant offering another friend's dinner.
    """
    register(client, username='owner')
    ctx = context(app_module, user_id=1)
    ctx.conn.execute(
        "INSERT INTO foods (name, slug, user_id, source, kcal_per_100g, protein_per_100g, "
        "                   carbs_per_100g, fat_per_100g) "
        "VALUES ('Owners Secret Curry', 'owners-secret-curry', 1, 'recipe', 100, 5, 10, 2)"
    )
    ctx.conn.commit()

    assert any(f['name'] == 'Owners Secret Curry' for f in tools.search_foods(ctx, 'Secret')['foods'])

    stranger = context(app_module, user_id=2)
    assert tools.search_foods(stranger, 'Secret')['foods'] == []


def test_search_needs_something_to_search_for(app_module, client):
    register(client)
    try:
        tools.search_foods(context(app_module), 'a')
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'two characters' in str(error)


# --- proposing changes nothing ------------------------------------------------

def test_proposing_a_meal_writes_no_rows(app_module, client):
    """The load-bearing test in this file."""
    register(client)
    ctx = context(app_module)
    oats = food_id(ctx, 'Oat')

    result = tools.propose_meal(
        ctx, date='2026-09-20', meal='breakfast',
        items=[{'food_id': oats, 'name': 'Oats', 'grams': 80}],
    )

    assert result['queued'] is True
    assert 'Not saved yet' in result['note']
    assert len(ctx.queued) == 1

    rows = ctx.conn.execute('SELECT COUNT(*) AS n FROM food_entries').fetchone()['n']
    assert rows == 0


def test_proposing_sleep_writes_no_rows(app_module, client):
    register(client)
    ctx = context(app_module)

    tools.propose_sleep(ctx, date='2026-09-20', bedtime='23:30', wake_time='06:45')

    assert ctx.conn.execute('SELECT COUNT(*) AS n FROM sleep_entries').fetchone()['n'] == 0


def test_a_made_up_food_id_is_refused(app_module, client):
    """Models invent ids. The queue is where that has to stop.

    The error names the fix, because the model reads it and usually corrects
    itself on the next turn - which is cheaper than failing the conversation.
    """
    register(client)
    ctx = context(app_module)

    try:
        tools.propose_meal(ctx, date='2026-09-20', meal='lunch',
                           items=[{'food_id': 999999, 'name': 'Invented', 'grams': 100}])
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'search_foods' in str(error)


def test_an_implausible_portion_is_refused(app_module, client):
    """Five kilos of anything is a decimal point in the wrong place."""
    register(client)
    ctx = context(app_module)
    oats = food_id(ctx, 'Oat')

    try:
        tools.propose_meal(ctx, date='2026-09-20', meal='lunch',
                           items=[{'food_id': oats, 'name': 'Oats', 'grams': 9000}])
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'plausible' in str(error)


def test_sleep_needs_either_clock_times_or_a_duration(app_module, client):
    register(client)
    ctx = context(app_module)

    try:
        tools.propose_sleep(ctx, date='2026-09-20', quality=4)
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'duration' in str(error)


def test_a_bad_date_is_caught_before_anything_else(app_module, client):
    register(client)
    ctx = context(app_module)

    try:
        tools.propose_lifestyle(ctx, date='last Tuesday', water_ml=500)
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'YYYY-MM-DD' in str(error)


# --- applying does ------------------------------------------------------------

def test_applying_a_meal_writes_it(app_module, client):
    register(client)
    ctx = context(app_module)
    oats = food_id(ctx, 'Oat')

    note = tools.apply_action(ctx, {
        'type': 'meal', 'date': '2026-09-20', 'meal': 'breakfast',
        'items': [{'food_id': oats, 'name': 'Oats', 'grams': 80}],
    })

    row = ctx.conn.execute('SELECT meal, grams FROM food_entries').fetchone()
    assert row['meal'] == 'breakfast' and row['grams'] == 80
    assert 'breakfast' in note


def test_applying_lifestyle_merges_rather_than_replaces(app_module, client):
    """A conversation about water must not blank out this morning's step count.

    The obvious implementation is an UPSERT of the whole row, and it silently
    erases every field the conversation did not happen to mention.
    """
    register(client)
    ctx = context(app_module)

    tools.apply_action(ctx, {'type': 'lifestyle', 'date': '2026-09-20',
                             'water_ml': None, 'steps': 8000, 'mood': None})
    tools.apply_action(ctx, {'type': 'lifestyle', 'date': '2026-09-20',
                             'water_ml': 2000, 'steps': None, 'mood': None})

    row = ctx.conn.execute('SELECT water_ml, steps FROM lifestyle_days').fetchone()
    assert row['steps'] == 8000, 'the step count was erased'
    assert row['water_ml'] == 2000


def test_applying_sleep_replaces_rather_than_duplicating(app_module, client):
    """One night, one row. Re-answering corrects rather than appending."""
    register(client)
    ctx = context(app_module)

    tools.apply_action(ctx, {'type': 'sleep', 'date': '2026-09-20', 'bedtime': '23:00',
                             'wake_time': '06:00', 'duration_minutes': None, 'quality': 3})
    tools.apply_action(ctx, {'type': 'sleep', 'date': '2026-09-20', 'bedtime': '23:30',
                             'wake_time': '07:00', 'duration_minutes': None, 'quality': 4})

    rows = ctx.conn.execute('SELECT bedtime, quality FROM sleep_entries').fetchall()
    assert len(rows) == 1
    assert rows[0]['bedtime'] == '23:30' and rows[0]['quality'] == 4


def test_an_unknown_action_type_is_refused(app_module, client):
    """The apply path is reachable from a client-supplied payload."""
    register(client)
    try:
        tools.apply_action(context(app_module), {'type': 'drop_everything'})
        assert False, 'expected a ToolError'
    except tools.ToolError as error:
        assert 'Unknown action type' in str(error)


# --- the money guard ----------------------------------------------------------

def test_cost_is_estimated_from_published_rates():
    """15k in / 500 out on Terra: 15000/1e6*2 + 500/1e6*12."""
    assert round(config.estimate_cost('gpt-5.6-terra', 15_000, 500), 4) == 0.036


def test_cached_tokens_are_not_billed_twice(app_module):
    """The provider reports cached tokens as a *subset* of input tokens.

    Adding them on top is the easy mistake, and it over-reports spend by the
    cache hit rate - which on a multi-turn conversation is most of the input.
    """
    full = config.estimate_cost('gpt-5.6-terra', 15_000, 500, cached_input_tokens=0)
    cached = config.estimate_cost('gpt-5.6-terra', 15_000, 500, cached_input_tokens=12_000)

    assert cached < full
    # 3k fresh + 12k discounted, not 15k + 12k.
    assert round(cached, 4) == round(
        3_000 * 2 / 1e6 + 12_000 * 2 * config.CACHED_INPUT_MULTIPLIER / 1e6 + 500 * 12 / 1e6, 4
    )


def test_an_unknown_model_costs_the_most_rather_than_nothing(app_module):
    """A model with no rate must over-estimate.

    Defaulting to zero means an unrecognised model bills silently against a
    budget it never touches - the cap stops working and nothing says so.
    """
    unknown = config.estimate_cost('gpt-7-unreleased', 1_000_000, 0)
    known = config.estimate_cost('gpt-5.6-terra', 1_000_000, 0)
    assert unknown > known


def test_spending_is_recorded_and_totalled(app_module, client):
    register(client)
    conn = app_module.get_db_connection()

    usage.record(conn, 1, 'chat', 'gpt-5.6-terra', {'input_tokens': 15_000, 'output_tokens': 500})

    state = usage.budget_state(conn, 1)
    assert state['month_calls'] == 1
    assert round(state['month_spent_usd'], 3) == 0.036


def test_a_failed_request_is_still_counted(app_module, client):
    """It consumed tokens. A log that only counts successes under-reports
    exactly when things are going wrong."""
    register(client)
    conn = app_module.get_db_connection()

    usage.record(conn, 1, 'chat', 'gpt-5.6-terra',
                 {'input_tokens': 900, 'output_tokens': 0}, ok=False, error='boom')

    assert usage.budget_state(conn, 1)['month_calls'] == 1
    assert usage.report(conn)['totals']['failures'] == 1


def test_the_budget_closes_the_door(app_module, client, monkeypatch):
    register(client)
    conn = app_module.get_db_connection()
    monkeypatch.setattr(config, 'DAILY_BUDGET_USD', 0.05)

    assert usage.check_budget(conn, 1)[0] is True

    usage.record(conn, 1, 'chat', 'gpt-5.6-terra',
                 {'input_tokens': 30_000, 'output_tokens': 1_000})

    allowed, message = usage.check_budget(conn, 1)
    assert allowed is False
    assert 'still works' in message, 'the refusal should say the rest of the app is fine'


def test_one_persons_spending_does_not_close_anothers_door(app_module, client):
    """Budgets are per account. A shared instance where one chatty friend locks
    everyone else out would be worse than no limit at all."""
    register(client, username='talker')
    conn = app_module.get_db_connection()

    for _ in range(50):
        usage.record(conn, 1, 'chat', 'gpt-5.6-sol',
                     {'input_tokens': 100_000, 'output_tokens': 5_000})

    assert usage.check_budget(conn, 1)[0] is False
    assert usage.check_budget(conn, 2)[0] is True


def test_the_rate_limiter_counts_recent_calls(app_module, client, monkeypatch):
    register(client)
    conn = app_module.get_db_connection()
    monkeypatch.setattr(config, 'RATE_LIMIT_PER_MINUTE', 3)

    assert usage.rate_limited(conn, 1) is False
    for _ in range(3):
        usage.record(conn, 1, 'chat', 'gpt-5.6-terra', {'input_tokens': 10, 'output_tokens': 1})
    assert usage.rate_limited(conn, 1) is True


def test_the_report_says_where_the_money_went(app_module, client):
    """One total tells you the bill is too high and nothing about what to fix."""
    register(client)
    conn = app_module.get_db_connection()

    usage.record(conn, 1, 'label', 'gpt-5.6-luna', {'input_tokens': 2_000, 'output_tokens': 300})
    usage.record(conn, 1, 'chat', 'gpt-5.6-terra', {'input_tokens': 20_000, 'output_tokens': 800})

    report = usage.report(conn)

    assert report['estimated'] is True, 'the figure must never be presented as billing truth'
    assert [row['feature'] for row in report['by_feature']] == ['chat', 'label']
