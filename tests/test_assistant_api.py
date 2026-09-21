"""The agent loop and the endpoints around it, against a fake provider.

Nothing here reaches the network. The fake returns whatever the test scripted,
which means the interesting cases - a model that invents a food id, a model that
loops forever, a model that goes down mid-turn - are ordinary tests rather than
things you hope not to see in production.

The test that matters most is `test_an_edited_proposal_cannot_change_what_it_does`.
Everything else is plumbing; that one is the security boundary.
"""
import json
from types import SimpleNamespace

import assistant.agent as agent
import assistant.cards as cards
import assistant.config as config
import assistant.store as store
import assistant.usage as usage
from conftest import register


# --- a provider that does what the test says ----------------------------------

def call(name, arguments, call_id='c1'):
    return SimpleNamespace(type='function_call', name=name,
                           arguments=json.dumps(arguments), call_id=call_id)


def turn(text='', calls=(), input_tokens=1000, output_tokens=100, cached=0):
    return SimpleNamespace(
        output=list(calls),
        output_text=text,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_tokens_details=SimpleNamespace(cached_tokens=cached),
        ),
    )


class FakeClient:
    """Returns scripted turns in order, and records what it was sent."""

    def __init__(self, *turns, fail_on=None):
        self._turns = list(turns)
        self._fail_on = fail_on
        self.calls = 0
        self.last_request = None
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        self.last_request = kwargs
        if self._fail_on == self.calls:
            raise RuntimeError('provider exploded')
        if not self._turns:
            return turn(text='(nothing scripted)')
        return self._turns.pop(0)


def drain(generator):
    """Every event, and the `done` one separately - the shape tests want."""
    events = list(generator)
    done = next((e for e in events if e['type'] == 'done'), None)
    return events, done


def food_id(conn, name='Oat'):
    return conn.execute(
        'SELECT id FROM foods WHERE name LIKE ? LIMIT 1', (f'%{name}%',)
    ).fetchone()['id']


# --- the loop ------------------------------------------------------------------

def test_a_plain_answer_needs_one_request(app_module, client):
    register(client)
    conn = app_module.get_db_connection()
    fake = FakeClient(turn(text='You logged 1,800 kcal yesterday.'))

    _, done = drain(agent.run_turn(conn, 1, [], 'what did I eat yesterday?', client=fake))

    assert fake.calls == 1
    assert done['reply'].startswith('You logged')
    assert done['queued'] == []


def test_a_tool_call_is_executed_and_fed_back(app_module, client):
    register(client)
    conn = app_module.get_db_connection()
    fake = FakeClient(
        turn(calls=[call('get_day', {'date': '2026-09-20'})]),
        turn(text='Nothing logged yet today.'),
    )

    events, done = drain(agent.run_turn(
        conn, 1, [], 'how am I doing today?', client=fake, today='2026-09-20'
    ))

    assert fake.calls == 2
    assert [e['tool'] for e in events if e['type'] == 'status'] == ['get_day']
    assert done['reply'] == 'Nothing logged yet today.'

    # The tool's output went back as a function_call_output, which is the bit
    # that makes the second request worth making.
    sent = fake.last_request['input']
    assert any(getattr(item, 'type', None) == 'function_call_output'
               or (isinstance(item, dict) and item.get('type') == 'function_call_output')
               for item in sent)


def test_a_write_tool_queues_instead_of_writing(app_module, client):
    register(client)
    conn = app_module.get_db_connection()
    oats = food_id(conn)
    fake = FakeClient(
        turn(calls=[call('propose_meal', {
            'date': '2026-09-20', 'meal': 'breakfast',
            'items': [{'food_id': oats, 'name': 'Oats', 'grams': 80}],
        })]),
        turn(text='Ready to save 80 g of oats for breakfast.'),
    )

    _, done = drain(agent.run_turn(conn, 1, [], 'I had oats', client=fake, today='2026-09-20'))

    assert len(done['queued']) == 1
    assert done['queued'][0]['type'] == 'meal'
    assert conn.execute('SELECT COUNT(*) AS n FROM food_entries').fetchone()['n'] == 0


