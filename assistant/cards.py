"""Small, deterministic input cards for the assistant.

The assistant still decides what it understands and can only queue a proposal.
Cards are a faster way to express the routine answers a model would otherwise
have to ask for one sentence at a time.  They deliberately produce plain
language messages, so they travel through the same validated tool path as a
typed answer.
"""
import re


MUSCLES = {
    'back': ('back',),
    'biceps': ('biceps',),
    'chest': ('chest',),
    'triceps': ('triceps',),
    'shoulders': ('shoulders',),
    'legs': ('quads', 'hamstrings', 'glutes', 'calves'),
    'core': ('core',),
}


def next_input_card(plan, queued=()):
    """Return the first missing measured topic as a serialisable card.

    The check-in plan already knows what is recorded and what matters most.
    Keeping the card selection derived from that plan avoids a second,
    eventually-wrong list of questions in the web layer.
    """
    queued_topics = {
        {'meal': 'food', 'sleep': 'sleep', 'lifestyle': 'steps',
         'study': 'study', 'workout': 'training'}.get(action.get('type'))
        for action in queued
    }
    item = next((item for item in plan['items']
                 if item['status'] == 'missing' and item['topic'] not in queued_topics
                 and item['topic'] != 'checkin'), None)
    if item is None:
        return None

    topic = item['topic']
    cards = {
        'sleep': {
            'title': 'Last night',
            'eyebrow': 'Recovery',
            'prompt': 'Add the times while they are still easy to remember.',
            'fields': [
                {'id': 'bedtime', 'label': 'Bedtime', 'type': 'time'},
                {'id': 'wake_time', 'label': 'Wake time', 'type': 'time'},
            ],
            'submit_label': 'Add sleep',
            'message': 'I slept from {bedtime} to {wake_time}.',
        },
        'food': {
            'title': 'What did you eat?',
            'eyebrow': 'Nutrition',
            'prompt': 'A meal and a rough amount are enough. You can correct it afterwards.',
            'fields': [
                {'id': 'meal', 'label': 'Meal', 'type': 'select',
                 'options': ['Breakfast', 'Lunch', 'Dinner', 'Snack']},
                {'id': 'details', 'label': 'What and how much?', 'type': 'text',
                 'placeholder': 'e.g. oats with milk, about one bowl'},
            ],
            'submit_label': 'Add meal',
            'message': 'For {meal}, I had {details}.',
        },
        'training': {
            'title': 'Movement',
            'eyebrow': 'Training',
            'prompt': 'Name the session, or mark it as a rest day.',
            'fields': [
                {'id': 'details', 'label': 'What did you do?', 'type': 'text',
                 'placeholder': 'e.g. 45 min upper body, 3 sets each'},
            ],
            'choices': [
                {'label': 'Rest day', 'message': 'I did not train today.'},
            ],
            'submit_label': 'Add session',
            'message': 'I trained: {details}.',
        },
        'study': {
            'title': 'Learning',
            'eyebrow': 'Focus',
            'prompt': 'A topic and approximate duration gives the assistant enough to log it.',
            'fields': [
                {'id': 'details', 'label': 'What did you work on?', 'type': 'text',
                 'placeholder': 'e.g. 50 min of a TypeScript course'},
            ],
            'choices': [
                {'label': 'No study today', 'message': 'I did not study today.'},
            ],
            'submit_label': 'Add study',
            'message': 'I studied {details}.',
        },
        'steps': {
            'title': 'Daily movement',
            'eyebrow': 'Activity',
            'prompt': 'A rough step count is useful. It does not have to be exact.',
            'fields': [
                {'id': 'steps', 'label': 'Steps', 'type': 'number', 'placeholder': 'e.g. 6800'},
            ],
            'choices': [
                {'label': 'No tracker today', 'message': 'I do not know my steps today.'},
            ],
            'submit_label': 'Add steps',
            'message': 'I took {steps} steps today.',
        },
    }
    card = cards.get(topic)
    if card is None:
        return None

    return {'id': f'checkin-{topic}', 'topic': topic, 'reason': item['reason'], **card}


def _conversation_text(message, prior):
    """The last few user turns are enough to retain a requested muscle group."""
    user_turns = [turn.get('content', '') for turn in prior[-8:]
                  if turn.get('role') == 'user']
    return ' '.join([*user_turns, message]).lower()


