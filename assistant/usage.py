"""What the assistant has spent, and whether it may spend more.

Three questions, all answered from one table:

- *May this person make a request right now?* - the budget check, which runs
  before every call and is the only thing standing between a bug and a bill.
- *What did that request cost?* - recorded after, tokens as fact and dollars as
  estimate.
- *Where is the money going?* - the admin page, broken down by feature, because
  one total tells you the bill is too high and nothing about which part to fix.

The counters live in SQLite rather than in a process, for the same reason the
login limiter does: gunicorn runs two workers, and two in-process counters each
let through the full quota.
"""
from . import config


def _spend(conn, user_id, since_sql):
    row = conn.execute(
        'SELECT COALESCE(SUM(estimated_cost_usd), 0) AS spent, COUNT(*) AS calls '
        f'FROM ai_usage WHERE user_id = ? AND created_at >= {since_sql}',
        (user_id,),
    ).fetchone()
    return float(row['spent'] or 0), int(row['calls'] or 0)


def budget_state(conn, user_id):
    """Everything the UI and the guard both need, in one query pass."""
    month_spent, month_calls = _spend(conn, user_id, "datetime('now', 'start of month')")
    day_spent, day_calls = _spend(conn, user_id, "datetime('now', 'start of day')")

    return {
        'month_spent_usd': round(month_spent, 4),
        'month_budget_usd': config.MONTHLY_BUDGET_USD,
        'month_calls': month_calls,
        'day_spent_usd': round(day_spent, 4),
        'day_budget_usd': config.DAILY_BUDGET_USD,
        'day_calls': day_calls,
        # Clamped at zero so a budget lowered below what is already spent reads
        # as "nothing left" rather than a negative number.
        'remaining_usd': round(max(0.0, config.MONTHLY_BUDGET_USD - month_spent), 4),
    }


def check_budget(conn, user_id):
    """`(allowed, message)` for one prospective request.

    Checked before the call, on spend already recorded. It cannot know what the
    request about to be made will cost, so a single expensive call can cross the
    line rather than being stopped at it - the overshoot is one request, which is
    why the defaults leave headroom rather than sitting at the real limit.
    """
    state = budget_state(conn, user_id)

    if state['day_spent_usd'] >= config.DAILY_BUDGET_USD:
        return False, (
            "The assistant has reached today's spending limit for this account. "
            'It resets at midnight UTC; everything else in the app still works.'
        )

    if state['month_spent_usd'] >= config.MONTHLY_BUDGET_USD:
        return False, (
            "The assistant has reached this month's spending limit for this "
            'account. Everything else in the app still works.'
        )

    return True, None


def rate_limited(conn, user_id):
    """Whether this account has called too often in the last minute.

    Counted from the usage log rather than a separate table - every attempt
    writes a row there, including the ones that failed, which is exactly the set
    a rate limiter wants to count.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS calls FROM ai_usage "
        "WHERE user_id = ? AND created_at >= datetime('now', '-60 seconds')",
        (user_id,),
    ).fetchone()
    return int(row['calls'] or 0) >= config.RATE_LIMIT_PER_MINUTE


def record(conn, user_id, feature, model, usage=None, ok=True, error=None):
    """Log one model request. Returns the estimated cost.

    Called for failures too, with `ok=0`. A request that errored still consumed
    tokens more often than not, and a usage log that only counts successes
    under-reports exactly when something is going wrong.
    """
    usage = usage or {}
    input_tokens = int(usage.get('input_tokens') or 0)
    output_tokens = int(usage.get('output_tokens') or 0)
    cached = int(usage.get('cached_input_tokens') or 0)

    cost = config.estimate_cost(model, input_tokens, output_tokens, cached)

    conn.execute(
        'INSERT INTO ai_usage '
        '(user_id, feature, model, input_tokens, output_tokens, '
        ' cached_input_tokens, estimated_cost_usd, ok, error) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            user_id, feature, model, input_tokens, output_tokens, cached,
            round(cost, 6), 1 if ok else 0,
            # Truncated: a provider error body can be long, and the useful part
            # is always at the front.
            str(error)[:500] if error else None,
        ),
    )
    conn.commit()
    return cost


def report(conn, days=30):
    """Spend across everyone, for the admin page.

    Deliberately not per-user-facing. Who talked to the assistant how much is
    the kind of thing that should stay with whoever pays the bill.
    """
    since = f"datetime('now', '-{int(days)} days')"

    totals = conn.execute(
        'SELECT COUNT(*) AS calls, '
        '       COALESCE(SUM(input_tokens), 0) AS input_tokens, '
        '       COALESCE(SUM(output_tokens), 0) AS output_tokens, '
        '       COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens, '
        '       COALESCE(SUM(estimated_cost_usd), 0) AS cost, '
        '       COALESCE(SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END), 0) AS failures '
        f'FROM ai_usage WHERE created_at >= {since}'
    ).fetchone()

    by_feature = conn.execute(
        'SELECT feature, COUNT(*) AS calls, '
        '       COALESCE(SUM(estimated_cost_usd), 0) AS cost '
        f'FROM ai_usage WHERE created_at >= {since} '
        'GROUP BY feature ORDER BY cost DESC'
    ).fetchall()

    by_day = conn.execute(
        "SELECT date(created_at) AS day, COUNT(*) AS calls, "
        '       COALESCE(SUM(estimated_cost_usd), 0) AS cost '
        f'FROM ai_usage WHERE created_at >= {since} '
        'GROUP BY day ORDER BY day'
    ).fetchall()

    return {
        'days': int(days),
        'estimated': True,
        'configured': config.is_configured(),
        'chat_model': config.CHAT_MODEL,
        'extraction_model': config.EXTRACTION_MODEL,
        'monthly_budget_usd': config.MONTHLY_BUDGET_USD,
        'totals': {
            'calls': int(totals['calls'] or 0),
            'failures': int(totals['failures'] or 0),
            'input_tokens': int(totals['input_tokens'] or 0),
            'output_tokens': int(totals['output_tokens'] or 0),
            'cached_input_tokens': int(totals['cached_input_tokens'] or 0),
            'estimated_cost_usd': round(float(totals['cost'] or 0), 4),
        },
        'by_feature': [
            {
                'feature': row['feature'],
                'calls': int(row['calls']),
                'estimated_cost_usd': round(float(row['cost']), 4),
            }
            for row in by_feature
        ],
        'by_day': [
            {
                'day': row['day'],
                'calls': int(row['calls']),
                'estimated_cost_usd': round(float(row['cost']), 4),
            }
            for row in by_day
        ],
    }
