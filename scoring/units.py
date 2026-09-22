"""Load, in one unit, from a table that stores two.

`exercise_sets.weight_unit` has existed since R3, with a comment saying why:
plates are kg in one gym and lb in another, and someone who switches preference
must not have their history silently reinterpreted. Storing the unit per set is
right.

What was missing is that almost nothing read it.

`scoring/producers.py` converted, so the Strength attribute was correct. Nothing
else did. The places that compute `workout_sessions.total_volume` summed
`weight x reps` raw, and so did every read path behind the Training page: the
heaviest set, the best set, volume per muscle group, and the personal records.

That was harmless only while nothing could enter pounds. Now that the logging
screen offers the toggle it is the quiet kind of failure - a pounds session
inflating volume by 2.2x, and a 135 lb bench outranking a 100 kg one in the
records table, with the attribute still correct underneath and every number
looking plausible.

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


def _kg_factor(column):
    """`CASE` that is 0.45359237 for a pounds row and 1 for everything else."""
    return (
        "CASE WHEN LOWER(COALESCE(" + column + ", 'kg')) "
        "IN ('lb', 'lbs', 'pound', 'pounds') "
        f"THEN {POUNDS_TO_KG} ELSE 1 END"
    )


def weight_kg_sql(prefix=''):
    """One row's load in kilograms, as SQL.

    `prefix` is the table alias with its dot, because these queries join and
    `weight` alone is ambiguous once `exercise_sets` sits next to `exercises`.
    """
    return f'({prefix}weight * {_kg_factor(prefix + "weight_unit")})'


def volume_kg_sql(prefix=''):
    """`SUM(weight x reps)` in kilograms, as SQL.

    A SQL fragment rather than a Python loop because every caller is already
    aggregating in SQL, and pulling every set back to add up in Python would
    scale with how much somebody trains rather than with what is being asked.
    """
    return (
        'COALESCE(SUM('
        f'  COALESCE({prefix}weight, 0)'
        f'  * {_kg_factor(prefix + "weight_unit")}'
        f'  * COALESCE({prefix}reps, 0)'
        '), 0)'
    )


#: The unprefixed form, for the queries that read `exercise_sets` unaliased.
VOLUME_KG_SQL = volume_kg_sql()


def normalise_unit(value):
    """The unit to store for a set, given whatever arrived.

    Anything unrecognised becomes kilograms rather than an error: the column has
    always defaulted to kg, and a typo in a unit is not a reason to refuse a set
    somebody just lifted.
    """
    unit = (value or 'kg').strip().lower()
    return 'lb' if unit in POUND_UNITS else 'kg'
