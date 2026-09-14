from flask import (
    Flask, render_template, request, jsonify, send_file, send_from_directory,
    session, redirect, url_for
)
from datetime import datetime, timedelta
import sqlite3
import json
from pathlib import Path
from uuid import uuid4
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv

import scoring

load_dotenv()

app = Flask(__name__)
# In production, SECRET_KEY must be set via the environment - the fallback below
# only exists so the app still boots for local/dev use without a .env file.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-insecure-secret-key')
DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'

# Database configuration
DATABASE = os.environ.get('DATABASE', 'neural_log.db')

# Resolved from this file rather than the cwd: the test suite chdirs into a tmp
# directory (tests/conftest.py), and the app is often started from elsewhere.
PROJECT_ROOT = Path(__file__).resolve().parent
MIGRATIONS_DIR = PROJECT_ROOT / 'migrations'
FRONTEND_DIST = PROJECT_ROOT / 'frontend' / 'dist'

DEFAULT_PATHS = [
    'Batman Path',
    'Thor Path',
    'Captain America Path',
    'Ironman Path'
]

# Keys map 1:1 to static/images/icons/<key>.png (see scripts/build_icons.py for how
# those were generated from artifacts/). Any icon value outside this set falls back
# to 'default' in normalize_checklist_items.
ICON_KEYS = {
    'sun', 'coffee', 'workout', 'code', 'chess', 'breakfast', 'lunch', 'water',
    'sleep', 'default'
}

def _time_item(name, options, weight=1, icon='default'):
    return {
        'name': name,
        'type': 'time',
        'icon': icon,
        'weight': weight,
        'options': options
    }

def _yes_no_item(name, weight=1, icon='default'):
    return {
        'name': name,
        'type': 'yes-no',
        'icon': icon,
        'weight': weight
    }

def _rating_item(name):
    # Rating items are self-reflection, not a completed task - excluded from XP scoring
    # (see calculate_daily_xp) and have no icon of their own.
    return {
        'name': name,
        'type': 'rating',
        'icon': 'default',
        'weight': 0
    }

