"""One turn of conversation: text in, tool calls run, text and a proposal out.

## Why this is a generator

A turn can take twenty seconds. It may call `get_day`, then `search_foods`
twice, then answer - four round trips to the provider, none of them fast. A
`POST` that returns at the end of all that is a spinner with nothing behind it,
and it is also a request long enough to argue with a proxy timeout.

So the turn yields events as it goes: `status` while a tool runs, `reply` when
there is text, `done` with whatever was queued. The endpoint turns those into
server-sent events and the client shows "checking your day" instead of nothing.

Tests consume the generator directly, which is why the SSE framing lives in the
blueprint and not here.

## Why the text is not streamed token by token

It could be, and it is deliberately not - yet. Streaming tokens means
reassembling tool-call JSON from partial deltas, and a half-parsed tool call is
a class of bug that ends in a wrong database row. Per-turn granularity gets most
of the perceived speed for none of that risk. Token streaming is worth adding
once the tool loop has earned trust.

## Why `store=False`

The provider is asked not to retain the conversation. Someone's food, sleep and
training is the most personal data this app holds, and it should not sit on a
third party's disk because a default said so.
"""
import json

from . import config, tools, usage

#: The contract, stated to the model as plainly as it is stated in the code.
#:
#: The paragraph about not claiming to have saved anything is load-bearing. A
#: model that believes its tool call wrote to the database will say "logged your
#: breakfast", the person will believe it, and they will never press Save.
SYSTEM_PROMPT = """\
You are the assistant inside Neural Log, a personal tracking app. You are \
talking to the person whose data it is.

Your job is to help them record their day quickly and accurately, and to answer \
questions about what they have logged.

HOW SAVING WORKS. You cannot write to the app. The propose_* tools queue a \
change for the person to confirm - they see a card and press Save. Never say you \
have logged, saved, recorded or added anything. Say what you are ready to save \
and let them confirm. If you are unsure of a number, ask rather than guessing: an \
unrecorded day is honest, and a wrong one quietly becomes part of the trend this \
app exists to show them.

BEFORE YOU ASK ANYTHING, call get_day. It returns `still_missing`. Do not ask \
about things that are already recorded - if they logged their training this \
morning, ask about food or sleep instead. Asking someone to repeat themselves is \
the fastest way to make this tool not worth using.

FOOD. Always search_foods before proposing a meal; never invent a food id. \
People say "a bowl of oats" and "two eggs", not grams. The search result tells \
you the serving weight, the cup weight and whether the food is countable - use \
those to convert, and say what you converted so they can correct you. If nothing \
in the catalogue matches, say so rather than substituting something close.

STYLE. Short. One question at a time. No preamble, no restating what they just \
said, no enthusiasm about their progress unless they ask. This is a logging tool \
that happens to talk, not a coach.

Today's date is {today}. When someone says "last night" they usually mean the \
sleep that ended this morning.
"""


#: The guided daily check-in. A different job from free chat, so a different
#: prompt rather than a paragraph bolted onto the last one.
#:
#: The ordering instruction is the substance. `get_checkin_plan` computes what is
#: worth asking from the scoring engine's own weights - a topic ranks highly
#: because its attribute is capped at half until something evidences it, not
#: because a developer listed it first. Telling the model to follow that order,
#: and to say why when it helps, is what turns a fixed questionnaire into
#: something that adapts to the day the person actually had.
TODAY_PROMPT = """\
You are running the daily check-in inside Neural Log, with the person whose data \
it is. The aim is to capture their day in about a minute.

START by calling get_checkin_plan. It returns the topics worth asking about, in \
order, each with the reason it ranks there. Follow that order.

The order is not arbitrary and not a script. A topic near the top is one whose \
attribute cannot rise above half until something is logged against it, so asking \
about it is worth more than anything else you could ask. Anything marked \
`recorded` is already logged - do not ask about it, do not confirm it, do not \
mention it unless they bring it up.

ONE QUESTION AT A TIME. Wait for the answer. If they answer three things at \
once, take all three and skip ahead - never re-ask something they already told \
you. If they say they did not do something, accept it and move on; "no training \
today" is an answer, not a gap to probe.

QUEUE AS YOU GO. Call the propose_* tools when you learn something, rather than \
saving everything for the end. You cannot write to the app - the tools queue a \
change for the person to confirm, and they see one card at the end and press \
Save. Never say you have logged, saved or recorded anything.

WHEN THE PLAN IS DONE, or when they say they are finished, stop asking and give \
them one short summary of what is ready to save. Do not keep going to the bottom \
of the list if they have clearly had enough.

NEVER INVENT A NUMBER. If they say "a bowl of oats", search_foods and use the \
serving weight, then tell them what you assumed so they can correct it. If they \
are vague about something that has no sensible default, ask once, and if they \
still do not know, leave it out. An unrecorded day is honest; a guessed one \
becomes part of the trend this app exists to show them.

STYLE. Short. No preamble, no restating their answer back, no praise. This is a \
logging tool that happens to talk.

Today's date is {today}. "Last night" means the sleep that ended this morning.
"""


class AssistantUnavailable(Exception):
    """No key, no budget, or the provider is down. Never fatal to the app."""


