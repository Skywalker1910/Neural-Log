"""The achievement catalogue.

WHY THESE ARE DATA RATHER THAN LAMBDAS
--------------------------------------
The Phase 2 badges were eight dicts each carrying a `check(ctx)` callable. That
works for deciding "earned or not" and cannot do anything else - in particular it
cannot say HOW CLOSE you are, because a lambda returning False tells you nothing
about the distance to True.

R7 asks for an unlock UI, and an unlock UI that cannot show progress is just a
list of things you do not have. So an achievement is now a metric name and a
threshold. "Earned" is `ctx[metric] >= threshold`, and progress falls out of the
same two numbers for free.

It also makes tiers almost free: bronze, silver and gold versions of one idea are
the same metric at three thresholds, rather than three near-identical lambdas.

THE CATALOGUE LIVES IN THE DATABASE
-----------------------------------
Synced into the `achievements` table on startup, the same arrangement as the
exercise and food libraries. The rules stay here in Python; what is stored is the
catalogue the UI groups, filters and shows progress against.

LEGACY CODES ARE PRESERVED
--------------------------
`user_badges` rows reference these codes, so the original eight keep theirs
exactly. Renaming one would silently un-earn it for everyone who had it.
"""
import xp_config as cfg

BRONZE, SILVER, GOLD = 'bronze', 'silver', 'gold'

# metric -> the context key it reads. Every achievement is "ctx[metric] >= threshold".
CATALOGUE = [
    # --- consistency: the original eight, re-expressed ----------------------
    dict(code='first-log', name='First Steps', category='consistency', tier=BRONZE,
         description='Logged your first daily checklist.',
         metric='total_days', threshold=1, xp_reward=10),
    dict(code='week-streak', name='One Week Strong', category='consistency', tier=BRONZE,
         description='Reached a 7-day streak.',
         metric='current_streak', threshold=7, xp_reward=25),
    dict(code='month-streak', name='Consistency Master', category='consistency', tier=GOLD,
         description='Reached a 30-day streak.',
         metric='current_streak', threshold=30, xp_reward=100),
    dict(code='century', name='Century Club', category='consistency', tier=GOLD,
         description='Logged 100 days.',
         metric='total_days', threshold=100, xp_reward=150),
    dict(code='custom-path', name='Path Finder', category='consistency', tier=BRONZE,
         description='Created your own custom Path.',
         metric='has_custom_path', threshold=1, xp_reward=15),
    dict(code='perfect-day', name='Perfectionist', category='consistency', tier=SILVER,
         description='Completed 100% of a daily checklist.',
         metric='completion_percent_today', threshold=100, xp_reward=30),

    # --- mastery ------------------------------------------------------------
    dict(code='level-5', name='Leveling Up', category='mastery', tier=SILVER,
         description='Reached level 5.',
         metric='level', threshold=5, xp_reward=40),
    dict(code='level-10', name='Double Digits', category='mastery', tier=GOLD,
         description='Reached level 10.',
         metric='level', threshold=10, xp_reward=100),

    # Rewards evidence over assertion, the same principle the XP rates encode:
    # a total built from logged work is worth more than one built from ticking.
    dict(code='evidence-1000', name='Receipts', category='mastery', tier=SILVER,
         description='Earned 1,000 XP from logged work rather than ticked boxes.',
         metric='measured_xp', threshold=1000, xp_reward=50),
    dict(code='goal-achieved', name='Finisher', category='mastery', tier=SILVER,
         description='Marked a goal as achieved.',
         metric='goals_achieved', threshold=1, xp_reward=40),

    # --- training -----------------------------------------------------------
    dict(code='first-workout', name='Rack Pulled', category='training', tier=BRONZE,
         description='Logged your first workout.',
         metric='workouts', threshold=1, xp_reward=15),
    dict(code='workouts-25', name='Regular', category='training', tier=SILVER,
         description='Logged 25 workouts.',
         metric='workouts', threshold=25, xp_reward=60),
    dict(code='workouts-100', name='Iron Habit', category='training', tier=GOLD,
         description='Logged 100 workouts.',
         metric='workouts', threshold=100, xp_reward=150),
    dict(code='volume-100k', name='Six Figures', category='training', tier=GOLD,
         description='Moved 100,000 kg of total volume.',
         metric='total_volume', threshold=100000, xp_reward=120),

    # --- learning -----------------------------------------------------------
    dict(code='first-study', name='Opened the Book', category='learning', tier=BRONZE,
         description='Logged your first study session.',
         metric='study_sessions', threshold=1, xp_reward=15),
    dict(code='study-10h', name='Ten Hours Deep', category='learning', tier=SILVER,
         description='Studied for 10 hours in total.',
         metric='study_minutes', threshold=600, xp_reward=50),
    dict(code='study-100h', name='Hundred Hours', category='learning', tier=GOLD,
         description='Studied for 100 hours in total.',
         metric='study_minutes', threshold=6000, xp_reward=150),

    # --- lifestyle ----------------------------------------------------------
    dict(code='first-night', name='Lights Out', category='lifestyle', tier=BRONZE,
         description='Logged your first night of sleep.',
         metric='nights_logged', threshold=1, xp_reward=10),
    dict(code='nights-30', name='Well Rested', category='lifestyle', tier=SILVER,
         description='Logged 30 nights of sleep.',
         metric='nights_logged', threshold=30, xp_reward=60),
    dict(code='steps-target-10', name='On Your Feet', category='lifestyle', tier=BRONZE,
         description='Hit your step target on 10 days.',
         metric='days_at_step_target', threshold=10, xp_reward=30),

    # --- nutrition ----------------------------------------------------------
    dict(code='first-meal', name='Weighed and Measured', category='nutrition', tier=BRONZE,
         description='Logged your first day of food.',
         metric='days_food_logged', threshold=1, xp_reward=10),
    dict(code='food-30', name='Tracked a Month', category='nutrition', tier=SILVER,
         description='Logged food on 30 days.',
         metric='days_food_logged', threshold=30, xp_reward=60),
    dict(code='first-recipe', name='Home Cook', category='nutrition', tier=BRONZE,
         description='Built a dish from its ingredients.',
         metric='recipes', threshold=1, xp_reward=20),
]

