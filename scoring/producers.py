"""Signal producers other than the daily checklist.

The checklist producer lives in engine.py because it came first. This is where
every later phase plugs in: R3 training here, R4 sleep and nutrition, R5 learning
sessions. Each one turns its own raw rows into `{date: {attribute: (ratio, weight)}}`
and the scoring core never learns what a workout is.

WHY TRAINING USES A TRAILING WINDOW
-----------------------------------
Checklist attributes are per-day because the question is per-day: did you do the
thing today. Training is not like that. Scoring it per-day would be wrong in both
directions - a rest day is not a failure, and someone lifting once a week would
score 100% on the day they lifted and be invisible on the other six, which the
EWMA would then read as a perfect lifter.

So a day's training ratio is "volume across the trailing window vs the weekly
target". Rest days inherit the window's credit, and frequency shows up on its own
because fewer sessions means less volume in the window. No special-casing.
"""
from datetime import date as _date, timedelta as _timedelta

from .config import (
    CATEGORY_ATTRIBUTES,
    DEFAULT_CONFIG,
    MEASURABLE_ATTRIBUTES,
    MUSCLE_ATTRIBUTES,
)


def set_contribution(row, config=DEFAULT_CONFIG):
    """One logged set -> (attribute, magnitude) or None.

    Magnitude is in the unit of that attribute's weekly target: kilogram-reps for
    Strength, minutes for Stamina and Agility.
    """
    category = (row.get('category') or 'strength').strip()
    muscle = (row.get('primary_muscle') or '').strip()

    # Category wins where the two disagree: a mobility movement targeting
    # hamstrings is Agility work, not a hamstring builder.
    attribute = CATEGORY_ATTRIBUTES.get(category) or MUSCLE_ATTRIBUTES.get(muscle)
    if not attribute:
        return None

    if row.get('is_warmup'):
        return None  # warm-ups are real work but not the signal
    if not row.get('completed', 1):
        return None

    if attribute == 'Strength':
        weight = float(row.get('weight') or 0)
        reps = int(row.get('reps') or 0)
        if weight > 0 and reps > 0:
            return attribute, _to_kg(weight, row.get('weight_unit')) * reps
        # Bodyweight work still counts - it is training, it just has no load to
        # measure. Credited at a nominal per-rep value rather than zero, which
        # would make a set of 30 press-ups worth nothing.
        if reps > 0:
            return attribute, reps * 5.0
        return None

    # Stamina and Agility are time-based.
    seconds = int(row.get('duration_seconds') or 0)
    if seconds > 0:
        return attribute, seconds / 60.0
    # A logged mobility set with no timer still counts as a couple of minutes.
    if attribute == 'Agility':
        return attribute, 2.0
    return None


def _to_kg(weight, unit):
    return weight * 0.45359237 if (unit or 'kg').lower() in ('lb', 'lbs') else weight


def training_ratios(set_rows, dates, config=DEFAULT_CONFIG):
    """Per-day training ratios over a trailing window.

    `set_rows` is every logged set for one user, each a mapping with at least:
    date, category, primary_muscle, weight, weight_unit, reps, duration_seconds,
    is_warmup, completed.

    `dates` is the ISO dates to produce ratios for (usually every logged day).

    Returns {date: {attribute: (ratio, weight)}} where ratio is 0-1 and weight is
    the measured-signal weight, so the caller can blend it against self-reported
    signals for the same attribute.
    """
    by_date = {}
    for row in set_rows:
        contribution = set_contribution(row, config)
        if not contribution:
            continue
        attribute, magnitude = contribution
        bucket = by_date.setdefault(row['date'], {})
        bucket[attribute] = bucket.get(attribute, 0.0) + magnitude

    if not by_date:
        return {}

    targets = {
        'Strength': config.weekly_strength_volume,
        'Stamina': config.weekly_cardio_minutes,
        'Agility': config.weekly_mobility_minutes,
    }

    # An attribute only becomes observable once there is a first signal for it.
    # Before that it is genuinely unobserved, and back-filling zeroes would
    # invent a history of not training.
    first_seen = {}
    for day, buckets in sorted(by_date.items()):
        for attribute in buckets:
            first_seen.setdefault(attribute, day)

    window = max(1, config.training_window_days)
    out = {}

    for iso in dates:
        day = _date.fromisoformat(iso)
        start = day - _timedelta(days=window - 1)

        totals = {}
        for logged_iso, buckets in by_date.items():
            logged = _date.fromisoformat(logged_iso)
            if start <= logged <= day:
                for attribute, magnitude in buckets.items():
                    totals[attribute] = totals.get(attribute, 0.0) + magnitude

        for attribute, target in targets.items():
            if attribute not in first_seen or iso < first_seen[attribute]:
                continue  # nothing measured yet - stay silent rather than score 0

            # Pro-rate the target by how much of the window actually has history.
            # Measuring someone's first training day against a full week's target
            # scores them ~15% for a genuinely hard session, and the EWMA then
            # carries that unfair start forward for a fortnight.
            started = _date.fromisoformat(first_seen[attribute])
            observed_days = min(window, (day - started).days + 1)
            effective_target = target * (observed_days / window)

            ratio = (min(1.0, totals.get(attribute, 0.0) / effective_target)
                     if effective_target > 0 else 0.0)
            out.setdefault(iso, {})[attribute] = (ratio, config.measured_weight)

    return out