def build_client():
    """The provider client, or a refusal that the caller can present.

    Imported lazily so the whole package stays importable - and the test suite
    stays runnable - on a machine where `openai` is not installed. The assistant
    is optional; nothing else in the app should fail to start because of it.
    """
    if not config.is_configured():
        raise AssistantUnavailable('The assistant is not configured on this instance.')
    try:
        from openai import OpenAI
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise AssistantUnavailable('The openai package is not installed.') from error
    return OpenAI()


def _usage_from(response):
    """Tokens, in the shape usage.record wants.

    `cached_tokens` lives under `input_tokens_details` and is a *subset* of
    `input_tokens` - counted, not added.
    """
    raw = getattr(response, 'usage', None)
    if raw is None:
        return {}
    details = getattr(raw, 'input_tokens_details', None)
    return {
        'input_tokens': getattr(raw, 'input_tokens', 0) or 0,
        'output_tokens': getattr(raw, 'output_tokens', 0) or 0,
        'cached_input_tokens': getattr(details, 'cached_tokens', 0) or 0 if details else 0,
    }


def _text_of(response):
    text = (getattr(response, 'output_text', '') or '').strip()
    return text


def _function_calls(response):
    return [item for item in (getattr(response, 'output', None) or [])
            if getattr(item, 'type', None) == 'function_call']


def _run_tool(ctx, call):
    """Execute one tool call and return the block to feed back.

    Every failure becomes a `tool_result` the model can read rather than an
    exception that ends the turn. Models recover from "no food with id 999999,
    use search_foods" perfectly well, and a turn that dies on the first bad
    argument is a turn the person has to start again.
    """
    name = getattr(call, 'name', '')
    spec = tools.TOOLS.get(name)

    if spec is None:
        payload = {'error': f'No tool named {name}.'}
    else:
        try:
            arguments = json.loads(getattr(call, 'arguments', '') or '{}')
        except ValueError:
            payload = {'error': 'Your arguments were not valid JSON. Send them again.'}
        else:
            try:
                payload = spec['handler'](ctx, **arguments)
            except tools.ToolError as error:
                payload = {'error': str(error)}
            except TypeError as error:
                payload = {'error': f'Wrong arguments for {name}: {error}'}

    return {
        'type': 'function_call_output',
        'call_id': getattr(call, 'call_id', ''),
        'output': json.dumps(payload, default=str)[:6000],
    }


def run_turn(conn, user_id, history, user_message, *,
             feature='chat', client=None, today=None, recompute=None,
             username=None, record_checklist=None, instructions=None):
    """Yield the events of one turn.

    `history` is the prior conversation in provider shape. The caller owns
    persistence - this function is pure with respect to the conversation, which
    is what lets a test run a whole multi-tool turn against a fake client and no
    database rows at all.
    """
    allowed, refusal = usage.check_budget(conn, user_id)
    if not allowed:
        yield {'type': 'error', 'message': refusal, 'kind': 'budget'}
        return

    if usage.rate_limited(conn, user_id):
        yield {'type': 'error', 'kind': 'rate_limit',
               'message': 'That is a lot of messages at once - give it a few seconds.'}
        return

    try:
        client = client or build_client()
    except AssistantUnavailable as error:
        yield {'type': 'error', 'message': str(error), 'kind': 'unavailable'}
        return

    ctx = tools.ToolContext(conn, user_id, today=today, username=username,
                            record_checklist=record_checklist)
    instructions = (instructions or SYSTEM_PROMPT).format(today=ctx.today)
    schema = tools.schema_for_provider()

    conversation = list(history) + [{'role': 'user', 'content': user_message}]
    reply = ''

    for iteration in range(config.MAX_TOOL_ITERATIONS):
        try:
            response = client.responses.create(
                model=config.CHAT_MODEL,
                instructions=instructions,
                input=conversation,
                tools=schema,
                tool_choice='auto',
                max_output_tokens=900,
                # The reasoning here is "which question is still unanswered",
                # not a proof. Low effort is both enough and most of the cost.
                reasoning={'effort': 'low'},
                # Not retained by the provider. See the module docstring.
                store=False,
            )
        except Exception as error:  # noqa: BLE001 - provider errors are not a fixed class
            usage.record(conn, user_id, feature, config.CHAT_MODEL, ok=False, error=error)
            yield {'type': 'error', 'kind': 'provider',
                   'message': 'The assistant is unreachable right now. Nothing was saved.'}
            return

        usage.record(conn, user_id, feature, config.CHAT_MODEL, _usage_from(response))

        calls = _function_calls(response)
        text = _text_of(response)
        if text:
            reply = text

        if not calls:
            break

        conversation.extend(getattr(response, 'output', None) or [])
        for call in calls:
            spec = tools.TOOLS.get(getattr(call, 'name', ''))
            yield {'type': 'status', 'tool': getattr(call, 'name', ''),
                   'writes': bool(spec and spec['writes'])}
            conversation.append(_run_tool(ctx, call))
    else:
        # Fell out of the loop still wanting tools. Almost always a model going
        # in circles; capped because every pass is another billed request.
        yield {'type': 'status', 'tool': None, 'writes': False,
               'note': 'stopped after the maximum number of steps'}

    yield {
        'type': 'done',
        'reply': reply or "I did not follow that - could you say it another way?",
        'queued': ctx.queued,
        'budget': usage.budget_state(conn, user_id),
    }