DEFAULT_PATH_LIBRARY = [
    {
        'id': 'batman-path',
        'name': 'Batman Path',
        'is_default': True,
        'checklist_items': [
            _time_item('What time did you wake up?', ['05:00 - 05:30 AM', '05:30 - 06:30 AM', '06:30 - 07:30 AM', 'After 07:30 AM'], icon='sun'),
            _yes_no_item('Did you hydrate or drink coffee this morning?', icon='coffee'),
            _yes_no_item('Did you complete strength training today?', weight=3, icon='workout'),
            _yes_no_item('Did you practice a skill today? (coding, martial arts, chess, etc.)', weight=3, icon='chess'),
            _yes_no_item('Did you study or learn something new today?', weight=3, icon='code'),
            _yes_no_item('Did you complete your most important task today?'),
            _yes_no_item('Did you eat balanced meals today?', icon='breakfast'),
            _yes_no_item('Did you spend time reflecting or journaling?'),
            _yes_no_item('Did you plan tomorrow’s tasks?'),
            _rating_item('Rate your day (1–5)')
        ]
    },
    {
        'id': 'thor-path',
        'name': 'Thor Path',
        'is_default': True,
        'checklist_items': [
            _time_item('What time did you wake up?', ['05:00 - 05:30 AM', '05:30 - 06:30 AM', '06:30 - 07:30 AM', 'After 07:30 AM'], icon='sun'),
            _yes_no_item('Did you drink enough water today?', icon='water'),
            _yes_no_item('Did you eat a protein-rich breakfast?', icon='breakfast'),
            _yes_no_item('Did you complete a strength workout?', weight=3, icon='workout'),
            _yes_no_item('Did you do cardio or endurance training?', weight=3, icon='workout'),
            _yes_no_item('Did you eat a healthy lunch?', icon='lunch'),
            _yes_no_item('Did you stay physically active today?', weight=3, icon='workout'),
            _yes_no_item('Did you stretch or do recovery exercises?', icon='workout'),
            _yes_no_item('Did you prepare for good sleep tonight?', icon='sleep'),
            _rating_item('Rate your energy/performance today (1–5)')
        ]
    },
    {
        'id': 'captain-america-path',
        'name': 'Captain America Path',
        'is_default': True,
        'checklist_items': [
            _time_item('What time did you wake up?', ['05:00 - 05:30 AM', '05:30 - 06:30 AM', '06:30 - 07:30 AM', 'After 07:30 AM'], icon='sun'),
            _yes_no_item('Did you start your morning in an organized way?'),
            _yes_no_item('Did you eat a healthy breakfast?', icon='breakfast'),
            _yes_no_item('Did you exercise today?', weight=3, icon='workout'),
            _yes_no_item('Did you complete your most important task?', weight=3, icon='code'),
            _yes_no_item('Did you help someone or contribute positively today?'),
            _yes_no_item('Did you keep your workspace clean and organized?'),
            _yes_no_item('Did you read or learn something new?', weight=3, icon='code'),
            _yes_no_item('Did you reflect on your day?'),
            _rating_item('Rate your discipline today (1–5)')
        ]
    },
    {
        'id': 'ironman-path',
        'name': 'Ironman Path',
        'is_default': True,
        'checklist_items': [
            _time_item('What time did you wake up?', ['05:00 - 05:30 AM', '05:30 - 06:30 AM', '06:30 - 07:30 AM', 'After 07:30 AM'], icon='sun'),
            _yes_no_item('Did you review your daily learning goals?'),
            _yes_no_item('Did you spend at least 1 hour studying or learning?', weight=3, icon='code'),
            _yes_no_item('Did you practice a technical skill (coding, engineering, etc.)?', weight=3, icon='code'),
            _yes_no_item('Did you read something educational today?'),
            _yes_no_item('Did you work on a project or build something?', weight=3, icon='code'),
            _yes_no_item('Did you solve a problem or learn a new concept?', icon='chess'),
            _yes_no_item('Did you document what you learned today?'),
            _yes_no_item('Did you plan tomorrow’s learning tasks?'),
            _rating_item('Rate your productivity today (1–5)')
        ]
    }
]

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

def normalize_checklist_items(items):
    """Normalize path checklist items for safe persistence"""
    normalized_items = []
    for item in items or []:
        if not isinstance(item, dict):
            continue

        name = str(item.get('name', '')).strip()
        if not name:
            continue

        item_type = str(item.get('type', 'yes-no')).strip() or 'yes-no'

        try:
            weight = int(item.get('weight', 1))
        except (TypeError, ValueError):
            weight = 1
        weight = max(0, min(5, weight))

        icon = str(item.get('icon', '')).strip()
        if icon not in ICON_KEYS:
            icon = 'default'

        normalized_item = {
            'id': str(item.get('id') or uuid4()),
            'name': name,
            'type': item_type,
            'icon': icon,
            'weight': weight
        }

        options = item.get('options')
        if isinstance(options, list):
            normalized_item['options'] = [str(option).strip() for option in options if str(option).strip()]

        sub_response = item.get('subResponse')
        if isinstance(sub_response, dict):
            sub_options = sub_response.get('options', [])
            if not isinstance(sub_options, list):
                sub_options = []
            normalized_item['subResponse'] = {
                'prompt': str(sub_response.get('prompt', '')).strip(),
                'type': str(sub_response.get('type', 'radio')).strip() or 'radio',
                'options': [str(option).strip() for option in sub_options if str(option).strip()]
            }

        normalized_items.append(normalized_item)

    return normalized_items

def build_default_paths():
    """Get cloned and normalized default paths"""
    paths = []
    for path in DEFAULT_PATH_LIBRARY:
        paths.append({
            'id': path['id'],
            'name': path['name'],
            'is_default': True,
            'checklist_items': normalize_checklist_items(path['checklist_items'])
        })
    return paths


