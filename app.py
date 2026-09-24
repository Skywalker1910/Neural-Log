from flask import (
    Flask, abort, render_template, request, jsonify, send_file, send_from_directory,
    session, redirect, url_for
)
from datetime import datetime, timedelta, timezone
import sqlite3
import json
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
import os
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv

import scoring
import habits
import security
import xp
import xp_config
import achievements

load_dotenv()

app = Flask(__name__)

# Secret key, session cookie flags, CSRF, and the JSON error shape - see
# security.py, which holds the whole pre-deploy list in one readable place rather
# than scattering it through this file.
security.init_security(app)

DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'

# Database configuration
DATABASE = os.environ.get('DATABASE', 'neural_log.db')

# Resolved from this file rather than the cwd: the test suite chdirs into a tmp
# directory (tests/conftest.py), and the app is often started from elsewhere.
PROJECT_ROOT = Path(__file__).resolve().parent
MIGRATIONS_DIR = PROJECT_ROOT / 'migrations'


def _read_version():
    """The release this build is, from the VERSION file beside this one.

    Read rather than hard-coded so a release is one file to edit, and reported
    over HTTP because the deploy pipeline ships images tagged by commit SHA -
    without this there is no way to ask a running instance what it is, which is
    the first question when something looks wrong.

    Missing file means somebody is running from a checkout that predates it, or
    a build that excluded it; 'unknown' is the honest answer and not a reason to
    fail to start.
    """
    try:
        return (PROJECT_ROOT / 'VERSION').read_text(encoding='utf-8').strip() or 'unknown'
    except OSError:
        return 'unknown'


__version__ = _read_version()

#: The commit this build came from, baked into the image by CI. 'unknown' for a
#: checkout being run directly, which is honest - a developer's working tree is
#: not any particular commit.
__commit__ = (os.environ.get('NEURAL_LOG_COMMIT') or 'unknown').strip()
FRONTEND_DIST = PROJECT_ROOT / 'frontend' / 'dist'

ICON_KEYS = {
    'sun', 'coffee', 'workout', 'code', 'chess', 'breakfast', 'lunch', 'water',
    'sleep', 'default'
}

def get_checklist_file_path(username):
    """Get per-user checklist JSONL file path"""
    safe_username = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in username)
    checklist_dir = Path('artifacts') / 'checklists'
    checklist_dir.mkdir(parents=True, exist_ok=True)
    return checklist_dir / f'{safe_username}.jsonl'

def get_user_paths_file_path(username):
    """Get per-user path-system JSON file path"""
    safe_username = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in username)
    path_dir = Path('artifacts') / 'paths'
    path_dir.mkdir(parents=True, exist_ok=True)
    return path_dir / f'{safe_username}.json'

def _resolve_user_id(conn, username):
    row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    return row['id'] if row else None


def load_user_paths(user_row, conn=None):
    """The user's paths, in the shape every caller has always received.

    Storage moved into SQL in R6; the payload did not change, which is what keeps
    the Jinja app, static/js/app.js and the SPA's Today page working untouched.

    Since migration 011 there is exactly one path in it, synthesised from the
    shared daily survey plus that person's own questions. Four hero Paths became
    one survey because choosing a Path quietly chose your *scores* - the
    opportunity denominator comes from the items in it, so an Ironman never had a
    Stamina denominator and a Thor never had a Knowledge one, while the
    leaderboard ranked them against each other regardless.

    The shape survives rather than the concept: three clients read
    `{paths: [...], selected_path_id}` and only ever used it to find the list of
    questions.

    `conn` is threaded through by callers that already hold one open. Opening a
    second connection while a caller has uncommitted writes - score_checklist_day
    does exactly that - would block on SQLite's write lock.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = get_db_connection()

    try:
        user_id = _resolve_user_id(conn, user_row['username'])
        if user_id is None:
            return {'paths': [], 'selected_path_id': None}

        # No seeding any more. The shared survey exists in the database from
        # migration 011 onward, so every account has questions the moment it is
        # created - there is nothing per-user left to lazily import.
        payload = habits.load_paths(conn, user_id)
        return payload or {'paths': [], 'selected_path_id': None}
    finally:
        if owns_connection:
            conn.close()


def get_selected_path(paths_payload):
    """Get selected path object from path payload"""
    for path in paths_payload.get('paths', []):
        if path['id'] == paths_payload.get('selected_path_id'):
            return path
    return paths_payload.get('paths', [None])[0]

def save_checklist_to_file(user_id, username, activity_id, payload):
    """Append a daily checklist entry to user's JSONL file"""
    file_path = get_checklist_file_path(username)
    entry = {
        'user_id': user_id,
        'username': username,
        'activity_id': activity_id,
        'saved_at': datetime.now().isoformat(),
        'checklist': payload
    }

    with file_path.open('a', encoding='utf-8') as file:
        file.write(json.dumps(entry, ensure_ascii=False) + '\n')

def get_db_connection():
    """Create a database connection.

    Two pragmas, both of which only start mattering once more than one process
    is serving requests - which is exactly what gunicorn does and the Werkzeug
    dev server never did.

    **WAL** lets readers and writers work at the same time. In the default
    journal mode a single write locks the whole database, so one person saving a
    workout blocks everyone else's dashboard for the duration. It is a property
    of the database file rather than the connection, so setting it here is
    idempotent - the first connection switches it and the rest confirm it.

    **busy_timeout** decides what happens when a lock is hit anyway: wait five
    seconds, or fail instantly with "database is locked". Without it, two
    concurrent writes are a 500 rather than a short pause.
    """
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=5000')
    return conn

