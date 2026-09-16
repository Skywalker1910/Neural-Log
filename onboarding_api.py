"""Onboarding: the first-run flow that gives the scoring engine something to
measure against.

Its own blueprint for the same reasons the others are: app.py is long enough, and
the auth, database and recompute helpers are injected at registration so this
module never imports app back.

## Why this phase exists

Every earlier phase assumed the numbers it scores against already existed. They
did not. `user_profile` is created lazily by whichever page first needs it, so an
account could reach Analytics with no height, no birth year and no targets - and
the engine would honestly report nearly everything as unobserved, which reads as
"this app is broken" rather than "you have not told it anything yet".

## What onboarding is allowed to set

Body metrics produce baselines (BMI, BMR, TDEE); baselines produce targets;
targets are denominators the engine already measures behaviour against. So
answering the questionnaire genuinely changes what your first logged day scores.

It does **not** write attribute scores. "I train four times a week" is a claim,
and the engine has a settled position on claims - self-report is capped at half
the range, and an attribute reports `calibrating` until three days of real
history exist. Seeding Strength at signup would walk past both rules and hand
someone a character sheet they had not earned.

## Non-blocking, and permanently dismissible

Nobody is redirected into this. New accounts land on Home like everyone else and
see a banner; declining is recorded and the banner does not come back, because a
prompt that reappears after being declined is not a prompt. The flow stays at its
own route, reachable from Profile.

The cost of that choice is that a skipped profile means estimated targets rather
than chosen ones - which is exactly what `resolve_targets` already reports
through its `sources` map, so the UI can keep saying "2,480 kcal (estimated)".
"""
from datetime import date as _date

from flask import Blueprint, jsonify, request, session

from scoring import nutrition as nut

onboarding_bp = Blueprint('onboarding', __name__)

_get_db = None
_login_required = None
_recompute = None


def init_onboarding(app, get_db_connection, login_required, recompute):
    global _get_db, _login_required, _recompute
    _get_db = get_db_connection
    _login_required = login_required
    _recompute = recompute
    app.register_blueprint(onboarding_bp)


