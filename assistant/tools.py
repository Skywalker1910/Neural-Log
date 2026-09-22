"""What the assistant can see, and what it can ask for.

Two kinds of tool, and the split is the whole safety model.

**Read tools run.** They query the database and hand the result back to the
model, because reading is free of consequence.

**Write tools do not write.** They validate their arguments, turn them into a
normalised action, and queue it. Nothing reaches the app until a person presses
Save. The model is told this in as many words, so it says "ready to log" rather
than "logged" - a model that believes it has already saved will happily move on
and leave the person thinking their day is recorded.

## Why not just wrap the HTTP endpoints

Because they are already here. Calling `/api/nutrition/<date>/entries` from
inside the same process means constructing a request, carrying the session
cookie, and parsing a response, to reach a function that is three imports away.
Worse, it puts the assistant's writes on the same path as the user's, so the
`before_request` CSRF guard has to be worked around - and working around CSRF is
not something a codebase should learn how to do.

The cost is that these handlers duplicate a little validation. That is the right
trade: the duplication is small and visible, and the alternative was a hole.

## Why so few tools

Fourteen, against sixty-odd endpoints. A model given sixty tools chooses worse
than one given fourteen, and most of those endpoints are read paths that collapse
into a single "what happened on this day" call. Tools are a prompt, not an API
surface - they should describe the jobs, not the routes.
"""
import json
from datetime import date as _date

from scoring.units import VOLUME_KG_SQL, to_kg

TOOLS = {}


class ToolError(Exception):
    """A tool was called with arguments it cannot use.

    Raised rather than returned, and caught by the runner, which hands the text
    back to the model as the tool's result. The model then usually fixes it
    itself - which is the point of saying what was wrong rather than just that
    something was.
    """


class ToolContext:
    """Everything a tool is allowed to touch.

    Carries the user id explicitly rather than reading the Flask session, so a
    tool cannot accidentally act as whoever is logged in when it happens to run -
    and so the whole registry is testable without a request.
    """

    def __init__(self, conn, user_id, today=None, username=None, record_checklist=None):
        self.conn = conn
        self.user_id = user_id
        self.today = today or _date.today().strftime('%Y-%m-%d')
        self.username = username or f'user_{user_id}'
        # app.record_checklist_day, injected. Answering the check-in has to run
        # the same code the Today page runs - see _apply_checkin - and tools.py
        # cannot import app without a cycle.
        self.record_checklist = record_checklist
        self.queued = []


def tool(name, description, parameters, writes=False):
    def register(handler):
        TOOLS[name] = {
            'name': name,
            'description': description,
            'parameters': parameters,
            'handler': handler,
            'writes': writes,
        }
        return handler
    return register


def schema_for_provider():
    """Tool definitions in the shape the Responses API wants.

    `strict` with `additionalProperties: false` throughout, which is what makes
    the arguments arrive schema-valid instead of merely plausible - the same
    choice the portfolio assistant makes, and worth more here because these
    arguments become database rows.
    """
    return [
        {
            'type': 'function',
            'name': spec['name'],
            'description': spec['description'],
            'strict': True,
            'parameters': spec['parameters'],
        }
        for spec in TOOLS.values()
    ]


def _date_or_today(ctx, value):
    day = (value or '').strip() or ctx.today
    try:
        _date.fromisoformat(day)
    except ValueError:
        raise ToolError(f'"{day}" is not a date. Use YYYY-MM-DD.')
    return day


def _obj(properties, required):
    return {
        'type': 'object',
        'properties': properties,
        'required': required,
        'additionalProperties': False,
    }


def _existing_responses(conn, user_id, date):
    """This day's checklist answers, as `{question name: response}`.

    Two things about the storage are easy to get wrong, so they are decided once
    here. The answers are not a column - they live inside `daily_log.payload_json`
    under `items`, which is the snapshot `day_detail` reads. And they are keyed by
    question *name*, not id, because that is the shape `record_checklist_day`
    expects and the shape the Today page posts.
    """
    row = conn.execute(
        'SELECT payload_json FROM daily_log WHERE user_id = ? AND date = ?',
        (user_id, date),
    ).fetchone()
    if not row:
        return {}

    try:
        payload = json.loads(row['payload_json'] or '{}')
    except (TypeError, ValueError):
        return {}

    return {
        item.get('name'): item.get('response')
        for item in payload.get('items', [])
        if item.get('name') and str(item.get('response') or '').strip()
    }


# --- reading ------------------------------------------------------------------

