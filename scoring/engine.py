"""Turning logged behaviour into attribute scores.

THE CENTRAL IDEA - the opportunity denominator
----------------------------------------------
An attribute scores `earned_credit / available_credit`, where available credit
comes only from items that actually feed that attribute. So an attribute nothing
in your Path feeds is *unobserved*, not zero - which is what makes it honest to
show an attribute as locked instead of inventing a number for it.

It also removes the need for artificial score ceilings. When R3 adds measured
workout signals, those enlarge Strength's denominator, so someone who only ticks
a checkbox naturally sits lower than someone who also logs real training - no
hard-coded cap required, and no retroactive rewrite of what the number means.

Everything here is a pure function over plain dicts: no database, no Flask, no
imports from app. Persistence is the caller's job.
"""
from .config import (
    ATTRIBUTES,
    DEFAULT_CONFIG,
    ICON_ATTRIBUTES,
    KEYWORD_ATTRIBUTES,
    LOCKED_UNTIL,
)

# Bump when a formula changes, so stored scores record which engine produced them
# and a recompute can be told apart from an original.
ENGINE_VERSION = 1


def resolve_item_attributes(item):
    """Which attributes an item feeds, as {attribute: share}.

    Three tiers, most explicit first:
      1. an explicit per-item `attributes` override,
      2. the curated icon vocabulary,
      3. keyword match on the item name.
    Returns {} when nothing matches - the item then contributes to no attribute
    rather than being dumped into a catch-all.
    """
    explicit = item.get('attributes')
    if isinstance(explicit, dict) and explicit:
        return {k: float(v) for k, v in explicit.items() if k in ATTRIBUTES}

    icon = (item.get('icon') or '').strip()
    if icon in ICON_ATTRIBUTES:
        return dict(ICON_ATTRIBUTES[icon])

    name = (item.get('name') or '').lower()
    for keywords, attributes in KEYWORD_ATTRIBUTES:
        if any(word in name for word in keywords):
            return dict(attributes)

    return {}


def item_credit(item, response_value, config=DEFAULT_CONFIG):
    """How much of this item's weight was earned, as 0.0-1.0.

    Deliberately richer than `_item_is_completed` in app.py, which XP uses and
    which treats every non-empty answer as full credit. Attributes grade ordinal
    'time' answers instead: waking at 05:00 and waking after 07:30 are different
    behaviours and should not score the same.
    """
    if response_value is None:
        return 0.0
    value = str(response_value).strip()
    if not value:
        return 0.0

    item_type = item.get('type')
    if item_type == 'rating':
        return 0.0  # self-reflection, not a completed action
    if item_type == 'yes-no':
        return 1.0 if value.lower().startswith('yes') else 0.0
    if item_type == 'time':
        options = item.get('options') or []
        try:
            index = options.index(value)
        except ValueError:
            return 0.5  # answered, but not one of the known buckets
        ladder = config.time_bucket_credit
        return ladder[index] if index < len(ladder) else ladder[-1]
    return 1.0  # free text and anything else: answered counts


def extract_signals(checklist_items, custom_responses, config=DEFAULT_CONFIG):
    """One day's items -> per-attribute earned/available credit.

    Snapshot this at submission time; never recompute it from live Path
    definitions, which are mutable (app.py rewrites the per-user path file on
    every read) and would silently rewrite history.
    """
    responses = custom_responses or {}
    per_attribute = {}
    items = []

    for item in checklist_items or []:
        if item.get('type') == 'rating':
            continue
        weight = float(item.get('weight', 1) or 0)
        if weight <= 0:
            continue

        attributes = resolve_item_attributes(item)
        response = responses.get(item.get('name'))
        credit = item_credit(item, response, config)

        items.append({
            'name': item.get('name'),
            'type': item.get('type'),
            'icon': item.get('icon'),
            'weight': weight,
            'response': response,
            'credit': credit,
            'attributes': attributes,
        })

        for attribute, share in attributes.items():
            bucket = per_attribute.setdefault(
                attribute, {'available': 0.0, 'earned': 0.0}
            )
            bucket['available'] += weight * share
            bucket['earned'] += weight * share * credit

    return {'items': items, 'attributes': per_attribute}