CATEGORIES = ('consistency', 'training', 'nutrition', 'lifestyle', 'learning', 'mastery')


def sync_catalogue(conn):
    """Insert or update the catalogue. Returns (added, updated).

    Idempotent, like the exercise and food library syncs. An achievement dropped
    from the catalogue is archived rather than deleted, because user_badges rows
    point at its code and deleting would orphan somebody's unlock.
    """
    existing = {row['code']: row for row in conn.execute('SELECT * FROM achievements')}

    added = updated = 0
    for position, entry in enumerate(CATALOGUE):
        values = (entry['name'], entry['description'], entry['category'],
                  entry['tier'], entry.get('xp_reward', 0), entry.get('threshold'),
                  entry.get('icon'), position)

        current = existing.get(entry['code'])
        if current is None:
            conn.execute(
                'INSERT INTO achievements (code, name, description, category, tier, '
                'xp_reward, threshold, icon, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (entry['code'], *values),
            )
            added += 1
            continue

        unchanged = (
            current['name'] == values[0] and current['description'] == values[1]
            and current['category'] == values[2] and current['tier'] == values[3]
            and current['xp_reward'] == values[4] and current['threshold'] == values[5]
            and current['position'] == values[7] and not current['archived']
        )
        if unchanged:
            continue

        conn.execute(
            'UPDATE achievements SET name = ?, description = ?, category = ?, tier = ?, '
            'xp_reward = ?, threshold = ?, icon = ?, position = ?, archived = 0 '
            'WHERE code = ?',
            (*values, entry['code']),
        )
        updated += 1

    shipped = {entry['code'] for entry in CATALOGUE}
    for code, row in existing.items():
        if code not in shipped and not row['archived']:
            conn.execute('UPDATE achievements SET archived = 1 WHERE code = ?', (code,))

    conn.commit()
    return added, updated


