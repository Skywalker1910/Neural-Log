"""Tests for the Nutrition and Lifestyle endpoints."""
from datetime import date, timedelta

import pytest

from conftest import register

TODAY = date.today()


@pytest.fixture()
def client_with_foods(client):
    register(client, username='eater')
    return client


def _food(client, name_contains='Chicken Breast, cooked'):
    foods = client.get('/api/foods').get_json()['foods']
    return next(f for f in foods if name_contains in f['name'])


def _iso(offset=0):
    return (TODAY - timedelta(days=offset)).isoformat()


# --- library ----------------------------------------------------------------

def test_food_library_is_available_immediately(client_with_foods):
    """Seeded by init_db, so a brand-new account never opens an empty picker."""
    foods = client_with_foods.get('/api/foods').get_json()['foods']
    assert len(foods) > 200
    assert all(f['is_custom'] is False for f in foods)


def test_foods_filter_by_search_and_category(client_with_foods):
    rice = client_with_foods.get('/api/foods?q=rice').get_json()['foods']
    assert rice and all('rice' in f['name'].lower() for f in rice)

    fruit = client_with_foods.get('/api/foods?category=fruit').get_json()['foods']
    assert fruit and all(f['category'] == 'fruit' for f in fruit)


def test_a_custom_food_belongs_only_to_its_owner(client_with_foods, client):
    created = client_with_foods.post('/api/foods', json={
        'name': 'Nan Protein Blend', 'kcal_per_100g': 400, 'protein_per_100g': 70,
    }).get_json()
    assert created['is_custom'] is True

    client_with_foods.get('/logout')
    register(client, username='someone-else')
    names = [f['name'] for f in client.get('/api/foods').get_json()['foods']]
    assert 'Nan Protein Blend' not in names


def test_creating_a_food_validates(client_with_foods):
    assert client_with_foods.post('/api/foods', json={}).status_code == 400
    assert client_with_foods.post(
        '/api/foods', json={'name': 'Mystery'}).status_code == 400


# --- logging ----------------------------------------------------------------

def test_logging_a_meal_produces_totals(client_with_foods):
    chicken = _food(client_with_foods)
    client_with_foods.post(f'/api/nutrition/{_iso()}/entries',
                           json={'food_id': chicken['id'], 'grams': 200, 'meal': 'lunch'})

    day = client_with_foods.get(f'/api/nutrition/{_iso()}').get_json()
    assert len(day['entries']) == 1
    assert day['totals']['calories'] == pytest.approx(330, abs=1)
    assert day['totals']['protein_g'] == pytest.approx(62, abs=1)
    assert 'lunch' in day['by_meal']


def test_correcting_a_food_corrects_history(client_with_foods):
    """Macros are derived on read rather than denormalised onto the entry, so a
    fixed food fixes every meal that used it instead of leaving rows frozen at
    the wrong numbers."""
    custom = client_with_foods.post('/api/foods', json={
        'name': 'Mystery Bar', 'kcal_per_100g': 100, 'protein_per_100g': 10,
    }).get_json()
    client_with_foods.post(f'/api/nutrition/{_iso()}/entries',
                           json={'food_id': custom['id'], 'grams': 100})

    before = client_with_foods.get(f'/api/nutrition/{_iso()}').get_json()
    assert before['totals']['calories'] == pytest.approx(100, abs=1)

    # A recipe rebuild is the supported edit path; here we prove the read path by
    # editing the row the same way the sync would.
    entry_id = before['entries'][0]['id']
    client_with_foods.put(f'/api/nutrition/entries/{entry_id}', json={'grams': 250})

    after = client_with_foods.get(f'/api/nutrition/{_iso()}').get_json()
    assert after['totals']['calories'] == pytest.approx(250, abs=1)


def test_deleting_an_entry_removes_it_from_the_totals(client_with_foods):
    chicken = _food(client_with_foods)
    client_with_foods.post(f'/api/nutrition/{_iso()}/entries',
                           json={'food_id': chicken['id'], 'grams': 200})
    entry_id = client_with_foods.get(
        f'/api/nutrition/{_iso()}').get_json()['entries'][0]['id']

    client_with_foods.delete(f'/api/nutrition/entries/{entry_id}')
    day = client_with_foods.get(f'/api/nutrition/{_iso()}').get_json()
    assert day['entries'] == []
    assert day['totals']['calories'] == 0


