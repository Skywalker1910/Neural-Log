"""Loading the shipped exercise library into the database.

The library is 85 rows of curated content, which is too much to put in a .sql
migration and too important to leave as a manual step - without it the Training
workspace opens to an empty exercise picker.

So it lives in data/exercises.json (version-controlled, reviewable as a diff) and
is synced into the `exercises` table on startup. The sync is idempotent and
matches on slug, so editing a description in the JSON updates the row rather than
creating a second one.

Only library rows (user_id IS NULL) are touched. A user's own exercises are never
modified, and an exercise removed from the JSON is archived rather than deleted -
someone may have logged sets against it, and deleting it would orphan their
history.
"""
import json
from pathlib import Path

LIBRARY_PATH = Path(__file__).resolve().parent.parent / 'data' / 'exercises.json'


def load_library(path=None):
    """Read the library file. Returns [] if it is missing rather than raising -
    a missing library is a degraded app, not a broken one."""
    source = Path(path) if path else LIBRARY_PATH
    if not source.exists():
        return []
    try:
        with source.open('r', encoding='utf-8') as handle:
            return json.load(handle).get('exercises', [])
    except (json.JSONDecodeError, OSError):
        return []


def sync_library(conn, path=None):
    """Insert or update the shipped exercises. Returns (added, updated, archived)."""
    exercises = load_library(path)
    if not exercises:
        return 0, 0, 0

    existing = {
        row['slug']: row
        for row in conn.execute(
            'SELECT id, slug, name, primary_muscle, secondary_muscles, equipment, '
            'category, difficulty, is_compound, instructions, archived '
            'FROM exercises WHERE user_id IS NULL'
        )
    }

    added = updated = 0
    for entry in exercises:
        values = (
            entry['name'],
            entry['primary_muscle'],
            json.dumps(entry.get('secondary_muscles', [])),
            entry.get('equipment'),
            entry.get('category', 'strength'),
            entry.get('difficulty'),
            1 if entry.get('is_compound') else 0,
            json.dumps(entry.get('instructions', [])),
        )

        current = existing.get(entry['slug'])
        if current is None:
            conn.execute(
                'INSERT INTO exercises (user_id, slug, name, primary_muscle, '
                'secondary_muscles, equipment, category, difficulty, is_compound, '
                'instructions) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (entry['slug'], *values),
            )
            added += 1
            continue

        unchanged = (
            current['name'] == values[0]
            and current['primary_muscle'] == values[1]
            and (current['secondary_muscles'] or '[]') == values[2]
            and current['equipment'] == values[3]
            and current['category'] == values[4]
            and current['difficulty'] == values[5]
            and current['is_compound'] == values[6]
            and (current['instructions'] or '[]') == values[7]
            and not current['archived']
        )
        if unchanged:
            continue

        conn.execute(
            'UPDATE exercises SET name = ?, primary_muscle = ?, secondary_muscles = ?, '
            'equipment = ?, category = ?, difficulty = ?, is_compound = ?, '
            'instructions = ?, archived = 0 WHERE id = ?',
            (*values, current['id']),
        )
        updated += 1

    # Anything dropped from the JSON is archived, never deleted: sets may point at
    # it, and deleting would orphan somebody's logged history.
    shipped_slugs = {entry['slug'] for entry in exercises}
    archived = 0
    for slug, row in existing.items():
        if slug not in shipped_slugs and not row['archived']:
            conn.execute('UPDATE exercises SET archived = 1 WHERE id = ?', (row['id'],))
            archived += 1

    conn.commit()
    return added, updated, archived