def run_migrations(conn):
    """Apply any migrations/NNN_*.sql files this database hasn't seen yet.

    Deliberately tiny - numbered SQL files plus a schema_migrations ledger. No
    ORM or migration framework, which keeps the raw-sqlite3 approach intact and
    ports cleanly to Postgres/RDS later. Each file is applied once, in filename
    order, and recorded; re-running is a no-op.
    """
    conn.execute('''
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    applied = {row[0] for row in conn.execute('SELECT version FROM schema_migrations')}

    for migration_path in sorted(MIGRATIONS_DIR.glob('*.sql')):
        version = migration_path.stem
        if version in applied:
            continue

        conn.executescript(migration_path.read_text(encoding='utf-8'))
        conn.execute('INSERT INTO schema_migrations (version) VALUES (?)', (version,))
        conn.commit()
        app.logger.info('Applied migration %s', version)


def init_db():
    """Bring the database up to date, then backfill columns legacy DBs may lack."""
    conn = get_db_connection()
    run_migrations(conn)

    # Pre-dates the migration system: databases created before the Paths feature
    # are missing these columns. SQLite has no ADD COLUMN IF NOT EXISTS, so this
    # stays a conditional Python step rather than becoming a migration file.
    cursor = conn.cursor()
    columns = [row[1] for row in cursor.execute('PRAGMA table_info(users)').fetchall()]
    if 'selected_path' not in columns:
        # No default. Paths were retired in 011 and nothing reads this column
        # any more; a default of 'Batman Path' would keep asserting a concept
        # the app no longer has. Kept rather than dropped because dropping it
        # means another table rebuild for nothing.
        cursor.execute('ALTER TABLE users ADD COLUMN selected_path TEXT')
    if 'custom_path_items' not in columns:
        cursor.execute('ALTER TABLE users ADD COLUMN custom_path_items TEXT')

    conn.commit()

    # The shipped exercise library lives in data/exercises.json rather than in a
    # migration: 85 curated rows are unreviewable as SQL, and every wording fix
    # would otherwise need a new migration file. Syncing here is idempotent and
    # keeps the JSON as the source of truth. See scoring/library.py.
    try:
        added, updated, archived = scoring.sync_library(conn)
        if added or updated or archived:
            app.logger.info(
                'Exercise library synced: %d added, %d updated, %d archived',
                added, updated, archived,
            )
    except sqlite3.Error:
        # A library that fails to sync is a thin Training page, not a reason to
        # refuse to boot.
        app.logger.exception('Could not sync the exercise library')

    # The achievement catalogue, synced like the exercise and food libraries.
    try:
        added, updated = achievements.sync_catalogue(conn)
        if added or updated:
            app.logger.info('Achievements synced: %d added, %d updated', added, updated)
    except sqlite3.Error:
        app.logger.exception('Could not sync the achievement catalogue')

    # R7 made the ledger the authority for total XP, so historical daily_xp rows
    # have to be represented in it or every day earned before that migration
    # stops counting and everyone's level drops. Idempotent, so it is safe here.
    try:
        seeded = xp.backfill_from_daily_xp(conn)
        if seeded:
            app.logger.info('XP ledger backfilled: %d historical days', seeded)
    except sqlite3.Error:
        app.logger.exception('Could not backfill the XP ledger')

    # Same arrangement for the food library (data/foods.json, 233 rows).
    try:
        added, updated, archived = scoring.sync_foods(conn)
        if added or updated or archived:
            app.logger.info(
                'Food library synced: %d added, %d updated, %d archived',
                added, updated, archived,
            )
    except sqlite3.Error:
        app.logger.exception('Could not sync the food library')

    conn.close()


# ---------------------------------------------------------------------------
# Gamification: XP, levels, streak multiplier, badges
# ---------------------------------------------------------------------------

XP_PER_WEIGHT_POINT = 10       # each weight point on a completed item is worth this much XP
STREAK_MULTIPLIER_PCT_PER_DAY = 2   # +2% total XP per consecutive day logged...
STREAK_MULTIPLIER_CAP_PCT = 50      # ...capped at +50% (a 25-day streak)


def calculate_current_streak(conn, user_id, as_of=None):
    """Consecutive-day streak, as of a date (default: today).

    `as_of` exists because XP is rebuilt per day and the multiplier has to be the
    streak that applied ON THAT DAY. Without it, rebuilding history stamps
    today's streak onto every past day - a day earned during a ten-day run would
    silently lose its multiplier, and a day earned with no streak at all would
    gain one.
    """
    streak_rows = conn.execute('''
        SELECT DISTINCT date
        FROM activities
        WHERE user_id = ? AND (? IS NULL OR date <= ?)
        ORDER BY date DESC
    ''', (user_id, as_of, as_of)).fetchall()

    activity_dates = []
    for row in streak_rows:
        try:
            activity_dates.append(datetime.strptime(row['date'], '%Y-%m-%d').date())
        except (ValueError, TypeError):
            continue

    if not activity_dates:
        return 0

    today = (datetime.strptime(as_of, '%Y-%m-%d').date() if as_of
             else datetime.now().date())
    latest_date = activity_dates[0]

    if latest_date < (today - timedelta(days=1)):
        return 0

    streak = 1
    previous_date = latest_date
    for activity_date in activity_dates[1:]:
        day_gap = (previous_date - activity_date).days
        if day_gap == 0:
            continue
        if day_gap == 1:
            streak += 1
            previous_date = activity_date
            continue
        break

    return streak


def _item_is_completed(item, response_value):
    """Whether a single checklist item counts as 'done' for XP purposes."""
    if response_value is None:
        return False
    value = str(response_value).strip()
    if not value:
        return False
    if item.get('type') == 'yes-no':
        return value.lower().startswith('yes')
    return True  # time / text / other answered types


def calculate_daily_xp(checklist_items, custom_responses):
    """Base XP for one day's checklist, before the streak multiplier.

    Rating-type items are self-reflection, not a completed task, and are
    excluded from scoring entirely.
    """
    base_xp = 0
    for item in checklist_items or []:
        if item.get('type') == 'rating':
            continue
        response_value = (custom_responses or {}).get(item.get('name'))
        if _item_is_completed(item, response_value):
            base_xp += int(item.get('weight', 1) or 0) * XP_PER_WEIGHT_POINT
    return base_xp


def _extract_self_rating(checklist_items, custom_responses):
    """The 1-5 self-rating answer, kept as itself rather than folded into a score.

    Note activities.progress_score is NOT this: the client sends rating*2 there,
    so that column is a doubled self-report and must not be read as a score.
    """
    for item in checklist_items or []:
        if item.get('type') != 'rating':
            continue
        value = (custom_responses or {}).get(item.get('name'))
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None
    return None


def compute_completion_percent(checklist_items, custom_responses):
    """Weight-based completion for one day, computed server-side.

    The client sends its own completion_percent, but it counts *answered*
    items rather than *completed* ones (static/js/app.js), and the wizard
    refuses to advance without an answer - so it reports 100 even for a day
    answered entirely "No". Scoring and badges must not trust it.

    Rating items are excluded, matching calculate_daily_xp.
    """
    total_weight = 0
    completed_weight = 0
    for item in checklist_items or []:
        if item.get('type') == 'rating':
            continue
        weight = int(item.get('weight', 1) or 0)
        total_weight += weight
        response_value = (custom_responses or {}).get(item.get('name'))
        if _item_is_completed(item, response_value):
            completed_weight += weight
    if total_weight <= 0:
        return 0
    return round(completed_weight * 100 / total_weight)


# The level curve moved into xp.py in R7 so it could be made configurable
# (xp_config.LEVEL_CURVE_*). These stay as thin aliases because a dozen call
# sites and the tests use them, and the defaults reproduce the original
# 50 * (level - 1) ** 2 exactly - nobody's level changed when this shipped.
xp_for_level = xp.xp_for_level
compute_level = xp.compute_level


def get_user_total_xp(conn, user_id):
    """Total XP, summed from the ledger rather than from daily_xp.

    daily_xp is still maintained as a rollup for the leaderboard, but the ledger
    is the authority: it is the only one that knows about achievement awards,
    which are not part of any day's rebuild.
    """
    return xp.total_xp(conn, user_id)


def award_daily_xp(conn, user_id, date, checklist_items, custom_responses, completion_percent=0):
    """Score one day's checklist submission, upsert daily_xp, evaluate badges.

    Returns the list of newly-earned badge definitions (empty if none).
    Safe to call more than once for the same (user_id, date) - it recomputes
    and replaces rather than accumulating, so editing today's log doesn't
    double-count XP.
    """
    base_xp = calculate_daily_xp(checklist_items, custom_responses)
    # As of the day being scored, not today: editing last Tuesday should use last
    # Tuesday's streak, not the one you happen to be on now.
    streak = calculate_current_streak(conn, user_id, as_of=date)

    # R7: the whole day is rebuilt through the ledger rather than daily_xp being
    # written directly. The checklist is now one source among several - training,
    # learning, nutrition and lifestyle all earn too - and the caps that stop XP
    # being farmed can only be applied correctly across a whole day at once.
    # daily_xp is still written, as a rollup, because the leaderboard reads it.
    xp.recompute_day(
        conn, user_id, date,
        checklist_base_xp=base_xp,
        targets=_xp_targets(conn, user_id, date),
        streak=streak,
    )
    conn.commit()

    return evaluate_badges(conn, user_id, completion_percent_today=completion_percent)


def _xp_targets(conn, user_id, on_date):
    """The day's targets, for the XP rules that check whether one was met.

    Reuses the nutrition resolver so "hit your calorie target" means exactly the
    same thing to XP as it does to the adherence signal - two definitions of one
    target would eventually disagree.
    """
    try:
        row = conn.execute('SELECT * FROM user_profile WHERE user_id = ?',
                           (user_id,)).fetchone()
        profile = dict(row) if row else {}

        weight_row = conn.execute(
            "SELECT value FROM body_measurements WHERE user_id = ? AND metric = 'weight' "
            'AND date <= ? ORDER BY date DESC LIMIT 1', (user_id, on_date),
        ).fetchone()
        weight = weight_row['value'] if weight_row else None

        return scoring.nutrition.resolve_targets(
            profile, weight, datetime.strptime(on_date, '%Y-%m-%d').date())
    except (sqlite3.Error, ValueError):
        # Targets are a bonus condition, not a prerequisite. A user with no
        # profile still earns the base XP for logging.
        return {}


def recompute_xp_day(conn, user_id, date):
    """Rebuild one day's XP after a non-checklist action.

    Called by the workspace blueprints: logging a workout or a study session has
    to move XP, and until R7 nothing outside the checklist did.
    """
    streak = calculate_current_streak(conn, user_id, as_of=date)
    return xp.recompute_day(
        conn, user_id, date,
        targets=_xp_targets(conn, user_id, date),
        streak=streak,
    )


def _dates_with_activity(conn, user_id):
    """Every date this user has anything on. Bounded by what they actually did."""
    dates = set()
    for table in ('daily_log', 'workout_sessions', 'learning_sessions',
                  'food_entries', 'sleep_entries', 'lifestyle_days',
                  'xp_transactions'):
        try:
            for row in conn.execute(
                f'SELECT DISTINCT date FROM {table} WHERE user_id = ?', (user_id,)
            ):
                dates.add(row['date'])
        except sqlite3.Error:
            continue
    return sorted(dates)


def recompute_after_change(conn, user_id, date=None, evaluate_badges_on_change=True):
    """Rebuild everything derived from a day: attribute scores, then XP.

    Injected into the workspace blueprints so logging a workout, a meal or a
    study session moves both. Before R7 they only moved the attribute scores -
    XP came from the checklist alone, so the leaderboard ignored most of what the
    app tracks.

    `date=None` means something changed that affects every day - editing your
    profile moves the targets that "hit your calorie target" is judged against -
    so every date with activity is rebuilt. Rare and bounded by real usage.
    """
    scoring.recompute_scores(conn, user_id, from_date=date)

    if date:
        recompute_xp_day(conn, user_id, date)
    else:
        for day in _dates_with_activity(conn, user_id):
            recompute_xp_day(conn, user_id, day)

    # Achievements are evaluated here too, not only on checklist submission.
    # Before R7 the gamification system listened to the checklist alone, so
    # logging your first workout could not unlock "Rack Pulled" - you had to go
    # and tick a box before the app noticed.
    #
    # After the XP rebuild, deliberately: the level-based achievements test a
    # total that the rebuild has just changed.
    if evaluate_badges_on_change:
        evaluate_badges(conn, user_id)


# The badge catalogue moved to achievements.py in R7, where it is data rather
# than eight dicts carrying check() lambdas - see the note at the top of that
# module on why progress reporting made that necessary.


def evaluate_badges(conn, user_id, completion_percent_today=0):
    """Unlock anything newly earned, and pay its XP into the ledger.

    Returns the newly-earned entries. R7 moved the catalogue into
    achievements.py: the old version held eight dicts each carrying a check()
    lambda, which can decide earned-or-not but cannot say how CLOSE you are - and
    an unlock UI that cannot show progress is just a list of things you lack.
    """
    total_days = conn.execute(
        'SELECT COUNT(DISTINCT date) as count FROM activities WHERE user_id = ?',
        (user_id,)
    ).fetchone()['count']
    current_streak = calculate_current_streak(conn, user_id)
    total = get_user_total_xp(conn, user_id)
    level, _, _ = compute_level(total)

    user_row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    has_custom_path = False
    if user_row:
        paths_payload = load_user_paths(user_row, conn)
        has_custom_path = any(not path.get('is_default', False)
                              for path in paths_payload.get('paths', []))

    ctx = achievements.build_context(
        conn, user_id,
        completion_percent_today=completion_percent_today,
        has_custom_path=has_custom_path,
        total_days=total_days, current_streak=current_streak,
        total_xp=total, level=level,
    )

    newly_earned = achievements.evaluate(conn, user_id, ctx)

    # An unlock is worth XP, and it goes through the ledger like everything else
    # so the total stays auditable. Uncapped and never rebuilt - an achievement
    # is one-off, and a cap would mean unlocking two in a day discarded one.
    awarded_on = datetime.now().date().isoformat()
    for entry in newly_earned:
        xp.award_achievement(conn, user_id, entry['code'], entry['name'],
                             entry.get('xp_reward', 0), day=awarded_on)

    if newly_earned:
        # Refresh that day's rollup. Badge XP is written after the day has
        # already been rebuilt, so without this daily_xp is short by exactly the
        # unlock - and daily_xp is what the leaderboard reads, so it would
        # under-report anyone who had just earned something.
        recompute_xp_day(conn, user_id, awarded_on)
        conn.commit()

    return newly_earned


def achievement_context(conn, user_id):
    """The context used to report progress, outside a checklist submission."""
    total_days = conn.execute(
        'SELECT COUNT(DISTINCT date) as count FROM activities WHERE user_id = ?',
        (user_id,)
    ).fetchone()['count']
    total = get_user_total_xp(conn, user_id)
    level, _, _ = compute_level(total)

    user_row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    has_custom_path = False
    if user_row:
        paths_payload = load_user_paths(user_row, conn)
        has_custom_path = any(not path.get('is_default', False)
                              for path in paths_payload.get('paths', []))

    return achievements.build_context(
        conn, user_id,
        # Not a submission, so today's completion is not in play - a locked
        # "Perfectionist" should show its real distance, not 0 of 100 by accident.
        completion_percent_today=_todays_completion_percent(conn, user_id),
        has_custom_path=has_custom_path,
        total_days=total_days,
        current_streak=calculate_current_streak(conn, user_id),
        total_xp=total, level=level,
    )


def _todays_completion_percent(conn, user_id):
    row = conn.execute(
        'SELECT completion_pct FROM daily_log WHERE user_id = ? ORDER BY date DESC LIMIT 1',
        (user_id,),
    ).fetchone()
    return row['completion_pct'] if row else 0


# Decorator for routes that require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))

        conn = get_db_connection()
        user = conn.execute(
            'SELECT is_admin, is_active FROM users WHERE id = ?',
            (session['user_id'],),
        ).fetchone()
        conn.close()

        if not user or not user['is_active']:
            session.clear()
            return redirect(url_for('login'))

        session['is_admin'] = bool(user['is_admin'])
        return f(*args, **kwargs)
    return decorated_function

# Decorator for routes that require admin access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        user = conn.execute(
            'SELECT is_admin, is_active FROM users WHERE id = ?',
            (session['user_id'],),
        ).fetchone()
        conn.close()

        if not user or not user['is_active']:
            session.clear()
            return redirect(url_for('login'))

        session['is_admin'] = bool(user['is_admin'])
        if not user['is_admin']:
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

def render_login_page():
    """The sign-in page, told how accounts are created here.

    The template needs this to decide whether to show the register tab at all,
    and whether to ask for an invite code. Getting it from the server rather than
    guessing means the form matches what the endpoint will actually accept.
    """
    return render_template(
        'login.html',
        registration_mode=security.registration_mode(),
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if request.method == 'POST':
        data = request.json or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        ip = security.client_ip()

        conn = get_db_connection()

        # Checked before the password is, so a locked-out caller learns nothing
        # about whether the username exists - and so a dictionary run costs the
        # attacker the wait rather than costing us the hashing.
        retry_after = security.login_retry_after(conn, username, ip)
        if retry_after:
            conn.close()
            return security.rate_limit_response(retry_after)

        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user and user['is_active'] and check_password_hash(user['password_hash'], password):
            security.clear_login_failures(conn, username, ip)
            conn.close()

            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            paths_payload = load_user_paths(user)
            selected_path = get_selected_path(paths_payload)

            return jsonify({
                'success': True,
                'username': user['username'],
                'is_admin': bool(user['is_admin']),
                'selected_path': selected_path['name'] if selected_path else 'Batman Path',
                'selected_path_id': paths_payload.get('selected_path_id')
            })

        security.record_login_failure(conn, username, ip)
        conn.close()
        # One message for both "no such user" and "wrong password". Telling them
        # apart is a username oracle, and at 2-5 accounts the usernames are the
        # easy half of the guess.
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
    
    return render_login_page()

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration"""
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        email = data.get('email', '')
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password required'}), 400

        # No path to choose since migration 011. Everyone gets the shared daily
        # survey, and anything they want on top of it they add afterwards.

        conn = get_db_connection()

        # Checked with the database open so DB-backed invite codes can be
        # validated alongside the legacy env-var code.
        allowed, refusal, status = security.check_registration(data, conn)
        if not allowed:
            conn.close()
            return jsonify({'success': False, 'message': refusal}), status
        
        # Check if username already exists
        existing_user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing_user:
            conn.close()
            return jsonify({'success': False, 'message': 'Username already exists'}), 400
        
        # Who gets the admin bit. `ADMIN_USERNAME` names the account outright;
        # without it the old first-user-wins rule stands, which is fine on a
        # laptop and a land-grab on a fresh public database.
        user_count = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
        is_admin = 1 if security.grants_admin(username, user_count) else 0
        
        # Create new user
        password_hash = generate_password_hash(password)
        cursor = conn.cursor()
        # selected_path is written explicitly as NULL. The baseline schema still
        # declares DEFAULT 'Batman Path' and SQLite cannot change a column default
        # without rebuilding the table - so leaving it out would keep stamping
        # every new account with a Path that no longer exists.
        cursor.execute(
            'INSERT INTO users (username, password_hash, email, is_admin, selected_path) '
            'VALUES (?, ?, ?, ?, NULL)',
            (username, password_hash, email, is_admin)
        )
        conn.commit()
        user_id = cursor.lastrowid

        # If a DB-backed invite code was used, mark it redeemed.
        invite_code = (data.get('invite_code') or '').strip()
        if invite_code:
            security.redeem_invite_code(conn, invite_code, user_id)

        conn.close()

        # Log in the new user
        session['user_id'] = user_id
        session['username'] = username
        session['is_admin'] = bool(is_admin)
        
        return jsonify({
            'success': True,
            'username': username,
            'is_admin': bool(is_admin),
        }), 201
    
    return render_login_page()

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Sign out - on POST only, because GET must not change anything.

    This was a GET, which meant any page anywhere could sign you out with an
    invisible `<img src="https://neurallog.../logout">`. That is a nuisance
    rather than a breach, and it is also the plainest possible example of the
    rule CSRF protection exists to enforce: a request the user did not make
    should not change their state.

    GET now renders a confirmation instead of a redirect, so the links in the
    classic app and any old bookmark still lead somewhere sensible rather than
    404ing. The SPA posts directly and never sees it.
    """
    if request.method == 'GET':
        return render_template('logout.html')

    session.clear()

    if request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json':
        return jsonify({'success': True})
    return redirect(url_for('index'))

@app.route('/api/current-user')
@login_required
def current_user():
    """Get current logged in user"""
    conn = get_db_connection()
    user = conn.execute(
        'SELECT username, selected_path, custom_path_items, leaderboard_opt_out '
        'FROM users WHERE id = ?',
        (session.get('user_id'),)
    ).fetchone()
    conn.close()

    paths_payload = load_user_paths(user) if user else {'paths': [], 'selected_path_id': None}
    selected_path = get_selected_path(paths_payload)

    return jsonify({
        'user_id': session.get('user_id'),
        'username': session.get('username'),
        'is_admin': session.get('is_admin', False),
        'selected_path': selected_path['name'] if selected_path else 'Batman Path',
        'selected_path_id': paths_payload.get('selected_path_id'),
        'leaderboard_opt_out': bool(user['leaderboard_opt_out']) if user else False,
    })


@app.route('/api/user/privacy', methods=['PUT'])
@login_required
def update_privacy():
    """Whether this account appears on the leaderboard.

    Its own endpoint rather than a field on the profile update, because that one
    renames the account and rewrites path selections - a toggle should not be
    able to fail because a username is taken.
    """
    data = request.json or {}
    opt_out = 1 if data.get('leaderboard_opt_out') else 0

    conn = get_db_connection()
    conn.execute(
        'UPDATE users SET leaderboard_opt_out = ? WHERE id = ?',
        (opt_out, session.get('user_id'))
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'leaderboard_opt_out': bool(opt_out)})

@app.route('/api/user/profile', methods=['PUT'])
@login_required
def update_user_profile():
    """Update current user's profile settings"""
    user_id = session.get('user_id')
    data = request.json or {}

    new_username = (data.get('username') or '').strip()
    selected_path_id = (data.get('selected_path') or '').strip()

    if not new_username:
        return jsonify({'success': False, 'message': 'Username is required'}), 400

    conn = get_db_connection()
    current_user_row = conn.execute('SELECT username, selected_path, custom_path_items FROM users WHERE id = ?', (user_id,)).fetchone()

    if not current_user_row:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    old_username = current_user_row['username']

    # Ensure username uniqueness (excluding current user)
    existing_user = conn.execute(
        'SELECT id FROM users WHERE username = ? AND id != ?',
        (new_username, user_id)
    ).fetchone()
    if existing_user:
        conn.close()
        return jsonify({'success': False, 'message': 'Username already exists'}), 400

    paths_payload = load_user_paths(current_user_row, conn)
    if selected_path_id and not any(path['id'] == selected_path_id for path in paths_payload['paths']):
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid path selection'}), 400

    if selected_path_id:
        paths_payload['selected_path_id'] = selected_path_id

    selected_path = get_selected_path(paths_payload)
    selected_path_name = selected_path['name'] if selected_path else 'Batman Path'

    conn.execute(
        'UPDATE users SET username = ?, selected_path = ? WHERE id = ?',
        (new_username, selected_path_name, user_id)
    )
    conn.commit()
    conn.close()

    # Keep session in sync with updated username
    session['username'] = new_username

    # Rename checklist artifact file if username changed
    if old_username != new_username:
        old_file = get_checklist_file_path(old_username)
        new_file = get_checklist_file_path(new_username)
        if old_file.exists() and not new_file.exists():
            old_file.rename(new_file)

        old_paths_file = get_user_paths_file_path(old_username)
        new_paths_file = get_user_paths_file_path(new_username)
        if old_paths_file.exists() and not new_paths_file.exists():
            old_paths_file.rename(new_paths_file)

    # Nothing to rewrite. Questions live in SQL keyed by user id, not by name,
    # so a rename no longer touches them.

    return jsonify({
        'success': True,
        'username': new_username,
        'selected_path': selected_path_name,
        'selected_path_id': paths_payload.get('selected_path_id')
    })

@app.route('/api/checklist-items', methods=['GET', 'PUT'])
@login_required
def checklist_items():
    """Get or update current user's checklist item definitions"""
    user_id = session.get('user_id')
    conn = get_db_connection()
    user_row = conn.execute(
        'SELECT username, selected_path, custom_path_items FROM users WHERE id = ?',
        (user_id,)
    ).fetchone()
    conn.close()

    if not user_row:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    paths_payload = load_user_paths(user_row)
    selected_path = get_selected_path(paths_payload)
    if not selected_path:
        return jsonify({'success': False, 'message': 'No paths available'}), 400

    if request.method == 'GET':
        items = selected_path.get('checklist_items', [])
        return jsonify({'success': True, 'items': items})

    # Wholesale rewriting of the question list is retired with Paths. Half of
    # this list is now shared with four other people, and a PUT that silently
    # reshaped everyone's survey is not something a client should be able to do
    # by accident.
    return jsonify(PATHS_RETIRED), 410

# ---------------------------------------------------------------------------
# Paths, retired.
#
# GET survives as a read-only compatibility view - the Jinja app,
# static/js/app.js and the SPA's Today page all read
# `{paths: [...], selected_path_id}`, and all three only ever used it to find the
# list of questions. It now returns exactly one path: the shared daily survey.
#
# The write half is gone. Creating, renaming, deleting and selecting a Path are
# all operations on a concept that no longer exists, and answering them with a
# plausible-looking success would leave a client believing it had changed
# something. 410 with a pointer is the honest reply.
# ---------------------------------------------------------------------------

PATHS_RETIRED = {
    'success': False,
    'message': ('Paths were retired: there is one shared daily survey now. '
                'Add or edit your own questions at /api/survey/questions.'),
}


@app.route('/api/paths', methods=['GET', 'POST'])
@login_required
def paths_collection():
    """The daily survey, in the shape Paths used to have."""
    if request.method == 'POST':
        return jsonify(PATHS_RETIRED), 410

    user_id = session.get('user_id')
    conn = get_db_connection()
    user_row = conn.execute(
        'SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()

    if not user_row:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    paths_payload = load_user_paths(user_row)
    selected_path = get_selected_path(paths_payload)
    return jsonify({
        'success': True,
        'paths': paths_payload.get('paths', []),
        'selected_path_id': paths_payload.get('selected_path_id'),
        'selected_path_name': selected_path['name'] if selected_path else None,
    })


@app.route('/api/paths/selected', methods=['PUT'])
@app.route('/api/paths/<string:path_id>', methods=['PUT', 'DELETE'])
@login_required
def paths_write_retired(path_id=None):
    return jsonify(PATHS_RETIRED), 410



@app.route('/api/user/reset-password', methods=['POST'])
@login_required
def reset_current_user_password():
    """Reset password for currently logged-in user"""
    user_id = session.get('user_id')
    data = request.json or {}

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'success': False, 'message': 'Current and new password are required'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'New password must be at least 6 characters'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,)).fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    if not check_password_hash(user['password_hash'], current_password):
        conn.close()
        return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400

    conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (generate_password_hash(new_password), user_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

# ---------------------------------------------------------------------------
# Routing: the redesigned SPA is the app.
#
# It lived at /app through R2-R7 while the classic Jinja dashboard held /, so the
# two could be compared side by side. That arrangement had one fatal flaw: /login
# redirects to /, so signing in normally never reached the new UI at all - the
# only way to see it was to type the URL. The redesign was invisible to the
# person it was built for.
#
# So / is the SPA, and the classic dashboard keeps its own address at /classic
# until the last few features that only exist there (notably Excel export) are
# ported. /app still resolves, because it is in the browser history of everyone
# who has been testing.
# ---------------------------------------------------------------------------

SPA_NOT_BUILT_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Neural Log - build required</title>
<style>body{background:#000;color:#f5f5f7;font:15px/1.6 -apple-system,system-ui,sans-serif;
padding:3rem;max-width:40rem;margin:0 auto}code{background:#1d1d1f;padding:.15rem .4rem;
border-radius:6px}a{color:#2997ff}</style></head><body>
<h1>The app hasn't been built yet</h1>
<p>Run the dev server for hot reload:</p>
<p><code>cd frontend &amp;&amp; npm run dev</code> then open
<a href="http://localhost:5173/">localhost:5173</a></p>
<p>Or build it once so Flask can serve it from here:</p>
<p><code>cd frontend &amp;&amp; npm run build</code></p>
<p><a href="/classic">Back to the classic dashboard</a></p>
</body></html>"""

# Prefixes Flask owns. Werkzeug already prefers a specific rule over the
# catch-all, so this only matters for *unknown* paths beneath them: without it
# GET /api/typo would hand back the SPA shell with a 200, and a fetch() would
# fail somewhere far away trying to parse HTML as JSON.
SERVER_PREFIXES = ('api/', 'static/', 'assets/', 'login', 'logout', 'register',
                   'admin', 'classic', 'healthz')


@app.route('/healthz')
def healthz():
    """Is this container actually serving, or merely running?

    Deliberately touches the database. A process that has booted but cannot read
    its own data is not healthy, and a health check that only proves Python
    started would let Docker keep routing traffic to it. Unauthenticated,
    because a check that needs a session is a check that cannot run.
    """
    try:
        conn = get_db_connection()
        conn.execute('SELECT 1 FROM schema_migrations LIMIT 1').fetchone()
        conn.close()
    except Exception:
        app.logger.exception('Health check could not reach the database')
        return jsonify({'status': 'unhealthy'}), 503

    return jsonify({
        'status': 'ok',
        'version': __version__,
        # The deploy asserts this matches the commit it just pushed. Without it,
        # a health check passes on whatever happens to be running - which is how
        # a silent rollback stays silent.
        'commit': __commit__,
    })


@app.route('/assets/<path:filename>')
def spa_assets(filename):
    """Hashed JS/CSS/font bundles. No auth: they hold no user data, and gating
    them would break the shell whenever a session expires mid-session."""
    return send_from_directory(FRONTEND_DIST / 'assets', filename)


def serve_spa_shell():
    if not (FRONTEND_DIST / 'index.html').exists():
        return SPA_NOT_BUILT_HTML, 200
    return send_from_directory(FRONTEND_DIST, 'index.html')


@app.route('/', strict_slashes=False)
@app.route('/<path:_subpath>')
def index(_subpath=''):
    """Serve the SPA shell; client-side routing handles every path below it.

    Not decorated with @login_required, because the 404 has to be decided before
    the auth check: otherwise a typo in an API path would answer 302-to-login
    rather than 404, and a fetch() would follow it and try to parse the sign-in
    page as JSON.
    """
    if _subpath.startswith(SERVER_PREFIXES):
        abort(404)
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return serve_spa_shell()


@app.route('/app', strict_slashes=False)
@app.route('/app/<path:subpath>')
def spa_legacy_redirect(subpath=''):
    """/app was the SPA's address until the cutover. Keep the bookmarks working."""
    return redirect('/' + subpath)


@app.route('/classic')
@login_required
def classic():
    """The original Jinja dashboard, kept for Excel export and legacy insights."""
    return render_template('index.html')


def score_checklist_day(conn, user_id, date, checklist_payload, activity_id=None):
    """Score one logged day: XP, badges, the daily log, and the attribute series.

    Shared by the legacy wizard's POST /api/activities and the SPA's
    PUT /api/days/<date>, because a day logged from one must score exactly the
    same as the same day logged from the other.

    Returns (newly_earned_badges, completion_percent).
    """
    user_row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user_row:
        return [], 0

    paths_payload = load_user_paths(user_row, conn)
    path_id = checklist_payload.get('selected_path_id')
    used_path = (
        next((p for p in paths_payload['paths'] if p['id'] == path_id), None)
        or get_selected_path(paths_payload)
        or {}
    )
    checklist_items = used_path.get('checklist_items', [])
    custom_responses = checklist_payload.get('custom_responses', {}) or {}

    # Deliberately ignores any completion_percent in the payload: the legacy
    # client reports answered/total, which is ~always 100 because the wizard
    # forces an answer to every step. Badges keyed off completion (perfect-day)
    # need completed/total, weighted, computed here.
    completion_percent = compute_completion_percent(checklist_items, custom_responses)

    newly_earned = award_daily_xp(
        conn, user_id, date, checklist_items, custom_responses,
        completion_percent=completion_percent,
    )

    # Snapshot the day and rebuild the derived series. Runs after award_daily_xp
    # because that commits internally, so the XP row is already durable; a
    # failure here costs the attribute scores, not the submission.
    scored = scoring.record_day(
        conn, user_id, date, checklist_items, custom_responses,
        path_id=used_path.get('id'),
        path_name=used_path.get('name'),
        activity_id=activity_id,
        self_rating=_extract_self_rating(checklist_items, custom_responses),
        notes=(checklist_payload.get('notes') or None),
    )

    # The same answers, also written per-habit. record_day's payload snapshot
    # stays the authority for scoring; this is the queryable index that makes
    # per-habit streaks and adherence possible at all. Written in the same
    # transaction so the two cannot disagree.
    habits.record_completions(conn, user_id, date, scored.get('items', []))
    conn.commit()
    # Only from this date forward: earlier days are unaffected by a later
    # submission, and recomputing them would be wasted work.
    scoring.recompute_scores(conn, user_id, from_date=date)
    conn.commit()

    badges = [
        {'code': b['code'], 'name': b['name'], 'description': b['description']}
        for b in newly_earned
    ]
    return badges, completion_percent


@app.route('/api/activities', methods=['GET', 'POST'])
@login_required
def activities():
    """Handle GET and POST requests for activities"""
    user_id = session.get('user_id')
    conn = get_db_connection()
    
    if request.method == 'POST':
        data = request.json
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO activities (user_id, date, activity_name, description, duration, progress_score, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            data['date'],
            data['activity_name'],
            data.get('description', ''),
            data.get('duration', 0),
            data.get('progress_score', 0),
            data.get('notes', '')
        ))
        conn.commit()
        activity_id = cursor.lastrowid

        newly_earned_badges = []
        if data.get('activity_name') == 'Daily Checklist':
            checklist_payload = data.get('checklist_data') if isinstance(data.get('checklist_data'), dict) else {
                'date': data.get('date'),
                'description': data.get('description', ''),
                'notes': data.get('notes', ''),
                'progress_score': data.get('progress_score', 0)
            }
            save_checklist_to_file(user_id, session.get('username', f'user_{user_id}'), activity_id, checklist_payload)

            newly_earned_badges, _ = score_checklist_day(
                conn, user_id, data.get('date'), checklist_payload, activity_id
            )

        conn.close()
        return jsonify({'success': True, 'id': activity_id, 'newly_earned_badges': newly_earned_badges}), 201
    
    # GET request - only return activities for current user
    activities = conn.execute(
        'SELECT * FROM activities WHERE user_id = ? ORDER BY date DESC',
        (user_id,)
    ).fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in activities])

@app.route('/api/activities/<int:activity_id>', methods=['DELETE'])
@login_required
def delete_activity(activity_id):
    """Delete a specific activity"""
    user_id = session.get('user_id')
    conn = get_db_connection()
    conn.execute('DELETE FROM activities WHERE id = ? AND user_id = ?', (activity_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/stats')
@login_required
def stats():
    """Get statistics about activities"""
    user_id = session.get('user_id')
    conn = get_db_connection()
    
    # Get total days logged
    total_days = conn.execute('''
        SELECT COUNT(DISTINCT date) as count FROM activities WHERE user_id = ?
    ''', (user_id,)).fetchone()['count']
    
    # Get total activities
    total_activities = conn.execute('''
        SELECT COUNT(*) as count FROM activities WHERE user_id = ?
    ''', (user_id,)).fetchone()['count']
    
    # Get average progress score
    avg_score = conn.execute('''
        SELECT AVG(progress_score) as avg FROM activities WHERE user_id = ? AND progress_score > 0
    ''', (user_id,)).fetchone()['avg'] or 0
    
    # Get activities by date for chart
    activities_by_date = conn.execute('''
        SELECT date, COUNT(*) as count, AVG(progress_score) as avg_score
        FROM activities
        WHERE user_id = ?
        GROUP BY date
        ORDER BY date
    ''', (user_id,)).fetchall()

    # Calculate current streak based on distinct activity dates
    current_streak = calculate_current_streak(conn, user_id)

    conn.close()
    
    return jsonify({
        'total_days': total_days,
        'total_activities': total_activities,
        'current_streak': current_streak,
        'avg_score': round(avg_score, 2),
        'activities_by_date': [dict(row) for row in activities_by_date]
    })

@app.route('/api/gamification/ledger')
@login_required
def gamification_ledger():
    """Where the XP actually came from.

    The point of R7's ledger: daily_xp stored one opaque total per day and could
    never answer "why did I get 18 XP for that". This can, including whether an
    award was capped and whether it was evidenced or merely claimed.
    """
    user_id = session.get('user_id')
    limit = min(int(request.args.get('limit', 50)), 200)
    days = min(int(request.args.get('days', 30)), 365)

    conn = get_db_connection()
    payload = {
        'entries': xp.ledger(conn, user_id, limit=limit),
        'by_source': xp.by_source(conn, user_id, days=days),
        'evidence': xp.evidence_split(conn, user_id),
        'total_xp': xp.total_xp(conn, user_id),
        'caps': {
            'per_source': xp_config.DAILY_SOURCE_CAPS,
            'daily_total': xp_config.DAILY_TOTAL_CAP,
        },
    }
    conn.close()
    return jsonify(payload)


@app.route('/api/gamification/summary')
@login_required
def gamification_summary():
    """Current user's XP, level, streak multiplier, and badge progress"""
    user_id = session.get('user_id')
    conn = get_db_connection()

    total_xp = get_user_total_xp(conn, user_id)
    level, xp_into_level, xp_for_next_level = compute_level(total_xp)
    current_streak = calculate_current_streak(conn, user_id)
    streak_multiplier_pct = min(current_streak * STREAK_MULTIPLIER_PCT_PER_DAY, STREAK_MULTIPLIER_CAP_PCT)

    # Every achievement with its progress, not just earned/not-earned: a locked
    # one should be able to say "18 of 30 nights" rather than sitting greyed out.
    badges = achievements.with_progress(
        conn, user_id, achievement_context(conn, user_id))
    conn.close()

    return jsonify({
        'total_xp': total_xp,
        'level': level,
        'xp_into_level': xp_into_level,
        'xp_for_next_level': xp_for_next_level,
        'current_streak': current_streak,
        'streak_multiplier_pct': streak_multiplier_pct,
        'badges': badges
    })

def _attributes_payload(conn, user_id, date=None):
    """All eight attributes, in radar-axis order, whether or not they have a row.

    scoring.store.get_attributes() returns only rows that exist, so an attribute
    the user has never had a signal for would simply be missing. The radar needs
    all eight every time - a chart whose axes appear and disappear is unreadable -
    so anything absent is filled in with its honest default (locked, or
    unobserved). unlocks_in / needs_days come from the engine rather than the
    table, which stores only the numbers.
    """
    stored = {row['attribute']: row for row in scoring.get_attributes(conn, user_id, date)}

    payload = []
    for attribute in scoring.ATTRIBUTES:
        row = stored.get(attribute)
        if row is None:
            payload.append(scoring.aggregate_attribute(attribute, []))
            continue

        entry = {
            'attribute': attribute,
            'status': row['status'],
            'score': row['score'],
            'confidence': row['confidence'],
            'sample_days': row['sample_days'],
            'raw_value': row['raw_value'],
        }
        # Re-derive the explanatory fields the table does not carry.
        hint = scoring.aggregate_attribute(attribute, [])
        if entry['status'] == 'locked' and 'unlocks_in' in hint:
            entry['unlocks_in'] = hint['unlocks_in']
        if entry['status'] == 'calibrating':
            entry['needs_days'] = max(
                scoring.DEFAULT_CONFIG.min_days_for_score - (row['sample_days'] or 0), 0
            )
        payload.append(entry)
    return payload


@app.route('/api/attributes')
@login_required
def attributes():
    """The attribute set for the radar, as of a date (default: most recent)."""
    user_id = session.get('user_id')
    date = request.args.get('date') or None

    conn = get_db_connection()
    payload = _attributes_payload(conn, user_id, date)
    latest = conn.execute(
        'SELECT MAX(date) AS d FROM attribute_scores WHERE user_id = ?', (user_id,)
    ).fetchone()
    conn.close()

    return jsonify({'date': date or (latest['d'] if latest else None),
                    'attributes': payload})


@app.route('/api/days/<string:date>')
@login_required
def day_detail(date):
    """One day's logged checklist - the per-item answers as they were that day.

    Nothing else exposes these: custom_responses are written to the JSONL file
    and never read back over HTTP. Today reads this to show what is already
    ticked, so it must come from daily_log's snapshot rather than the live Path.
    """
    user_id = session.get('user_id')
    conn = get_db_connection()

    row = conn.execute(
        'SELECT * FROM daily_log WHERE user_id = ? AND date = ?', (user_id, date)
    ).fetchone()
    scores = conn.execute(
        'SELECT daily_score, discipline_score, completion_pct FROM daily_scores '
        'WHERE user_id = ? AND date = ?', (user_id, date)
    ).fetchone()
    conn.close()

    if row is None:
        # Not an error: most dates simply have not been logged.
        return jsonify({'date': date, 'logged': False, 'items': [], 'scores': None})

    try:
        payload = json.loads(row['payload_json'] or '{}')
    except (TypeError, ValueError):
        payload = {}

    return jsonify({
        'date': date,
        'logged': True,
        'path': {'id': row['path_id'], 'name': row['path_name']},
        'completion_pct': row['completion_pct'],
        'items_total': row['items_total'],
        'items_completed': row['items_completed'],
        'self_rating': row['self_rating'],
        'notes': row['notes'],
        'items': payload.get('items', []),
        'scores': dict(scores) if scores else None,
    })


@app.route('/api/days/<string:date>', methods=['PUT'])
@login_required
def save_day(date):
    """Log or re-log one day from the SPA.

    The legacy wizard posts to /api/activities and APPENDS a row every time,
    which is why `activities` accumulates duplicates for a re-submitted day.
    This updates in place instead - one checklist row per date - so editing
    today corrects the record rather than logging it twice.

    Scoring goes through the same score_checklist_day() the wizard uses, so a
    day logged here is indistinguishable from one logged there.
    """
    user_id = session.get('user_id')
    username = session.get('username', f'user_{user_id}')
    data = request.json or {}

    responses = data.get('responses')
    if not isinstance(responses, dict):
        return jsonify({'error': 'responses must be an object of item name -> answer'}), 400

    try:
        datetime.strptime(date, '%Y-%m-%d')
    except (TypeError, ValueError):
        return jsonify({'error': 'date must be YYYY-MM-DD'}), 400

    conn = get_db_connection()
    try:
        completion_percent, badges = record_checklist_day(
            conn, user_id, username, date, responses,
            notes=data.get('notes', ''),
            self_rating=data.get('self_rating'),
            path_id=data.get('path_id'),
            path_name=data.get('path_name'),
        )
    finally:
        conn.close()

    return jsonify({
        'date': date,
        'completion_pct': completion_percent,
        'newly_earned_badges': badges,
    })


def record_checklist_day(conn, user_id, username, date, responses, *,
                         notes='', self_rating=None, path_id=None,
                         path_name=None, source='spa'):
    """Write one day's checklist and score it. The only path that does this.

    Extracted from save_day() so the assistant can answer the check-in through
    exactly the same code. That matters more than the deduplication: save_day's
    own docstring says a day logged there must be indistinguishable from one
    logged by the legacy wizard, and a second implementation behind a chat
    window is precisely the drift it warns about - one that writes the
    daily_log row but forgets the activity row, or scores without the audit
    trail, and shows up weeks later as a streak that is wrong by a day.

    Returns `(completion_pct, newly_earned_badges)`.
    """
    checklist_payload = {
        'date': date,
        'checklist': {},
        'custom_responses': responses,
        'selected_path_id': path_id,
        'selected_path_name': path_name,
        'notes': notes,
        'source': source,
    }

    answered = sum(1 for value in responses.values() if str(value).strip())
    description = f'{answered} of {len(responses)} answered'
    # Mirrors the legacy client, which sends the 1-5 self-rating doubled. Kept
    # identical so /api/stats keeps meaning one thing across both writers.
    progress_score = int(self_rating) * 2 if str(self_rating or '').strip().isdigit() else 0

    existing = conn.execute(
        "SELECT id FROM activities WHERE user_id = ? AND date = ? "
        "AND activity_name = 'Daily Checklist' ORDER BY id DESC LIMIT 1",
        (user_id, date),
    ).fetchone()

    if existing:
        activity_id = existing['id']
        conn.execute(
            'UPDATE activities SET description = ?, progress_score = ?, notes = ? WHERE id = ?',
            (description, progress_score, notes, activity_id),
        )
    else:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO activities (user_id, date, activity_name, description, '
            'duration, progress_score, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (user_id, date, 'Daily Checklist', description, 0, progress_score, notes),
        )
        activity_id = cursor.lastrowid
    conn.commit()

    # The JSONL file stays an append-only audit trail of every submission,
    # including corrections - daily_log holds the current truth.
    save_checklist_to_file(user_id, username, activity_id, checklist_payload)

    badges, completion_percent = score_checklist_day(
        conn, user_id, date, checklist_payload, activity_id
    )
    return completion_percent, badges


@app.route('/api/home')
@login_required
def home_summary():
    """Everything the Home dashboard needs, in one response.

    Composed server-side on purpose: QueryBoundary wraps a single query, so five
    separate calls would mean five independent skeletons and five error states on
    one screen. One call, one loading state.
    """
    user_id = session.get('user_id')
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()

    total_xp = get_user_total_xp(conn, user_id)
    level, xp_into_level, xp_for_next_level = compute_level(total_xp)
    current_streak = calculate_current_streak(conn, user_id)

    recent = scoring.get_daily_scores(conn, user_id, limit=14)
    latest = recent[-1] if recent else None

    today_row = conn.execute(
        'SELECT completion_pct, items_total, items_completed FROM daily_log '
        'WHERE user_id = ? AND date = ?', (user_id, today)
    ).fetchone()

    days_logged = conn.execute(
        'SELECT COUNT(*) AS n FROM daily_log WHERE user_id = ?', (user_id,)
    ).fetchone()['n']

    payload = {
        'date': today,
        'level': level,
        'total_xp': total_xp,
        'xp_into_level': xp_into_level,
        'xp_for_next_level': xp_for_next_level,
        'current_streak': current_streak,
        'streak_multiplier_pct': min(
            current_streak * STREAK_MULTIPLIER_PCT_PER_DAY, STREAK_MULTIPLIER_CAP_PCT
        ),
        'days_logged': days_logged,
        'daily_score': latest['daily_score'] if latest else None,
        'discipline_score': latest['discipline_score'] if latest else None,
        'today': {
            'logged': today_row is not None,
            'completion_pct': today_row['completion_pct'] if today_row else 0,
            'items_total': today_row['items_total'] if today_row else 0,
            'items_completed': today_row['items_completed'] if today_row else 0,
        },
        'attributes': _attributes_payload(conn, user_id),
        'trend': recent,
    }
    conn.close()
    return jsonify(payload)


@app.route('/api/leaderboard/<string:scope>')
@login_required
def leaderboard(scope):
    """Ranked XP leaderboard across all users - 'overall' or 'monthly'"""
    if scope not in ('overall', 'monthly'):
        return jsonify({'error': 'Invalid leaderboard scope'}), 400

    conn = get_db_connection()

    if scope == 'monthly':
        month_prefix = datetime.now().strftime('%Y-%m')
        rows = conn.execute('''
            SELECT users.id as user_id, users.username, COALESCE(SUM(daily_xp.total_xp), 0) as total_xp
            FROM users
            LEFT JOIN daily_xp ON daily_xp.user_id = users.id AND daily_xp.date LIKE ?
            WHERE users.leaderboard_opt_out = 0
            GROUP BY users.id
            ORDER BY total_xp DESC, users.username ASC
        ''', (f'{month_prefix}%',)).fetchall()
    else:
        rows = conn.execute('''
            SELECT users.id as user_id, users.username, COALESCE(SUM(daily_xp.total_xp), 0) as total_xp
            FROM users
            LEFT JOIN daily_xp ON daily_xp.user_id = users.id
            WHERE users.leaderboard_opt_out = 0
            GROUP BY users.id
            ORDER BY total_xp DESC, users.username ASC
        ''').fetchall()

    entries = []
    for rank, row in enumerate(rows, start=1):
        level, _, _ = compute_level(row['total_xp'])
        entries.append({
            'rank': rank,
            'username': row['username'],
            'total_xp': row['total_xp'],
            'level': level,
            'current_streak': calculate_current_streak(conn, row['user_id'])
        })

    opted_out = conn.execute(
        'SELECT leaderboard_opt_out FROM users WHERE id = ?', (session.get('user_id'),)
    ).fetchone()
    conn.close()

    return jsonify({
        'scope': scope,
        'entries': entries,
        # So the page can say "you are hidden" instead of leaving someone to
        # wonder why they are not on a board they are looking at.
        'viewer_hidden': bool(opted_out['leaderboard_opt_out']) if opted_out else False,
    })

@app.route('/api/milestones/<int:days>')
@login_required
def get_milestone(days):
    """Get milestone insights for specific day count"""
    if days not in [10, 25, 45, 70, 100]:
        return jsonify({'error': 'Invalid milestone day'}), 400
    
    user_id = session.get('user_id')
    conn = get_db_connection()
    
    # Get all activities up to this milestone for current user
    activities = conn.execute('''
        SELECT * FROM activities WHERE user_id = ? ORDER BY date
    ''', (user_id,)).fetchall()
    
    # Calculate insights
    total_activities = len(activities)
    avg_score = sum(a['progress_score'] for a in activities if a['progress_score']) / max(total_activities, 1)
    unique_activity_types = len(set(a['activity_name'] for a in activities))
    total_duration = sum(a['duration'] for a in activities if a['duration'])
    
    # Get activity distribution
    activity_counts = {}
    for activity in activities:
        name = activity['activity_name']
        activity_counts[name] = activity_counts.get(name, 0) + 1
    
    insights = {
        'milestone_day': days,
        'total_activities': total_activities,
        'avg_progress_score': round(avg_score, 2),
        'unique_activity_types': unique_activity_types,
        'total_duration_hours': round(total_duration / 60, 2),
        'activity_distribution': activity_counts,
        'activities': [dict(row) for row in activities]
    }
    
    # Save milestone
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO milestones (user_id, milestone_day, insights)
        VALUES (?, ?, ?)
    ''', (user_id, days, json.dumps(insights)))
    conn.commit()
    conn.close()
    
    return jsonify(insights)

