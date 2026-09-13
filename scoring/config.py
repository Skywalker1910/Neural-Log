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
LOCKED_UNTIL = {
    'Agility': 'R3',   # needs mobility//flexibility work from the Training phase
}

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

    # Weights for the composite daily score.
    daily_score_weights: dict = field(default_factory=lambda: {
        'completion': 0.6,   # how much of today's Path you actually completed
        'consistency': 0.4,  # whether you showed up at all, recently
    })


DEFAULT_CONFIG = ScoringConfig()