def _routine_choices(conn, user_id):
    rows = conn.execute(
        'SELECT routines.id, routines.name, routines.split_type, '
        'COUNT(routine_exercises.id) AS exercise_count '
        'FROM routines LEFT JOIN routine_exercises ON routine_exercises.routine_id = routines.id '
        'WHERE routines.user_id = ? AND COALESCE(routines.archived, 0) = 0 '
        'GROUP BY routines.id ORDER BY routines.name LIMIT 6',
        (user_id,),
    ).fetchall()
    return [
        {
            'label': row['name'],
            'detail': f"{row['exercise_count']} exercise{'s' if row['exercise_count'] != 1 else ''}"
            + (f" · {row['split_type']}" if row['split_type'] else ''),
            # The assistant can resolve the routine through its ordinary tools;
            # this is a plain language answer, not a browser-supplied action.
            'message': f"I want to log routine #{row['id']}: {row['name']} today.",
        }
        for row in rows
    ]


def _exercise_card(conn, user_id, muscles):
    values = sorted({muscle for group in muscles for muscle in MUSCLES[group]})
    marks = ', '.join('?' for _ in values)
    rows = conn.execute(
        'SELECT id, name, primary_muscle, equipment FROM exercises '
        f'WHERE primary_muscle IN ({marks}) '
        'AND (user_id IS NULL OR user_id = ?) AND COALESCE(archived, 0) = 0 '
        'ORDER BY is_compound DESC, name LIMIT 12',
        (*values, user_id),
    ).fetchall()
    if not rows:
        return None
    return {
        'id': f"exercise-picker-{'-'.join(muscles)}",
        'topic': 'training',
        'eyebrow': 'Training',
        'title': 'Choose your exercises',
        'prompt': 'Pick everything you did, then add the common set details below.',
        'reason': 'Your selected muscle groups shape this list.',
        'options': [
            {'label': row['name'], 'value': row['name'],
             'detail': ' · '.join(part for part in (row['primary_muscle'], row['equipment']) if part)}
            for row in rows
        ],
        'fields': [
            {'id': 'sets', 'label': 'Sets each', 'type': 'number', 'placeholder': '3'},
            {'id': 'reps', 'label': 'Reps each', 'type': 'number', 'placeholder': '10'},
            {'id': 'weight', 'label': 'Weight kg (optional)', 'type': 'number', 'placeholder': '40'},
        ],
        'submit_label': 'Log selected exercises',
        'message': 'I did {selection}: {sets} sets of {reps} reps each at {weight} kg.',
    }


def _routine_exercise_card(conn, user_id, text):
    match = re.search(r'routine #(\d+)', text)
    if not match:
        return None
    routine = conn.execute(
        'SELECT id, name FROM routines WHERE id = ? AND user_id = ? '
        'AND COALESCE(archived, 0) = 0', (int(match.group(1)), user_id),
    ).fetchone()
    if routine is None:
        return None
    rows = conn.execute(
        'SELECT exercises.name, exercises.primary_muscle, exercises.equipment, '
        'routine_exercises.target_sets, routine_exercises.target_reps '
        'FROM routine_exercises JOIN exercises ON exercises.id = routine_exercises.exercise_id '
        'WHERE routine_exercises.routine_id = ? ORDER BY routine_exercises.position',
        (routine['id'],),
    ).fetchall()
    if not rows:
        return None
    return {
        'id': f"routine-exercises-{routine['id']}", 'topic': 'training', 'eyebrow': 'Training',
        'title': routine['name'],
        'prompt': 'Select the exercises you completed. The targets are shown as a guide.',
        'reason': 'This is one of your saved routines.',
        'options': [
            {'label': row['name'], 'value': row['name'],
             'detail': ' · '.join(part for part in (
                 row['primary_muscle'],
                 f"{row['target_sets']} × {row['target_reps']}" if row['target_sets'] and row['target_reps'] else None,
             ) if part)}
            for row in rows
        ],
        'fields': [
            {'id': 'sets', 'label': 'Sets each', 'type': 'number', 'placeholder': '3'},
            {'id': 'reps', 'label': 'Reps each', 'type': 'number', 'placeholder': '10'},
            {'id': 'weight', 'label': 'Weight kg (optional)', 'type': 'number', 'placeholder': '40'},
        ],
        'submit_label': 'Log selected exercises',
        'message': 'I did {selection}: {sets} sets of {reps} reps each at {weight} kg.',
    }


