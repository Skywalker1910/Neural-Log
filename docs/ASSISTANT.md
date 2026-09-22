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
| `get_open_work` | active goals and outstanding tasks |
| `propose_tasks_done` | queues tasks as finished |
| `propose_goal_progress` | queues a new total on a measured goal |

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

### Goals and tasks close it, and rank nowhere

A check-in ends by asking about anything outstanding - open tasks, goals with a
number to move.

They are deliberately **not** in the weighted order above. `init_goals` is
registered with no recompute function, because a goal is an intention rather than
evidence, and neither goals nor tasks feed any attribute. Ranking them beside
sleep and training would mean inventing an analytical weight the scoring engine
does not give them, which is the kind of quiet dishonesty the rest of this app is
built to avoid.

So the plan carries them in a separate `follow_up` block that says
`affects_scores: false`, and the prompt asks for one question at the end, dropped
entirely if the person is done talking. Nothing to follow up on means no closing
question rather than a limp "anything else?".

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

### Firing the shutter on its own

Point the camera at the panel and it captures by itself, once the frame is
worth sending. The manual shutter never goes away.

**It did not work.** The first detector scored a frame as
`horizontalRules * 0.5 + verticalRules * 0.25 + denseText * 0.25` and captured
above `0.57`. The rule terms counted scanlines where a quarter of the pixels
changed sharply against the line above, which finds the black bars of a US panel
— while the pack is parallel to the sensor.

Measured against a rendered panel:

| Tilt | Score | |
|---|---|---|
| 0 degrees | 0.651 | fires |
| 2 degrees | 0.277 | never |
| 5 degrees | 0.027 | never |

Tilt smears a bar across several rows and the term collapses. With it gone the
other two cap out at `0.5`, so the threshold was **arithmetically unreachable**
— not unlikely, unreachable. Nobody holds a phone to two degrees, so it
never fired for anyone, and the preview said *"Centre the nutrition table"*
while a centred nutrition table sat in the middle of it.

#### What it looks for now

Three signals, none of which assume the pack is square to the camera.

| Signal | What it is | Why |
|---|---|---|
| **Banding** | Ink binned into rows at seven shear angles, best one wins | A tilted table is still a table. This is the term that was broken. |
| **Ink** | Share of the crop that is dark, after an Otsu split | Too little is a label too far away; too much is a thumb over the lens. |
| **Focus** | Share of edges that are steep rather than smeared | A blurred frame spends a scan on something the model cannot read. |

Ink and focus **multiply** rather than vote. Scoring all three as a weighted sum
is what let a blurred frame pass on banding alone; as gates, a beautifully
banded frame that is out of focus is simply not worth sending, and no amount of
banding can outvote that.

Two other things changed with it:

- **It scores the guide box, not the sensor frame.** The preview is
  `object-cover` in a 4:3 box, so a 16:9 stream loses its edges before anybody
  sees them. Judging the framing by pixels the person is not being shown is how
  a detector ends up disagreeing with the instruction printed over it.
- **Steady now means steady.** The old loop counted qualifying frames, which is
  also what you get panning along a shelf. Consecutive frames are compared.

The preview says which signal is short — *"Hold still while it focuses"*,
*"Move closer to the table"* — because *"Centre the nutrition table"*, held
forever, tells you nothing about what to change.

#### Why this has tests and the rest of the SPA does not

`frontend/src/lib/imageCapture.test.ts` is the first frontend test in the
project, and the reason is specific: this is arithmetic, it was wrong, and
nothing else could have caught it. Typecheck, lint and build all passed the
whole time it could not fire. Driving a browser did not catch it either —
the camera looked completely normal.

The fixtures are panels rendered into plain pixel buffers with tilt, blur,
lighting and sensor grain dialled by hand, so the tilt regression is four
assertions rather than a story. `npm test` runs them; CI runs them on every pull
request.

Verified end to end the other way too: Chromium will serve a `.y4m` file as a
webcam, so a photograph of a panel held four degrees off square goes in as a
real camera stream. The current build fires on it and fills the review form. The
previous build, same feed, never fires at all.

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

## Logging a session

Ask to log a workout and the assistant looks for your saved routines first.

```
you        "I want to log my workout"
           -> Back & Biceps  (4 exercises)
           -> Chest & Triceps (4 exercises)
you        picks one
           -> a row per exercise, targets pre-filled, each with its own numbers
you        corrects what differed, unticks what you skipped, adds what you added
           -> one card to confirm
```

With no routines saved it asks which muscles you worked and offers exercises
from those groups instead, with nothing pre-ticked.

### Why a row per exercise

The first version asked for "sets each", "reps each" and "weight each" — one
set of numbers for everything you ticked — and flattened the lot into a
sentence for the model to re-read.

That is fine for a circuit that genuinely is 3x10 and wrong for every other
session, because nobody benches and curls the same load. It recorded a number
that was false for most of the exercises, or you gave up and typed the session
out by hand.

Routine rows arrive **pre-ticked with the targets filled in**, because you said
you followed that routine — the likely edit is removing one, not adding six. A
muscle-group pick arrives with **nothing ticked**, because that list is a menu of
what you *could* have done and a pre-ticked menu logs the menu.

Every card can add an exercise from the library. Nobody follows a routine
exactly, and without that you log the plan rather than the session.

### Why the card submits data rather than a sentence

Every other card answers by composing a sentence and sending it as an ordinary
chat turn. That is a good rule — one validated path — and this deliberately
departs from it.

Six exercises with their own sets, reps, weights and units flatten into a
paragraph that costs one round trip to write and another to re-parse, and throws
away the exercise ids the card already looked up — so the model searches every
name back up and can pick the wrong Bench Press.

So the card submits what it already knows, and the server queues it by calling
**the same tool function the model would have called**. Same validation, same
plausibility checks, same confirmation card. It is not a second path into the
database; it is the same path with a different caller, and it costs nothing.

## Kilograms and pounds

The workout card carries a `kg`/`lb` toggle, defaulting to
`user_profile.weight_unit`, and the sets it queues store the unit they were
entered in. So does the logging screen, which is where the same preference and
the same conversion rules are written down in full: see
**[TRAINING.md](TRAINING.md#kilograms-and-pounds)**.

Two things are worth repeating here, because the assistant is a second way
into the same table:

- **Weights are stored exactly as entered and converted only on read.** The
  tool layer applies its plausibility ceiling in kilograms — 600 kg is the
  limit whichever unit you typed — and stores the number untouched.
- **`scoring/units.py` owns the factor.** The tool that totals a session's
  volume uses the same SQL fragment the Training endpoints use, because the
  version that drifts is always the one nobody is looking at.

A real session logged through the card at 40/135/65 lb stores **3483.6 kg**,
not 7680.

## What a scanned label knows about a serving

A panel does not only say what is in 100 g. It usually says what one serving is,
and that is what somebody actually eats.

| Label says | Stored as |
|---|---|
| Whey protein, "per scoop (30 g)" | `serving_name` "1 scoop", `serving_grams` 30, **countable** |
| Chicken breast, "per 100 g" | no serving, not countable |

`is_countable` is what makes the food picker offer **"2 scoops"** instead of
making you do the 30 g multiplication in your head before typing it. It is set
only when the label names a serving as a thing — a scoop, a bar, a slice —
*and* says what one weighs, because a counter without a weight cannot be turned
into macros.

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
