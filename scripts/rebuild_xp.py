"""Rebuild the XP ledger across a user's whole history.

WHY THIS IS A SCRIPT AND NOT AUTOMATIC
--------------------------------------
R7 made every workspace earn XP. Before it, only the daily checklist did - so a
workout logged last week earned nothing, while the identical workout logged
tomorrow earns 16.

Two defensible positions, and the app deliberately does not pick for you:

  Leave history alone   Totals keep the meaning they had when they were earned.
                        Past activity stays unpaid; only new days earn from the
                        new sources. Nobody's level moves.

  Rebuild everything    Past activity is paid at today's rates, which is fairer
                        in the sense that it reflects what people actually did -
                        but it moves levels and reorders the leaderboard, and it
                        does so silently unless someone chose it.

Running this is choosing the second. It is reversible only in the sense that you
can run it again after changing the rates; it will not restore the old totals.

    python scripts/rebuild_xp.py --user AdityaMore
    python scripts/rebuild_xp.py --all --dry-run
"""
import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--user', help='username to rebuild')
    group.add_argument('--all', action='store_true', help='every user')
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would change without writing')
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)
    import app as neural_log

    conn = neural_log.get_db_connection()

    if args.all:
        users = conn.execute('SELECT id, username FROM users ORDER BY id').fetchall()
    else:
        users = conn.execute('SELECT id, username FROM users WHERE username = ?',
                             (args.user,)).fetchall()
        if not users:
            print(f'No such user: {args.user}')
            return 1

    for user in users:
        before = neural_log.xp.total_xp(conn, user['id'])
        dates = neural_log._dates_with_activity(conn, user['id'])

        if args.dry_run:
            print(f"{user['username']:<14} {before:>6} XP over {len(dates)} dates "
                  f'(dry run - nothing written)')
            continue

        for day in dates:
            neural_log.recompute_xp_day(conn, user['id'], day)
        conn.commit()

        # Evaluate achievements after the rebuild, not during it.
        #
        # recompute_xp_day only rebuilds XP; unlocking happens on the write paths
        # that call recompute_after_change. A rebuild that skipped this left the
        # catalogue stale - seven logged workouts with "Logged your first
        # workout" still showing as locked, reading "7 of 1".
        unlocked = neural_log.evaluate_badges(conn, user['id'])
        conn.commit()

        after = neural_log.xp.total_xp(conn, user['id'])
        level_before = neural_log.compute_level(before)[0]
        level_after = neural_log.compute_level(after)[0]
        arrow = '->' if after != before else '=='
        unlocked_note = f'   +{len(unlocked)} unlocked' if unlocked else ''
        print(f"{user['username']:<14} {before:>6} {arrow} {after:<6} XP   "
              f'level {level_before} {arrow} {level_after}   '
              f'({len(dates)} dates){unlocked_note}')

    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