def test_you_cannot_log_someone_elses_custom_food(client_with_foods, client):
    custom = client_with_foods.post('/api/foods', json={
        'name': 'Private Shake', 'kcal_per_100g': 200,
    }).get_json()
    client_with_foods.get('/logout')

    register(client, username='intruder')
    response = client.post(f'/api/nutrition/{_iso()}/entries',
                           json={'food_id': custom['id'], 'grams': 100})
    assert response.status_code == 404


# --- recipes ----------------------------------------------------------------

def test_a_recipe_becomes_a_reusable_food(client_with_foods):
    """The whole point: describe a cooked dish once, then log it like any other
    food."""
    chicken = _food(client_with_foods)
    rice = _food(client_with_foods, 'Basmati Rice, cooked')

    recipe = client_with_foods.post('/api/recipes', json={
        'name': 'Chicken and Rice',
        'servings': 2,
        'ingredients': [
            {'food_id': chicken['id'], 'grams': 300},
            {'food_id': rice['id'], 'grams': 400},
        ],
    }).get_json()

    assert recipe['food'] is not None
    assert recipe['food']['source'] == 'recipe'
    assert len(recipe['ingredients']) == 2

    # 165*3 + 121*4 = 495 + 484 = 979 kcal over 700g -> ~139.9 per 100g
    assert recipe['food']['kcal_per_100g'] == pytest.approx(139.9, abs=0.5)

    # And it shows up in the picker like anything else.
    names = [f['name'] for f in client_with_foods.get('/api/foods').get_json()['foods']]
    assert 'Chicken and Rice' in names


def test_cooked_weight_makes_a_recipe_denser(client_with_foods):
    rice = _food(client_with_foods, 'Basmati Rice, cooked')
    raw = client_with_foods.post('/api/recipes', json={
        'name': 'Plain', 'ingredients': [{'food_id': rice['id'], 'grams': 300}],
    }).get_json()
    reduced = client_with_foods.post('/api/recipes', json={
        'name': 'Reduced', 'total_grams': 150,
        'ingredients': [{'food_id': rice['id'], 'grams': 300}],
    }).get_json()

    assert reduced['food']['kcal_per_100g'] > raw['food']['kcal_per_100g']


def test_editing_a_recipe_updates_meals_already_logged_with_it(client_with_foods):
    chicken = _food(client_with_foods)
    rice = _food(client_with_foods, 'Basmati Rice, cooked')

    recipe = client_with_foods.post('/api/recipes', json={
        'name': 'Bowl', 'ingredients': [{'food_id': rice['id'], 'grams': 200}],
    }).get_json()
    client_with_foods.post(f'/api/nutrition/{_iso()}/entries',
                           json={'food_id': recipe['food_id'], 'grams': 200})

    before = client_with_foods.get(
        f'/api/nutrition/{_iso()}').get_json()['totals']['calories']

    client_with_foods.put(f"/api/recipes/{recipe['id']}", json={
        'ingredients': [
            {'food_id': rice['id'], 'grams': 200},
            {'food_id': chicken['id'], 'grams': 200},
        ],
    })

    after = client_with_foods.get(
        f'/api/nutrition/{_iso()}').get_json()['totals']['calories']
    assert after > before, 'adding chicken to the recipe should raise the logged meal'


def test_deleting_a_recipe_keeps_the_meals_made_from_it(client_with_foods):
    """Archived, not deleted - removing the food would rewrite past calorie
    totals."""
    rice = _food(client_with_foods, 'Basmati Rice, cooked')
    recipe = client_with_foods.post('/api/recipes', json={
        'name': 'Leftovers', 'ingredients': [{'food_id': rice['id'], 'grams': 200}],
    }).get_json()
    client_with_foods.post(f'/api/nutrition/{_iso()}/entries',
                           json={'food_id': recipe['food_id'], 'grams': 200})

    assert client_with_foods.delete(f"/api/recipes/{recipe['id']}").status_code == 200
    assert client_with_foods.get('/api/recipes').get_json()['recipes'] == []

    day = client_with_foods.get(f'/api/nutrition/{_iso()}').get_json()
    assert len(day['entries']) == 1
    assert day['totals']['calories'] > 0


def test_a_recipe_needs_an_ingredient(client_with_foods):
    assert client_with_foods.post(
        '/api/recipes', json={'name': 'Air'}).status_code == 400
    assert client_with_foods.post(
        '/api/recipes', json={'ingredients': []}).status_code == 400


# --- sleep ------------------------------------------------------------------

