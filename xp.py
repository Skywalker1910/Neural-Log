"""The XP ledger: what you earned, from what, and why.

WHY A DAY IS REBUILT RATHER THAN APPENDED TO
--------------------------------------------
Every award function here works on a whole (user, date) and replaces that day's
rows. That is not laziness - it is what makes the daily caps correct.

A cap is a statement about a day. Applying one while inserting rows one at a time
means each insert has to know what the rest of the day already holds, and any
edit to an earlier action leaves the cap computed against stale data. Rebuilding
the day sidesteps the whole class of bug, exactly as `recompute_scores` does for
attributes, and makes re-saving a workout idempotent for free.

WHY `daily_xp` IS STILL WRITTEN
-------------------------------
The leaderboard, `/api/gamification/summary` and the legacy Jinja app all read
it. The ledger is the authority; `daily_xp` is kept as a per-day rollup so those
three keep working - the same compatibility approach R6 used for Paths.
"""
import sqlite3
from datetime import date as _date

import xp_config as cfg

SOURCES = ('checklist', 'training', 'nutrition', 'lifestyle', 'learning', 'badge')


# --- level curve -------------------------------------------------------------

def xp_for_level(level):
    """Cumulative XP required to reach a level. Level 1 is the start, so 0."""
    return cfg.LEVEL_CURVE_FACTOR * ((level - 1) ** cfg.LEVEL_CURVE_EXPONENT)


def compute_level(total_xp):
    """(level, xp_into_current_level, xp_needed_for_next_level)."""
    level = 1
    while xp_for_level(level + 1) <= total_xp:
        level += 1
    return level, total_xp - xp_for_level(level), xp_for_level(level + 1) - xp_for_level(level)


def total_xp(conn, user_id):
    """Authoritative total, summed from the ledger."""
    row = conn.execute(
        'SELECT COALESCE(SUM(xp), 0) AS total FROM xp_transactions WHERE user_id = ?',
        (user_id,),
    ).fetchone()
    return row['total'] if row else 0


# --- gathering what a day earned ---------------------------------------------

def _award(source, key, reason, base, evidence='measured'):
    return {
        'source': source, 'source_key': key, 'reason': reason,
        'base_xp': int(round(base)), 'evidence': evidence,
    }


def _training_awards(conn, user_id, day):
    """One award per finished session, sized by what is actually in it."""
    sessions = conn.execute(
        'SELECT id, name FROM workout_sessions WHERE user_id = ? AND date = ?',
        (user_id, day),
    ).fetchall()

    awards = []
    for session in sessions:
        rows = conn.execute(
            '''
            SELECT x.weight, x.reps, x.duration_seconds, x.is_warmup, e.category
            FROM exercise_sets x JOIN exercises e ON e.id = x.exercise_id
            WHERE x.session_id = ?
            ''',
            (session['id'],),
        ).fetchall()

        working = [r for r in rows if not r['is_warmup']]
        if len(working) < cfg.MIN_WORKING_SETS:
            continue  # an empty session is not a session

        base = 0.0
        strength_sets = 0
        for row in working:
            minutes = (row['duration_seconds'] or 0) / 60.0
            if row['category'] == 'cardio':
                base += minutes * cfg.XP_PER_CARDIO_MINUTE
            elif row['category'] == 'mobility':
                base += max(minutes, 2.0) * cfg.XP_PER_MOBILITY_MINUTE
            else:
                base += cfg.XP_PER_WORKING_SET
                strength_sets += 1

        if base <= 0:
            continue

        detail = f'{len(working)} sets' if strength_sets else f'{len(working)} logged'
        awards.append(_award(
            'training', f'workout:{session["id"]}',
            f'{session["name"] or "Workout"} - {detail}', base,
        ))
    return awards


def _learning_awards(conn, user_id, day):
    rows = conn.execute(
        'SELECT id, duration_minutes, started_at FROM learning_sessions '
        'WHERE user_id = ? AND date = ?',
        (user_id, day),
    ).fetchall()

    awards = []
    for row in rows:
        minutes = row['duration_minutes'] or 0
        if minutes < cfg.MIN_STUDY_MINUTES:
            continue

        base = (minutes / 10.0) * cfg.XP_PER_STUDY_10_MINUTES
        reason = f'Studied {minutes} min'
        if minutes >= cfg.DEEP_BLOCK_MINUTES:
            base += cfg.XP_DEEP_BLOCK_BONUS
            reason += ' (deep block)'

        awards.append(_award('learning', f'session:{row["id"]}', reason, base))
    return awards


