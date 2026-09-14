"""Nutrition arithmetic: energy expenditure, targets, and daily totals.

Pure functions, no database and no Flask - the same split as engine.py, and for
the same reason: this is the part that has to be testable and re-tunable without
standing an app up.

ON CALLING ANY OF THIS AN ESTIMATE
----------------------------------
Every number here except the totals is a population-level approximation applied
to one person. Mifflin-St Jeor has a standard error around 10%, and activity
multipliers are coarser still. The brief asks for energy balance, so the app
computes it - but `estimated: True` rides along with every figure so the UI can
never present it as a measurement, and `tdee()` returns None rather than guessing
when the inputs it needs are missing.

That last part matters: an app that invents a TDEE from defaults would then show
you a confident surplus or deficit against a number it made up.
"""

# Mifflin-St Jeor is the default because it outperforms Harris-Benedict on modern
# populations and needs nothing a phone cannot ask for.
SEX_OFFSET = {
    'male': 5,
    'female': -161,
    # Halfway between the two. Someone who declines to state should get a usable
    # estimate rather than no feature, with the error split rather than assumed
    # in one direction.
    'unspecified': -78,
}

ACTIVITY_MULTIPLIERS = {
    'sedentary': 1.2,      # desk job, little deliberate movement
    'light': 1.375,        # light exercise 1-3 days a week
    'moderate': 1.55,      # 3-5 days a week
    'active': 1.725,       # 6-7 days a week
    'very-active': 1.9,    # hard daily training or a physical job
}

# Applied to TDEE. Percentages rather than flat calorie offsets so the adjustment
# scales with body size - a flat -500 is a far harsher cut for a 55kg person than
# for a 100kg one.
GOAL_MULTIPLIERS = {
    'cut': 0.80,
    'maintain': 1.0,
    'bulk': 1.10,
}

# Grams of protein per kg of body weight. Higher on a cut, where protein protects
# lean mass against the deficit.
PROTEIN_PER_KG = {
    'cut': 2.0,
    'maintain': 1.6,
    'bulk': 1.8,
}

FAT_FRACTION_OF_CALORIES = 0.25
KCAL_PER_G = {'protein': 4, 'carbs': 4, 'fat': 9}


def bmr(weight_kg, height_cm, age, sex='unspecified'):
    """Basal metabolic rate, Mifflin-St Jeor. None if anything needed is missing."""
    if not weight_kg or not height_cm or not age:
        return None
    if weight_kg <= 0 or height_cm <= 0 or age <= 0:
        return None
    offset = SEX_OFFSET.get((sex or 'unspecified').lower(), SEX_OFFSET['unspecified'])
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + offset


def tdee(weight_kg, height_cm, age, sex='unspecified', activity_level='moderate'):
    """Total daily energy expenditure. None when BMR is not computable."""
    base = bmr(weight_kg, height_cm, age, sex)
    if base is None:
        return None
    multiplier = ACTIVITY_MULTIPLIERS.get(activity_level, ACTIVITY_MULTIPLIERS['moderate'])
    return base * multiplier


def age_from_birth_year(birth_year, today):
    """Whole years, from a birth year alone.

    Only the year is collected - a full date of birth is more personal data than
    a calorie estimate justifies, and the resulting error is at most one year,
    which moves BMR by 5 kcal.
    """
    if not birth_year:
        return None
    age = today.year - int(birth_year)
    return age if 0 < age < 130 else None