@tool(
    name='get_day',
    description=(
        'Everything already recorded for one day: survey answers, meals and '
        'macros against target, sleep, study, and which habits are due. Call '
        'this first, always. It is what tells you which questions not to ask.'
    ),
    parameters=_obj(
        {'date': {'type': ['string', 'null'], 'description': 'YYYY-MM-DD. Null means today.'}},
        ['date'],
    ),
)
def get_day(ctx, date=None):
    day = _date_or_today(ctx, date)
    conn, user_id = ctx.conn, ctx.user_id

    logged = conn.execute(
        'SELECT 1 FROM daily_log WHERE user_id = ? AND date = ?', (user_id, day)
    ).fetchone()

    meals = conn.execute(
        'SELECT food_entries.meal, foods.name, food_entries.grams, '
        '       ROUND(foods.kcal_per_100g * food_entries.grams / 100.0) AS kcal '
        'FROM food_entries JOIN foods ON foods.id = food_entries.food_id '
        'WHERE food_entries.user_id = ? AND food_entries.date = ? '
        'ORDER BY food_entries.position',
        (user_id, day),
    ).fetchall()

    sleep = conn.execute(
        'SELECT bedtime, wake_time, duration_minutes, quality FROM sleep_entries '
        'WHERE user_id = ? AND date = ?',
        (user_id, day),
    ).fetchone()

    workouts = conn.execute(
        'SELECT name, total_sets, total_volume, duration_seconds FROM workout_sessions '
        'WHERE user_id = ? AND date = ?',
        (user_id, day),
    ).fetchall()

    study = conn.execute(
        'SELECT COALESCE(SUM(duration_minutes), 0) AS minutes, COUNT(*) AS sessions '
        'FROM learning_sessions WHERE user_id = ? AND date = ?',
        (user_id, day),
    ).fetchone()

    lifestyle = conn.execute(
        'SELECT water_ml, steps, mood FROM lifestyle_days WHERE user_id = ? AND date = ?',
        (user_id, day),
    ).fetchone()

    return {
        'date': day,
        'is_today': day == ctx.today,
        'checklist_submitted': bool(logged),
        'meals': [
            {'meal': row['meal'], 'food': row['name'],
             'grams': row['grams'], 'kcal': row['kcal']}
            for row in meals
        ],
        'total_kcal': sum(row['kcal'] or 0 for row in meals),
        'sleep': dict(sleep) if sleep else None,
        'workouts': [dict(row) for row in workouts],
        'study_minutes': int(study['minutes'] or 0) if study else 0,
        'lifestyle': dict(lifestyle) if lifestyle else None,
        # Named so the model reads it as a to-do rather than a summary.
        'still_missing': [
            name for name, present in (
                ('food', bool(meals)),
                ('sleep', bool(sleep)),
                ('training', bool(workouts)),
                ('study', bool(study and study['sessions'])),
                ('daily check-in', bool(logged)),
            ) if not present
        ],
    }


@tool(
    name='search_foods',
    description=(
        'Find foods in the catalogue by name. Returns the id needed to log a '
        'meal, plus how the food is measured - grams, millilitres, whether it '
        'has a cup weight, and whether it is countable like an egg.'
    ),
    parameters=_obj(
        {'query': {'type': 'string', 'description': 'Part of a food name, e.g. "oat" or "chicken breast".'}},
        ['query'],
    ),
)
def search_foods(ctx, query):
    needle = (query or '').strip()
    if len(needle) < 2:
        raise ToolError('Give at least two characters to search for.')

    rows = ctx.conn.execute(
        'SELECT id, name, unit, kcal_per_100g, protein_per_100g, serving_name, '
        '       serving_grams, grams_per_cup, is_countable, source '
        'FROM foods WHERE name LIKE ? AND (user_id IS NULL OR user_id = ?) '
        '  AND COALESCE(archived, 0) = 0 '
        'ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END, LENGTH(name) '
        'LIMIT 12',
        (f'%{needle}%', ctx.user_id, f'{needle}%'),
    ).fetchall()

    return {
        'query': needle,
        'foods': [
            {
                'id': row['id'], 'name': row['name'],
                'unit': row['unit'] or 'g',
                'kcal_per_100': row['kcal_per_100g'],
                'protein_per_100': row['protein_per_100g'],
                'serving': row['serving_name'],
                'serving_grams': row['serving_grams'],
                'grams_per_cup': row['grams_per_cup'],
                'countable': bool(row['is_countable']),
                'is_own_recipe': row['source'] == 'recipe',
            }
            for row in rows
        ],
    }


@tool(
    name='get_survey_questions',
    description=(
        'The daily check-in questions this person is asked, with their ids and '
        'answer types. Needed before answering the check-in.'
    ),
    parameters=_obj({}, []),
)
def get_survey_questions(ctx):
    import habits
    items = habits.load_survey(ctx.conn, ctx.user_id)
    return {
        'questions': [
            {
                'id': item.get('id'),
                'name': item.get('name'),
                'type': item.get('type'),
                'options': item.get('options') or None,
                'weight': item.get('weight'),
                'personal': not item.get('is_core', True),
            }
            for item in items
        ]
    }


