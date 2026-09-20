"""What the assistant is allowed to cost, and which model it costs it on.

Every value here is an environment variable with a default that works. The
defaults matter more than usual: this is the first feature in the app that spends
real money per request, and a misconfiguration is not a crash - it is a bill.

## On the prices below

They are estimates, and the code says so everywhere it uses them.

The provider's billing is the authority on what was actually charged. These rates
exist for one job the billing API cannot do: refusing a request *before* it is
made, because the person has already spent their month's budget. That needs a
number that is local and instant, and the usage API is neither - it reports the
whole organisation, minutes to hours late.

So the admin page labels its figures "estimated", and when they drift from the
real invoice the rates are one environment variable away from being corrected.
"""
import os


def _env_float(name, default):
    raw = (os.environ.get(name) or '').strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name, default):
    raw = (os.environ.get(name) or '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# --- which model -------------------------------------------------------------

#: Conversation. Terra is the same model Tech-Portfolio's assistant runs on, so
#: the two apps share a price point and a known quantity.
CHAT_MODEL = (os.environ.get('OPENAI_CHAT_MODEL') or 'gpt-5.6-terra').strip()

#: Extraction - reading a nutrition panel into JSON, classifying a short message.
#: Ten times cheaper than Terra, and the job is transcription rather than
#: judgement. Splitting these two is most of the difference between a bill that
#: is noticeable and one that is not.
EXTRACTION_MODEL = (os.environ.get('OPENAI_EXTRACTION_MODEL') or 'gpt-5.6-luna').strip()


# --- what it costs -----------------------------------------------------------

#: (input $/1M, output $/1M). Published rates as of September 2026.
DEFAULT_PRICES = {
    'gpt-5.6-sol': (4.00, 20.00),
    'gpt-5.6-terra': (2.00, 12.00),
    'gpt-5.6-luna': (0.20, 1.20),
}

#: A model we have no rate for. Deliberately the most expensive known rate rather
#: than zero: an unknown model should over-estimate and trip the cap early, not
#: bill silently against a budget it never touches.
FALLBACK_PRICE = (4.00, 20.00)

#: Cached input tokens bill at a fraction of fresh ones. The exact discount is a
#: provider detail that moves, so it is configurable and assumed generous - if it
#: is wrong, it is wrong in the direction of under-estimating spend, which is why
#: the cap has headroom below the real budget.
CACHED_INPUT_MULTIPLIER = _env_float('OPENAI_CACHED_INPUT_MULTIPLIER', 0.1)


def prices_for(model):
    """(input, output) dollars per million tokens.

    Environment overrides are per-model and named after it, so correcting a rate
    after reading a real invoice needs no code change:

        OPENAI_PRICE_GPT_5_6_TERRA_INPUT=1.80
    """
    slug = model.upper().replace('-', '_').replace('.', '_')
    base_in, base_out = DEFAULT_PRICES.get(model, FALLBACK_PRICE)
    return (
        _env_float(f'OPENAI_PRICE_{slug}_INPUT', base_in),
        _env_float(f'OPENAI_PRICE_{slug}_OUTPUT', base_out),
    )


def estimate_cost(model, input_tokens, output_tokens, cached_input_tokens=0):
    """Dollars, approximately, for one request.

    Cached tokens are counted once at the discounted rate and removed from the
    fresh count - the provider reports them as a subset of `input_tokens`, so
    billing them twice is the easy mistake here.
    """
    price_in, price_out = prices_for(model)

    cached = max(0, min(cached_input_tokens, input_tokens))
    fresh = max(0, input_tokens - cached)

    return (
        fresh * price_in / 1_000_000
        + cached * price_in * CACHED_INPUT_MULTIPLIER / 1_000_000
        + max(0, output_tokens) * price_out / 1_000_000
    )


# --- what it is allowed to cost ----------------------------------------------

#: Per person, per calendar month, in dollars. Five people at this ceiling is
#: $15/month worst case - three times the instance, and a number that cannot
#: surprise anyone. Raise it once the real usage is known; that is what the
#: admin page is for.
MONTHLY_BUDGET_USD = _env_float('ASSISTANT_MONTHLY_BUDGET_USD', 3.00)

#: A single runaway day cannot consume the month. Mostly this catches a bug -
#: a loop that re-asks the model - rather than a person talking too much.
DAILY_BUDGET_USD = _env_float('ASSISTANT_DAILY_BUDGET_USD', 0.75)

#: Requests per minute per person. A human conversation does not exceed this; a
#: runaway client will.
RATE_LIMIT_PER_MINUTE = _env_int('ASSISTANT_RATE_LIMIT_PER_MINUTE', 12)

#: How many times the model may call tools before the turn is cut off. Each pass
#: is a billed request, so this is a cost ceiling as much as a safety one.
MAX_TOOL_ITERATIONS = _env_int('ASSISTANT_MAX_TOOL_ITERATIONS', 8)

#: Turns kept in context. Older ones are dropped rather than summarised - a
#: check-in is short by nature, and summarising is another billed request to
#: solve a problem this app does not have.
MAX_HISTORY_MESSAGES = _env_int('ASSISTANT_MAX_HISTORY_MESSAGES', 40)


def is_configured():
    """Whether there is an API key at all.

    The assistant is additive: every workspace it can reach is reachable without
    it. So an unconfigured instance hides the feature rather than erroring, and
    the app is fully usable by someone who never sets a key.
    """
    return bool((os.environ.get('OPENAI_API_KEY') or '').strip())