def build_context(conn, user_id, completion_percent_today=0, has_custom_path=False,
                  total_days=0, current_streak=0, total_xp=0, level=1):
    """Every number the catalogue can test against.

    Gathered in one pass rather than per achievement: twenty-odd achievements
    sharing eight metrics would otherwise mean twenty-odd near-identical queries
    on every checklist submission.
    """
    def scalar(sql, default=0):
        try:
            row = conn.execute(sql, (user_id,)).fetchone()
            return (row[0] if row and row[0] is not None else default)
        except Exception:
            # A workspace whose tables do not exist yet must not break unlocking
            # for the ones that do.
            return default

    return {
        'total_days': total_days,
        'current_streak': current_streak,
        'total_xp': total_xp,
        'level': level,
        'has_custom_path': 1 if has_custom_path else 0,
        'completion_percent_today': completion_percent_today,

        # Counts sessions with real work in them, matching the XP floor. A
        # session holding nothing but a warm-up earns no XP, so it should not
        # unlock "logged your first workout" either.
        'workouts': scalar(
            'SELECT COUNT(*) FROM workout_sessions s WHERE s.user_id = ? AND EXISTS ('
            'SELECT 1 FROM exercise_sets x WHERE x.session_id = s.id AND x.is_warmup = 0)'),
        'total_volume': scalar(
            'SELECT COALESCE(SUM(total_volume), 0) FROM workout_sessions WHERE user_id = ?'),

        # Both respect the XP floor. A three-minute session is opening a book and
        # closing it: it earns no XP, so it should not unlock "logged your first
        # study session" either, and it should not creep into an hours total.
        'study_sessions': scalar(
            'SELECT COUNT(*) FROM learning_sessions WHERE user_id = ? '
            f'AND duration_minutes >= {cfg.MIN_STUDY_MINUTES}'),
        'study_minutes': scalar(
            'SELECT COALESCE(SUM(duration_minutes), 0) FROM learning_sessions '
            f'WHERE user_id = ? AND duration_minutes >= {cfg.MIN_STUDY_MINUTES}'),

        # Same floor as the XP rule: a one-hour "night" is a typo or a nap,
        # and should not unlock an achievement any more than it earns XP.
        'nights_logged': scalar(
            'SELECT COUNT(*) FROM sleep_entries WHERE user_id = ? AND '
            'duration_minutes >= {}'.format(cfg.MIN_SLEEP_MINUTES)),
        'days_at_step_target': scalar(
            'SELECT COUNT(*) FROM lifestyle_days WHERE user_id = ? AND steps >= 8000'),

        'days_food_logged': scalar(
            'SELECT COUNT(DISTINCT date) FROM food_entries WHERE user_id = ?'),
        'recipes': scalar('SELECT COUNT(*) FROM recipes WHERE user_id = ?'),

        'goals_achieved': scalar(
            "SELECT COUNT(*) FROM goals WHERE user_id = ? AND status = 'achieved'"),
        'measured_xp': scalar(
            "SELECT COALESCE(SUM(xp), 0) FROM xp_transactions "
            "WHERE user_id = ? AND evidence = 'measured'"),
    }


def progress_for(entry, ctx):
    """(current, threshold, fraction) for one achievement."""
    threshold = entry.get('threshold') or 1
    current = ctx.get(entry['metric'], 0) or 0
    return current, threshold, min(1.0, current / threshold) if threshold else 0.0


def is_earned(entry, ctx):
    current, threshold, _ = progress_for(entry, ctx)
    return current >= threshold


def evaluate(conn, user_id, ctx):
    """Unlock anything newly earned. Returns the newly-earned entries.

    Awarding the XP is the caller's job, so that this stays a pure decision about
    what was unlocked and the ledger write happens where the connection is being
    committed.
    """
    already = {
        row['badge_code'] for row in conn.execute(
            'SELECT badge_code FROM user_badges WHERE user_id = ?', (user_id,))
    }

    newly_earned = []
    for entry in CATALOGUE:
        if entry['code'] in already:
            continue
        if is_earned(entry, ctx):
            conn.execute(
                'INSERT OR IGNORE INTO user_badges (user_id, badge_code) VALUES (?, ?)',
                (user_id, entry['code']),
            )
            newly_earned.append(entry)

    return newly_earned


def with_progress(conn, user_id, ctx):
    """The whole catalogue, each entry marked earned or with its progress.

    This is what makes an unlock UI possible: a locked achievement can say "18 of
    30 nights" rather than just sitting there greyed out.
    """
    earned = {
        row['badge_code'] for row in conn.execute(
            'SELECT badge_code FROM user_badges WHERE user_id = ?', (user_id,))
    }

    out = []
    for entry in CATALOGUE:
        current, threshold, fraction = progress_for(entry, ctx)
        is_unlocked = entry['code'] in earned
        out.append({
            'code': entry['code'],
            'name': entry['name'],
            'description': entry['description'],
            'category': entry['category'],
            'tier': entry['tier'],
            'xp_reward': entry.get('xp_reward', 0),
            'earned': is_unlocked,
            'current': current if not is_unlocked else threshold,
            'threshold': threshold,
            'progress': 1.0 if is_unlocked else round(fraction, 3),
        })
    return out