# --- proposing ----------------------------------------------------------------
#
# Every handler below ends the same way: it validates, describes, and queues.
# None of them touch a table.

def _queue(ctx, action, summary):
    ctx.queued.append({'type': action.pop('type'), 'summary': summary, **action})
    return {
        'queued': True,
        'summary': summary,
        # Said plainly because the model will otherwise tell the person it is
        # done, and they will believe it.
        'note': 'Not saved yet. This is waiting for the person to confirm.',
    }


@tool(
    name='propose_meal',
    description=(
        'Queue a meal to be logged. Look up every food with search_foods first - '
        'never invent a food id. Amounts are in grams; convert from what the '
        'person said using the serving or cup weight the search returned, and '
        'say in your reply what you converted so they can correct you.'
    ),
    parameters=_obj(
        {
            'date': {'type': ['string', 'null']},
            'meal': {'type': 'string', 'enum': ['breakfast', 'lunch', 'dinner', 'snack']},
            'items': {
                'type': 'array',
                'items': _obj(
                    {
                        'food_id': {'type': 'integer'},
                        'name': {'type': 'string', 'description': 'As it should read on the confirmation card.'},
                        'grams': {'type': 'number'},
                    },
                    ['food_id', 'name', 'grams'],
                ),
            },
        },
        ['date', 'meal', 'items'],
    ),
    writes=True,
)
def propose_meal(ctx, date=None, meal='snack', items=None):
    day = _date_or_today(ctx, date)
    items = items or []
    if not items:
        raise ToolError('A meal needs at least one item.')

    clean = []
    for item in items:
        grams = float(item.get('grams') or 0)
        if grams <= 0 or grams > 5000:
            raise ToolError(f'{item.get("name")}: {grams} g is not a plausible amount.')
        food = ctx.conn.execute(
            'SELECT id, name FROM foods WHERE id = ? AND (user_id IS NULL OR user_id = ?) '
            '  AND COALESCE(archived, 0) = 0',
            (item.get('food_id'), ctx.user_id),
        ).fetchone()
        if not food:
            raise ToolError(
                f'No food with id {item.get("food_id")}. Use search_foods and take the id from it.'
            )
        clean.append({'food_id': food['id'], 'name': food['name'], 'grams': round(grams, 1)})

    summary = f'{meal.title()} on {day}: ' + ', '.join(
        f'{entry["name"]} {entry["grams"]:g} g' for entry in clean
    )
    return _queue(ctx, {'type': 'meal', 'date': day, 'meal': meal, 'items': clean}, summary)


@tool(
    name='propose_sleep',
    description=(
        'Queue last night\'s sleep. Give clock times when the person said them; '
        'the duration is worked out from those. The date is the morning they '
        'woke up on.'
    ),
    parameters=_obj(
        {
            'date': {'type': ['string', 'null']},
            'bedtime': {'type': ['string', 'null'], 'description': 'HH:MM, 24-hour.'},
            'wake_time': {'type': ['string', 'null'], 'description': 'HH:MM, 24-hour.'},
            'duration_minutes': {'type': ['integer', 'null'], 'description': 'Only if no clock times are known.'},
            'quality': {'type': ['integer', 'null'], 'description': '1-5, if they said how they slept.'},
        },
        ['date', 'bedtime', 'wake_time', 'duration_minutes', 'quality'],
    ),
    writes=True,
)
def propose_sleep(ctx, date=None, bedtime=None, wake_time=None,
                  duration_minutes=None, quality=None):
    day = _date_or_today(ctx, date)
    if not duration_minutes and not (bedtime and wake_time):
        raise ToolError('Either a bedtime and wake time, or a duration in minutes.')
    if quality is not None and not 1 <= int(quality) <= 5:
        raise ToolError('Sleep quality is 1 to 5.')

    if bedtime and wake_time:
        told = f'{bedtime} to {wake_time}'
    else:
        told = f'{duration_minutes} minutes'

    return _queue(
        ctx,
        {'type': 'sleep', 'date': day, 'bedtime': bedtime, 'wake_time': wake_time,
         'duration_minutes': duration_minutes, 'quality': quality},
        f'Sleep on {day}: {told}' + (f', quality {quality}/5' if quality else ''),
    )


