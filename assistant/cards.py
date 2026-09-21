"""Small, deterministic input cards for the guided daily check-in.

The assistant still decides what it understands and can only queue a proposal.
Cards are a faster way to express the routine answers a model would otherwise
have to ask for one sentence at a time.  They deliberately produce plain
language messages, so they travel through the same validated tool path as a
typed answer.
"""


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
            'prompt': 'A meal and a rough amount are enough. You can correct it before saving.',
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