def blend(attribute, self_reported, measured, config=DEFAULT_CONFIG):
    """Combine a self-reported ratio with a measured one for the same attribute.

    Two rules, and the difference between them matters:

    1. WHERE BOTH EXIST, they are averaged with the measured side weighted far
       higher. Evidence beats assertion, but a ticked box is not thrown away.

    2. WHERE ONLY SELF-REPORT EXISTS and the attribute is one a workspace can
       actually measure, the result is capped at `self_report_ceiling`. The top of
       the scale is reserved for evidence, because the app cannot tell a hard
       session from a claim about one.

    Rule 2 deliberately does NOT apply to Discipline, Knowledge, Focus, Recovery
    or Consistency: nothing measures those yet, so capping them would punish
    people for a feature that does not exist.

    Either side may be None.
    """
    if measured is None:
        if self_reported is None:
            return None
        if attribute in MEASURABLE_ATTRIBUTES:
            return min(self_reported, config.self_report_ceiling)
        return self_reported

    parts = [measured]
    if self_reported is not None:
        parts.append((self_reported, config.self_report_weight))

    total_weight = sum(weight for _, weight in parts)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in parts) / total_weight


# --- R4: sleep, steps, hydration and nutrition adherence ---------------------
#
# WHY SLEEP IS PER-NIGHT AND STEPS ARE WINDOWED
# ---------------------------------------------
# Training uses a trailing window because a rest day is not a failure. Sleep is
# the opposite: you cannot bank it, and a night you did not get is a real gap in
# recovery on that day. So sleep is scored per night and steps are windowed, and
# the difference is not an inconsistency - it is the two behaviours actually
# being different.
#
# WHAT IS DELIBERATELY NOT SCORED
# -------------------------------
# Mood, stress, energy and sleep quality are recorded by the Lifestyle workspace
# and never appear here. They are self-reported feelings rather than behaviour,
# so scoring them would be dishonest in the same way an unevidenced "I trained"
# is - and worse, it would pay you to report feeling good. The same reasoning
# that produced the self-report ceiling in R3 keeps them out entirely.
import math as _math


def _minutes_since_midnight(value):
    """"23:30" -> 1410. None for anything unparseable."""
    if not value:
        return None
    try:
        hours, _, minutes = str(value).partition(':')
        total = int(hours) * 60 + int(minutes or 0)
    except (TypeError, ValueError):
        return None
    return total if 0 <= total < 1440 else None


def _circular_spread(times):
    """Spread of clock times in minutes, respecting midnight.

    A plain standard deviation is wrong here, and wrong in the worst direction:
    bedtimes of 23:50 and 00:10 are twenty minutes apart, but as raw numbers they
    are 1430 and 10, which reads as a 23-hour swing. Someone with an admirably
    fixed bedtime around midnight would score the worst possible consistency.

    So the values are rotated to sit around their own circular mean before the
    spread is taken.
    """
    if len(times) < 2:
        return 0.0

    radians = [t / 1440.0 * 2 * _math.pi for t in times]
    mean_x = sum(_math.cos(r) for r in radians) / len(radians)
    mean_y = sum(_math.sin(r) for r in radians) / len(radians)
    mean_angle = _math.atan2(mean_y, mean_x)

    deviations = []
    for r in radians:
        diff = r - mean_angle
        # Wrap into (-pi, pi] so the distance is always the short way round.
        while diff > _math.pi:
            diff -= 2 * _math.pi
        while diff <= -_math.pi:
            diff += 2 * _math.pi
        deviations.append(diff / (2 * _math.pi) * 1440.0)

    variance = sum(d * d for d in deviations) / len(deviations)
    return _math.sqrt(variance)