@tool(
    name='propose_lifestyle',
    description='Queue water, steps or mood for a day. Only include what was actually mentioned.',
    parameters=_obj(
        {
            'date': {'type': ['string', 'null']},
            'water_ml': {'type': ['integer', 'null']},
            'steps': {'type': ['integer', 'null']},
            'mood': {'type': ['integer', 'null'], 'description': '1-5.'},
        },
        ['date', 'water_ml', 'steps', 'mood'],
    ),
    writes=True,
)
def propose_lifestyle(ctx, date=None, water_ml=None, steps=None, mood=None):
    day = _date_or_today(ctx, date)
    if water_ml is None and steps is None and mood is None:
        raise ToolError('Nothing to record - give water, steps or mood.')
    if mood is not None and not 1 <= int(mood) <= 5:
        raise ToolError('Mood is 1 to 5.')

    parts = []
    if water_ml is not None:
        parts.append(f'{water_ml} ml water')
    if steps is not None:
        parts.append(f'{steps:,} steps')
    if mood is not None:
        parts.append(f'mood {mood}/5')

    return _queue(
        ctx,
        {'type': 'lifestyle', 'date': day, 'water_ml': water_ml, 'steps': steps, 'mood': mood},
        f'{day}: ' + ', '.join(parts),
    )


@tool(
    name='propose_study',
    description=(
        'Queue a study session. Use get_day first to see whether one is already '
        'recorded, so the same hour is not logged twice.'
    ),
    parameters=_obj(
        {
            'date': {'type': ['string', 'null']},
            'topic': {'type': 'string', 'description': 'What they studied, in their words.'},
            'duration_minutes': {'type': 'integer'},
        },
        ['date', 'topic', 'duration_minutes'],
    ),
    writes=True,
)
def propose_study(ctx, date=None, topic='', duration_minutes=0):
    day = _date_or_today(ctx, date)
    minutes = int(duration_minutes or 0)
    if not 1 <= minutes <= 24 * 60:
        raise ToolError(f'{minutes} minutes is not a plausible study session.')
    if not (topic or '').strip():
        raise ToolError('Say what was studied.')

    return _queue(
        ctx,
        {'type': 'study', 'date': day, 'topic': topic.strip(), 'duration_minutes': minutes},
        f'Study on {day}: {topic.strip()}, {minutes} min',
    )


# `propose_checkin` is deliberately absent.
#
# Answering the daily check-in has to go through the same path the Today page
# uses - `save_day()` in app.py, which writes the activity row, the daily_log
# row, and runs `score_checklist_day()`. Its own docstring says a day logged
# there must be indistinguishable from one logged by the legacy wizard, and a
# second implementation here would be exactly the drift it warns about.
#
# So the check-in waits for the phase that extracts that function properly,
# which is also the phase that needs it: the guided Today conversation.

# --- applying -----------------------------------------------------------------

def apply_action(ctx, action, recompute=None):
    """Execute one confirmed action. Called only from the proposal apply path.

    Returns a short description of what happened, which is stored on the
    proposal - a half-applied change-set has to be legible afterwards.
    """
    kind = action.get('type')
    handler = _APPLIERS.get(kind)
    if handler is None:
        raise ToolError(f'Unknown action type "{kind}".')
    return handler(ctx, action, recompute)


def _apply_meal(ctx, action, recompute):
    day, meal = action['date'], action.get('meal', 'snack')
    position = ctx.conn.execute(
        'SELECT COALESCE(MAX(position), 0) AS top FROM food_entries '
        'WHERE user_id = ? AND date = ? AND meal = ?',
        (ctx.user_id, day, meal),
    ).fetchone()['top']

    for item in action['items']:
        position += 1
        ctx.conn.execute(
            'INSERT INTO food_entries (user_id, date, meal, food_id, grams, position) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (ctx.user_id, day, meal, item['food_id'], float(item['grams']), position),
        )
    ctx.conn.commit()
    if recompute:
        recompute(ctx.conn, ctx.user_id, day)
    return f'Logged {len(action["items"])} item(s) to {meal} on {day}.'


def _apply_sleep(ctx, action, recompute):
    day = action['date']
    duration = action.get('duration_minutes')
    if not duration and action.get('bedtime') and action.get('wake_time'):
        from nutrition_api import _duration_from_clock
        duration = _duration_from_clock(action['bedtime'], action['wake_time'])

    ctx.conn.execute('DELETE FROM sleep_entries WHERE user_id = ? AND date = ?', (ctx.user_id, day))
    ctx.conn.execute(
        'INSERT INTO sleep_entries (user_id, date, bedtime, wake_time, '
        'duration_minutes, quality) VALUES (?, ?, ?, ?, ?, ?)',
        (ctx.user_id, day, action.get('bedtime'), action.get('wake_time'),
         duration, action.get('quality')),
    )
    ctx.conn.commit()
    if recompute:
        recompute(ctx.conn, ctx.user_id, day)
    return f'Logged {duration} minutes of sleep on {day}.'