def _nutrition_awards(conn, user_id, day, targets):
    entries = conn.execute(
        '''
        SELECT COUNT(*) AS n,
               SUM(f.kcal_per_100g    * e.grams / 100.0) AS calories,
               SUM(f.protein_per_100g * e.grams / 100.0) AS protein
        FROM food_entries e JOIN foods f ON f.id = e.food_id
        WHERE e.user_id = ? AND e.date = ?
        ''',
        (user_id, day),
    ).fetchone()

    if not entries or (entries['n'] or 0) < cfg.MIN_FOOD_ENTRIES:
        return []

    awards = [_award('nutrition', 'meals', f'Logged {entries["n"]} items', cfg.XP_MEALS_LOGGED)]

    calorie_target = (targets or {}).get('calories')
    if calorie_target and entries['calories']:
        # The same tolerance band the adherence producer uses, so the two cannot
        # disagree about whether you hit your target.
        tolerance = calorie_target * 0.10
        if abs(entries['calories'] - calorie_target) <= tolerance:
            awards.append(_award('nutrition', 'calories', 'Hit your calorie target',
                                 cfg.XP_CALORIE_TARGET_MET))

    protein_target = (targets or {}).get('protein_g')
    if protein_target and (entries['protein'] or 0) >= protein_target:
        awards.append(_award('nutrition', 'protein', 'Hit your protein target',
                             cfg.XP_PROTEIN_TARGET_MET))
    return awards


def _lifestyle_awards(conn, user_id, day, targets):
    awards = []

    sleep = conn.execute(
        'SELECT duration_minutes FROM sleep_entries WHERE user_id = ? AND date = ?',
        (user_id, day),
    ).fetchone()
    if sleep and (sleep['duration_minutes'] or 0) >= cfg.MIN_SLEEP_MINUTES:
        awards.append(_award('lifestyle', 'sleep', 'Logged a night', cfg.XP_SLEEP_LOGGED))
        target = (targets or {}).get('sleep_minutes') or 480
        if sleep['duration_minutes'] >= target:
            awards.append(_award('lifestyle', 'sleep-target', 'Slept your target',
                                 cfg.XP_SLEEP_TARGET_MET))

    lifestyle = conn.execute(
        'SELECT water_ml, steps FROM lifestyle_days WHERE user_id = ? AND date = ?',
        (user_id, day),
    ).fetchone()
    if lifestyle:
        water_target = (targets or {}).get('water_ml') or 2500
        if (lifestyle['water_ml'] or 0) >= water_target:
            awards.append(_award('lifestyle', 'water', 'Hit your water target',
                                 cfg.XP_WATER_TARGET_MET))

        step_target = (targets or {}).get('steps') or 8000
        if (lifestyle['steps'] or 0) >= step_target:
            awards.append(_award('lifestyle', 'steps', 'Hit your step target',
                                 cfg.XP_STEPS_TARGET_MET))
    return awards


def _checklist_award(conn, user_id, day, base_xp, evidenced_sources):
    """The daily checklist, discounted where the day also holds evidence.

    A ticked "Did you complete strength training today?" alongside a logged
    session is one behaviour being paid for twice. The logged session is the
    better record, so it keeps its full rate and the claim is discounted - not
    removed, because filling the checklist in is still the daily ritual the whole
    app is built around.
    """
    if base_xp <= 0:
        return []

    if evidenced_sources:
        discounted = base_xp * cfg.EVIDENCE_DISCOUNT
        reason = ('Daily checklist (reduced - the same day was also logged in '
                  + ', '.join(sorted(evidenced_sources)) + ')')
        return [_award('checklist', 'checklist', reason, discounted, evidence='claimed')]

    return [_award('checklist', 'checklist', 'Daily checklist', base_xp,
                   evidence='claimed')]


# --- the rebuild -------------------------------------------------------------

