"""Tests for the R5 learning producer.

The theme: Knowledge is about how much you studied, Focus is about the shape of
it, and the two must not collapse into each other.
"""
from datetime import date, timedelta

from scoring import producers
from scoring.config import DEFAULT_CONFIG, MEASURABLE_ATTRIBUTES

TODAY = date.today()


def _iso(offset=0):
    return (TODAY - timedelta(days=offset)).isoformat()


def _session(offset=0, minutes=60, start=None):
    return {'date': _iso(offset), 'duration_minutes': minutes, 'started_at': start}


# --- depth, the statistic --------------------------------------------------

def test_one_long_block_is_deeper_than_several_short_ones():
    """The same total, shaped differently, is not the same work."""
    assert producers.session_depth([120]) > producers.session_depth([30] * 4)


def test_a_stray_short_session_barely_dents_a_deep_day():
    """A plain mean would score a two-hour block plus a five-minute one at 62,
    worse than the two-hour block alone. Weighting by duration asks "for a random
    minute of study, how long was its block" - which is the actual question."""
    deep = producers.session_depth([120])
    with_stray = producers.session_depth([120, 5])

    assert with_stray > 100
    assert with_stray < deep
    # The plain mean, for contrast, would be 62.5.
    assert with_stray > (125 / 2)


def test_depth_of_nothing_is_none_not_zero():
    assert producers.session_depth([]) is None
    assert producers.session_depth([0]) is None


# --- blocks ----------------------------------------------------------------

def test_sessions_a_few_minutes_apart_are_one_block():
    """Getting up for coffee does not end deep work."""
    blocks = producers._block_minutes([
        {'duration_minutes': 45, 'started_at': '09:00'},
        {'duration_minutes': 45, 'started_at': '09:55'},
    ])
    assert blocks == [100.0]


def test_sessions_hours_apart_are_separate_blocks():
    blocks = producers._block_minutes([
        {'duration_minutes': 45, 'started_at': '09:00'},
        {'duration_minutes': 45, 'started_at': '14:00'},
    ])
    assert sorted(blocks) == [45.0, 45.0]


def test_sessions_without_clock_times_stand_alone():
    """Nothing can be joined to a session that has no start time, so each is its
    own block rather than being optimistically merged."""
    blocks = producers._block_minutes([
        {'duration_minutes': 45}, {'duration_minutes': 45},
    ])
    assert sorted(blocks) == [45.0, 45.0]


def test_overlapping_sessions_do_not_double_count():
    blocks = producers._block_minutes([
        {'duration_minutes': 60, 'started_at': '09:00'},
        {'duration_minutes': 30, 'started_at': '09:30'},
    ])
    assert blocks == [60.0]


# --- knowledge -------------------------------------------------------------

def test_study_minutes_feed_knowledge():
    rows = [_session(offset, 60) for offset in range(7)]
    out = producers.learning_ratios(rows, [_iso(0)])
    assert out[_iso(0)]['Knowledge'][0] == 1.0


def test_the_first_study_day_is_not_measured_against_a_full_week():
    """Two genuine hours on day one should not score 40% because six days of
    nothing sit in the window."""
    out = producers.learning_ratios([_session(0, 120)], [_iso(0)])
    assert out[_iso(0)]['Knowledge'][0] == 1.0


def test_learning_says_nothing_before_the_first_session():
    out = producers.learning_ratios([_session(0, 60)], [_iso(5), _iso(0)])
    assert _iso(5) not in out, 'back-filling zeroes would invent a history of not studying'


def test_a_day_off_does_not_erase_the_week():
    """Windowed, like training: not studying today is not a failure if the week
    holds up."""
    rows = [_session(offset, 90) for offset in range(1, 6)]
    out = producers.learning_ratios(rows, [_iso(0)])
    assert out[_iso(0)]['Knowledge'][0] > 0.9


# --- focus -----------------------------------------------------------------

