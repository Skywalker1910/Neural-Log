"""Scoring configuration - every weight and threshold lives here.

The product brief requires formulas be adjustable in one place rather than
scattered through UI components, so nothing outside this module should hard-code
a scoring constant.
"""
from dataclasses import dataclass, field

# The eight character attributes. Order is the radar's axis order.
ATTRIBUTES = (
    'Discipline',
    'Knowledge',
    'Strength',
    'Stamina',
    'Agility',
    'Recovery',
    'Consistency',
    'Focus',
)

# Attributes that no data source can honestly feed yet, mapped to the phase that
# unlocks them. These render locked rather than as a fabricated number.
# Empty since R3: mobility work in the Training workspace unlocked Agility, the
# last attribute with no data source. Kept as a mechanism - a future attribute
# added before the phase that feeds it belongs here rather than silently
# reporting 'unobserved', which would read as "your Path is missing something"
# instead of "this does not exist yet".
LOCKED_UNTIL = {}

# Tier 2 of the resolver: the curated icon vocabulary already attached to every
# checklist item. Values are {attribute: share}; shares within an item sum to 1.
ICON_ATTRIBUTES = {
    'sun':       {'Discipline': 1.0},
    'coffee':    {'Recovery': 1.0},
    'water':     {'Recovery': 1.0},
    'workout':   {'Strength': 0.6, 'Stamina': 0.4},
    'code':      {'Knowledge': 0.7, 'Focus': 0.3},
    'chess':     {'Knowledge': 0.5, 'Focus': 0.5},
    'breakfast': {'Recovery': 1.0},
    'lunch':     {'Recovery': 1.0},
    'sleep':     {'Recovery': 0.7, 'Discipline': 0.3},
    # 'default' deliberately absent - it means "no icon chosen", so such items
    # fall through to the keyword tier rather than silently feeding Discipline.
}

# Tier 3: keyword match on the item name, for items left on the default icon.
# First match wins, so order matters - more specific patterns first.
KEYWORD_ATTRIBUTES = (
    (('cardio', 'endurance', 'run', 'steps', 'physically active'), {'Stamina': 1.0}),
    (('stretch', 'mobility', 'yoga'), {'Agility': 0.6, 'Recovery': 0.4}),
    (('strength', 'workout', 'exercise', 'gym', 'train'), {'Strength': 0.6, 'Stamina': 0.4}),
    (('study', 'learn', 'read', 'course', 'document', 'project', 'build'), {'Knowledge': 0.7, 'Focus': 0.3}),
    (('sleep', 'bed'), {'Recovery': 0.7, 'Discipline': 0.3}),
    (('water', 'hydrate', 'protein', 'meal', 'eat', 'breakfast', 'lunch', 'dinner'), {'Recovery': 1.0}),
    (('plan', 'organiz', 'reflect', 'journal'), {'Discipline': 0.6, 'Focus': 0.4}),
    (('task', 'important', 'goal', 'help', 'clean'), {'Discipline': 1.0}),
)


# Which attribute a trained muscle group feeds. Derived from the exercises
# actually performed rather than a blanket per-session guess, because the data is
# there: a session of squats and a session of stretching are not the same signal.
MUSCLE_ATTRIBUTES = {
    'chest': 'Strength', 'back': 'Strength', 'shoulders': 'Strength',
    'biceps': 'Strength', 'triceps': 'Strength', 'forearms': 'Strength',
    'quads': 'Strength', 'hamstrings': 'Strength', 'glutes': 'Strength',
    'calves': 'Strength', 'core': 'Strength', 'full-body': 'Strength',
    'cardio': 'Stamina',
}

# Attributes that a measuring workspace can evidence. Only these are subject to
# the self-report ceiling: capping Discipline because you did not log a workout
# would be nonsense - there is nothing to log.
MEASURABLE_ATTRIBUTES = frozenset({'Strength', 'Stamina', 'Agility'})

# Exercise category overrides the muscle map where it disagrees - a mobility
# movement targeting hamstrings is Agility work, not a hamstring builder.
CATEGORY_ATTRIBUTES = {
    'cardio': 'Stamina',
    'mobility': 'Agility',
}


@dataclass(frozen=True)
class ScoringConfig:
    """Tunable knobs. Change here, bump ENGINE_VERSION, recompute."""

    # How fast a score follows behaviour. A 7-day half-life means one missed day
    # nudges the score while a bad week moves it decisively - the brief asks for
    # both ("don't punish one missed day", "reflect a drop in consistency").
    half_life_days: int = 7

    # Days of history before an attribute is considered measurable at all. Below
    # this it reports 'calibrating' with no number, rather than a number derived
    # from one data point.
    min_days_for_score: int = 3

    # Days of history at which confidence reaches 1.0.
    full_confidence_days: int = 14

    # How much a self-reported yes/no is trusted relative to a measured quantity
    # (minutes studied, kg lifted). Surfaced to the UI, not used to cap the score -
    # see the note on the opportunity denominator in engine.py.
    self_report_quality: float = 0.6
    measured_quality: float = 1.0

    # Graded credit for ordinal 'time' items (e.g. wake-up buckets). Index 0 is
    # the best option. XP still treats these as binary; attributes do not, because
    # "woke at 5am" and "woke after 7:30" are not the same behaviour.
    time_bucket_credit: tuple = (1.0, 0.8, 0.55, 0.3)

    # --- Training (R3) ------------------------------------------------------
    # Workout attributes are measured over a TRAILING WINDOW rather than per day.
    # Per-day would be wrong in both directions: a rest day is not a failure, and
    # one session a week would otherwise score 100% on the day it happened and be
    # invisible on the other six.
    training_window_days: int = 7

    # Weekly targets a fully-credited window represents. Deliberately modest -
    # these describe "training consistently", not "training like an athlete".
    weekly_strength_volume: float = 12000.0   # kg x reps across the window
    weekly_cardio_minutes: float = 90.0
    weekly_mobility_minutes: float = 30.0

    # The top of the scale is reserved for evidence. A ticked "I trained today"
    # box, with nothing logged, takes a measurable attribute to this and no
    # further - the app genuinely cannot tell a hard session from a claim.
    # Logging sets is what opens the last quarter of the range.
    #
    # Only applies to MEASURABLE_ATTRIBUTES, and only while no measured signal
    # exists for that day; once sets are logged the blend below takes over and
    # can reach 1.0.
    #
    # 0.5 rather than something higher, and the reason is a perverse incentive
    # rather than taste. With measured_weight 3, an unevidenced claim worth C is
    # only beaten by real training once that training reaches (4C - 1)/3 of the
    # weekly target: 67% at C=0.75, but 33% at C=0.5. A ceiling of 0.75 would
    # mean honestly logging a light week scored *lower* than claiming a perfect
    # one and logging nothing - an app that punishes honest logging is worse
    # than one that does not measure at all.
    self_report_ceiling: float = 0.5

    # How much a measured signal counts relative to a self-reported one when both
    # describe the same attribute on the same day. This is the honest core of it:
    # a logged set of 80kg x 8 is better evidence than a ticked box, so it
    # dominates the blend - but the checkbox is not discarded either.
    measured_weight: float = 3.0
    self_report_weight: float = 1.0

    # Weights for the composite daily score.
    daily_score_weights: dict = field(default_factory=lambda: {
        'completion': 0.6,   # how much of today's Path you actually completed
        'consistency': 0.4,  # whether you showed up at all, recently
    })


DEFAULT_CONFIG = ScoringConfig()