def test_a_tool_error_goes_back_to_the_model_rather_than_ending_the_turn(app_module, client):
    """Models invent ids. Ending the turn on the first one means the person
    starts again; handing back the error means the model usually fixes it."""
    register(client)
    conn = app_module.get_db_connection()
    oats = food_id(conn)
    fake = FakeClient(
        turn(calls=[call('propose_meal', {
            'date': '2026-09-20', 'meal': 'lunch',
            'items': [{'food_id': 999999, 'name': 'Invented', 'grams': 100}],
        })]),
        turn(calls=[call('propose_meal', {
            'date': '2026-09-20', 'meal': 'lunch',
            'items': [{'food_id': oats, 'name': 'Oats', 'grams': 100}],
        }, call_id='c2')]),
        turn(text='Ready to save that.'),
    )

    _, done = drain(agent.run_turn(conn, 1, [], 'lunch was oats', client=fake, today='2026-09-20'))

    assert fake.calls == 3
    assert len(done['queued']) == 1


def test_a_model_going_in_circles_is_capped(app_module, client, monkeypatch):
    """Every pass is another billed request, so the ceiling is a cost control
    as much as a safety one."""
    register(client)
    conn = app_module.get_db_connection()
    monkeypatch.setattr(config, 'MAX_TOOL_ITERATIONS', 3)
    fake = FakeClient(*[turn(calls=[call('get_day', {'date': None})]) for _ in range(10)])

    events, done = drain(agent.run_turn(conn, 1, [], 'hello', client=fake))

    assert fake.calls == 3
    assert any(e.get('note') for e in events if e['type'] == 'status')
    assert done is not None, 'the turn must still finish rather than hanging'


def test_a_provider_outage_is_recorded_and_reported(app_module, client):
    register(client)
    conn = app_module.get_db_connection()
    fake = FakeClient(fail_on=1)

    events, done = drain(agent.run_turn(conn, 1, [], 'hello', client=fake))

    assert done is None
    error = next(e for e in events if e['type'] == 'error')
    assert error['kind'] == 'provider'
    assert 'Nothing was saved' in error['message']
    # Recorded as a failure, because a failed request usually still cost tokens.
    assert usage.report(conn)['totals']['failures'] == 1


def test_every_request_is_metered(app_module, client):
    register(client)
    conn = app_module.get_db_connection()
    fake = FakeClient(
        turn(calls=[call('get_day', {'date': None})], input_tokens=5000, output_tokens=50),
        turn(text='done', input_tokens=6000, output_tokens=120),
    )

    drain(agent.run_turn(conn, 1, [], 'hi', client=fake))

    state = usage.budget_state(conn, 1)
    assert state['month_calls'] == 2
    assert state['month_spent_usd'] > 0


def test_the_budget_stops_the_turn_before_the_provider_is_called(app_module, client, monkeypatch):
    register(client)
    conn = app_module.get_db_connection()
    monkeypatch.setattr(config, 'DAILY_BUDGET_USD', 0.001)
    usage.record(conn, 1, 'chat', 'gpt-5.6-terra', {'input_tokens': 50_000, 'output_tokens': 500})
    fake = FakeClient(turn(text='should never be reached'))

    events, _ = drain(agent.run_turn(conn, 1, [], 'hello', client=fake))

    assert fake.calls == 0
    assert next(e for e in events if e['type'] == 'error')['kind'] == 'budget'


def test_the_model_is_told_it_cannot_save(app_module, client):
    """The one instruction that, if lost, makes the whole design fail quietly:
    the model says 'logged it', the person believes it, nobody presses Save."""
    assert 'Never say you have logged' in agent.SYSTEM_PROMPT
    assert 'cannot write to the app' in agent.SYSTEM_PROMPT


# --- the endpoints -------------------------------------------------------------

def use_fake(monkeypatch, *turns, **kwargs):
    fake = FakeClient(*turns, **kwargs)
    monkeypatch.setattr(agent, 'build_client', lambda: fake)
    return fake


def sse(response):
    """The events out of an event-stream response body."""
    return [
        json.loads(line[len('data: '):])
        for line in response.get_data(as_text=True).splitlines()
        if line.startswith('data: ')
    ]


def test_state_reports_whether_the_feature_exists(client, monkeypatch):
    """An instance with no key is not broken; it is an instance with no chat
    button. The client hides the whole feature off this flag."""
    register(client)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)

    payload = client.get('/api/assistant/state').get_json()

    assert payload['configured'] is False
    assert payload['pending_proposal'] is None
    assert 'month_budget_usd' in payload['budget']


def test_chat_streams_events_and_creates_a_proposal(client, app_module, monkeypatch):
    register(client)
    conn = app_module.get_db_connection()
    oats = food_id(conn)
    use_fake(
        monkeypatch,
        turn(calls=[call('propose_meal', {
            'date': None, 'meal': 'breakfast',
            'items': [{'food_id': oats, 'name': 'Oats', 'grams': 80}],
        })]),
        turn(text='Ready to save 80 g of oats.'),
    )

    response = client.post('/api/assistant/chat', json={'message': 'I had oats'})
    events = sse(response)

    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'
    kinds = [event['type'] for event in events]
    assert 'status' in kinds and 'done' in kinds and 'proposal' in kinds and kinds[-1] == 'end'

    proposal = next(e for e in events if e['type'] == 'proposal')
    assert proposal['actions'][0]['type'] == 'meal'
    # Still nothing written.
    assert conn.execute('SELECT COUNT(*) AS n FROM food_entries').fetchone()['n'] == 0