def _apply_lifestyle(ctx, action, recompute):
    day = action['date']
    existing = ctx.conn.execute(
        'SELECT water_ml, steps, mood FROM lifestyle_days WHERE user_id = ? AND date = ?',
        (ctx.user_id, day),
    ).fetchone()

    # Merge rather than replace: a conversation about water should not blank out
    # the step count somebody entered by hand this morning.
    def pick(key):
        supplied = action.get(key)
        if supplied is not None:
            return supplied
        return existing[key] if existing else None

    values = (pick('water_ml'), pick('steps'), pick('mood'))
    if existing:
        ctx.conn.execute(
            'UPDATE lifestyle_days SET water_ml = ?, steps = ?, mood = ? '
            'WHERE user_id = ? AND date = ?',
            (*values, ctx.user_id, day),
        )
    else:
        ctx.conn.execute(
            'INSERT INTO lifestyle_days (user_id, date, water_ml, steps, mood) '
            'VALUES (?, ?, ?, ?, ?)',
            (ctx.user_id, day, *values),
        )
    ctx.conn.commit()
    if recompute:
        recompute(ctx.conn, ctx.user_id, day)
    return f'Updated lifestyle for {day}.'


def _apply_study(ctx, action, recompute):
    day = action['date']
    ctx.conn.execute(
        'INSERT INTO learning_sessions (user_id, date, duration_minutes, notes) '
        'VALUES (?, ?, ?, ?)',
        (ctx.user_id, day, int(action['duration_minutes']), action.get('topic')),
    )
    ctx.conn.commit()
    if recompute:
        recompute(ctx.conn, ctx.user_id, day)
    return f'Logged {action["duration_minutes"]} minutes of study on {day}.'


_APPLIERS = {
    'meal': _apply_meal,
    'sleep': _apply_sleep,
    'lifestyle': _apply_lifestyle,
    'study': _apply_study,
}


# --- the guided check-in -------------------------------------------------------

@tool(
    name='get_checkin_plan',
    description=(
        'What is worth asking about today, in order, with the reason each one '
        'ranks where it does. The order comes from the scoring engine: a topic '
        'near the top is one whose attribute is currently capped because nothing '
        'has evidenced it. Use this to run a check-in. Anything marked recorded '
        'must not be asked about.'
    ),
    parameters=_obj({'date': {'type': ['string', 'null']}}, ['date']),
)
def get_checkin_plan(ctx, date=None):
    import habits

    from . import checkin

    day = _date_or_today(ctx, date)
    items = habits.load_survey(ctx.conn, ctx.user_id)

    # Answers are stored by name; the plan and the model both work in ids.
    answered_names = set(_existing_responses(ctx.conn, ctx.user_id, day))
    answered = {
        item.get('id') for item in items if item.get('name') in answered_names
    }

    return checkin.plan(ctx.conn, ctx.user_id, day, survey_items=items, answered=answered)


@tool(
    name='propose_checkin',
    description=(
        'Queue answers to the daily check-in. Take the question ids from '
        'get_checkin_plan. Answer only what the person actually told you - an '
        'unanswered question is honest, and a guessed one silently becomes part '
        'of their score.'
    ),
    parameters=_obj(
        {
            'date': {'type': ['string', 'null']},
            'answers': {
                'type': 'array',
                'items': _obj(
                    {
                        'question_id': {'type': 'string'},
                        'question': {'type': 'string',
                                     'description': 'The wording, for the card.'},
                        'value': {'type': 'string',
                                  'description': 'yes or no for yes-no questions, '
                                                 'otherwise the answer as text.'},
                    },
                    ['question_id', 'question', 'value'],
                ),
            },
        },
        ['date', 'answers'],
    ),
    writes=True,
)
def propose_checkin(ctx, date=None, answers=None):
    import habits

    day = _date_or_today(ctx, date)
    answers = answers or []
    if not answers:
        raise ToolError('No answers given.')

    known = {item.get('id') for item in habits.load_survey(ctx.conn, ctx.user_id)}
    unknown = [a.get('question_id') for a in answers if a.get('question_id') not in known]
    if unknown:
        raise ToolError(
            f'Not questions this person is asked: {", ".join(map(str, unknown))}. '
            'Call get_checkin_plan and use the ids from it.'
        )

    shown = ', '.join(f'{a["question"]}: {a["value"]}' for a in answers[:3])
    if len(answers) > 3:
        shown += f' (+{len(answers) - 3} more)'

    return _queue(
        ctx,
        {'type': 'checkin', 'date': day, 'answers': answers},
        f'Check-in for {day} - {shown}',
    )


# --- training ------------------------------------------------------------------

