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
# the self-report ceiling: capping an attribute because you did not log something
# would be nonsense where there is nothing to log.
#
# Recovery joined in R4 when sleep became loggable; Knowledge and Focus joined in
# R5 when study sessions did.
#
# Two deliberate exclusions, for different reasons:
#
#   Discipline  - has measured signals since R4 (sleep consistency, adherence),
#                 but the daily checklist is already DIRECT evidence of
#                 discipline, so those are additional evidence rather than the
#                 only possible evidence. Capping it would punish someone for not
#                 using a workspace, which is the opposite of what the ceiling is
#                 for.
#   Consistency - has no self-reported route at all. Nothing in a Path feeds it;
#                 it is derived from whether you logged. There is nothing to cap.
MEASURABLE_ATTRIBUTES = frozenset({
    'Strength', 'Stamina', 'Agility', 'Recovery', 'Knowledge', 'Focus',
})

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
    #
    # Strength is the one that scales with how often you train, because kg x reps
    # is per-session work that accumulates: a flat weekly figure asks someone on a
    # deliberate twice-a-week programme to do a four-day week's volume, so they
    # score permanently low for executing their plan perfectly.
    #
    # The denominator being partly self-declared is not a departure. The whole
    # engine already works that way - your Path decides which attributes have a
    # denominator at all, and you choose your Path. Declaring how often you train
    # is the same kind of act, and it is bounded below so that declaring "once a
    # week" cannot collapse the bar into a free 100.
    per_session_strength_volume: float = 3000.0   # kg x reps in one session
    default_training_days: int = 4                # 4 x 3000 = the old flat 12000
    min_training_days: int = 2
    max_training_days: int = 6

    # Cardio and mobility stay absolute. They are weekly time budgets rather than
    # per-session work products - how many days you lift says nothing about how
    # many minutes of cardio a week is a reasonable ask.
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

    # --- Sleep and lifestyle (R4) -------------------------------------------
    # Sleep is scored per night rather than over a window: unlike training, a
    # night is not something you can bank. Missing one is a real gap in recovery
    # on that day, and the EWMA already stops a single bad night from mattering
    # much.
    #
    # Full credit is a BAND, not a threshold. Below target, credit falls off
    # proportionally. Above it, credit holds for a couple of hours and then
    # tapers - sleeping eleven hours is not better recovery than eight, but the
    # evidence that it is actively bad is weak enough that it should not crater
    # the score either.
    sleep_target_minutes: int = 480          # the default; the profile overrides it
    sleep_surplus_tolerance_minutes: int = 120
    # How long the taper takes to reach the floor once the tolerance is used
    # up. Named rather than reusing the target as an incidental span: with an
    # 8h target that reached the floor only at 18h in bed, which scored an
    # eleven-hour night at 0.95.
    sleep_oversleep_taper_minutes: int = 240
    sleep_oversleep_floor: float = 0.6       # credit never falls below this from oversleeping

    # Schedule consistency -> Discipline. Measured as the spread of bedtimes and
    # wake times across a trailing window. Going to bed at a similar hour is a
    # behaviour you control, which is exactly what Discipline should be made of.
    sleep_consistency_window_days: int = 14
    sleep_consistency_min_nights: int = 3
    # Spread at which consistency credit reaches zero. 90 minutes is deliberately
    # forgiving: a weekend lie-in should cost something, not everything.
    sleep_consistency_tolerance_minutes: float = 90.0

    # Steps -> Stamina, over a trailing window for the same reason training uses
    # one: a rest day is not a failure.
    steps_window_days: int = 7
    daily_step_target: int = 8000

    # Hydration and nutrition adherence -> Discipline. Hitting targets you set
    # for yourself is adherence behaviour, which is why it feeds Discipline
    # rather than Recovery or Strength. Eating protein is not training.
    daily_water_target_ml: int = 2500
    # How far from the calorie target still counts as hitting it. Nutrition
    # tracking is approximate at the best of times, and a 2,000 kcal target met
    # at 2,050 is a hit by any honest reading.
    calorie_tolerance_fraction: float = 0.10

    # Relative weights of the adherence components inside the Discipline signal.
    adherence_weights: dict = field(default_factory=lambda: {
        'water': 1.0,
        'calories': 1.0,
        'protein': 1.0,
    })

    # --- Learning (R5) ------------------------------------------------------
    # Knowledge is study minutes over a trailing window, same shape as training:
    # a day off is not a failure, and someone who studies hard twice a week would
    # otherwise score 100 on those days and be invisible on the other five.
    learning_window_days: int = 7
    weekly_study_minutes: float = 300.0      # the default; the profile overrides it

    # Focus is measured from the SHAPE of study time rather than its total.
    # `focus_target_block_minutes` is the length at which a block counts as fully
    # deep work. 50 minutes rather than a round hour because that is roughly
    # where a worked session lands once you subtract settling in.
    focus_target_block_minutes: float = 50.0

    # Sessions closer together than this are treated as one interrupted block.
    # Getting up for coffee does not end deep work, and counting it as two short
    # sessions would score an honest three-hour stretch worse than it deserves.
    focus_block_gap_minutes: int = 15

    # Below this much study in the window there is not enough to characterise a
    # pattern, so Focus stays silent rather than reporting a number derived from
    # a single ten-minute session.
    focus_min_window_minutes: float = 30.0

    # Weights for the composite daily score.
    daily_score_weights: dict = field(default_factory=lambda: {
        'completion': 0.6,   # how much of today's Path you actually completed
        'consistency': 0.4,  # whether you showed up at all, recently
    })


DEFAULT_CONFIG = ScoringConfig()
