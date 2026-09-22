"""Load, in one unit, from a table that stores two.

`exercise_sets.weight_unit` has existed since R3, with a comment saying why:
plates are kg in one gym and lb in another, and someone who switches preference
must not have their history silently reinterpreted. Storing the unit per set is
right.

What was missing is that almost nothing read it.

`scoring/producers.py` converted, so the Strength attribute was correct. The two
places that compute `workout_sessions.total_volume` did not, so a session logged
in pounds inflated by 2.2x - and `total_volume` is what the Training page shows
and what the Analytics volume chart sums. Until now that was harmless, because
nothing in the app could enter pounds. It stops being harmless the moment
anything can, and the failure is the quiet kind: the attribute says one thing,
the chart says another, and both look plausible.

So the factor lives here once, in both the shape Python needs and the shape SQL
needs, and every caller uses it.
"""

#: Exact by definition, not an approximation: the international pound is defined
#: as 0.45359237 kg.
POUNDS_TO_KG = 0.45359237

#: Everything that is not pounds is taken as kilograms, including a missing unit.
#: Rows written before `weight_unit` had any writer are kg, which is what the
#: column default has always said.
POUND_UNITS = frozenset({'lb', 'lbs', 'pound', 'pounds'})


def to_kg(weight, unit):
    """One set's load in kilograms."""
    if weight is None:
        return None
    return weight * POUNDS_TO_KG if (unit or 'kg').strip().lower() in POUND_UNITS else weight


#: `SUM(weight x reps)` in kilograms, for a query over `exercise_sets`.
#:
#: A SQL fragment rather than a Python loop because both callers are already
#: aggregating in SQL, and pulling every set back to add them up in Python would
#: scale with how much someone trains rather than with what is being asked.
VOLUME_KG_SQL = (
    "COALESCE(SUM("
    "  COALESCE(weight, 0)"
    "  * CASE WHEN LOWER(COALESCE(weight_unit, 'kg')) IN ('lb', 'lbs', 'pound', 'pounds')"
    f"      THEN {POUNDS_TO_KG} ELSE 1 END"
    "  * COALESCE(reps, 0)"
    "), 0)"
)
