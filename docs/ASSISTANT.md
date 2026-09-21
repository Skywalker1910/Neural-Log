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
| `get_checkin_plan` | what is worth asking about, in order, with reasons |
| `search_foods` | the catalogue, with serving and cup weights |
| `search_exercises` | the movement library |
| `get_survey_questions` | the check-in questions this account is asked |
| `propose_meal` | queues a meal |
| `propose_sleep` | queues a night |
| `propose_workout` | queues a training session |
| `propose_lifestyle` | queues water, steps, mood |
| `propose_study` | queues a study session |
| `propose_checkin` | queues answers to the daily check-in |

They talk to the database directly rather than to the app's own HTTP endpoints.
Self-calling would mean carrying a session cookie and working around the CSRF
guard, and a codebase should not learn how to do that.

The check-in does not write `daily_log` itself. `save_day()` was extracted into
`record_checklist_day()` and injected, so a day answered by talking goes through
the same activity row, the same audit trail and the same scoring as a day
answered by tapping. That function's docstring says a day logged there must be
indistinguishable from one logged by the legacy wizard; a second implementation
behind a chat window is exactly the drift it warns about, and it would surface
weeks later as a streak wrong by a day.

## The guided check-in

**Today —> Check in by chat** runs the whole day as a conversation. An
alternative route through the same data, not a replacement: tapping the list is
faster when you know what you did, talking is faster when you have to remember
it.

### The order is derived, not written down

The obvious way to build this is a fixed script — wake time, breakfast,
training, study. It works until the third day, when it asks about the workout you
logged from the gym two hours ago and you stop using it.

So `get_checkin_plan` computes the order from two numbers that were already in
`scoring/config.py` long before there was an assistant:

- **`measured_weight = 3.0` against `self_report_weight = 1.0`.** One answer
  about what you actually ate is worth three checklist ticks.
- **`self_report_ceiling = 0.5`.** An attribute with no measured evidence is
  capped at half, whatever the checklist claims. Asking about sleep does not
  merely add evidence — it lifts a ceiling.

Which gives the ranking without anyone having to invent one:

| Priority | Meaning |
|---|---|
| 3 | nothing has evidenced this attribute today, so it is stuck at 50% |
| 2 | nothing logged, but the attribute is evidenced by something else |
| 1 | the checklist — 1x, but the only direct evidence of Discipline |
| 0 | already recorded. Not asked about. |

Within a band, whichever topic unblocks the most capped attributes comes first:
training unlocks three, study two, sleep one.

A worked example. Nothing logged yet:

```
3  training  Agility, Stamina and Strength have no measured evidence today...
3  study     Focus and Knowledge have no measured evidence today...
3  food      Recovery has no measured evidence today...
3  sleep     Recovery has no measured evidence today...
3  steps     Stamina has no measured evidence today...
1  checkin   10 question(s) unanswered...
```

Log a workout and your steps, then ask again:

```
3  food      Recovery has no measured evidence today...
3  sleep     Recovery has no measured evidence today...
3  study     Focus and Knowledge have no measured evidence today...
1  checkin   10 question(s) unanswered...
0  steps     Already logged today - do not ask about this.
0  training  Already logged today - do not ask about this.
```

The model is given the reasons, not just the order, so it can explain itself
truthfully when asked why it wants to know about sleep. They are also true: the
50% in that sentence is the number the engine actually enforces.

### The card accumulates

A check-in queues as it goes — sleep on one turn, training on the next — and
all of it lands on **one** card at the end.

Worth stating because the first implementation got it wrong, and no unit test
caught it. Each turn's proposal superseded the last, so the card at the end held
only the final topic and everything earlier was silently dropped: you press Save
on something that looks right and lose two thirds of what you just said. A
browser found it in about a minute.

Proposals now extend the pending card within a conversation and supersede only
across conversations, which keeps the property that mattered — there are never
two live Save buttons.

One-per-day actions replace rather than stack, so correcting your bedtime
updates the queued one instead of queueing a second. The rule mirrors the
appliers: `_apply_sleep` deletes and reinserts, so two queued sleeps for one date
would be a card promising something the save cannot deliver.

## Scanning a nutrition label

**Nutrition —> Scan a label.** Photograph the panel on the back of a pack and
the product joins your catalogue, usable in the food picker and as a recipe
ingredient like anything else.

The shipped library has 248 foods and does not have the oat milk you actually
buy. Typing a packet in by hand means squinting at six numbers and getting the
units wrong on at least one, which is precisely the job for a camera.

### The model transcribes, the code computes

This is the whole design, and it exists because of one failure mode.

A panel states its values **per 100 g**, **per 100 ml**, or **per serving**. US
packaging leads with per-serving, EU packaging with per-100, and plenty of packs
print both in columns. Read the wrong one and every macro is off by the serving
factor — a 30 g cereal portion read as per-100 g understates the food by 70%.

Nothing about that looks broken. The numbers are plausible, the food saves
cleanly, and it quietly misreports every meal it is ever used in.

So the model is asked for two things it is good at — the numbers as printed,
and which column they came from — and explicitly **not** asked to convert. The
arithmetic happens in `label.to_per_100g`, which is pure, deterministic and
tested against every basis. Asking a language model to divide by 30 and multiply
by 100 is inviting an arithmetic error into the one place nothing would catch it.

The only conversion the model does do is kJ to kcal, because that factor is
exact and unambiguous.

### The review card shows its working

| | |
|---|---|
| **Conversion note** | "Scaled from a 30 g serving to 100 g (x3.33)" |
| **Unreadable list** | fields the model could not see, flagged amber rather than shown as a confident zero |

Both exist so the check is real rather than theatre. `x3.33 from a 30 g serving`
is checkable in a way that `400 kcal` is not, and *zero fibre* and *unknown
fibre* are different claims — only one of them belongs in somebody's intake.

A panel it cannot make sense of is refused with what to do about it: *"Could not
tell whether the panel is per serving or per 100 g — retake the photo with the
column headings visible."* Refusing beats guessing, because a guessed serving
factor produces a food that is wrong in a way nobody will notice.

### What it costs, and what leaves the device

Scanning runs on the **extraction model**, not the chat one — this is
transcription, not judgement. Measured: **$0.00045 a scan**, about a fortieth of
a check-in.

The photo is resized to 1400px on its long edge before it is sent. That is a
legibility floor rather than a guess: the interesting part is six numbers in
six-point type, and compressing past that starts making the model guess. It also
cuts a 4 MB camera file to about 300 KB.

Re-encoding as JPEG **strips the EXIF**, which on a phone carries GPS
coordinates. Sending someone's kitchen location to a third party along with a
picture of their cereal is not a trade anybody agreed to.

The image is held in memory for one request and **never written to disk**. It is
a picture of a packet; once the numbers are out there is nothing left to want.

### Bytes, not file names

The upload is checked against its own magic bytes rather than the declared
content type, which is whatever the client said it was. A photograph is the one
thing this app accepts that it did not generate, so it is the one place worth
looking. JPEG, PNG and WebP only — a camera produces nothing else, and every
extra format is another decoder to trust.

Request bodies are now capped at 8 MB, which until this feature there was no
limit on at all.

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
