"""Tests for the shipped exercise library.

The library is content, not code, so the risk is not that it crashes - it is that
a sync silently duplicates rows, clobbers a user's own exercises, or deletes one
that somebody has logged sets against.
"""
import json

import pytest

import scoring
from scoring import library


def test_library_file_is_valid_and_complete():
    """The file ships with the app; a typo in it is a broken Training page."""
    exercises = library.load_library()
    assert len(exercises) > 50

    muscles = {'chest', 'back', 'shoulders', 'biceps', 'triceps', 'quads',
               'hamstrings', 'glutes', 'calves', 'core', 'forearms', 'full-body', 'cardio'}
    equipment = {'barbell', 'dumbbell', 'machine', 'cable', 'bodyweight',
                 'kettlebell', 'band', 'none'}

    slugs = set()
    for entry in exercises:
        assert entry['slug'] not in slugs, f"duplicate slug {entry['slug']}"
        slugs.add(entry['slug'])
        assert entry['primary_muscle'] in muscles, entry['slug']
        assert entry['equipment'] in equipment, entry['slug']
        assert entry['category'] in {'strength', 'cardio', 'mobility'}, entry['slug']
        assert entry['difficulty'] in {'beginner', 'intermediate', 'advanced'}, entry['slug']
        assert entry['primary_muscle'] not in entry['secondary_muscles'], entry['slug']
        assert entry['instructions'], entry['slug']


def test_library_covers_every_attribute_training_can_feed():
    """Mobility is what unlocks Agility and cardio is what feeds Stamina. A
    library with neither would leave two attributes permanently unobserved."""
    exercises = library.load_library()
    categories = {entry['category'] for entry in exercises}
    assert {'strength', 'cardio', 'mobility'} <= categories


def test_library_supports_a_home_workout():
    """Someone with no gym has to be able to train. Every muscle group that can
    be trained at home should have at least one no-equipment option."""
    exercises = library.load_library()
    home = [e for e in exercises if e['equipment'] in ('bodyweight', 'none', 'band')]
    covered = {e['primary_muscle'] for e in home}
    for muscle in ('chest', 'back', 'shoulders', 'quads', 'glutes', 'core'):
        assert muscle in covered, f'no home option for {muscle}'


def test_sync_is_idempotent(app_module):
    """init_db runs on every import, so a non-idempotent sync would grow the
    table on every boot."""
    conn = app_module.get_db_connection()
    before = conn.execute(
        'SELECT COUNT(*) AS n FROM exercises WHERE user_id IS NULL').fetchone()['n']
    assert before > 50  # seeded by init_db already

    added, updated, archived = scoring.sync_library(conn)
    assert (added, updated, archived) == (0, 0, 0)

    after = conn.execute(
        'SELECT COUNT(*) AS n FROM exercises WHERE user_id IS NULL').fetchone()['n']
    assert after == before
    conn.close()


def test_sync_updates_a_changed_row_rather_than_duplicating(app_module, tmp_path):
    conn = app_module.get_db_connection()
    source = tmp_path / 'exercises.json'
    source.write_text(json.dumps({'exercises': [{
        'slug': 'barbell-bench-press', 'name': 'Bench Press (revised)',
        'primary_muscle': 'chest', 'secondary_muscles': ['triceps'],
        'equipment': 'barbell', 'category': 'strength', 'difficulty': 'intermediate',
        'is_compound': True, 'instructions': ['Updated cue.'],
    }]}), encoding='utf-8')

    added, updated, _ = scoring.sync_library(conn, path=source)
    assert (added, updated) == (0, 1)

    rows = conn.execute(
        "SELECT name FROM exercises WHERE slug = 'barbell-bench-press'").fetchall()
    assert len(rows) == 1
    assert rows[0]['name'] == 'Bench Press (revised)'
    conn.close()


def test_removed_exercise_is_archived_not_deleted(app_module, tmp_path):
    """Someone may have logged sets against it. Deleting would orphan their
    history; archiving hides it from the picker and keeps the record."""
    conn = app_module.get_db_connection()
    source = tmp_path / 'exercises.json'
    source.write_text(json.dumps({'exercises': [{
        'slug': 'barbell-bench-press', 'name': 'Barbell Bench Press',
        'primary_muscle': 'chest', 'secondary_muscles': [], 'equipment': 'barbell',
        'category': 'strength', 'difficulty': 'intermediate', 'is_compound': True,
        'instructions': ['Press.'],
    }]}), encoding='utf-8')

    _, _, archived = scoring.sync_library(conn, path=source)
    assert archived > 0

    survivors = conn.execute(
        'SELECT COUNT(*) AS n FROM exercises WHERE user_id IS NULL').fetchone()['n']
    assert survivors > 1, 'rows were deleted rather than archived'
    conn.close()