def repair_default_path_items(paths):
    """Re-attach shipped weights/icons to stock paths that predate them.

    A per-user path file is created once and never re-seeded from
    DEFAULT_PATH_LIBRARY, so accounts made before weights and icons existed
    keep weight=1 / icon='default' on every item. That flattens XP scoring and
    makes every wizard step show the same fallback artwork.

    Only fills in items that still look untouched (weight 1 AND no real icon)
    and whose name matches a shipped item exactly, so a user's own edits to a
    stock path are never overwritten. Returns True if anything changed.
    """
    shipped = {
        path['id']: {item['name']: item for item in path['checklist_items']}
        for path in DEFAULT_PATH_LIBRARY
    }

    changed = False
    for path in paths or []:
        if not path.get('is_default'):
            continue
        by_name = shipped.get(path.get('id'))
        if not by_name:
            continue
        for item in path.get('checklist_items', []):
            original = by_name.get(item.get('name'))
            if not original:
                continue
            untouched = (
                int(item.get('weight', 1) or 1) == 1
                and item.get('icon') in ('', 'default', None)
            )
            if not untouched:
                continue
            if (original.get('weight') != item.get('weight')
                    or original.get('icon') != item.get('icon')):
                item['weight'] = original.get('weight', 1)
                item['icon'] = original.get('icon', 'default')
                changed = True
    return changed

def resolve_selected_path_id(paths, selected_path_name):
    """Resolve selected path id from legacy/new selected_path values"""
    if not paths:
        return None

    normalized_selected_name = (selected_path_name or '').strip()

    for path in paths:
        if path['id'] == normalized_selected_name or path['name'] == normalized_selected_name:
            return path['id']

    if normalized_selected_name == 'Thor: God of the Thunder Path':
        for path in paths:
            if path['id'] == 'thor-path':
                return path['id']

    return paths[0]['id']