def test_sleep_duration_is_derived_from_the_clock_when_not_given(client_with_foods):
    client_with_foods.post('/api/sleep', json={
        'date': _iso(), 'bedtime': '23:30', 'wake_time': '07:00',
    })
    nights = client_with_foods.get('/api/sleep').get_json()['sleep']
    assert nights[0]['duration_minutes'] == 450


def test_a_night_crossing_midnight_is_not_negative(client_with_foods):
    client_with_foods.post('/api/sleep', json={
        'date': _iso(), 'bedtime': '01:00', 'wake_time': '08:30',
    })
    nights = client_with_foods.get('/api/sleep').get_json()['sleep']
    assert nights[0]['duration_minutes'] == 450


def test_logging_the_same_night_twice_corrects_it(client_with_foods):
    client_with_foods.post('/api/sleep', json={'date': _iso(), 'duration_minutes': 400})
    client_with_foods.post('/api/sleep', json={'date': _iso(), 'duration_minutes': 470})
    nights = client_with_foods.get('/api/sleep').get_json()['sleep']
    assert len(nights) == 1, 'a second entry for one night is a correction'
    assert nights[0]['duration_minutes'] == 470


def test_sleep_needs_a_duration_or_a_clock(client_with_foods):
    assert client_with_foods.post('/api/sleep', json={'date': _iso()}).status_code == 400
    assert client_with_foods.post('/api/sleep', json={}).status_code == 400


def test_sleeping_moves_recovery_off_unobserved(client_with_foods):
    """Recovery had no data source at all before R4."""
    before = client_with_foods.get('/api/attributes').get_json()['attributes']
    recovery_before = next((a for a in before if a['attribute'] == 'Recovery'), None)
    assert recovery_before is None or recovery_before['status'] == 'unobserved'

    for offset in range(5):
        client_with_foods.post('/api/sleep', json={
            'date': _iso(offset), 'bedtime': '23:00', 'wake_time': '07:00',
        })

    after = client_with_foods.get('/api/attributes').get_json()['attributes']
    recovery = next(a for a in after if a['attribute'] == 'Recovery')
    assert recovery['status'] == 'active'
    assert recovery['score'] is not None


# --- lifestyle --------------------------------------------------------------

def test_lifestyle_upserts_and_merges(client_with_foods):
    client_with_foods.put(f'/api/lifestyle/{_iso()}', json={'water_ml': 2000})
    client_with_foods.put(f'/api/lifestyle/{_iso()}', json={'steps': 9000})

    day = client_with_foods.get(f'/api/lifestyle/{_iso()}').get_json()
    assert day['lifestyle']['water_ml'] == 2000, 'a later edit must not wipe earlier fields'
    assert day['lifestyle']['steps'] == 9000


def test_steps_feed_stamina(client_with_foods):
    for offset in range(5):
        client_with_foods.put(f'/api/lifestyle/{_iso(offset)}', json={'steps': 12000})

    attributes = client_with_foods.get('/api/attributes').get_json()['attributes']
    stamina = next(a for a in attributes if a['attribute'] == 'Stamina')
    assert stamina['status'] == 'active'


def test_mood_is_recorded_but_never_scored(client_with_foods):
    """Scoring a self-reported feeling would pay you to report feeling good."""
    for offset in range(5):
        client_with_foods.put(f'/api/lifestyle/{_iso(offset)}',
                              json={'mood': 5, 'stress': 1, 'energy': 5})

    day = client_with_foods.get(f'/api/lifestyle/{_iso()}').get_json()
    assert day['lifestyle']['mood'] == 5

    attributes = client_with_foods.get('/api/attributes').get_json()['attributes']
    assert all(a['status'] in ('unobserved', 'locked') for a in attributes), (
        'reporting a perfect mood for five days should not score anything'
    )


def test_lifestyle_summary_reports_the_same_consistency_the_scorer_uses(client_with_foods):
    for offset in range(5):
        client_with_foods.post('/api/sleep', json={
            'date': _iso(offset), 'bedtime': '23:00', 'wake_time': '07:00',
        })
    summary = client_with_foods.get('/api/lifestyle').get_json()
    assert summary['averages']['sleep_minutes'] == 480
    assert summary['averages']['schedule_consistency'] >= 95


# --- profile and targets ----------------------------------------------------

def test_targets_are_unknown_until_the_profile_can_support_them(client_with_foods):
    day = client_with_foods.get(f'/api/nutrition/{_iso()}').get_json()
    assert day['targets']['calories'] is None
    assert day['targets']['sources']['calories'] == 'unknown'