def _auth(view):
    def wrapper(*args, **kwargs):
        return _login_required(view)(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


# --- the steps --------------------------------------------------------------

# Declared here rather than in the React component so the API and the UI cannot
# disagree about how many steps there are or what each one writes. The client
# renders these; it does not define them.
#
# `fields` are user_profile columns. The two exceptions are called out on their
# own steps: weight is a body measurement (it changes weekly; the profile is for
# things that do not), and the Path lives on `users` because it predates this
# table by the whole project.
STEPS = [
    {
        'key': 'profile',
        'title': 'About you',
        'blurb': 'Only what the energy estimate actually needs.',
        'fields': ['birth_year', 'sex', 'height_cm'],
    },
    {
        'key': 'activity',
        'title': 'How active are you?',
        'blurb': 'Activity scales your energy estimate; training frequency sets what a '
                 'full week of volume means for you.',
        'fields': ['activity_level', 'training_days_per_week'],
    },
    {
        'key': 'body_goal',
        'title': 'What are you working towards?',
        'blurb': 'Sets your calorie and protein targets.',
        'fields': ['goal'],
        'extra': ['weight_kg'],
    },
    {
        'key': 'sleep',
        'title': 'Sleep',
        'blurb': 'Duration is scored. The schedule is yours to aim at.',
        'fields': ['sleep_target_minutes', 'target_bedtime', 'target_wake_time'],
    },
    {
        'key': 'learning',
        'title': 'Learning',
        'blurb': 'A weekly study target, which Knowledge is measured against.',
        'fields': ['weekly_study_minutes'],
    },
    {
        'key': 'path',
        'title': 'Choose your Path',
        'blurb': 'The daily checklist you will run through each evening.',
        'fields': [],
        'extra': ['selected_path'],
    },
    {
        'key': 'baselines',
        'title': 'Your starting point',
        'blurb': 'Computed from what you just entered. Nothing here is a score.',
        'fields': [],
    },
]

PROFILE_FIELDS = [field for step in STEPS for field in step['fields']]

# Values the client is allowed to send for the closed sets. Anything else is
# rejected rather than stored: an unrecognised activity_level silently falls back
# to 'moderate' inside resolve_targets, so a typo would quietly become a 1.55
# multiplier on someone's calorie target with nothing to show it happened.
ALLOWED = {
    'sex': {'male', 'female', 'unspecified'},
    'activity_level': set(nut.ACTIVITY_MULTIPLIERS),
    'goal': set(nut.GOAL_MULTIPLIERS),
}

# Sanity ranges. These reject impossible input rather than plausible-but-wrong
# input - the point is to stop a typo becoming a permanent baseline, not to argue
# with someone about their own body.
RANGES = {
    'birth_year': (1900, _date.today().year),
    'height_cm': (60, 260),
    'weight_kg': (20, 400),
    'sleep_target_minutes': (180, 840),
    'training_days_per_week': (0, 7),
    'weekly_study_minutes': (0, 10080),
}


def _validate(payload):
    """(cleaned, errors). Unknown keys are ignored rather than rejected."""
    cleaned, errors = {}, {}

    for key, value in payload.items():
        if key not in PROFILE_FIELDS and key not in ('weight_kg', 'selected_path'):
            continue
        if value is None or value == '':
            cleaned[key] = None
            continue

        if key in ALLOWED:
            if str(value) not in ALLOWED[key]:
                errors[key] = f'must be one of: {", ".join(sorted(ALLOWED[key]))}'
                continue
            cleaned[key] = str(value)
            continue

        if key in RANGES:
            low, high = RANGES[key]
            try:
                number = float(value)
            except (TypeError, ValueError):
                errors[key] = 'must be a number'
                continue
            if not low <= number <= high:
                errors[key] = f'must be between {low} and {high}'
                continue
            cleaned[key] = number if key in ('height_cm', 'weight_kg') else int(number)
            continue

        if key in ('target_bedtime', 'target_wake_time'):
            text = str(value).strip()
            if len(text) != 5 or text[2] != ':' or not text.replace(':', '').isdigit():
                errors[key] = 'must be HH:MM'
                continue
            hours, minutes = int(text[:2]), int(text[3:])
            if not (0 <= hours < 24 and 0 <= minutes < 60):
                errors[key] = 'must be a real time'
                continue
            cleaned[key] = text
            continue

        cleaned[key] = value

    return cleaned, errors


# --- reading state ----------------------------------------------------------

def _latest_weight(conn, user_id):
    row = conn.execute(
        "SELECT value FROM body_measurements WHERE user_id = ? AND metric = 'weight' "
        'ORDER BY date DESC LIMIT 1', (user_id,)
    ).fetchone()
    return row['value'] if row else None


def _profile_row(conn, user_id):
    row = conn.execute('SELECT * FROM user_profile WHERE user_id = ?', (user_id,)).fetchone()
    return dict(row) if row else {}


def _state(conn, user_id):
    """Everything the flow and the banner need, in one response."""
    profile = _profile_row(conn, user_id)
    user = conn.execute('SELECT selected_path FROM users WHERE id = ?', (user_id,)).fetchone()
    weight = _latest_weight(conn, user_id)

    answers = {field: profile.get(field) for field in PROFILE_FIELDS}
    answers['weight_kg'] = weight
    answers['selected_path'] = user['selected_path'] if user else None

    targets = nut.resolve_targets(profile, weight, _date.today())

    return {
        'steps': [
            {k: step[k] for k in ('key', 'title', 'blurb', 'fields') if k in step}
            for step in STEPS
        ],
        'step': profile.get('onboarding_step') or 0,
        'completed': bool(profile.get('onboarded_at')),
        'completed_at': profile.get('onboarded_at'),
        'dismissed': bool(profile.get('onboarding_dismissed_at')),
        # The banner shows when the flow is neither finished nor waved away. Kept
        # server-side so every client agrees, rather than each one re-deriving it.
        'should_prompt': not profile.get('onboarded_at')
                         and not profile.get('onboarding_dismissed_at'),
        'answers': answers,
        'baselines': _baselines(profile, weight, targets),
        'targets': targets,
    }


def _baselines(profile, weight, targets):
    """BMI, BMR and TDEE - each None rather than guessed when an input is missing.

    `missing` names what is still needed, so the last step can say "add your
    height and this fills in" instead of showing three dashes and no reason.
    """
    height = profile.get('height_cm')
    age = nut.age_from_birth_year(profile.get('birth_year'), _date.today())

    missing = []
    if not height:
        missing.append('height')
    if not weight:
        missing.append('weight')
    if not age:
        missing.append('birth year')

    return {
        'bmi': nut.bmi(weight, height),
        'bmr': targets['estimated_bmr'],
        'tdee': targets['estimated_tdee'],
        'age': age,
        'weight_kg': weight,
        'height_cm': height,
        'missing': missing,
    }


# --- endpoints --------------------------------------------------------------

@onboarding_bp.route('/api/onboarding')
@_auth
def get_onboarding():
    conn = _get_db()
    try:
        return jsonify(_state(conn, session.get('user_id')))
    finally:
        conn.close()


@onboarding_bp.route('/api/onboarding', methods=['PUT'])
@_auth
def save_onboarding():
    """Save one step's answers, and optionally advance or finish.

    Partial by design: each step PUTs only its own fields, so closing the tab
    half way through costs the step you were on and nothing before it.
    """
    user_id = session.get('user_id')
    data = request.json or {}

    cleaned, errors = _validate(data.get('answers') or {})
    if errors:
        return jsonify({'error': 'Some answers could not be saved', 'fields': errors}), 400

    conn = _get_db()
    try:
        weight = cleaned.pop('weight_kg', None)
        path = cleaned.pop('selected_path', None)

        if cleaned:
            _upsert_profile(conn, user_id, cleaned)

        if weight is not None:
            # Today's date, and ON CONFLICT, so repeatedly correcting a typo in
            # the same session leaves one row rather than a fake weigh-in streak.
            conn.execute(
                'INSERT INTO body_measurements (user_id, date, metric, value, unit) '
                "VALUES (?, ?, 'weight', ?, 'kg') "
                'ON CONFLICT(user_id, date, metric) DO UPDATE SET value = excluded.value',
                (user_id, _date.today().isoformat(), weight),
            )

        if path:
            conn.execute('UPDATE users SET selected_path = ? WHERE id = ?', (path, user_id))

        updates = {}
        if 'step' in data:
            updates['onboarding_step'] = max(0, min(int(data['step']), len(STEPS) - 1))
        if data.get('complete'):
            updates['onboarded_at'] = 'CURRENT_TIMESTAMP'
        if updates:
            _upsert_profile(conn, user_id, updates, raw={'onboarded_at'})

        conn.commit()

        # Targets are denominators the engine scores against, so changing them
        # re-judges history. No date argument: a new calorie target changes what
        # every past day was aiming at, not just today's.
        if cleaned or weight is not None:
            _recompute(conn, user_id)
            conn.commit()

        return jsonify(_state(conn, user_id))
    finally:
        conn.close()


@onboarding_bp.route('/api/onboarding/dismiss', methods=['POST'])
@_auth
def dismiss_onboarding():
    """Record "not now". Permanent - see the module docstring."""
    user_id = session.get('user_id')
    conn = _get_db()
    try:
        _upsert_profile(conn, user_id,
                        {'onboarding_dismissed_at': 'CURRENT_TIMESTAMP'},
                        raw={'onboarding_dismissed_at'})
        conn.commit()
        return jsonify(_state(conn, user_id))
    finally:
        conn.close()


@onboarding_bp.route('/api/onboarding/reopen', methods=['POST'])
@_auth
def reopen_onboarding():
    """Clear the dismissal so Profile's "finish setup" works after a decline."""
    user_id = session.get('user_id')
    conn = _get_db()
    try:
        _upsert_profile(conn, user_id, {'onboarding_dismissed_at': None})
        conn.commit()
        return jsonify(_state(conn, user_id))
    finally:
        conn.close()


def _upsert_profile(conn, user_id, values, raw=frozenset()):
    """Write columns into user_profile, creating the row if it does not exist.

    `raw` names keys whose value is a SQL expression (CURRENT_TIMESTAMP) rather
    than a parameter. Everything else is bound.

    activity_level and goal are NOT NULL with schema defaults, so an INSERT that
    omits them - which every step except the second and third does - has to
    supply them explicitly on the create path.
    """
    columns = list(values)
    placeholders = [values[c] if c in raw else '?' for c in columns]
    params = [values[c] for c in columns if c not in raw]

    defaults = {'activity_level': "'moderate'", 'goal': "'maintain'"}
    insert_columns = list(columns)
    insert_values = list(placeholders)
    for column, default in defaults.items():
        if column not in insert_columns:
            insert_columns.append(column)
            insert_values.append(default)

    assignments = ', '.join(
        f'{c} = {values[c] if c in raw else "?"}' for c in columns
    )
    update_params = [values[c] for c in columns if c not in raw]

    conn.execute(
        f'INSERT INTO user_profile (user_id, {", ".join(insert_columns)}) '
        f'VALUES (?, {", ".join(insert_values)}) '
        f'ON CONFLICT(user_id) DO UPDATE SET {assignments}, '
        'updated_at = CURRENT_TIMESTAMP',
        (user_id, *params, *update_params),
    )