@tool(
    name='search_exercises',
    description=(
        'Find exercises by name or muscle. Returns the id needed to propose a '
        'workout, and whether the movement is strength, cardio or mobility - '
        'which decides whether its sets take a weight or a duration.'
    ),
    parameters=_obj(
        {'query': {'type': 'string',
                   'description': 'Part of an exercise name, or a muscle like "chest".'}},
        ['query'],
    ),
)
def search_exercises(ctx, query):
    needle = (query or '').strip()
    if len(needle) < 2:
        raise ToolError('Give at least two characters to search for.')

    rows = ctx.conn.execute(
        'SELECT id, name, primary_muscle, category, equipment FROM exercises '
        'WHERE (name LIKE ? OR primary_muscle LIKE ?) '
        '  AND (user_id IS NULL OR user_id = ?) AND COALESCE(archived, 0) = 0 '
        'ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END, LENGTH(name) LIMIT 12',
        (f'%{needle}%', f'%{needle}%', ctx.user_id, f'{needle}%'),
    ).fetchall()

    return {
        'query': needle,
        'exercises': [
            {'id': row['id'], 'name': row['name'], 'muscle': row['primary_muscle'],
             'category': row['category'], 'equipment': row['equipment']}
            for row in rows
        ],
    }


@tool(
    name='propose_workout',
    description=(
        'Queue a training session. Look every movement up with search_exercises '
        'first. Every set carries its own reps, weight and unit - do not average '
        'them or assume the same load across exercises. Say the unit the person '
        'said: "three sets of ten at sixty" in a gym that talks in pounds is '
        'weight 60, weight_unit lb. Cardio and mobility take duration_minutes '
        'instead of a weight.'
    ),
    parameters=_obj(
        {
            'date': {'type': ['string', 'null']},
            'name': {'type': ['string', 'null'],
                     'description': 'What to call the session, e.g. "Upper body".'},
            'exercises': {
                'type': 'array',
                'items': _obj(
                    {
                        'exercise_id': {'type': 'integer'},
                        'name': {'type': 'string'},
                        'sets': {
                            'type': 'array',
                            'items': _obj(
                                {
                                    'reps': {'type': ['integer', 'null']},
                                    'weight': {'type': ['number', 'null']},
                                    'weight_unit': {'type': ['string', 'null'],
                                                    'enum': ['kg', 'lb', None]},
                                    'duration_minutes': {'type': ['number', 'null']},
                                },
                                ['reps', 'weight', 'weight_unit', 'duration_minutes'],
                            ),
                        },
                    },
                    ['exercise_id', 'name', 'sets'],
                ),
            },
        },
        ['date', 'name', 'exercises'],
    ),
    writes=True,
)
def propose_workout(ctx, date=None, name=None, exercises=None):
    day = _date_or_today(ctx, date)
    exercises = exercises or []
    if not exercises:
        raise ToolError('A session needs at least one exercise.')

    clean, total_sets = [], 0
    for entry in exercises:
        found = ctx.conn.execute(
            'SELECT id, name FROM exercises WHERE id = ? AND (user_id IS NULL OR user_id = ?)',
            (entry.get('exercise_id'), ctx.user_id),
        ).fetchone()
        if not found:
            raise ToolError(
                f'No exercise with id {entry.get("exercise_id")}. Use search_exercises.'
            )

        sets = entry.get('sets') or []
        if not sets:
            raise ToolError(f'{found["name"]}: no sets given.')

        for one in sets:
            reps = one.get('reps')
            if reps is not None and not 0 < int(reps) <= 200:
                raise ToolError(f'{found["name"]}: {reps} reps is not plausible.')
            # Accepts the older `weight_kg` too, so a proposal queued before this
            # change still applies rather than 400ing on somebody's Save button.
            weight = one.get('weight', one.get('weight_kg'))
            unit = (one.get('weight_unit') or 'kg').lower()
            if unit not in ('kg', 'lb', 'lbs'):
                raise ToolError(f'{found["name"]}: "{unit}" is not kg or lb.')
            # Checked in kilograms whatever was typed, so the ceiling means the
            # same thing in both units - 600 lb would sail past a 600 kg test.
            if weight is not None and not 0 <= to_kg(float(weight), unit) <= 600:
                raise ToolError(f'{found["name"]}: {weight} {unit} is not plausible.')

        total_sets += len(sets)
        clean.append({'exercise_id': found['id'], 'name': found['name'], 'sets': sets})

    described = ', '.join(f'{entry["name"]} x{len(entry["sets"])}' for entry in clean)
    return _queue(
        ctx,
        {'type': 'workout', 'date': day, 'name': name or 'Session', 'exercises': clean},
        f'Training on {day} - {described} ({total_sets} sets)',
    )