def load_user_paths(user_row):
    """Load or initialize per-user path system"""
    username = user_row['username']
    file_path = get_user_paths_file_path(username)

    if file_path.exists():
        try:
            with file_path.open('r', encoding='utf-8') as file:
                data = json.load(file)

            paths = data.get('paths', []) if isinstance(data, dict) else []
            selected_path_id = data.get('selected_path_id') if isinstance(data, dict) else None
            if isinstance(paths, list) and paths:
                normalized_paths = []
                for path in paths:
                    if not isinstance(path, dict):
                        continue
                    normalized_paths.append({
                        'id': str(path.get('id') or uuid4()),
                        'name': str(path.get('name', 'Untitled Path')).strip() or 'Untitled Path',
                        'is_default': bool(path.get('is_default', False)),
                        'checklist_items': normalize_checklist_items(path.get('checklist_items', []))
                    })

                if normalized_paths:
                    repair_default_path_items(normalized_paths)
                    resolved_selected_path_id = resolve_selected_path_id(normalized_paths, selected_path_id or user_row['selected_path'])
                    payload = {
                        'paths': normalized_paths,
                        'selected_path_id': resolved_selected_path_id
                    }
                    save_user_paths(username, payload)
                    return payload
        except (json.JSONDecodeError, OSError):
            pass

    paths = build_default_paths()

    custom_path_items = []
    if user_row['custom_path_items']:
        try:
            parsed = json.loads(user_row['custom_path_items'])
            if isinstance(parsed, list):
                custom_path_items = [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            custom_path_items = []

    if custom_path_items:
        paths.append({
            'id': f'custom-{uuid4().hex[:8]}',
            'name': 'My Custom Path',
            'is_default': False,
            'checklist_items': normalize_checklist_items([
                {'name': item_name, 'type': 'yes-no', 'icon': ''}
                for item_name in custom_path_items
            ])
        })

    selected_path_id = resolve_selected_path_id(paths, user_row['selected_path'])
    payload = {
        'paths': paths,
        'selected_path_id': selected_path_id
    }
    save_user_paths(username, payload)
    return payload

def save_user_paths(username, payload):
    """Persist per-user path system JSON"""
    file_path = get_user_paths_file_path(username)
    with file_path.open('w', encoding='utf-8') as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

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
    """Create a database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
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
        cursor.execute("ALTER TABLE users ADD COLUMN selected_path TEXT DEFAULT 'Batman Path'")
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


def calculate_current_streak(conn, user_id):
    """Current consecutive-day streak (today or yesterday must be logged)."""
    streak_rows = conn.execute('''
        SELECT DISTINCT date
        FROM activities
        WHERE user_id = ?
        ORDER BY date DESC
    ''', (user_id,)).fetchall()

    activity_dates = []
    for row in streak_rows:
        try:
            activity_dates.append(datetime.strptime(row['date'], '%Y-%m-%d').date())
        except (ValueError, TypeError):
            continue

    if not activity_dates:
        return 0

    today = datetime.now().date()
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


def xp_for_level(level):
    """Cumulative total XP required to reach a given level. Level 1 is the
    starting level everyone begins at, so it requires 0 XP."""
    return 50 * ((level - 1) ** 2)


def compute_level(total_xp):
    """Return (level, xp_into_current_level, xp_needed_for_next_level)."""
    level = 1
    while xp_for_level(level + 1) <= total_xp:
        level += 1

    xp_into_level = total_xp - xp_for_level(level)
    xp_for_next = xp_for_level(level + 1) - xp_for_level(level)
    return level, xp_into_level, xp_for_next


def get_user_total_xp(conn, user_id):
    row = conn.execute(
        'SELECT COALESCE(SUM(total_xp), 0) as total FROM daily_xp WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    return row['total'] if row else 0


def award_daily_xp(conn, user_id, date, checklist_items, custom_responses, completion_percent=0):
    """Score one day's checklist submission, upsert daily_xp, evaluate badges.

    Returns the list of newly-earned badge definitions (empty if none).
    Safe to call more than once for the same (user_id, date) - it recomputes
    and replaces rather than accumulating, so editing today's log doesn't
    double-count XP.
    """
    base_xp = calculate_daily_xp(checklist_items, custom_responses)
    streak = calculate_current_streak(conn, user_id)
    multiplier_pct = min(streak * STREAK_MULTIPLIER_PCT_PER_DAY, STREAK_MULTIPLIER_CAP_PCT)
    total_xp = round(base_xp * (1 + multiplier_pct / 100))

    conn.execute('''
        INSERT INTO daily_xp (user_id, date, base_xp, streak_multiplier_pct, total_xp)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET
            base_xp = excluded.base_xp,
            streak_multiplier_pct = excluded.streak_multiplier_pct,
            total_xp = excluded.total_xp
    ''', (user_id, date, base_xp, multiplier_pct, total_xp))
    conn.commit()

    return evaluate_badges(conn, user_id, completion_percent_today=completion_percent)


BADGE_DEFINITIONS = [
    {
        'code': 'first-log',
        'name': 'First Steps',
        'description': 'Logged your first daily checklist.',
        'check': lambda ctx: ctx['total_days'] >= 1
    },
    {
        'code': 'week-streak',
        'name': 'One Week Strong',
        'description': 'Reached a 7-day streak.',
        'check': lambda ctx: ctx['current_streak'] >= 7
    },
    {
        'code': 'month-streak',
        'name': 'Consistency Master',
        'description': 'Reached a 30-day streak.',
        'check': lambda ctx: ctx['current_streak'] >= 30
    },
    {
        'code': 'century',
        'name': 'Century Club',
        'description': 'Logged 100 days.',
        'check': lambda ctx: ctx['total_days'] >= 100
    },
    {
        'code': 'custom-path',
        'name': 'Path Finder',
        'description': 'Created your own custom Path.',
        'check': lambda ctx: ctx['has_custom_path']
    },
    {
        'code': 'perfect-day',
        'name': 'Perfectionist',
        'description': 'Completed 100% of a daily checklist.',
        'check': lambda ctx: ctx['completion_percent_today'] >= 100
    },
    {
        'code': 'level-5',
        'name': 'Leveling Up',
        'description': 'Reached level 5.',
        'check': lambda ctx: ctx['level'] >= 5
    },
    {
        'code': 'level-10',
        'name': 'Double Digits',
        'description': 'Reached level 10.',
        'check': lambda ctx: ctx['level'] >= 10
    }
]


def evaluate_badges(conn, user_id, completion_percent_today=0):
    """Check all badge definitions against the user's current stats and
    unlock any newly-earned ones. Returns the list of newly-earned definitions.
    """
    total_days = conn.execute(
        'SELECT COUNT(DISTINCT date) as count FROM activities WHERE user_id = ?',
        (user_id,)
    ).fetchone()['count']
    current_streak = calculate_current_streak(conn, user_id)
    total_xp = get_user_total_xp(conn, user_id)
    level, _, _ = compute_level(total_xp)

    user_row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    has_custom_path = False
    if user_row:
        paths_payload = load_user_paths(user_row)
        has_custom_path = any(not path.get('is_default', False) for path in paths_payload.get('paths', []))

    ctx = {
        'total_days': total_days,
        'current_streak': current_streak,
        'total_xp': total_xp,
        'level': level,
        'has_custom_path': has_custom_path,
        'completion_percent_today': completion_percent_today
    }

    already_earned = {
        row['badge_code']
        for row in conn.execute('SELECT badge_code FROM user_badges WHERE user_id = ?', (user_id,)).fetchall()
    }

    newly_earned = []
    for badge in BADGE_DEFINITIONS:
        if badge['code'] in already_earned:
            continue
        if badge['check'](ctx):
            conn.execute(
                'INSERT OR IGNORE INTO user_badges (user_id, badge_code) VALUES (?, ?)',
                (user_id, badge['code'])
            )
            newly_earned.append(badge)

    if newly_earned:
        conn.commit()

    return newly_earned

# Decorator for routes that require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Decorator for routes that require admin access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        user = conn.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        
        if not user or not user['is_admin']:
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
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
        else:
            return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration"""
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        email = data.get('email', '')
        selected_path = data.get('selected_path', 'Batman Path')
        custom_path_items = data.get('custom_path_items', [])
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password required'}), 400

        if selected_path == 'Thor: God of the Thunder Path':
            selected_path = 'Thor Path'

        if selected_path not in DEFAULT_PATHS:
            return jsonify({'success': False, 'message': 'Invalid path selection'}), 400

        custom_path_items = [str(item).strip() for item in (custom_path_items or []) if str(item).strip()]
        
        conn = get_db_connection()
        
        # Check if username already exists
        existing_user = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing_user:
            conn.close()
            return jsonify({'success': False, 'message': 'Username already exists'}), 400
        
        # Check if this is the first user (make them admin)
        user_count = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
        is_admin = 1 if user_count == 0 else 0
        
        # Create new user
        password_hash = generate_password_hash(password)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO users (username, password_hash, email, is_admin, selected_path, custom_path_items) VALUES (?, ?, ?, ?, ?, ?)',
            (username, password_hash, email, is_admin, selected_path, json.dumps(custom_path_items))
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        # Log in the new user
        session['user_id'] = user_id
        session['username'] = username
        session['is_admin'] = bool(is_admin)
        
        return jsonify({
            'success': True,
            'username': username,
            'is_admin': bool(is_admin),
            'selected_path': selected_path
        }), 201
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Handle user logout"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/current-user')
@login_required
def current_user():
    """Get current logged in user"""
    conn = get_db_connection()
    user = conn.execute(
        'SELECT username, selected_path, custom_path_items FROM users WHERE id = ?',
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
        'selected_path_id': paths_payload.get('selected_path_id')
    })

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

    paths_payload = load_user_paths(current_user_row)
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

    save_user_paths(new_username, paths_payload)

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

    data = request.json or {}
    items = data.get('items')

    if not isinstance(items, list):
        return jsonify({'success': False, 'message': 'Items must be a list'}), 400

    normalized_items = normalize_checklist_items(items)
    for path in paths_payload['paths']:
        if path['id'] == selected_path['id']:
            path['checklist_items'] = normalized_items
            break

    save_user_paths(user_row['username'], paths_payload)
    return jsonify({'success': True, 'items': normalized_items})