def recompute_day(conn, user_id, day, checklist_base_xp=None, targets=None,
                  streak=0):
    """Rebuild one day's ledger from scratch. Returns the day's total XP.

    `checklist_base_xp` is passed in rather than recomputed here because it
    depends on the user's live habit list, which app.py already has in hand at
    the point it calls this.
    """
    if checklist_base_xp is None:
        existing = conn.execute(
            'SELECT base_xp FROM daily_xp WHERE user_id = ? AND date = ?',
            (user_id, day),
        ).fetchone()
        checklist_base_xp = existing['base_xp'] if existing else 0

    measured = (
        _training_awards(conn, user_id, day)
        + _learning_awards(conn, user_id, day)
        + _nutrition_awards(conn, user_id, day, targets)
        + _lifestyle_awards(conn, user_id, day, targets)
    )
    evidenced_sources = {award['source'] for award in measured}
    awards = measured + _checklist_award(
        conn, user_id, day, checklist_base_xp, evidenced_sources)

    awards = _apply_caps(awards)

    multiplier_pct = min(streak * cfg.STREAK_MULTIPLIER_PCT_PER_DAY,
                         cfg.STREAK_MULTIPLIER_CAP_PCT)

    conn.execute(
        "DELETE FROM xp_transactions WHERE user_id = ? AND date = ? AND source != 'badge'",
        (user_id, day),
    )

    day_total = 0
    for award in awards:
        final = int(round(award['base_xp'] * (1 + multiplier_pct / 100)))
        day_total += final
        conn.execute(
            'INSERT INTO xp_transactions (user_id, date, source, source_key, reason, '
            'base_xp, multiplier_pct, xp, capped_from, evidence) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) '
            'ON CONFLICT(user_id, date, source_key) DO UPDATE SET '
            'source = excluded.source, reason = excluded.reason, '
            'base_xp = excluded.base_xp, multiplier_pct = excluded.multiplier_pct, '
            'xp = excluded.xp, capped_from = excluded.capped_from, '
            'evidence = excluded.evidence',
            (user_id, day, award['source'], award['source_key'], award['reason'],
             award['base_xp'], multiplier_pct, final, award.get('capped_from'),
             award['evidence']),
        )

    # Badge awards already live in the ledger and are not rebuilt, but they do
    # count toward the day's rollup.
    badge_total = conn.execute(
        "SELECT COALESCE(SUM(xp), 0) AS n FROM xp_transactions "
        "WHERE user_id = ? AND date = ? AND source = 'badge'",
        (user_id, day),
    ).fetchone()['n']

    _write_rollup(conn, user_id, day, checklist_base_xp, multiplier_pct,
                  day_total + badge_total)
    return day_total + badge_total


def _apply_caps(awards):
    """Per-source caps, then a whole-day ceiling.

    Applied largest-first within a source so that when a cap bites it is the
    marginal action that loses value, not an arbitrary one.
    """
    capped = []
    for source in SOURCES:
        group = sorted([a for a in awards if a['source'] == source],
                       key=lambda a: -a['base_xp'])
        limit = cfg.DAILY_SOURCE_CAPS.get(source)
        running = 0
        for award in group:
            if limit is None:
                capped.append(award)
                continue
            allowed = max(0, limit - running)
            if award['base_xp'] > allowed:
                award = {**award, 'capped_from': award['base_xp'], 'base_xp': allowed}
            running += award['base_xp']
            if award['base_xp'] > 0 or award.get('capped_from'):
                capped.append(award)

    total = sum(a['base_xp'] for a in capped)
    if total <= cfg.DAILY_TOTAL_CAP:
        return capped

    # Over the day ceiling: scale everything down proportionally rather than
    # truncating whichever happened to be last, so no single source is singled
    # out for an overage they all contributed to.
    scale = cfg.DAILY_TOTAL_CAP / total
    scaled = []
    for award in capped:
        reduced = int(award['base_xp'] * scale)
        scaled.append({**award,
                       'capped_from': award.get('capped_from') or award['base_xp'],
                       'base_xp': reduced})
    return scaled