def _apply_checkin(ctx, action, recompute):
    """Answers merged into what is already there, then scored by app.py.

    Two things this deliberately does not do.

    It does not replace the response set: sending only what the assistant heard
    would erase answers typed on the Today page an hour ago.

    And it does not score the day itself. `record_checklist_day` is injected, so
    a day answered by talking goes through exactly the code a day answered by
    tapping goes through - the activity row, the audit trail, the scoring, all of
    it. A second implementation here is the drift that function's docstring warns
    about, and it would show up weeks later as a streak wrong by a day.
    """
    if ctx.record_checklist is None:
        raise ToolError('The check-in writer is not wired up on this instance.')

    import habits

    day = action['date']
    responses = _existing_responses(ctx.conn, ctx.user_id, day)

    # The model works in ids because they are unambiguous; storage works in
    # names because that is what the scoring path takes. Translated here rather
    # than at either end, so neither has to know about the other's convention.
    names = {item.get('id'): item.get('name')
             for item in habits.load_survey(ctx.conn, ctx.user_id)}

    for answer in action['answers']:
        name = names.get(answer['question_id'])
        if name:
            responses[name] = answer['value']

    completion, _badges = ctx.record_checklist(
        ctx.conn, ctx.user_id, ctx.username, day, responses, source='assistant',
    )
    return f'Answered {len(action["answers"])} question(s) for {day} - {completion}% complete.'


def _apply_workout(ctx, action, recompute):
    day = action['date']
    cursor = ctx.conn.cursor()
    cursor.execute(
        'INSERT INTO workout_sessions (user_id, date, name) VALUES (?, ?, ?)',
        (ctx.user_id, day, action.get('name') or 'Session'),
    )
    session_id = cursor.lastrowid

    position = 0
    for entry in action['exercises']:
        for one in entry['sets']:
            position += 1
            duration = one.get('duration_minutes')
            ctx.conn.execute(
                'INSERT INTO exercise_sets (session_id, exercise_id, position, weight, '
                'weight_unit, reps, duration_seconds) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (session_id, entry['exercise_id'], position,
                 one.get('weight', one.get('weight_kg')),
                 # Stored as entered, never converted on the way in. Someone who
                 # switches gyms must not have last year's log reinterpreted -
                 # which is what the column was added for. Conversion happens on
                 # read, in scoring/units.py.
                 (one.get('weight_unit') or 'kg').lower().replace('lbs', 'lb'),
                 one.get('reps'),
                 int(float(duration) * 60) if duration else None),
            )

    # The same totals the Training workspace keeps, by the same rule: warm-ups
    # excluded, volume as weight times reps.
    totals = ctx.conn.execute(
        'SELECT COUNT(*) AS n, ' + VOLUME_KG_SQL + ' AS volume '
        'FROM exercise_sets WHERE session_id = ? AND is_warmup = 0',
        (session_id,),
    ).fetchone()
    ctx.conn.execute(
        'UPDATE workout_sessions SET total_sets = ?, total_volume = ? WHERE id = ?',
        (totals['n'], totals['volume'], session_id),
    )
    ctx.conn.commit()
    if recompute:
        recompute(ctx.conn, ctx.user_id, day)
    return f'Logged {totals["n"]} sets on {day}.'


_APPLIERS['checkin'] = _apply_checkin
_APPLIERS['workout'] = _apply_workout


# --- goals and tasks -----------------------------------------------------------
#
# Deliberately outside the weighted plan. Goals and tasks feed no attribute -
# `init_goals` takes no recompute function, because a goal is an intention rather
# than evidence - so ranking them alongside sleep and training would be inventing
# an analytical weight the engine does not give them.
#
# They are a closing follow-up instead, which is also how they were asked for:
# "followup with the user on their learning goals and any pending tasks".

@tool(
    name='get_open_work',
    description=(
        'Open goals and outstanding tasks. Use this at the end of a check-in to '
        'follow up on what someone said they would do. These do not affect any '
        'score - they are commitments, not evidence - so ask about them last and '
        'briefly.'
    ),
    parameters=_obj({}, []),
)
def get_open_work(ctx):
    today = ctx.today

    goals = ctx.conn.execute(
        'SELECT id, title, metric_name, target_value, current_value, target_date '
        "FROM goals WHERE user_id = ? AND status = 'active' AND COALESCE(archived, 0) = 0 "
        'ORDER BY target_date IS NULL, target_date LIMIT 8',
        (ctx.user_id,),
    ).fetchall()

    tasks = ctx.conn.execute(
        'SELECT tasks.id, tasks.title, tasks.due_date, tasks.priority, goals.title AS goal '
        'FROM tasks LEFT JOIN goals ON goals.id = tasks.goal_id '
        'WHERE tasks.user_id = ? AND tasks.completed_on IS NULL '
        '  AND COALESCE(tasks.archived, 0) = 0 '
        'ORDER BY tasks.due_date IS NULL, tasks.due_date, tasks.priority, tasks.position '
        'LIMIT 12',
        (ctx.user_id,),
    ).fetchall()

    return {
        'goals': [
            {
                'id': row['id'], 'title': row['title'],
                'metric': row['metric_name'],
                'progress': (
                    f'{row["current_value"] or 0:g} of {row["target_value"]:g}'
                    if row['target_value'] else None
                ),
                'target_date': row['target_date'],
            }
            for row in goals
        ],
        'tasks': [
            {
                'id': row['id'], 'title': row['title'],
                'due': row['due_date'],
                # Flagged rather than left for the model to work out from dates,
                # so "anything overdue?" is one field instead of arithmetic.
                'overdue': bool(row['due_date'] and row['due_date'] < today),
                'goal': row['goal'],
            }
            for row in tasks
        ],
    }