@app.route('/api/paths', methods=['GET', 'POST'])
@login_required
def paths_collection():
    """Get all user paths or create a custom path"""
    user_id = session.get('user_id')
    conn = get_db_connection()
    user_row = conn.execute('SELECT username, selected_path, custom_path_items FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()

    if not user_row:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    paths_payload = load_user_paths(user_row)

    if request.method == 'GET':
        selected_path = get_selected_path(paths_payload)
        return jsonify({
            'success': True,
            'paths': paths_payload.get('paths', []),
            'selected_path_id': paths_payload.get('selected_path_id'),
            'selected_path_name': selected_path['name'] if selected_path else None
        })

    data = request.json or {}
    path_name = (data.get('name') or '').strip()
    checklist_items = data.get('checklist_items', [])

    if not path_name:
        return jsonify({'success': False, 'message': 'Path name is required'}), 400

    if any(path['name'].lower() == path_name.lower() for path in paths_payload['paths']):
        return jsonify({'success': False, 'message': 'A path with this name already exists'}), 400

    normalized_items = normalize_checklist_items(checklist_items)
    new_path = {
        'id': f'custom-{uuid4().hex[:8]}',
        'name': path_name,
        'is_default': False,
        'checklist_items': normalized_items
    }
    paths_payload['paths'].append(new_path)
    save_user_paths(user_row['username'], paths_payload)
    return jsonify({'success': True, 'path': new_path}), 201

@app.route('/api/paths/selected', methods=['PUT'])
@login_required
def select_path():
    """Set selected path for current user"""
    user_id = session.get('user_id')
    data = request.json or {}
    selected_path_id = (data.get('path_id') or '').strip()

    if not selected_path_id:
        return jsonify({'success': False, 'message': 'Path id is required'}), 400

    conn = get_db_connection()
    user_row = conn.execute('SELECT username, selected_path, custom_path_items FROM users WHERE id = ?', (user_id,)).fetchone()

    if not user_row:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    paths_payload = load_user_paths(user_row)
    selected_path = next((path for path in paths_payload['paths'] if path['id'] == selected_path_id), None)
    if not selected_path:
        conn.close()
        return jsonify({'success': False, 'message': 'Path not found'}), 404

    paths_payload['selected_path_id'] = selected_path_id
    save_user_paths(user_row['username'], paths_payload)
    conn.execute('UPDATE users SET selected_path = ? WHERE id = ?', (selected_path['name'], user_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'selected_path_id': selected_path_id, 'selected_path_name': selected_path['name']})

@app.route('/api/paths/<string:path_id>', methods=['PUT', 'DELETE'])
@login_required
def path_detail(path_id):
    """Update or delete a user path"""
    user_id = session.get('user_id')
    conn = get_db_connection()
    user_row = conn.execute('SELECT username, selected_path, custom_path_items FROM users WHERE id = ?', (user_id,)).fetchone()

    if not user_row:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    paths_payload = load_user_paths(user_row)
    paths = paths_payload.get('paths', [])
    target_index = next((index for index, path in enumerate(paths) if path['id'] == path_id), -1)

    if target_index < 0:
        conn.close()
        return jsonify({'success': False, 'message': 'Path not found'}), 404

    target_path = paths[target_index]

    if request.method == 'DELETE':
        if len(paths) <= 1:
            conn.close()
            return jsonify({'success': False, 'message': 'At least one path must remain'}), 400

        deleted_selected = paths_payload.get('selected_path_id') == path_id
        paths.pop(target_index)

        if deleted_selected:
            paths_payload['selected_path_id'] = paths[0]['id']

        selected_path = get_selected_path(paths_payload)
        save_user_paths(user_row['username'], paths_payload)
        conn.execute('UPDATE users SET selected_path = ? WHERE id = ?', (selected_path['name'], user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

    data = request.json or {}
    new_name = (data.get('name') or target_path['name']).strip()
    checklist_items = data.get('checklist_items', target_path.get('checklist_items', []))

    if not new_name:
        conn.close()
        return jsonify({'success': False, 'message': 'Path name is required'}), 400

    name_exists = any(
        index != target_index and path['name'].lower() == new_name.lower()
        for index, path in enumerate(paths)
    )
    if name_exists:
        conn.close()
        return jsonify({'success': False, 'message': 'A path with this name already exists'}), 400

    target_path['name'] = new_name
    target_path['checklist_items'] = normalize_checklist_items(checklist_items)
    paths[target_index] = target_path

    save_user_paths(user_row['username'], paths_payload)

    if paths_payload.get('selected_path_id') == path_id:
        conn.execute('UPDATE users SET selected_path = ? WHERE id = ?', (new_name, user_id))
        conn.commit()

    conn.close()
    return jsonify({'success': True, 'path': target_path})

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

@app.route('/')
@login_required
def index():
    """Render the main page"""
    return render_template('index.html')


# ---------------------------------------------------------------------------
# Redesigned SPA (frontend/) - served under /app while the classic Jinja UI
# above stays the default at /. Phase 2 flips the default over once Home and
# Today are real; until then both are reachable side by side.
# ---------------------------------------------------------------------------

SPA_NOT_BUILT_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Neural Log - build required</title>
<style>body{background:#0b0c0e;color:#f2f4f7;font:15px/1.6 system-ui,sans-serif;
padding:3rem;max-width:40rem;margin:0 auto}code{background:#1a1d22;padding:.15rem .4rem;
border-radius:4px}a{color:#e5484d}</style></head><body>
<h1>The redesigned app hasn't been built yet</h1>
<p>Run the dev server for hot reload:</p>
<p><code>cd frontend &amp;&amp; npm run dev</code> then open
<a href="http://localhost:5173/app">localhost:5173/app</a></p>
<p>Or build it once so Flask can serve it from here:</p>
<p><code>cd frontend &amp;&amp; npm run build</code></p>
<p><a href="/">Back to the classic dashboard</a></p>
</body></html>"""


@app.route('/app/assets/<path:filename>')
def spa_assets(filename):
    """Hashed JS/CSS/font bundles. No auth: they hold no user data, and gating
    them would break the shell whenever a session expires mid-session."""
    return send_from_directory(FRONTEND_DIST / 'assets', filename)


# strict_slashes=False so /app and /app/ both work. The <path:> converter does
# not match an empty string, so without it a trailing slash - exactly what a
# bookmark or a typed URL tends to have - returns 404.
@app.route('/app', strict_slashes=False)
@app.route('/app/<path:_subpath>')
@login_required
def serve_spa(_subpath=''):
    """Serve the SPA shell; client-side routing handles everything below /app."""
    if not (FRONTEND_DIST / 'index.html').exists():
        return SPA_NOT_BUILT_HTML, 200
    return send_from_directory(FRONTEND_DIST, 'index.html')

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

    paths_payload = load_user_paths(user_row)
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
    scoring.record_day(
        conn, user_id, date, checklist_items, custom_responses,
        path_id=used_path.get('id'),
        path_name=used_path.get('name'),
        activity_id=activity_id,
        self_rating=_extract_self_rating(checklist_items, custom_responses),
        notes=(checklist_payload.get('notes') or None),
    )
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

    earned_codes = {
        row['badge_code']
        for row in conn.execute('SELECT badge_code FROM user_badges WHERE user_id = ?', (user_id,)).fetchall()
    }
    conn.close()

    badges = [
        {
            'code': badge['code'],
            'name': badge['name'],
            'description': badge['description'],
            'earned': badge['code'] in earned_codes
        }
        for badge in BADGE_DEFINITIONS
    ]

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

    checklist_payload = {
        'date': date,
        'checklist': {},
        'custom_responses': responses,
        'selected_path_id': data.get('path_id'),
        'selected_path_name': data.get('path_name'),
        'notes': data.get('notes', ''),
        'source': 'spa',
    }

    conn = get_db_connection()

    answered = sum(1 for value in responses.values() if str(value).strip())
    description = f'{answered} of {len(responses)} answered'
    # Mirrors the legacy client, which sends the 1-5 self-rating doubled. Kept
    # identical so /api/stats keeps meaning one thing across both writers.
    self_rating = data.get('self_rating')
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
            (description, progress_score, data.get('notes', ''), activity_id),
        )
    else:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO activities (user_id, date, activity_name, description, '
            'duration, progress_score, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (user_id, date, 'Daily Checklist', description, 0, progress_score,
             data.get('notes', '')),
        )
        activity_id = cursor.lastrowid
    conn.commit()

    # The JSONL file stays an append-only audit trail of every submission,
    # including corrections - daily_log holds the current truth.
    save_checklist_to_file(user_id, username, activity_id, checklist_payload)

    badges, completion_percent = score_checklist_day(
        conn, user_id, date, checklist_payload, activity_id
    )
    conn.close()

    return jsonify({
        'date': date,
        'completion_pct': completion_percent,
        'newly_earned_badges': badges,
    })


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
            GROUP BY users.id
            ORDER BY total_xp DESC, users.username ASC
        ''', (f'{month_prefix}%',)).fetchall()
    else:
        rows = conn.execute('''
            SELECT users.id as user_id, users.username, COALESCE(SUM(daily_xp.total_xp), 0) as total_xp
            FROM users
            LEFT JOIN daily_xp ON daily_xp.user_id = users.id
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

    conn.close()
    return jsonify({'scope': scope, 'entries': entries})

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
    """Admin dashboard page"""
    return render_template('admin.html')

@app.route('/api/admin/users')
@admin_required
def get_all_users():
    """Get all users (admin only)"""
    conn = get_db_connection()
    users = conn.execute('''
        SELECT id, username, email, is_admin, created_at,
               (SELECT COUNT(*) FROM activities WHERE user_id = users.id) as activity_count
        FROM users
        ORDER BY created_at DESC
    ''').fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in users])

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete a user and all their data (admin only)"""
    # Prevent deleting yourself
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400
    
    conn = get_db_connection()

    username_row = conn.execute(
        'SELECT username FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    if not username_row:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Every per-user table. SQLite foreign keys are not enforced here (PRAGMA
    # foreign_keys is never enabled), so nothing cascades - each new per-user
    # table added by a later phase must be listed here, or deleting an account
    # silently leaves that person's data behind.
    for table in ('activities', 'milestones', 'daily_xp', 'user_badges',
                  'daily_log', 'attribute_scores', 'daily_scores'):
        conn.execute(f'DELETE FROM {table} WHERE user_id = ?', (user_id,))

    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

    # Their Path templates and daily submissions live on disk, not in SQL.
    # Deleting an account has to remove those too, or "delete this user" leaves
    # their personal log content sitting in artifacts/.
    for artifact in (get_user_paths_file_path(username_row['username']),
                     get_checklist_file_path(username_row['username'])):
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
    user = conn.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'User not found'}), 404
    
    new_admin_status = 0 if user['is_admin'] else 1
    conn.execute('UPDATE users SET is_admin = ? WHERE id = ?', (new_admin_status, user_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'is_admin': bool(new_admin_status)})

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

@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    """Get overall system statistics (admin only)"""
    conn = get_db_connection()
    
    total_users = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    total_activities = conn.execute('SELECT COUNT(*) as count FROM activities').fetchone()['count']
    total_admins = conn.execute('SELECT COUNT(*) as count FROM users WHERE is_admin = 1').fetchone()['count']
    
    # Most active users
    active_users = conn.execute('''
        SELECT users.username, COUNT(activities.id) as activity_count
        FROM users
        LEFT JOIN activities ON users.id = activities.user_id
        GROUP BY users.id
        ORDER BY activity_count DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    return jsonify({
        'total_users': total_users,
        'total_activities': total_activities,
        'total_admins': total_admins,
        'active_users': [dict(row) for row in active_users]
    })

# Training endpoints live in their own module - app.py is already long enough,
# and they are self-contained. Registered after the helpers they depend on are
# defined, and injected rather than imported so the module never imports app
# back (the test suite swaps modules per test).
from training_api import init_training  # noqa: E402

init_training(app, get_db_connection, login_required)

# Applied at import time so migrations run under gunicorn too, not only when
# this module is executed directly. init_db() is idempotent.
init_db()

if __name__ == '__main__':
    app.run(debug=DEBUG, port=int(os.environ.get('PORT', 5000)))