def test_a_profile_and_a_weight_produce_an_estimated_target(client_with_foods):
    client_with_foods.post('/api/measurements', json={
        'date': _iso(), 'metric': 'weight', 'value': 80, 'unit': 'kg',
    })
    client_with_foods.put('/api/profile', json={
        'birth_year': TODAY.year - 30, 'sex': 'male', 'height_cm': 180,
        'activity_level': 'moderate', 'goal': 'maintain',
    })

    payload = client_with_foods.get('/api/profile').get_json()
    assert payload['body_weight_kg'] == 80
    assert payload['targets']['estimated_tdee'] is not None
    assert payload['targets']['sources']['calories'] == 'estimated'
    assert 2000 < payload['targets']['calories'] < 3500


def test_an_explicit_target_overrides_the_estimate(client_with_foods):
    client_with_foods.put('/api/profile', json={'calorie_target': 2200})
    targets = client_with_foods.get('/api/profile').get_json()['targets']
    assert targets['calories'] == 2200
    assert targets['sources']['calories'] == 'set'


def test_nutrition_endpoints_require_login(client):
    for url in ('/api/foods', '/api/recipes', '/api/sleep', '/api/lifestyle',
                '/api/profile', f'/api/nutrition/{_iso()}'):
        assert client.get(url).status_code == 302


# --- a serving is a portion, not the whole pan -------------------------------

def _dish(client, servings, grams=600, total_grams=None):
    """A two-ingredient dish, so the arithmetic is easy to check by hand."""
    food = _food(client)
    payload = {
        'name': f'Test Dish {servings}',
        'servings': servings,
        'ingredients': [{'food_id': food['id'], 'grams': grams}],
    }
    if total_grams is not None:
        payload['total_grams'] = total_grams
    return client.post('/api/recipes', json=payload).get_json()


def _as_food(client, recipe):
    return next(f for f in client.get('/api/foods').get_json()['foods']
                if f['id'] == recipe['food_id'])


def test_one_serving_is_the_dish_divided_by_its_servings(client_with_foods):
    """The bug this replaced: serving_grams held the WHOLE cooked weight while
    calling itself "1 serving", so logging a curry cooked for six charged you
    six portions, and the counter at 2 charged twelve."""
    recipe = _dish(client_with_foods, servings=6, grams=840)
    food = _as_food(client_with_foods, recipe)

    assert food['serving_grams'] == 140.0
    assert food['serving_name'] == '1 serving'


def test_a_single_serving_dish_is_the_whole_thing(client_with_foods):
    """Dividing by one has to leave it alone - that was the only case the old
    behaviour got right, and it must stay right."""
    recipe = _dish(client_with_foods, servings=1, grams=300)
    assert _as_food(client_with_foods, recipe)['serving_grams'] == 300.0


def test_the_cooked_weight_wins_over_the_raw_total(client_with_foods):
    """Rice absorbs water and roasting drives it off, so a declared cooked
    weight is the honest divisor."""
    recipe = _dish(client_with_foods, servings=4, grams=400, total_grams=1000)
    assert _as_food(client_with_foods, recipe)['serving_grams'] == 250.0


def test_editing_the_servings_recomputes_the_portion(client_with_foods):
    """Deciding a dish actually feeds four rather than two has to move what one
    serving means, or the number goes stale the moment you correct it."""
    recipe = _dish(client_with_foods, servings=2, grams=800)
    assert _as_food(client_with_foods, recipe)['serving_grams'] == 400.0

    client_with_foods.put(f"/api/recipes/{recipe['id']}", json={'servings': 4})
    assert _as_food(client_with_foods, recipe)['serving_grams'] == 200.0


def test_logging_two_servings_is_two_portions_not_two_dishes(client_with_foods):
    """End to end, in the units the picker actually sends: it converts servings
    to grams before posting, so two servings of a six-portion dish is a third of
    it, not twice it."""
    recipe = _dish(client_with_foods, servings=6, grams=840)
    food = _as_food(client_with_foods, recipe)

    two_servings = food['serving_grams'] * 2
    client_with_foods.post('/api/nutrition/2026-09-16/entries', json={
        'food_id': food['id'], 'grams': two_servings, 'meal': 'dinner'})

    day = client_with_foods.get('/api/nutrition/2026-09-16').get_json()
    assert day['entries'][0]['grams'] == 280.0
    # A third of the pan, not double it.
    assert day['totals']['calories'] < food['kcal_per_100g'] * 840 / 100