@tool(
    name='propose_tasks_done',
    description=(
        'Queue one or more tasks as finished. Take the ids from get_open_work - '
        'never guess one. Only mark what they actually said they did.'
    ),
    parameters=_obj(
        {
            'tasks': {
                'type': 'array',
                'items': _obj(
                    {
                        'task_id': {'type': 'integer'},
                        'title': {'type': 'string', 'description': 'For the confirmation card.'},
                    },
                    ['task_id', 'title'],
                ),
            },
        },
        ['tasks'],
    ),
    writes=True,
)
def propose_tasks_done(ctx, tasks=None):
    tasks = tasks or []
    if not tasks:
        raise ToolError('No tasks given.')

    clean = []
    for entry in tasks:
        row = ctx.conn.execute(
            'SELECT id, title FROM tasks WHERE id = ? AND user_id = ? '
            'AND completed_on IS NULL',
            (entry.get('task_id'), ctx.user_id),
        ).fetchone()
        if not row:
            raise ToolError(
                f'No open task with id {entry.get("task_id")}. Call get_open_work.'
            )
        clean.append({'task_id': row['id'], 'title': row['title']})

    listed = ', '.join(entry['title'] for entry in clean)
    return _queue(
        ctx,
        {'type': 'tasks_done', 'date': ctx.today, 'tasks': clean},
        f'Mark done: {listed}',
    )


@tool(
    name='propose_goal_progress',
    description=(
        'Queue an update to where a goal has got to. Only for goals with a '
        'metric, and only when they told you a number. The value is the new '
        'total, not the amount added.'
    ),
    parameters=_obj(
        {
            'goal_id': {'type': 'integer'},
            'title': {'type': 'string', 'description': 'For the confirmation card.'},
            'current_value': {'type': 'number', 'description': 'The new total.'},
        },
        ['goal_id', 'title', 'current_value'],
    ),
    writes=True,
)
def propose_goal_progress(ctx, goal_id=None, title='', current_value=None):
    row = ctx.conn.execute(
        'SELECT id, title, metric_name, target_value FROM goals '
        "WHERE id = ? AND user_id = ? AND status = 'active'",
        (goal_id, ctx.user_id),
    ).fetchone()
    if not row:
        raise ToolError(f'No active goal with id {goal_id}. Call get_open_work.')
    if not row['metric_name']:
        raise ToolError(
            f'"{row["title"]}" has no metric to update - it is not measured by a number.'
        )
    if current_value is None or float(current_value) < 0:
        raise ToolError('Give the new total as a number.')

    target = f' of {row["target_value"]:g}' if row['target_value'] else ''
    return _queue(
        ctx,
        {'type': 'goal_progress', 'date': ctx.today, 'goal_id': row['id'],
         'title': row['title'], 'current_value': float(current_value)},
        f'{row["title"]}: {float(current_value):g}{target} {row["metric_name"]}',
    )


def _apply_tasks_done(ctx, action, recompute):
    """No recompute call, and that is not an omission.

    Goals and tasks feed no attribute - `init_goals` is registered without one,
    because a goal is an intention rather than evidence. Rescoring here would
    move nothing and imply otherwise.
    """
    done = ctx.today
    for entry in action['tasks']:
        ctx.conn.execute(
            'UPDATE tasks SET completed_on = ? WHERE id = ? AND user_id = ? '
            'AND completed_on IS NULL',
            (done, entry['task_id'], ctx.user_id),
        )
    ctx.conn.commit()
    return f'Marked {len(action["tasks"])} task(s) done.'


def _apply_goal_progress(ctx, action, recompute):
    ctx.conn.execute(
        'UPDATE goals SET current_value = ? WHERE id = ? AND user_id = ?',
        (float(action['current_value']), action['goal_id'], ctx.user_id),
    )
    ctx.conn.commit()
    return f'{action["title"]} is now at {float(action["current_value"]):g}.'


_APPLIERS['tasks_done'] = _apply_tasks_done
_APPLIERS['goal_progress'] = _apply_goal_progress