def sleep_duration_ratio(minutes, target_minutes, config=DEFAULT_CONFIG):
    """One night's duration as a 0-1 ratio against the target.

    Below target: proportional. At or just above: full credit. Well above: tapers
    toward a floor rather than to zero - sleeping eleven hours is not better
    recovery than eight, but the evidence that it is actively bad is weak enough
    that it should not crater the score either.
    """
    if not minutes or minutes <= 0 or not target_minutes or target_minutes <= 0:
        return None

    if minutes <= target_minutes:
        return minutes / target_minutes

    surplus = minutes - target_minutes
    tolerance = config.sleep_surplus_tolerance_minutes
    if surplus <= tolerance:
        return 1.0

    excess = surplus - tolerance
    floor = config.sleep_oversleep_floor
    taper = max(1, config.sleep_oversleep_taper_minutes)
    return max(floor, 1.0 - (excess / taper) * (1.0 - floor))


def sleep_ratios(sleep_rows, dates, targets_by_date=None, config=DEFAULT_CONFIG):
    """Per-day Recovery (duration) and Discipline (schedule consistency) ratios.

    `sleep_rows` are mappings with date, duration_minutes, bedtime and wake_time.
    `targets_by_date` optionally overrides the sleep target per day from the
    user's profile; the config default is used where it is absent.

    Returns {date: {attribute: (ratio, weight)}}.
    """
    by_date = {row['date']: row for row in sleep_rows if row.get('date')}
    if not by_date:
        return {}

    targets_by_date = targets_by_date or {}
    ordered = sorted(by_date)
    first_night = ordered[0]

    window = max(1, config.sleep_consistency_window_days)
    out = {}

    for iso in dates:
        if iso < first_night:
            continue  # nothing measured yet - silence, not a zero

        row = by_date.get(iso)
        target = targets_by_date.get(iso) or config.sleep_target_minutes

        if row:
            ratio = sleep_duration_ratio(row.get('duration_minutes'), target, config)
            if ratio is not None:
                out.setdefault(iso, {})['Recovery'] = (ratio, config.measured_weight)

        # Schedule consistency looks back over the window, so it produces a value
        # on every day once there is enough history - including days with no
        # entry, where the recent pattern is still the honest answer.
        day = _date.fromisoformat(iso)
        start = (day - _timedelta(days=window - 1)).isoformat()
        recent = [by_date[d] for d in ordered if start <= d <= iso]
        if len(recent) < config.sleep_consistency_min_nights:
            continue

        spreads = []
        for field_name in ('bedtime', 'wake_time'):
            times = [
                minutes for minutes in
                (_minutes_since_midnight(entry.get(field_name)) for entry in recent)
                if minutes is not None
            ]
            if len(times) >= config.sleep_consistency_min_nights:
                spreads.append(_circular_spread(times))

        if not spreads:
            continue

        spread = sum(spreads) / len(spreads)
        tolerance = config.sleep_consistency_tolerance_minutes
        consistency = max(0.0, 1.0 - (spread / tolerance)) if tolerance > 0 else 0.0
        out.setdefault(iso, {})['Discipline'] = (consistency, config.measured_weight)

    return out


def steps_ratios(lifestyle_rows, dates, targets_by_date=None, config=DEFAULT_CONFIG):
    """Per-day Stamina ratios from step counts, over a trailing window."""
    by_date = {
        row['date']: row['steps']
        for row in lifestyle_rows
        if row.get('date') and row.get('steps')
    }
    if not by_date:
        return {}

    targets_by_date = targets_by_date or {}
    first_seen = min(by_date)
    window = max(1, config.steps_window_days)
    out = {}

    for iso in dates:
        if iso < first_seen:
            continue

        day = _date.fromisoformat(iso)
        start = day - _timedelta(days=window - 1)
        total = sum(
            steps for logged_iso, steps in by_date.items()
            if start <= _date.fromisoformat(logged_iso) <= day
        )

        # Pro-rate by observed history, exactly as training does: measuring the
        # first logged day against a full week of steps would score a genuine
        # 10,000-step day at 18%.
        started = _date.fromisoformat(first_seen)
        observed_days = min(window, (day - started).days + 1)
        target = targets_by_date.get(iso) or config.daily_step_target
        effective = target * observed_days
        if effective <= 0:
            continue

        out.setdefault(iso, {})['Stamina'] = (
            min(1.0, total / effective), config.measured_weight,
        )

    return out


