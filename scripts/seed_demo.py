"""Generate realistic demo history for a user.

Dashboards are hard to build against an empty database and impossible to judge
against one - a radar with two days of data tells you nothing about whether the
radar works. This fills an account with plausible history so the UI can be
developed and reviewed without waiting weeks.

The behaviour it simulates is deliberately imperfect: weekends are weaker than
weekdays, some days are missed entirely, wake times drift, and the overall trend
improves slowly. A seed where every day is 100% produces a dashboard that looks
great and proves nothing.

SAFETY. Seeded days are written with source='seed' in daily_log, so they can
always be told apart from real logs and removed again. The script refuses to
touch an account that already has real ('checklist') history unless you pass
--force, because the obvious mistake here is seeding your own live account.

Usage:
    python scripts/seed_demo.py --user demo --days 45
    python scripts/seed_demo.py --user demo --clear
"""
import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as neural_log  # noqa: E402  (path set up above)
import scoring  # noqa: E402


def _weekday_strength(day: date, progress: float) -> float:
    """Probability of completing any given item, 0-1.

    `progress` runs 0 -> 1 across the seeded window, so the person visibly gets
    better over time rather than being uniformly good.
    """
    base = 0.42 + 0.40 * progress          # improves from ~42% to ~82%
    if day.weekday() >= 5:                  # weekends are weaker
        base -= 0.15
    return max(0.05, min(0.97, base))


def _answer_day(items, strength: float, rng: random.Random) -> dict:
    """One day's answers, with the wake time correlated to the rest of the day."""
    responses = {}
    for item in items:
        if item['type'] == 'time':
            options = item.get('options') or []
            if not options:
                continue
            # A strong day tends to start earlier. Not deterministic - the point
            # is correlation, not a rule.
            index = min(len(options) - 1, max(0, int(rng.gauss((1 - strength) * 3, 0.8))))
            responses[item['name']] = options[index]
        elif item['type'] == 'yes-no':
            # Heavier items are the ones people skip first when the day is bad.
            penalty = 0.08 * (item.get('weight', 1) - 1)
            responses[item['name']] = 'Yes' if rng.random() < strength - penalty else 'No'
        elif item['type'] == 'rating':
            responses[item['name']] = str(max(1, min(5, round(1 + strength * 4 + rng.gauss(0, 0.5)))))
        elif item['type'] == 'text':
            responses[item['name']] = ''
    return responses


def clear(conn, user_id: int) -> int:
    """Remove seeded days only, leaving real logs untouched."""
    dates = [row['date'] for row in conn.execute(
        "SELECT date FROM daily_log WHERE user_id = ? AND source = 'seed'", (user_id,))]
    if not dates:
        return 0

    marks = ','.join('?' * len(dates))
    params = [user_id, *dates]
    conn.execute(f'DELETE FROM daily_log WHERE user_id = ? AND date IN ({marks})', params)
    conn.execute(f'DELETE FROM daily_scores WHERE user_id = ? AND date IN ({marks})', params)
    conn.execute(f'DELETE FROM attribute_scores WHERE user_id = ? AND date IN ({marks})', params)
    conn.execute(f'DELETE FROM daily_xp WHERE user_id = ? AND date IN ({marks})', params)
    conn.execute(
        f"DELETE FROM activities WHERE user_id = ? AND activity_name = 'Daily Checklist' "
        f'AND date IN ({marks})', params)
    conn.commit()
    return len(dates)


def seed(conn, user_row, days: int, miss_rate: float, rng: random.Random) -> int:
    user_id = user_row['id']
    paths = neural_log.load_user_paths(user_row)
    path = neural_log.get_selected_path(paths) or {}
    items = path.get('checklist_items', [])
    if not items:
        raise SystemExit('That user has no checklist items on their selected Path.')

    today = date.today()
    written = 0

    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        progress = 1 - (offset / max(days - 1, 1))

        # Missed days matter: a streak that never breaks makes the streak
        # mechanic untestable, and Consistency has nothing to measure.
        if rng.random() < miss_rate:
            continue

        strength = _weekday_strength(day, progress)
        responses = _answer_day(items, strength, rng)
        iso = day.isoformat()

        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO activities (user_id, date, activity_name, description, '
            'duration, progress_score, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (user_id, iso, 'Daily Checklist', 'seeded demo day', 0, 0, ''),
        )
        activity_id = cursor.lastrowid

        completion = neural_log.compute_completion_percent(items, responses)
        neural_log.award_daily_xp(conn, user_id, iso, items, responses,
                                  completion_percent=completion)
        scoring.record_day(
            conn, user_id, iso, items, responses,
            path_id=path.get('id'), path_name=path.get('name'),
            activity_id=activity_id, source='seed',
            self_rating=neural_log._extract_self_rating(items, responses),
        )
        written += 1

    conn.commit()
    scoring.recompute_scores(conn, user_id)
    conn.commit()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True, help='username to seed')
    parser.add_argument('--days', type=int, default=45)
    parser.add_argument('--miss-rate', type=float, default=0.15,
                        help='fraction of days skipped entirely (default 0.15)')
    parser.add_argument('--seed', type=int, default=7, help='RNG seed, for reproducibility')
    parser.add_argument('--clear', action='store_true', help='remove seeded days and exit')
    parser.add_argument('--force', action='store_true',
                        help='seed even if the account has real logged days')
    args = parser.parse_args()

    neural_log.init_db()
    conn = neural_log.get_db_connection()

    user_row = conn.execute('SELECT * FROM users WHERE username = ?', (args.user,)).fetchone()
    if not user_row:
        raise SystemExit(f'No such user: {args.user}')

    if args.clear:
        print(f'Removed {clear(conn, user_row["id"])} seeded days from {args.user}.')
        return

    real_days = conn.execute(
        "SELECT COUNT(*) AS n FROM daily_log WHERE user_id = ? AND source != 'seed'",
        (user_row['id'],),
    ).fetchone()['n']
    if real_days and not args.force:
        raise SystemExit(
            f'{args.user} already has {real_days} real logged day(s). Seeding would mix '
            f'fabricated history into a real account - pass --force if that is genuinely '
            f'what you want.'
        )

    written = seed(conn, user_row, args.days, args.miss_rate, random.Random(args.seed))
    print(f'Seeded {written} of the last {args.days} days for {args.user} '
          f'(source=seed; remove with --clear).')


if __name__ == '__main__':
    main()
