# The assistant

Logging a day by typing is fast if you already know where everything lives. It
is slow if you have to remember that sleep is under Lifestyle, open the right
date, find "oats" in a catalogue of 248 foods and convert a bowl into grams.

The assistant is for the second case: say what happened, once, in a sentence.

It is also the first thing in this app that costs money per use and the first
thing that can write to your data without you typing the numbers. Both of those
shaped it more than the conversation did.

## The one rule

**The assistant cannot write to the app.**

Its write tools do not write. They validate what was said, turn it into a
normalised action, and queue it. You see a card, you fix any number it got
wrong, you press Save. Only then does anything reach the database.

This is not caution for its own sake. Logging a meal is not like opening a page:
`recompute_after_change` runs, attribute scores move, XP is awarded, a streak
extends, the leaderboard reorders. A misheard "eighty grams" that becomes eight
hundred is not a wrong row you notice — it is a bend in the trend the whole app
exists to show you, and the resulting chart looks completely normal.

So the model is also *told* it cannot save, in as many words, because a model
that thinks its tool call already wrote will say "logged your breakfast", you
will believe it, and you will never press Save.

## How a turn works

```
you                 "bowl of oats and a banana, slept 11:30 to 6:45"
  -> get_day         what is already recorded today
  -> search_foods    find oats, and what a serving of it weighs
  -> propose_meal    queued, not written
  -> propose_sleep   queued, not written
  <- "Ready to save: 80 g of oats and a banana... I took a bowl as 80 g."
  -> [ Save ]        now it is written
```

Four requests to the provider, one card, one tap.

### Why it asks about the right things

The first call is always `get_day`, and it returns `still_missing`. Anything
already logged is not asked about. If you recorded your training this morning,
the assistant asks about food and sleep instead — because being asked to repeat
yourself is the fastest way to make a tool like this not worth opening.

### Seven tools, not sixty

The app has sixty-odd endpoints. The assistant has seven tools. A model given
sixty chooses worse than one given seven, and most of those endpoints are read
paths that collapse into a single "what happened on this day" call.

| Tool | Reads or proposes |
|---|---|
| `get_day` | everything recorded on a date, and what is missing |
| `search_foods` | the catalogue, with serving and cup weights |
| `get_survey_questions` | the check-in questions this account is asked |
| `propose_meal` | queues a meal |
| `propose_sleep` | queues a night |
| `propose_lifestyle` | queues water, steps, mood |
| `propose_study` | queues a study session |

They talk to the database directly rather than to the app's own HTTP endpoints.
Self-calling would mean carrying a session cookie and working around the CSRF
guard, and a codebase should not learn how to do that.

**Not here yet:** training (sets and exercises are a richer shape and deserve
their own pass) and the daily check-in. The check-in has to run `save_day()`'s
scoring path, whose docstring says a day logged there must be indistinguishable
from one logged by the legacy wizard — a second implementation in the tool layer
is exactly the drift it warns about. Both land with the guided Today
conversation.

## Editing a proposal, and why that is safe

The card lets you correct numbers, because the mistakes are numeric. The
assistant rarely invents a meal you did not eat; it mishears eighty as eight
hundred.

The edited payload comes back from your browser, so it cannot simply be trusted.
`store.apply` reconciles it against what was stored: **same number of actions,
same types, same order — only values may differ.** An edit is a correction, never
a new instruction.

Without that check, "log a 300 kcal breakfast" could come back as "delete every
workout" and the Save button would mean nothing.

A proposal can be applied once. A second proposal supersedes a pending one, so
there are never two live Save buttons — pressing the older one would log
something you already talked past.

## What it costs

The first feature here that spends per request, so it is metered before it can
spend anything.

| | |
|---|---|
| Conversation | `gpt-5.6-terra`, $2 / $12 per Mtok |
| Extraction | `gpt-5.6-luna`, $0.20 / $1.20 per Mtok |
| Measured | ~$0.036 an uncached turn, ~$0.014 cached |
| A four-request check-in | ~$0.02 |

Per account: a daily cap and a monthly cap, both configurable, both defaulting
low. At the ceiling the assistant declines politely and says the rest of the app
still works — which it does, entirely.

**Admin → Assistant spend** shows the last 30 days broken down by feature,
because one total tells you the bill is too high and nothing about which part to
fix.

### The dollars are estimates and the page says so

They are computed locally from configurable rates. That is deliberate: the
provider's own billing lags by minutes to hours and reports the whole
organisation, so it cannot answer the one question the cap needs answered —
*may this person make a request right now?*

When the estimate and the invoice disagree, the invoice is right and the rates
want correcting:

```
OPENAI_PRICE_GPT_5_6_TERRA_INPUT=1.80
```

Tokens, by contrast, are recorded as fact. Failed requests are recorded too: a
log that counts only successes under-reports exactly when something is going
wrong.

## Configuration

```bash
OPENAI_API_KEY=                      # absent: the feature hides itself entirely
OPENAI_CHAT_MODEL=gpt-5.6-terra
OPENAI_EXTRACTION_MODEL=gpt-5.6-luna
ASSISTANT_MONTHLY_BUDGET_USD=3.00
ASSISTANT_DAILY_BUDGET_USD=0.75
```

With no key, `/api/assistant/state` reports `configured: false` and the SPA
renders no chat button at all — not a disabled one, not a "coming soon". An
instance without a key is the app as it was, and every workspace the assistant
can reach is reachable by hand.

## Privacy

`store=False` on every request: the provider is asked not to retain the
conversation. Someone's food, sleep and training is the most personal data this
app holds and it should not sit on a third party's disk because a default said
so.

Conversations are stored locally, per account, in `ai_conversations` and
`ai_messages`. Tool calls are not replayed into later turns — only your text and
the assistant's — which halves the token count and avoids feeding a stale
`get_day` from an hour ago back to the model.

## Testing it without spending anything

The tool layer is ordinary Python over the ordinary database, so the part that
decides what happens to your data is tested exhaustively and for free. The agent
loop is tested against a scripted fake client, which makes the interesting cases
— a model that invents a food id, one that loops forever, one that goes down
mid-turn — ordinary tests rather than things you hope not to see.

Nothing in the suite reaches the network.

## Related

- [`assistant/tools.py`](../assistant/tools.py) — the tool descriptions are the
  assistant's personality; they decide whether it asks about your protein or
  your bedtime
- [`assistant/store.py`](../assistant/store.py) — `apply()` is the security
  boundary
- [ARCHITECTURE.md](ARCHITECTURE.md) — how the app is built
