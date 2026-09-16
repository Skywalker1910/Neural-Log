"""Loading the shipped food library into the database.

Same reasoning as library.py does for exercises: 233 rows of curated content is
too much for a .sql migration and too important to leave as a manual step, so it
lives in data/foods.json and syncs on startup.

Only library rows (user_id IS NULL) are touched. A user's own foods and recipes
are never modified, and a food dropped from the JSON is archived rather than
deleted - someone may have logged a meal against it, and deleting it would orphan
their history and silently change past calorie totals.
"""
import json
from pathlib import Path

LIBRARY_PATH = Path(__file__).resolve().parent.parent / 'data' / 'foods.json'


def load_foods(path=None):
    """Read the library file. Returns [] if missing rather than raising - a
    missing library is a degraded app, not a broken one."""
    source = Path(path) if path else LIBRARY_PATH
    if not source.exists():
        return []
    try:
        with source.open('r', encoding='utf-8') as handle:
            return json.load(handle).get('foods', [])
    except (json.JSONDecodeError, OSError):
        return []


def sync_foods(conn, path=None):
    """Insert or update the shipped foods. Returns (added, updated, archived)."""
    foods = load_foods(path)
    if not foods:
        return 0, 0, 0

    existing = {
        row['slug']: row
        for row in conn.execute(
            'SELECT id, slug, name, category, kcal_per_100g, protein_per_100g, '
            'carbs_per_100g, fat_per_100g, fibre_per_100g, serving_name, '
            'serving_grams, unit, archived FROM foods WHERE user_id IS NULL'
        )
    }

    added = updated = 0
    for entry in foods:
        values = (
            entry['name'],
            entry.get('category', 'prepared'),
            float(entry['kcal']),
            float(entry.get('protein', 0)),
            float(entry.get('carbs', 0)),
            float(entry.get('fat', 0)),
            float(entry.get('fibre', 0)),
            entry.get('serving_name'),
            float(entry['serving_grams']) if entry.get('serving_grams') else None,
            entry.get('unit') or 'g',
        )

        current = existing.get(entry['slug'])
        if current is None:
            conn.execute(
                'INSERT INTO foods (user_id, slug, source, name, category, '
                'kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, '
                'fibre_per_100g, serving_name, serving_grams, unit) '
                "VALUES (NULL, ?, 'library', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entry['slug'], *values),
            )
            added += 1
            continue

        unchanged = (
            current['name'] == values[0]
            and current['category'] == values[1]
            and current['kcal_per_100g'] == values[2]
            and current['protein_per_100g'] == values[3]
            and current['carbs_per_100g'] == values[4]
            and current['fat_per_100g'] == values[5]
            and current['fibre_per_100g'] == values[6]
            and current['serving_name'] == values[7]
            and current['serving_grams'] == values[8]
            and current['unit'] == values[9]
            and not current['archived']
        )
        if unchanged:
            continue

        conn.execute(
            'UPDATE foods SET name = ?, category = ?, kcal_per_100g = ?, '
            'protein_per_100g = ?, carbs_per_100g = ?, fat_per_100g = ?, '
            'fibre_per_100g = ?, serving_name = ?, serving_grams = ?, unit = ?, '
            'archived = 0 '
            'WHERE id = ?',
            (*values, current['id']),
        )
        updated += 1

    shipped = {entry['slug'] for entry in foods}
    archived = 0
    for slug, row in existing.items():
        if slug not in shipped and not row['archived']:
            conn.execute('UPDATE foods SET archived = 1 WHERE id = ?', (row['id'],))
            archived += 1

    conn.commit()
    return added, updated, archived
