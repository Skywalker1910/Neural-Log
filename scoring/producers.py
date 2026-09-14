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