def resolve_targets(profile, weight_kg, today):
    """Work out the day's targets from the profile, filling gaps from the estimate.

    Returns a dict where every value is either what the user explicitly set or a
    derivation from their TDEE, plus `sources` recording which - so the UI can
    show "2,480 kcal (estimated)" honestly rather than implying you chose it.

    Calories, protein, carbs and fat all fall back to None when there is no TDEE
    and nothing was set by hand. Water, steps, fibre and sleep have sensible
    fixed defaults instead, because those do not depend on body composition.
    """
    profile = profile or {}
    goal = profile.get('goal') or 'maintain'

    age = age_from_birth_year(profile.get('birth_year'), today)
    estimated_tdee = tdee(
        weight_kg,
        profile.get('height_cm'),
        age,
        profile.get('sex'),
        profile.get('activity_level') or 'moderate',
    )

    sources = {}

    calorie_target = profile.get('calorie_target')
    if calorie_target:
        sources['calories'] = 'set'
    elif estimated_tdee is not None:
        calorie_target = round(estimated_tdee * GOAL_MULTIPLIERS.get(goal, 1.0))
        sources['calories'] = 'estimated'
    else:
        sources['calories'] = 'unknown'

    protein_target = profile.get('protein_target_g')
    if protein_target:
        sources['protein'] = 'set'
    elif weight_kg:
        protein_target = round(weight_kg * PROTEIN_PER_KG.get(goal, 1.6))
        sources['protein'] = 'estimated'
    else:
        sources['protein'] = 'unknown'

    fat_target = profile.get('fat_target_g')
    if fat_target:
        sources['fat'] = 'set'
    elif calorie_target:
        fat_target = round(calorie_target * FAT_FRACTION_OF_CALORIES / KCAL_PER_G['fat'])
        sources['fat'] = 'estimated'
    else:
        sources['fat'] = 'unknown'

    carb_target = profile.get('carb_target_g')
    if carb_target:
        sources['carbs'] = 'set'
    elif calorie_target and protein_target and fat_target:
        # Carbohydrate is the remainder, not an independent target: it is what is
        # left of the calorie budget once protein and fat are allocated.
        remaining = (calorie_target
                     - protein_target * KCAL_PER_G['protein']
                     - fat_target * KCAL_PER_G['fat'])
        carb_target = max(0, round(remaining / KCAL_PER_G['carbs']))
        sources['carbs'] = 'estimated'
    else:
        sources['carbs'] = 'unknown'

    return {
        'calories': calorie_target,
        'protein_g': protein_target,
        'carbs_g': carb_target,
        'fat_g': fat_target,
        'fibre_g': profile.get('fibre_target_g') or 30,
        'water_ml': profile.get('water_target_ml') or 2500,
        'steps': profile.get('step_target') or 8000,
        'sleep_minutes': profile.get('sleep_target_minutes') or 480,
        'estimated_tdee': round(estimated_tdee) if estimated_tdee is not None else None,
        'estimated_bmr': (round(bmr(weight_kg, profile.get('height_cm'), age, profile.get('sex')))
                          if estimated_tdee is not None else None),
        'goal': goal,
        'sources': sources,
    }


def entry_macros(food, grams):
    """What one logged portion contributes. `food` holds per-100g values."""
    factor = (grams or 0) / 100.0
    return {
        'calories': (food.get('kcal_per_100g') or 0) * factor,
        'protein_g': (food.get('protein_per_100g') or 0) * factor,
        'carbs_g': (food.get('carbs_per_100g') or 0) * factor,
        'fat_g': (food.get('fat_per_100g') or 0) * factor,
        'fibre_g': (food.get('fibre_per_100g') or 0) * factor,
    }


def total_macros(entries):
    """Sum a day's entries. Each entry is a mapping with a food and grams."""
    totals = {'calories': 0.0, 'protein_g': 0.0, 'carbs_g': 0.0,
              'fat_g': 0.0, 'fibre_g': 0.0}
    for entry in entries:
        for key, value in entry_macros(entry, entry.get('grams')).items():
            totals[key] += value
    return totals


def recipe_per_100g(ingredients, total_grams=None):
    """Collapse a recipe's ingredients into per-100g values for the food row.

    `total_grams` is the COOKED weight where it is known, and it is not the sum of
    the raw ingredients: rice roughly triples, a sauce reduces, roasting drives
    off water. Dividing by the raw sum when a dish lost a third of its mass would
    understate its density by a third and quietly under-report every meal made
    from it.

    Falling back to the raw sum is the honest default when the cooked weight was
    not measured - it is right for anything assembled rather than cooked, and the
    UI asks for the cooked weight where it matters.
    """
    totals = {'calories': 0.0, 'protein_g': 0.0, 'carbs_g': 0.0,
              'fat_g': 0.0, 'fibre_g': 0.0}
    raw_grams = 0.0

    for ingredient in ingredients:
        grams = ingredient.get('grams') or 0
        raw_grams += grams
        for key, value in entry_macros(ingredient, grams).items():
            totals[key] += value

    basis = total_grams if total_grams and total_grams > 0 else raw_grams
    if basis <= 0:
        return None

    factor = 100.0 / basis
    return {
        'kcal_per_100g': round(totals['calories'] * factor, 2),
        'protein_per_100g': round(totals['protein_g'] * factor, 2),
        'carbs_per_100g': round(totals['carbs_g'] * factor, 2),
        'fat_per_100g': round(totals['fat_g'] * factor, 2),
        'fibre_per_100g': round(totals['fibre_g'] * factor, 2),
        'total_grams': basis,
    }