def test_guided_checkin_streams_a_structured_input_card(client, monkeypatch):
    """A card is only a faster answer; it arrives beside the normal reply."""
    register(client)
    use_fake(monkeypatch, turn(text='What movement did you do today?'))

    events = sse(client.post('/api/assistant/chat', json={
        'message': "Let's run through today.", 'kind': 'today', 'date': '2026-09-20',
    }))

    card = next(event['card'] for event in events if event['type'] == 'input_card')
    assert card['topic'] == 'training'
    assert card['fields'][0]['id'] == 'details'
    assert card['message'] == 'I trained: {details}.'


def test_general_assistant_offers_exercise_tiles_for_a_muscle_group(client, app_module):
    register(client)
    conn = app_module.get_db_connection()

    card = cards.general_input_card(conn, 1, 'show me options to select', [
        {'role': 'user', 'content': 'I trained back and biceps today.'},
    ])

    assert card['topic'] == 'training'
    assert card['options']
    assert {'sets', 'reps'} <= {field['id'] for field in card['fields']}


def test_card_answers_apply_and_report_the_change(client, app_module, monkeypatch):
    """A structured answer is explicit input, so it does not need a second Save."""
    register(client)
    conn = app_module.get_db_connection()
    oats = food_id(conn)
    use_fake(
        monkeypatch,
        turn(calls=[call('propose_meal', {
            'date': None, 'meal': 'breakfast',
            'items': [{'food_id': oats, 'name': 'Oats', 'grams': 80}],
        })]),
        turn(text='Added your breakfast.'),
    )

    events = sse(client.post('/api/assistant/chat', json={
        'message': 'For breakfast, I had oats.', 'auto_apply': True,
    }))

    applied = next(event for event in events if event['type'] == 'applied')
    assert applied['failed'] is None
    assert applied['actions'][0]['type'] == 'meal'
    assert conn.execute('SELECT COUNT(*) AS n FROM food_entries').fetchone()['n'] == 1


def test_an_empty_message_is_refused_without_calling_anything(client, monkeypatch):
    register(client)
    fake = use_fake(monkeypatch, turn(text='unreachable'))

    assert client.post('/api/assistant/chat', json={'message': '   '}).status_code == 400
    assert fake.calls == 0


def test_a_conversation_is_resumed_rather_than_restarted(client, app_module, monkeypatch):
    """People close the tab mid-check-in. Being asked about breakfast twice is
    the fastest way to make this not worth using."""
    register(client)
    use_fake(monkeypatch, turn(text='one'), turn(text='two'))

    client.post('/api/assistant/chat', json={'message': 'first', 'kind': 'today', 'date': '2026-09-20'})
    client.post('/api/assistant/chat', json={'message': 'second', 'kind': 'today', 'date': '2026-09-20'})

    conn = app_module.get_db_connection()
    conversations = conn.execute(
        "SELECT COUNT(*) AS n FROM ai_conversations WHERE kind = 'today'"
    ).fetchone()['n']
    assert conversations == 1


# --- confirming, and the boundary ----------------------------------------------

def propose(client, app_module, monkeypatch, grams=80):
    # Session-aware rather than unconditional: some tests call this twice, and
    # one of them switches account in between.
    if client.get('/api/current-user').status_code != 200:
        register(client)
    conn = app_module.get_db_connection()
    oats = food_id(conn)
    use_fake(
        monkeypatch,
        turn(calls=[call('propose_meal', {
            'date': '2026-09-20', 'meal': 'breakfast',
            'items': [{'food_id': oats, 'name': 'Oats', 'grams': grams}],
        })]),
        turn(text='Ready.'),
    )
    events = sse(client.post('/api/assistant/chat', json={'message': 'oats'}))
    proposal = next(e for e in events if e['type'] == 'proposal')
    return conn, proposal


def test_confirming_writes_it(client, app_module, monkeypatch):
    conn, proposal = propose(client, app_module, monkeypatch)

    response = client.post(f'/api/assistant/proposals/{proposal["id"]}/apply', json={})

    assert response.get_json()['success'] is True
    row = conn.execute('SELECT meal, grams FROM food_entries').fetchone()
    assert row['meal'] == 'breakfast' and row['grams'] == 80