def adherence_ratios(lifestyle_rows, nutrition_by_date, targets_by_date,
                     config=DEFAULT_CONFIG):
    """Per-day Discipline ratios from hitting your own water and calorie targets.

    Adherence, not health: the question is whether you did the thing you decided
    to do. That is why this feeds Discipline, and why protein does NOT feed
    Strength - eating protein is not training.

    Calories are scored as a two-sided band. Overshooting a target by 500 and
    undershooting it by 500 are both misses, and a one-sided "more is better"
    reading would score a 4,000 kcal day against a 2,000 target as perfect
    adherence.
    """
    water_by_date = {
        row['date']: row['water_ml']
        for row in lifestyle_rows
        if row.get('date') and row.get('water_ml')
    }

    dates = sorted(set(water_by_date) | set(nutrition_by_date or {}))
    if not dates:
        return {}

    weights = config.adherence_weights
    out = {}

    for iso in dates:
        targets = (targets_by_date or {}).get(iso) or {}
        parts = []

        water = water_by_date.get(iso)
        water_target = targets.get('water_ml') or config.daily_water_target_ml
        if water and water_target > 0:
            parts.append((min(1.0, water / water_target), weights['water']))

        totals = (nutrition_by_date or {}).get(iso)
        if totals:
            calorie_target = targets.get('calories')
            if calorie_target and calorie_target > 0 and totals.get('calories'):
                tolerance = calorie_target * config.calorie_tolerance_fraction
                miss = abs(totals['calories'] - calorie_target)
                credit = (1.0 if miss <= tolerance
                          else max(0.0, 1.0 - (miss - tolerance) / calorie_target))
                parts.append((credit, weights['calories']))

            protein_target = targets.get('protein_g')
            if protein_target and protein_target > 0:
                # Protein is one-sided on purpose: exceeding it is not a failure
                # the way exceeding a calorie budget is.
                parts.append((
                    min(1.0, (totals.get('protein_g') or 0) / protein_target),
                    weights['protein'],
                ))

        if not parts:
            continue

        total_weight = sum(w for _, w in parts)
        if total_weight <= 0:
            continue
        ratio = sum(value * w for value, w in parts) / total_weight
        out.setdefault(iso, {})['Discipline'] = (ratio, config.measured_weight)

    return out


def merge_measured(*sources):
    """Combine several producers into one {date: {attribute: (ratio, weight)}}.

    Two producers can legitimately speak to the same attribute on the same day -
    after R4, sleep consistency and nutrition adherence both feed Discipline, and
    steps and logged cardio both feed Stamina. Where that happens the signals are
    averaged by weight rather than one overwriting the other, which is what a
    plain dict update would silently have done.
    """
    combined = {}
    for source in sources:
        for iso, attributes in (source or {}).items():
            bucket = combined.setdefault(iso, {})
            for attribute, (ratio, weight) in attributes.items():
                bucket.setdefault(attribute, []).append((ratio, weight))

    out = {}
    for iso, attributes in combined.items():
        for attribute, entries in attributes.items():
            if len(entries) == 1:
                # Short-circuited rather than averaged with itself: the round trip
                # through a weighted mean turns 0.8 into 0.8000000000000002.
                out.setdefault(iso, {})[attribute] = entries[0]
                continue

            total_weight = sum(w for _, w in entries)
            if total_weight <= 0:
                continue
            ratio = sum(r * w for r, w in entries) / total_weight
            # The combined signal keeps the total weight, so an attribute
            # evidenced by two independent measurements outweighs one evidenced
            # by a single measurement when blended against self-report.
            out.setdefault(iso, {})[attribute] = (ratio, total_weight)
    return out