def _write_rollup(conn, user_id, day, checklist_base_xp, multiplier_pct, day_total):
    """Keep daily_xp in step, since the leaderboard and legacy API read it.

    `base_xp` keeps the meaning it had before R7: the CHECKLIST's base, not the
    day's total across sources. That distinction is load-bearing, because
    recompute_day() reads this column back when no checklist figure is passed in.

    Writing the day's full base here created a feedback loop: a workout's XP was
    summed into base_xp, then read back on the next rebuild as if it were
    checklist XP, so deleting the workout left its value behind re-labelled as a
    checklist award.
    """
    base = int(round(checklist_base_xp or 0))
    conn.execute(
        'INSERT INTO daily_xp (user_id, date, base_xp, streak_multiplier_pct, total_xp) '
        'VALUES (?, ?, ?, ?, ?) '
        'ON CONFLICT(user_id, date) DO UPDATE SET base_xp = excluded.base_xp, '
        'streak_multiplier_pct = excluded.streak_multiplier_pct, '
        'total_xp = excluded.total_xp',
        (user_id, day, base, multiplier_pct, day_total),
    )


def award_achievement(conn, user_id, code, name, xp_reward, day=None):
    """Write an achievement's XP into the ledger.

    Uncapped and never rebuilt: an achievement is one-off by definition, and a
    cap would mean unlocking two in a day silently discarded one.
    """
    if xp_reward <= 0:
        return 0
    day = day or _date.today().isoformat()
    try:
        conn.execute(
            'INSERT INTO xp_transactions (user_id, date, source, source_key, reason, '
            "base_xp, multiplier_pct, xp, evidence) "
            "VALUES (?, ?, 'badge', ?, ?, ?, 0, ?, 'measured')",
            (user_id, day, f'badge:{code}', f'Achievement: {name}', xp_reward, xp_reward),
        )
    except sqlite3.IntegrityError:
        return 0  # already awarded
    return xp_reward


# --- reading it back ---------------------------------------------------------

def backfill_from_daily_xp(conn):
    """Seed the ledger from historical daily_xp rows. Returns rows written.

    Without this, R7 is a silent data loss: get_user_total_xp() reads the ledger
    from now on, so every day earned before this migration would simply stop
    counting and everyone's level would drop.

    Each historical day becomes a single 'checklist' entry, because that is
    honestly all the old schema knew - daily_xp stored one opaque total with no
    record of where it came from, and inventing a per-source breakdown for it
    would be fabricating detail that was never captured.

    Idempotent: days already represented in the ledger are skipped, so it is safe
    to run on every startup.
    """
    rows = conn.execute(
        '''
        SELECT d.user_id, d.date, d.base_xp, d.streak_multiplier_pct, d.total_xp
        FROM daily_xp d
        WHERE NOT EXISTS (
            SELECT 1 FROM xp_transactions t
            WHERE t.user_id = d.user_id AND t.date = d.date
        )
        ''',
    ).fetchall()

    written = 0
    for row in rows:
        if (row['total_xp'] or 0) <= 0:
            continue
        conn.execute(
            'INSERT INTO xp_transactions (user_id, date, source, source_key, reason, '
            "base_xp, multiplier_pct, xp, evidence) "
            "VALUES (?, ?, 'checklist', 'checklist', ?, ?, ?, ?, 'claimed') "
            'ON CONFLICT(user_id, date, source_key) DO NOTHING',
            (row['user_id'], row['date'], 'Daily checklist (before the XP ledger)',
             row['base_xp'] or row['total_xp'], row['streak_multiplier_pct'] or 0,
             row['total_xp']),
        )
        written += 1

    if written:
        conn.commit()
    return written


def ledger(conn, user_id, limit=50):
    rows = conn.execute(
        'SELECT * FROM xp_transactions WHERE user_id = ? '
        'ORDER BY date DESC, id DESC LIMIT ?',
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def by_source(conn, user_id, days=30):
    """Where the XP actually came from - the question daily_xp could not answer."""
    rows = conn.execute(
        '''
        SELECT source, COALESCE(SUM(xp), 0) AS xp, COUNT(*) AS entries
        FROM xp_transactions
        WHERE user_id = ? AND date >= date('now', ?)
        GROUP BY source ORDER BY xp DESC
        ''',
        (user_id, f'-{days} days'),
    ).fetchall()
    return [dict(row) for row in rows]


def evidence_split(conn, user_id):
    """How much of a total was evidenced rather than claimed."""
    rows = conn.execute(
        'SELECT evidence, COALESCE(SUM(xp), 0) AS xp FROM xp_transactions '
        'WHERE user_id = ? GROUP BY evidence',
        (user_id,),
    ).fetchall()
    return {row['evidence']: row['xp'] for row in rows}