def test_the_person_may_correct_a_number(client, app_module, monkeypatch):
    """The point of the confirmation card. '45 minutes' they meant as 35 should
    be fixable without another round of conversation."""
    conn, proposal = propose(client, app_module, monkeypatch, grams=80)

    edited = proposal['actions']
    edited[0]['items'][0]['grams'] = 120

    response = client.post(f'/api/assistant/proposals/{proposal["id"]}/apply',
                           json={'actions': edited})

    assert response.get_json()['success'] is True
    assert conn.execute('SELECT grams FROM food_entries').fetchone()['grams'] == 120


def test_an_edited_proposal_cannot_change_what_it_does(client, app_module, monkeypatch):
    """The security boundary, stated once.

    The confirmation payload is client-supplied. Values may be corrected; the
    shape may not. Without this check, "log a 300 kcal breakfast" comes back as
    something else entirely and the Save button means nothing.
    """
    conn, proposal = propose(client, app_module, monkeypatch)

    hostile = [{'type': 'sleep', 'date': '2026-09-20', 'bedtime': '23:00',
                'wake_time': '07:00', 'duration_minutes': None, 'quality': 5}]

    response = client.post(f'/api/assistant/proposals/{proposal["id"]}/apply',
                           json={'actions': hostile})

    assert response.status_code == 400
    assert 'Only values may be edited' in response.get_json()['message']
    assert conn.execute('SELECT COUNT(*) AS n FROM sleep_entries').fetchone()['n'] == 0
    assert conn.execute('SELECT COUNT(*) AS n FROM food_entries').fetchone()['n'] == 0


def test_extra_actions_cannot_be_smuggled_in(client, app_module, monkeypatch):
    conn, proposal = propose(client, app_module, monkeypatch)

    padded = proposal['actions'] + [{'type': 'meal', 'date': '2026-09-20',
                                     'meal': 'dinner', 'items': []}]

    response = client.post(f'/api/assistant/proposals/{proposal["id"]}/apply',
                           json={'actions': padded})

    assert response.status_code == 400
    assert conn.execute('SELECT COUNT(*) AS n FROM food_entries').fetchone()['n'] == 0


def test_a_proposal_can_only_be_applied_once(client, app_module, monkeypatch):
    """Otherwise a double-tapped Save button logs breakfast twice."""
    conn, proposal = propose(client, app_module, monkeypatch)

    assert client.post(f'/api/assistant/proposals/{proposal["id"]}/apply', json={}).status_code == 200
    second = client.post(f'/api/assistant/proposals/{proposal["id"]}/apply', json={})

    assert second.status_code == 400
    assert conn.execute('SELECT COUNT(*) AS n FROM food_entries').fetchone()['n'] == 1


def test_discarding_writes_nothing_and_closes_it(client, app_module, monkeypatch):
    conn, proposal = propose(client, app_module, monkeypatch)

    assert client.post(f'/api/assistant/proposals/{proposal["id"]}/discard', json={}).status_code == 200
    assert client.post(f'/api/assistant/proposals/{proposal["id"]}/apply', json={}).status_code == 400
    assert conn.execute('SELECT COUNT(*) AS n FROM food_entries').fetchone()['n'] == 0


def test_a_proposal_belongs_to_one_account(client, app_module, monkeypatch):
    """Ids are sequential integers, so this is guessable by anyone who tries."""
    _, proposal = propose(client, app_module, monkeypatch)
    client.post('/logout')
    register(client, username='someone-else')

    response = client.post(f'/api/assistant/proposals/{proposal["id"]}/apply', json={})

    assert response.status_code == 400
    assert 'No such proposal' in response.get_json()['message']


def test_a_conversation_accumulates_onto_one_card(client, app_module, monkeypatch):
    """The bug a browser caught that the unit tests did not.

    A check-in queues as it goes - sleep on one turn, training on the next. When
    each turn replaced the last, the card at the end held only the final topic
    and everything earlier was silently marked superseded. The person presses
    Save on a card that looks right and loses two thirds of what they just said.
    """
    conn, first = propose(client, app_module, monkeypatch, grams=80)
    _, second = propose(client, app_module, monkeypatch, grams=200)

    assert first['id'] == second['id'], 'the same conversation should extend one card'
    assert len(second['actions']) == 2

    assert client.post(f'/api/assistant/proposals/{second["id"]}/apply', json={}).status_code == 200
    saved = [row['grams'] for row in conn.execute('SELECT grams FROM food_entries ORDER BY grams')]
    assert saved == [80, 200], 'both turns should be saved, not just the last'