def test_focus_separates_deep_work_from_fragmented_work():
    """Identical totals, opposite shapes. If these scored the same, Focus would
    just be Knowledge with extra steps."""
    deep = producers.learning_ratios(
        [_session(0, 120, '09:00')], [_iso(0)])[_iso(0)]['Focus'][0]
    fragmented = producers.learning_ratios([
        _session(0, 30, '09:00'), _session(0, 30, '12:00'),
        _session(0, 30, '15:00'), _session(0, 30, '18:00'),
    ], [_iso(0)])[_iso(0)]['Focus'][0]

    assert deep == 1.0
    assert fragmented < 0.7
    assert deep > fragmented


def test_knowledge_is_unmoved_by_the_shape_that_moves_focus():
    """The same total minutes must produce the same Knowledge either way."""
    deep = producers.learning_ratios(
        [_session(0, 120, '09:00')], [_iso(0)])[_iso(0)]
    fragmented = producers.learning_ratios([
        _session(0, 30, '09:00'), _session(0, 30, '12:00'),
        _session(0, 30, '15:00'), _session(0, 30, '18:00'),
    ], [_iso(0)])[_iso(0)]

    assert deep['Knowledge'][0] == fragmented['Knowledge'][0]
    assert deep['Focus'][0] != fragmented['Focus'][0]


def test_focus_stays_silent_on_too_little_study():
    """Ten minutes is not a pattern, and reporting one from it would be noise."""
    out = producers.learning_ratios([_session(0, 10, '09:00')], [_iso(0)])
    assert 'Knowledge' in out[_iso(0)]
    assert 'Focus' not in out[_iso(0)]


def test_a_broken_up_long_session_still_counts_as_deep():
    """Three 50-minute stretches with short breaks are one long block, not three
    mediocre ones - otherwise the app would punish taking a breath."""
    out = producers.learning_ratios([
        _session(0, 50, '09:00'), _session(0, 50, '10:00'), _session(0, 50, '11:00'),
    ], [_iso(0)])
    assert out[_iso(0)]['Focus'][0] == 1.0


def test_blocks_do_not_span_midnight():
    """Blocks are pooled per day. Treating the window as one long timeline would
    join last night's late session to this morning's early one."""
    out = producers.learning_ratios([
        _session(1, 40, '23:30'), _session(0, 40, '06:00'),
    ], [_iso(0)])
    # Two 40-minute blocks, not one 80-minute one.
    assert out[_iso(0)]['Focus'][0] < 1.0


# --- the ceiling -----------------------------------------------------------

def test_knowledge_and_focus_became_measurable_in_r5():
    assert 'Knowledge' in MEASURABLE_ATTRIBUTES
    assert 'Focus' in MEASURABLE_ATTRIBUTES
    ceiling = DEFAULT_CONFIG.self_report_ceiling
    assert producers.blend('Knowledge', 1.0, None) == ceiling
    assert producers.blend('Focus', 1.0, None) == ceiling


def test_logging_real_study_always_beats_claiming_it():
    """The incentive check every measurable attribute gets."""
    claimed = producers.blend('Knowledge', 1.0, None)
    for ratio in (0.35, 0.5, 0.75, 1.0):
        logged = producers.blend('Knowledge', 1.0, (ratio, DEFAULT_CONFIG.measured_weight))
        assert logged > claimed, (
            f'{ratio:.0%} of the weekly study target scored {logged:.2f}, worse '
            f'than claiming it and logging nothing ({claimed:.2f})'
        )


def test_the_focus_rating_is_never_an_input():
    """The self-reported rating is recorded but must not reach the producer -
    scoring it would pay you to rate yourself a five."""
    honest = producers.learning_ratios(
        [{**_session(0, 60, '09:00'), 'focus_rating': 1}], [_iso(0)])
    flattering = producers.learning_ratios(
        [{**_session(0, 60, '09:00'), 'focus_rating': 5}], [_iso(0)])
    assert honest == flattering