@app.route('/api/export/excel')
@login_required
def export_excel():
    """Export all activities to Excel file"""
    user_id = session.get('user_id')
    username = session.get('username')
    conn = get_db_connection()
    activities = conn.execute(
        'SELECT * FROM activities WHERE user_id = ? ORDER BY date',
        (user_id,)
    ).fetchall()
    conn.close()
    
    # Create workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Activities"
    
    # Headers
    headers = ['Date', 'Activity Name', 'Description', 'Duration (min)', 'Progress Score', 'Notes']
    ws.append(headers)
    
    # Style headers
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
    
    # Add data
    for activity in activities:
        ws.append([
            activity['date'],
            activity['activity_name'],
            activity['description'],
            activity['duration'],
            activity['progress_score'],
            activity['notes']
        ])
    
    # Adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    # Save file
    filename = f'neural_log_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    filepath = os.path.join('exports', filename)
    
    # Create exports directory if it doesn't exist
    os.makedirs('exports', exist_ok=True)
    
    wb.save(filepath)
    
    return send_file(filepath, as_attachment=True, download_name=filename)

# Admin Routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    """Serve the admin route inside the main React application."""
    return serve_spa_shell()

@app.route('/api/admin/users')
@admin_required
def get_all_users():
    """Get all users (admin only)"""
    conn = get_db_connection()
    users = conn.execute('''
        SELECT users.id, users.username, users.email, users.is_admin, users.is_active,
               users.leaderboard_opt_out, users.created_at,
               (SELECT COUNT(*) FROM activities WHERE user_id = users.id) AS activity_count,
               (SELECT COUNT(*) FROM daily_log WHERE user_id = users.id) AS logged_days,
               (SELECT MAX(date) FROM daily_log WHERE user_id = users.id) AS last_logged_on,
               COALESCE((SELECT SUM(total_xp) FROM daily_xp WHERE user_id = users.id), 0) AS total_xp
        FROM users
        ORDER BY users.is_active DESC, users.created_at DESC
    ''').fetchall()
    conn.close()

    payload = []
    for row in users:
        user = dict(row)
        user['is_admin'] = bool(user['is_admin'])
        user['is_active'] = bool(user['is_active'])
        user['leaderboard_opt_out'] = bool(user['leaderboard_opt_out'])
        payload.append(user)

    return jsonify(payload)

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete a user and all their data (admin only)"""
    # Prevent deleting yourself
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400
    
    conn = get_db_connection()

    user_row = conn.execute(
        'SELECT username, is_admin, is_active FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    if not user_row:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    if user_row['is_admin'] and user_row['is_active']:
        active_admins = conn.execute(
            'SELECT COUNT(*) AS count FROM users WHERE is_admin = 1 AND is_active = 1'
        ).fetchone()['count']
        if active_admins <= 1:
            conn.close()
            return jsonify({'success': False, 'message': 'Cannot remove the last active admin'}), 400

    conn.execute(
        'DELETE FROM exercise_sets WHERE session_id IN '
        '(SELECT id FROM workout_sessions WHERE user_id = ?)',
        (user_id,),
    )
    conn.execute(
        'DELETE FROM routine_exercises WHERE routine_id IN '
        '(SELECT id FROM routines WHERE user_id = ?)',
        (user_id,),
    )
    conn.execute(
        'DELETE FROM recipe_ingredients WHERE recipe_id IN '
        '(SELECT id FROM recipes WHERE user_id = ?)',
        (user_id,),
    )
    conn.execute(
        'DELETE FROM goal_habits WHERE goal_id IN '
        '(SELECT id FROM goals WHERE user_id = ?) OR habit_id IN '
        '(SELECT id FROM habits WHERE user_id = ?)',
        (user_id, user_id),
    )

    for table in (
        'activities', 'milestones', 'daily_xp', 'user_badges', 'daily_log',
        'attribute_scores', 'daily_scores', 'xp_transactions', 'body_measurements',
        'workout_sessions', 'routines', 'food_entries', 'sleep_entries',
        'lifestyle_days', 'user_profile', 'learning_sessions', 'learning_topics',
        'learning_areas', 'goal_milestones', 'tasks', 'goals', 'habit_completions',
        'habit_imports', 'habits', 'habit_groups', 'recipes', 'foods',
    ):
        conn.execute(f'DELETE FROM {table} WHERE user_id = ?', (user_id,))

    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

    # Their Path templates and daily submissions live on disk, not in SQL.
    # Deleting an account has to remove those too, or "delete this user" leaves
    # their personal log content sitting in artifacts/.
    for artifact in (get_user_paths_file_path(user_row['username']),
                     get_checklist_file_path(user_row['username'])):
        try:
            artifact.unlink(missing_ok=True)
        except OSError:
            app.logger.warning('Could not remove %s for deleted user', artifact)

    return jsonify({'success': True})

@app.route('/api/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    """Toggle admin status for a user (admin only)"""
    # Prevent removing your own admin status
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': 'Cannot modify your own admin status'}), 400
    
    conn = get_db_connection()
    user = conn.execute(
        'SELECT is_admin, is_active FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    new_admin_status = 0 if user['is_admin'] else 1
    if user['is_admin'] and user['is_active']:
        active_admins = conn.execute(
            'SELECT COUNT(*) AS count FROM users WHERE is_admin = 1 AND is_active = 1'
        ).fetchone()['count']
        if active_admins <= 1:
            conn.close()
            return jsonify({'success': False, 'message': 'Cannot remove the last active admin'}), 400

    conn.execute('UPDATE users SET is_admin = ? WHERE id = ?', (new_admin_status, user_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'is_admin': bool(new_admin_status)})

@app.route('/api/admin/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    """Suspend or resume an account without deleting its history."""
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': 'Cannot suspend your own account'}), 400

    conn = get_db_connection()
    user = conn.execute(
        'SELECT is_admin, is_active FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    new_active_status = 0 if user['is_active'] else 1
    if user['is_admin'] and user['is_active']:
        active_admins = conn.execute(
            'SELECT COUNT(*) AS count FROM users WHERE is_admin = 1 AND is_active = 1'
        ).fetchone()['count']
        if active_admins <= 1:
            conn.close()
            return jsonify({'success': False, 'message': 'Cannot suspend the last active admin'}), 400

    conn.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_active_status, user_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'is_active': bool(new_active_status)})

@app.route('/api/admin/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(user_id):
    """Reset password for a specific user (admin only)"""
    data = request.json or {}
    new_password = data.get('new_password', '')

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

    conn = get_db_connection()
    user = conn.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    password_hash = generate_password_hash(new_password)
    conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

@app.route('/api/admin/users/<int:user_id>/activities')
@admin_required
def get_user_activities(user_id):
    """Get all activities for a specific user (admin only)"""
    conn = get_db_connection()
    activities = conn.execute('''
        SELECT * FROM activities WHERE user_id = ? ORDER BY date DESC
    ''', (user_id,)).fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in activities])

# A daily timer is only reassuring if somebody would notice it stopping, and
# nobody runs `systemctl status` on a Tuesday. scripts/backup.sh drops its
# outcome beside the database - the one directory the container can already see
# - and the admin page reads it back. Silent failure becomes visible failure.
BACKUP_STALE_AFTER_HOURS = 36


def read_backup_status():
    """What the last backup run had to say for itself.

    Everything here is a claim made by a script the app does not run and cannot
    see, so every field is optional and a missing or unreadable file is reported
    as "unknown" rather than as a failure. Those are different: a fresh instance
    has no status yet, and saying "FAILED" at somebody on their first afternoon
    would teach them to ignore the indicator.
    """
    path = Path(DATABASE).resolve().parent / 'backup-status.json'

    try:
        with path.open('r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return {'known': False, 'reason': 'No backup has run yet.'}
    except (OSError, ValueError) as error:
        # A truncated or unparseable file is worth surfacing rather than hiding:
        # something writes here nightly, and if what it writes is unreadable then
        # the reporting is broken even if the backups are not.
        app.logger.warning('Could not read %s: %s', path, error)
        return {'known': False, 'reason': 'The backup status file could not be read.'}

    age_hours = None
    finished_at = payload.get('finished_at')
    if finished_at:
        try:
            # The script writes UTC with a trailing Z, which strptime parses as
            # naive - so the tzinfo has to be put back before this can be
            # subtracted from an aware `now`. (datetime.utcnow() would avoid
            # that and is deprecated in 3.12+, which is what the app runs on.)
            finished = datetime.strptime(finished_at, '%Y-%m-%dT%H:%M:%SZ').replace(
                tzinfo=timezone.utc
            )
            age_hours = round(
                (datetime.now(timezone.utc) - finished).total_seconds() / 3600, 1
            )
        except ValueError:
            pass

    return {
        'known': True,
        'ok': bool(payload.get('ok')),
        # Reported separately from `ok`, because a backup that succeeded onto the
        # same disk as the database is a real backup against fat fingers and no
        # backup at all against losing the instance.
        'offsite': bool(payload.get('offsite')),
        'finished_at': finished_at,
        'age_hours': age_hours,
        'stale': age_hours is not None and age_hours > BACKUP_STALE_AFTER_HOURS,
        'message': payload.get('message') or '',
        'users': payload.get('users'),
        'logged_days': payload.get('logged_days'),
        'local_copies': payload.get('local_copies'),
    }


@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    """Get overall system statistics (admin only)"""
    conn = get_db_connection()
    total_users = conn.execute('SELECT COUNT(*) AS count FROM users').fetchone()['count']
    active_accounts = conn.execute(
        'SELECT COUNT(*) AS count FROM users WHERE is_active = 1'
    ).fetchone()['count']
    total_admins = conn.execute(
        'SELECT COUNT(*) AS count FROM users WHERE is_admin = 1 AND is_active = 1'
    ).fetchone()['count']
    active_this_week = conn.execute('''
        SELECT COUNT(*) AS count FROM users
        WHERE EXISTS (
            SELECT 1 FROM daily_log
            WHERE daily_log.user_id = users.id
              AND daily_log.date >= date('now', '-6 days')
        )
    ''').fetchone()['count']
    total_activities = conn.execute('SELECT COUNT(*) AS count FROM activities').fetchone()['count']
    total_logged_days = conn.execute('SELECT COUNT(*) AS count FROM daily_log').fetchone()['count']
    feature_counts = {
        'workouts': conn.execute('SELECT COUNT(*) AS count FROM workout_sessions').fetchone()['count'],
        'meals': conn.execute('SELECT COUNT(*) AS count FROM food_entries').fetchone()['count'],
        'learning_sessions': conn.execute('SELECT COUNT(*) AS count FROM learning_sessions').fetchone()['count'],
        'goals': conn.execute('SELECT COUNT(*) AS count FROM goals').fetchone()['count'],
        'habits': conn.execute('SELECT COUNT(*) AS count FROM habits WHERE is_core = 0').fetchone()['count'],
    }
    integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
    conn.close()

    return jsonify({
        'accounts': {
            'total': total_users,
            'active': active_accounts,
            'admins': total_admins,
            'active_this_week': active_this_week,
        },
        'logging': {
            'activities': total_activities,
            'days': total_logged_days,
        },
        'features': feature_counts,
        'registration_mode': security.registration_mode(),
        'database_integrity': integrity,
        'version': __version__,
        'commit': __commit__,
        'backup': read_backup_status(),
    })

# --- invite codes (admin) ---------------------------------------------------

@app.route('/api/admin/invite-codes')
@admin_required
def list_invite_codes():
    """List all invite codes with usage info."""
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT ic.id, ic.code, ic.label, ic.revoked,
               ic.created_at, ic.used_at,
               creator.username AS created_by,
               redeemer.username AS used_by
        FROM invite_codes ic
        JOIN users creator ON creator.id = ic.created_by
        LEFT JOIN users redeemer ON redeemer.id = ic.used_by
        ORDER BY ic.created_at DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/admin/invite-codes', methods=['POST'])
@admin_required
def create_invite_code():
    """Generate a new invite code."""
    data = request.json or {}
    label = (data.get('label') or '').strip() or None
    code = secrets.token_urlsafe(12)

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO invite_codes (code, label, created_by) VALUES (?, ?, ?)',
        (code, label, session['user_id']),
    )
    conn.commit()
    conn.close()

    return jsonify({'code': code, 'label': label}), 201


@app.route('/api/admin/invite-codes/<int:code_id>/revoke', methods=['POST'])
@admin_required
def revoke_invite_code(code_id):
    """Revoke an unused invite code so it can no longer be redeemed."""
    conn = get_db_connection()
    row = conn.execute(
        'SELECT used_by FROM invite_codes WHERE id = ?', (code_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Code not found.'}), 404
    if row['used_by'] is not None:
        conn.close()
        return jsonify({'success': False, 'message': 'Code has already been used.'}), 400

    conn.execute('UPDATE invite_codes SET revoked = 1 WHERE id = ?', (code_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# Training endpoints live in their own module - app.py is already long enough,
# and they are self-contained. Registered after the helpers they depend on are
# defined, and injected rather than imported so the module never imports app
# back (the test suite swaps modules per test).
from training_api import init_training  # noqa: E402
from nutrition_api import init_nutrition  # noqa: E402
from learning_api import init_learning  # noqa: E402
from habits_api import init_habits  # noqa: E402
from goals_api import init_goals  # noqa: E402
from analytics_api import init_analytics  # noqa: E402
from onboarding_api import init_onboarding  # noqa: E402
from survey_api import init_survey  # noqa: E402
from assistant_api import init_assistant  # noqa: E402
from feed_api import init_feed  # noqa: E402

init_training(app, get_db_connection, login_required, recompute_after_change)

# Nutrition and Lifestyle also get the recompute function injected: logging a
# meal or a night's sleep moves attribute scores, so those endpoints have to
# rescore, and reaching for scoring.recompute_scores directly would be the same
# import cycle the injection exists to avoid.
init_nutrition(app, get_db_connection, login_required, recompute_after_change)

# Learning, same arrangement: logging a study session moves Knowledge and Focus.
init_learning(app, get_db_connection, login_required, recompute_after_change)

# Habits and Goals take no recompute function, and that absence is deliberate.
# Editing a habit's schedule does not change what you actually did, and a goal is
# an intention rather than evidence - neither moves an attribute score.
init_habits(app, get_db_connection, login_required)
init_goals(app, get_db_connection, login_required)
init_analytics(app, get_db_connection, login_required)
init_onboarding(app, get_db_connection, login_required, recompute_after_change)
init_survey(app, get_db_connection, login_required, recompute_after_change)

# The assistant is the one blueprint that also needs admin_required: its spend is
# reported on /admin rather than to the person spending it. It takes recompute
# because a confirmed proposal writes meals and sleep, which move scores exactly
# as they would if the person had typed them in.
init_assistant(app, get_db_connection, login_required, admin_required,
               recompute_after_change, record_checklist_day)
init_feed(app, get_db_connection, login_required)

# Applied at import time so migrations run under gunicorn too, not only when
# this module is executed directly. init_db() is idempotent.
init_db()

if __name__ == '__main__':
    app.run(debug=DEBUG, port=int(os.environ.get('PORT', 5000)))

