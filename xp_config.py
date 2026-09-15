"""Every XP rate, threshold and cap, in one place.

Separate from `scoring/config.py` on purpose. Attribute scoring answers "how are
you actually doing"; XP answers "what did you earn for showing up". They are
different systems with different failure modes, and GAMIFICATION.md has said so
since Phase 2.

THE TWO RULES EVERYTHING HERE SERVES
------------------------------------
1. Evidence beats a claim. Logging real sets pays more than ticking "I trained",
   and ticking the box as well does not pay twice for one behaviour. This is the
   same principle as the scoring engine's self-report ceiling, applied to XP.

2. Farming is pointless rather than merely difficult. Every source has a daily
   cap and a floor. You cannot grind XP by logging twenty two-minute study
   sessions, and you cannot out-earn someone by inventing a bigger number,
   because the cap lands first.
"""

# --- checklist ---------------------------------------------------------------

# Each weight point on a completed checklist item. Unchanged from Phase 2, so
# existing totals keep their meaning.
XP_PER_WEIGHT_POINT = 10

# A ticked box you ALSO evidenced that day pays this fraction.
#
# Not zero: answering the checklist is still the daily ritual the app is built
# around, and zeroing it would punish people for filling it in. But it is not
# full either - the logged sets are already being paid for that behaviour, and
# paying twice is what would make claiming as good as doing.
EVIDENCE_DISCOUNT = 0.4

# --- training ----------------------------------------------------------------

XP_PER_WORKING_SET = 4
XP_PER_CARDIO_MINUTE = 0.5
XP_PER_MOBILITY_MINUTE = 0.6

# A session with nothing logged in it is not a session. Guards against the
# "start workout, never fill it in, collect XP" path.
MIN_WORKING_SETS = 1

# --- learning ----------------------------------------------------------------

XP_PER_STUDY_10_MINUTES = 5

# Below this, a session is not study - it is opening a book and closing it.
MIN_STUDY_MINUTES = 10

# A deep block earns a bonus, because R5 established that the shape of study time
# is the thing worth encouraging, not just its total.
XP_DEEP_BLOCK_BONUS = 8
DEEP_BLOCK_MINUTES = 50

# --- nutrition ---------------------------------------------------------------

XP_MEALS_LOGGED = 8            # logging anything at all for the day
XP_CALORIE_TARGET_MET = 10     # within the scoring engine's tolerance band
XP_PROTEIN_TARGET_MET = 8

# One or two entries is not a day's food. Paying for it would reward the gesture
# rather than the habit.
MIN_FOOD_ENTRIES = 3

# --- lifestyle ---------------------------------------------------------------

XP_SLEEP_LOGGED = 8
XP_SLEEP_TARGET_MET = 8
XP_WATER_TARGET_MET = 6
XP_STEPS_TARGET_MET = 10

MIN_SLEEP_MINUTES = 120        # a two-hour "night" is a typo or a nap

# --- streaks -----------------------------------------------------------------

STREAK_MULTIPLIER_PCT_PER_DAY = 2
STREAK_MULTIPLIER_CAP_PCT = 50

# --- caps --------------------------------------------------------------------

# Per source, per day. Sized so a genuinely excellent day in one area reaches its
# cap but a fabricated one gains nothing beyond it.
DAILY_SOURCE_CAPS = {
    'checklist': 150,
    'training': 80,
    'learning': 60,
    'nutrition': 40,
    'lifestyle': 40,
}

# Across everything, before the streak multiplier. A ceiling on the whole day
# matters because the per-source caps sum to more than any real day produces.
DAILY_TOTAL_CAP = 300

# Achievement XP is deliberately NOT capped: it is one-off by definition, cannot
# be repeated, and a cap would mean unlocking two achievements in a day silently
# discarded one of them.

# --- level curve -------------------------------------------------------------

# Cumulative XP to reach a level is LEVEL_CURVE_FACTOR * (level - 1) ** exponent.
#
# Configurable because the curve was previously hard-coded in a function, and
# R7's brief asks for it to be tunable. The defaults reproduce the original
# 50 * (level - 1) ** 2 exactly, so nobody's level changes when this ships.
LEVEL_CURVE_FACTOR = 50
LEVEL_CURVE_EXPONENT = 2
