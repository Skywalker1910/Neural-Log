"""Neural Log scoring engine.

Pure, dependency-free scoring so it can be imported by app.py, exercised
directly by tests, and later reused by other producers (workouts, sleep,
learning sessions) without circular imports. Nothing in here imports app.
"""
from .config import ATTRIBUTES, ScoringConfig, DEFAULT_CONFIG
from .library import load_library, sync_library
from .store import (
    record_day,
    recompute_scores,
    get_attributes,
    get_attribute_history,
    get_daily_scores,
)
from .engine import (
    extract_signals,
    score_day,
    aggregate_attribute,
    ENGINE_VERSION,
)

__all__ = [
    'ATTRIBUTES',
    'ScoringConfig',
    'DEFAULT_CONFIG',
    'extract_signals',
    'score_day',
    'aggregate_attribute',
    'ENGINE_VERSION',
    'record_day',
    'recompute_scores',
    'get_attributes',
    'get_attribute_history',
    'get_daily_scores',
    'load_library',
    'sync_library',
]