def test_sync_never_touches_a_users_own_exercises(app_module):
    conn = app_module.get_db_connection()
    conn.execute("INSERT INTO users (username, password_hash) VALUES ('owner', 'x')")
    user_id = conn.execute(
        "SELECT id FROM users WHERE username = 'owner'").fetchone()['id']
    conn.execute(
        'INSERT INTO exercises (user_id, slug, name, primary_muscle) '
        'VALUES (?, ?, ?, ?)', (user_id, 'my-lift', 'My Lift', 'chest'))
    conn.commit()

    scoring.sync_library(conn)

    row = conn.execute(
        'SELECT name, archived FROM exercises WHERE user_id = ?', (user_id,)).fetchone()
    assert row['name'] == 'My Lift'
    assert not row['archived']
    conn.close()


def test_a_user_may_reuse_a_library_slug(app_module):
    """Library slugs are globally unique, a user's are unique to them - so
    someone can keep their own variant of a shipped exercise."""
    conn = app_module.get_db_connection()
    conn.execute("INSERT INTO users (username, password_hash) VALUES ('owner2', 'x')")
    user_id = conn.execute(
        "SELECT id FROM users WHERE username = 'owner2'").fetchone()['id']

    conn.execute(
        'INSERT INTO exercises (user_id, slug, name, primary_muscle) '
        'VALUES (?, ?, ?, ?)', (user_id, 'barbell-bench-press', 'My Bench', 'chest'))
    conn.commit()

    rows = conn.execute(
        "SELECT user_id FROM exercises WHERE slug = 'barbell-bench-press'").fetchall()
    assert len(rows) == 2
    conn.close()


def test_missing_library_file_is_survivable(app_module, tmp_path):
    """A missing library is a thin Training page, not a boot failure."""
    conn = app_module.get_db_connection()
    assert scoring.sync_library(conn, path=tmp_path / 'nope.json') == (0, 0, 0)
    conn.close()


# --- movement patterns ------------------------------------------------------

# Kept in step with PATTERNS in frontend/src/components/training/ExerciseAnimation.tsx.
# A pattern here with no drawing there shows no animation; a drawing with no
# exercise is dead code. Neither is fatal, which is exactly why it needs a test -
# the failure is silent on both sides.
ANIMATED_PATTERNS = {
    'horizontal-press', 'vertical-press', 'horizontal-pull', 'vertical-pull',
    'squat', 'hinge', 'lunge', 'curl', 'extension', 'raise', 'fly', 'calf-raise',
    'core-flexion', 'core-brace', 'core-rotation', 'carry', 'cardio-cyclic',
    'mobility',
}


def test_every_exercise_names_a_movement_pattern():
    """The animation is keyed to the pattern, so an exercise without one is an
    exercise that silently shows nothing."""
    from scoring.library import load_library

    missing = [e['name'] for e in load_library() if not e.get('movement_pattern')]
    assert missing == [], f'no movement_pattern: {missing}'


def test_every_pattern_used_has_an_animation():
    """A typo in a pattern name would leave the exercise looking fine in the
    library and blank in the UI."""
    from scoring.library import load_library

    used = {e['movement_pattern'] for e in load_library()}
    assert used <= ANIMATED_PATTERNS, f'no animation drawn for: {sorted(used - ANIMATED_PATTERNS)}'


def test_no_animation_is_drawn_for_nothing():
    """The other direction: a pattern nothing uses is dead art."""
    from scoring.library import load_library

    used = {e['movement_pattern'] for e in load_library()}
    assert ANIMATED_PATTERNS <= used, f'drawn but unused: {sorted(ANIMATED_PATTERNS - used)}'


def test_the_library_covers_every_muscle_group_it_scores():
    """MUSCLE_ATTRIBUTES decides what a logged set feeds. A muscle group with no
    exercises is an attribute nobody can train on purpose."""
    from scoring.config import MUSCLE_ATTRIBUTES
    from scoring.library import load_library

    covered = {e['primary_muscle'] for e in load_library()}
    assert set(MUSCLE_ATTRIBUTES) <= covered, sorted(set(MUSCLE_ATTRIBUTES) - covered)


def test_the_pattern_survives_a_sync(app_module):
    """It is a column like any other - if sync_library drops it, every animation
    disappears the next time the library is re-read."""
    conn = app_module.get_db_connection()
    try:
        rows = conn.execute(
            'SELECT COUNT(*) AS n FROM exercises '
            'WHERE user_id IS NULL AND movement_pattern IS NOT NULL').fetchone()
        total = conn.execute(
            'SELECT COUNT(*) AS n FROM exercises WHERE user_id IS NULL').fetchone()
        assert rows['n'] == total['n'] > 100
    finally:
        conn.close()