def score_day(checklist_items, custom_responses, config=DEFAULT_CONFIG):
    """Everything derivable from a single day, with nothing carried over."""
    signals = extract_signals(checklist_items, custom_responses, config)

    total_weight = sum(i['weight'] for i in signals['items'])
    earned_weight = sum(i['weight'] * i['credit'] for i in signals['items'])
    completion = (earned_weight / total_weight) if total_weight else 0.0

    return {
        'engine_version': ENGINE_VERSION,
        'items': signals['items'],
        'attributes': signals['attributes'],
        'weight_total': round(total_weight, 4),
        'weight_earned': round(earned_weight, 4),
        'completion': round(completion, 4),
    }


def _ewma(values, half_life_days):
    """Recency-weighted mean. `values` is oldest-first.

    Half-life rather than a flat window: a single bad day moves the number a
    little, a bad fortnight moves it a lot, and nothing falls off a cliff on an
    arbitrary boundary.
    """
    if not values:
        return None
    decay = 0.5 ** (1.0 / max(half_life_days, 1))
    weighted_sum = 0.0
    weight_sum = 0.0
    age = len(values) - 1
    for value in values:
        weight = decay ** age
        weighted_sum += value * weight
        weight_sum += weight
        age -= 1
    return weighted_sum / weight_sum if weight_sum else None


def aggregate_attribute(attribute, daily_ratios, config=DEFAULT_CONFIG):
    """Roll a series of daily ratios into one reportable attribute.

    `daily_ratios` is oldest-first, containing only days where the attribute was
    actually observable (available credit > 0). Days where the Path offered no
    signal are absent rather than zero - not doing cardio is different from not
    being asked about cardio.

    Returns a status rather than forcing a number:
      locked       - no data source exists yet; the phase that adds one is named
      unobserved   - nothing in the user's Path feeds this attribute
      calibrating  - observed, but on too little history to report honestly
      active       - a real score
    """
    if attribute in LOCKED_UNTIL:
        return {
            'attribute': attribute,
            'status': 'locked',
            'score': None,
            'confidence': 0.0,
            'sample_days': 0,
            'unlocks_in': LOCKED_UNTIL[attribute],
        }

    sample_days = len(daily_ratios)
    if sample_days == 0:
        return {
            'attribute': attribute,
            'status': 'unobserved',
            'score': None,
            'confidence': 0.0,
            'sample_days': 0,
        }

    if sample_days < config.min_days_for_score:
        return {
            'attribute': attribute,
            'status': 'calibrating',
            'score': None,
            'confidence': 0.0,
            'sample_days': sample_days,
            'needs_days': config.min_days_for_score - sample_days,
        }

    ratio = _ewma(daily_ratios, config.half_life_days)
    confidence = min(sample_days / config.full_confidence_days, 1.0)

    return {
        'attribute': attribute,
        'status': 'active',
        'score': round(ratio * 100),
        'confidence': round(confidence, 2),
        'sample_days': sample_days,
        'quality': config.self_report_quality,
    }


def consistency_from_log_dates(log_dates, window_days, as_of, config=DEFAULT_CONFIG):
    """Consistency is not derived from any checklist item - it measures whether
    you showed up at all, so it has its own producer.

    `log_dates` is a set/list of ISO date strings that have a submission. The
    ratio is days-logged over the window, which is exactly the "how reliably do
    you follow your routine" the brief asks for.

    Returns a per-day ratio list shaped like the other attributes so it can go
    through aggregate_attribute unchanged.
    """
    from datetime import date as _date, timedelta as _timedelta

    logged = {str(d) for d in (log_dates or [])}
    if not logged:
        return []

    parsed = [_date.fromisoformat(d) for d in logged]
    anchor = _date.fromisoformat(str(as_of))
    oldest = min(parsed)

    # Anchor the window at TODAY, not at the last day logged. Anchoring at the
    # newest submission would let someone who logged four days and then vanished
    # for a week still read as perfectly consistent - the gap has to be visible.
    #
    # Still never claim more history than exists: a user one day in has one day
    # of evidence, not a full window of mostly-zeroes.
    days_of_history = (anchor - oldest).days + 1
    span = min(window_days, config.full_confidence_days, max(days_of_history, 0))

    # One "ratio" per day: did a submission land on that day. Recency weighting
    # in aggregate_attribute then does the rest.
    ratios = []
    for offset in range(span - 1, -1, -1):
        day = anchor - _timedelta(days=offset)
        ratios.append(1.0 if day.isoformat() in logged else 0.0)
    return ratios