def general_input_card(conn, user_id, message, prior):
    """Return a useful form after a free-form assistant reply, if one fits."""
    text = _conversation_text(message, prior)
    training_words = ('workout', 'train', 'training', 'gym', 'exercise', 'lift', 'routine')
    if any(word in text for word in training_words):
        from_routine = _routine_exercise_card(conn, user_id, text)
        if from_routine:
            return from_routine
        selected_muscles = [key for key in MUSCLES if key in text]
        if selected_muscles:
            return _exercise_card(conn, user_id, selected_muscles)
        routines = _routine_choices(conn, user_id)
        if routines:
            return {
                'id': 'routine-picker', 'topic': 'training', 'eyebrow': 'Training',
                'title': 'Start from a routine',
                'prompt': 'Choose one of your saved routines, or build a session from scratch.',
                'reason': 'Saved routines keep familiar workouts quick to log.',
                'fields': [], 'choices': routines + [
                    {'label': 'Build a session', 'message': 'I want to build a workout from scratch.'},
                ], 'submit_label': 'Continue', 'message': '',
            }
        return {
            'id': 'training-focus', 'topic': 'training', 'eyebrow': 'Training',
            'title': 'What did you train?',
            'prompt': 'Choose the area and the next card will show exercises to select.',
            'reason': 'Exercise choices are more useful after narrowing the movement.',
            'fields': [], 'choices': [
                {'label': 'Back & biceps', 'message': 'I trained back and biceps today.'},
                {'label': 'Chest & triceps', 'message': 'I trained chest and triceps today.'},
                {'label': 'Shoulders', 'message': 'I trained shoulders today.'},
                {'label': 'Legs', 'message': 'I trained legs today.'},
                {'label': 'Core', 'message': 'I trained core today.'},
            ], 'submit_label': 'Continue', 'message': '',
        }

    if any(word in text for word in ('breakfast', 'lunch', 'dinner', 'meal', 'food', 'calorie')):
        return {
            'id': 'meal-entry', 'topic': 'food', 'eyebrow': 'Nutrition',
            'title': 'Add a meal', 'prompt': 'Name the meal and what you had.',
            'reason': 'A rough amount is enough to get a useful first draft.',
            'fields': [
                {'id': 'meal', 'label': 'Meal', 'type': 'select',
                 'options': ['Breakfast', 'Lunch', 'Dinner', 'Snack']},
                {'id': 'details', 'label': 'What and how much?', 'type': 'text',
                 'placeholder': 'e.g. chicken rice, about 250 g'},
            ], 'submit_label': 'Log meal', 'message': 'For {meal}, I had {details}.',
        }

    if any(word in text for word in ('sleep', 'bed', 'wake', 'tired')):
        return {
            'id': 'sleep-entry', 'topic': 'sleep', 'eyebrow': 'Recovery',
            'title': 'Add sleep', 'prompt': 'Use the time you went to bed and woke up.',
            'reason': 'Clock times calculate the duration without a second question.',
            'fields': [
                {'id': 'bedtime', 'label': 'Bedtime', 'type': 'time'},
                {'id': 'wake_time', 'label': 'Wake time', 'type': 'time'},
            ], 'submit_label': 'Log sleep', 'message': 'I slept from {bedtime} to {wake_time}.',
        }

    if any(word in text for word in ('water', 'steps', 'mood', 'walk')):
        return {
            'id': 'lifestyle-entry', 'topic': 'lifestyle', 'eyebrow': 'Lifestyle',
            'title': 'Daily signals', 'prompt': 'Fill in only the parts you know.',
            'reason': 'These small signals make the daily record more complete.',
            'fields': [
                {'id': 'water', 'label': 'Water (ml)', 'type': 'number', 'placeholder': '2000'},
                {'id': 'steps', 'label': 'Steps', 'type': 'number', 'placeholder': '7000'},
                {'id': 'mood', 'label': 'Mood (1–5)', 'type': 'number', 'placeholder': '4'},
            ], 'submit_label': 'Log lifestyle',
            'message': 'Today I had {water} ml of water, took {steps} steps, and my mood was {mood} out of 5.',
        }

    if any(word in text for word in ('study', 'learn', 'reading', 'course')):
        return {
            'id': 'study-entry', 'topic': 'study', 'eyebrow': 'Learning',
            'title': 'Log learning', 'prompt': 'A topic and duration is all that is needed.',
            'reason': 'Short, real sessions are more useful than a guessed total.',
            'fields': [
                {'id': 'topic', 'label': 'What did you learn?', 'type': 'text', 'placeholder': 'TypeScript course'},
                {'id': 'minutes', 'label': 'Minutes', 'type': 'number', 'placeholder': '45'},
            ], 'submit_label': 'Log session', 'message': 'I studied {topic} for {minutes} minutes.',
        }
    return None


def input_card(conn, user_id, kind, subject_date, message, prior, queued=()):
    if kind == 'today':
        return next_input_card(checkin_plan(conn, user_id, subject_date), queued)
    if queued:
        return None
    return general_input_card(conn, user_id, message, prior)


def checkin_plan(conn, user_id, subject_date):
    """Imported lazily to keep this presentation module independent of Flask."""
    from . import checkin
    return checkin.plan(conn, user_id, subject_date)