def test_a_corrected_one_per_day_answer_replaces_rather_than_doubling(client, app_module, monkeypatch):
    """Sleep is one row per day, so a corrected bedtime overwrites the queued one.

    The rule mirrors what the applier does: `_apply_sleep` deletes and reinserts,
    so two queued sleeps for one date would be a card promising something the
    save cannot deliver.
    """
    if client.get('/api/current-user').status_code != 200:
        register(client)
    conn = app_module.get_db_connection()

    def queue_sleep(bedtime):
        use_fake(
            monkeypatch,
            turn(calls=[call('propose_sleep', {
                'date': '2026-09-20', 'bedtime': bedtime, 'wake_time': '07:00',
                'duration_minutes': None, 'quality': None,
            })]),
            turn(text='Ready.'),
        )
        events = sse(client.post('/api/assistant/chat', json={'message': f'bed at {bedtime}'}))
        return next(e for e in events if e['type'] == 'proposal')

    queue_sleep('23:00')
    corrected = queue_sleep('23:45')

    sleeps = [a for a in corrected['actions'] if a['type'] == 'sleep']
    assert len(sleeps) == 1, 'a corrected bedtime should replace, not stack'
    assert sleeps[0]['bedtime'] == '23:45'

    client.post(f'/api/assistant/proposals/{corrected["id"]}/apply', json={})
    assert conn.execute('SELECT bedtime FROM sleep_entries').fetchone()['bedtime'] == '23:45'


def test_a_new_conversation_still_supersedes_the_old_card(client, app_module, monkeypatch):
    """Accumulating within a conversation must not resurrect the old property.

    Two live Save buttons means pressing the older one logs something the person
    already talked past - so a check-in starting fresh retires whatever a chat
    left pending.
    """
    conn, first = propose(client, app_module, monkeypatch, grams=80)

    # A check-in is a different conversation from the free chat above.
    use_fake(
        monkeypatch,
        turn(calls=[call('propose_sleep', {
            'date': '2026-09-20', 'bedtime': '22:30', 'wake_time': '06:30',
            'duration_minutes': None, 'quality': None,
        })]),
        turn(text='Ready.'),
    )
    events = sse(client.post('/api/assistant/chat',
                             json={'message': 'slept 10:30 to 6:30', 'kind': 'today',
                                   'date': '2026-09-20'}))
    second = next(e for e in events if e['type'] == 'proposal')

    assert first['id'] != second['id']
    assert client.post(f'/api/assistant/proposals/{first["id"]}/apply', json={}).status_code == 400
    assert conn.execute('SELECT COUNT(*) AS n FROM food_entries').fetchone()['n'] == 0


def test_free_chat_remembers_the_previous_turn(client, app_module, monkeypatch):
    """Without this the assistant cannot answer "make that 120 grams instead",
    because every message started a conversation with no history."""
    register(client)
    fake = use_fake(monkeypatch, turn(text='one'), turn(text='two'))

    client.post('/api/assistant/chat', json={'message': 'I had oats'})
    client.post('/api/assistant/chat', json={'message': 'make that 120 grams'})

    conn = app_module.get_db_connection()
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM ai_conversations WHERE kind = 'general'"
    ).fetchone()['n'] == 1

    # The second request carried the first exchange with it.
    sent = fake.last_request['input']
    assert any(isinstance(item, dict) and item.get('content') == 'I had oats' for item in sent)


def test_a_pending_proposal_survives_a_reload(client, app_module, monkeypatch):
    _, proposal = propose(client, app_module, monkeypatch)

    state = client.get('/api/assistant/state').get_json()

    assert state['pending_proposal']['id'] == proposal['id']


# --- the bill ------------------------------------------------------------------

def test_spend_is_admin_only(client, monkeypatch):
    register(client, username='owner')
    client.post('/logout')
    register(client, username='friend')

    assert client.get('/api/admin/ai-usage').status_code == 403


def test_spend_is_broken_down_by_feature(client, app_module):
    register(client, username='owner')
    conn = app_module.get_db_connection()
    usage.record(conn, 1, 'today', 'gpt-5.6-terra', {'input_tokens': 20_000, 'output_tokens': 900})
    usage.record(conn, 1, 'label', 'gpt-5.6-luna', {'input_tokens': 3_000, 'output_tokens': 200})

    payload = client.get('/api/admin/ai-usage?days=7').get_json()

    assert payload['estimated'] is True
    assert payload['days'] == 7
    assert {row['feature'] for row in payload['by_feature']} == {'today', 'label'}
