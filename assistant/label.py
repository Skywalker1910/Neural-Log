"""Reading a nutrition panel off a photograph.

The catalogue ships 248 foods. It does not have the oat milk you actually buy,
and typing a packet in by hand means squinting at six numbers and getting the
units wrong on at least one. A photograph is the obvious input.

## The division of labour, which is the whole design

**The model transcribes. The code computes.**

A nutrition panel states its values on one of three bases - per 100 g, per 100 ml,
or per serving - and which one it is decides everything. US packaging leads with
per-serving; EU packaging leads with per 100 g; plenty of packets print both, in
columns, in small type, at an angle, under a flash reflection.

Get the basis wrong and every macro is off by the serving factor. A 30 g cereal
portion read as per-100 g understates the food by 70%, and nothing about the
result looks broken: the numbers are plausible, the food saves cleanly, and it
quietly misreports every meal it is ever used in.

So the model is asked for two things it is good at - the numbers as printed, and
which column they came from - and explicitly *not* asked to convert. The
arithmetic happens in `to_per_100g` below, which is pure, deterministic and
tested against every basis. Asking a language model to divide by 30 and multiply
by 100 is inviting an arithmetic error into the one place nothing would catch it.

## What is not stored

The photograph. It is a picture of a packet, it is the largest thing the request
touches, and once the numbers are out of it there is nothing left to want. It
lives in memory for one request and is never written to disk.
"""
import base64
import json

from . import config, usage

#: Everything the model may return, as a forced tool call.
#:
#: A tool rather than a free-text JSON reply, for the same reason the rest of the
#: assistant uses tools: `strict` with a closed schema means the fields arrive
#: typed and complete, instead of arriving as prose that parses on a good day.
EXTRACTION_TOOL = {
    'type': 'function',
    'name': 'record_nutrition_panel',
    'description': 'Report what the nutrition panel in the photograph says.',
    'strict': True,
    'parameters': {
        'type': 'object',
        'properties': {
            'product_name': {
                'type': ['string', 'null'],
                'description': 'The product name from the packaging, if legible.',
            },
            'basis': {
                'type': 'string',
                'enum': ['per_100g', 'per_100ml', 'per_serving', 'unknown'],
                'description': (
                    'Which column these numbers came from. If the panel shows '
                    'both a per-100 and a per-serving column, use the per-100 one '
                    'and report per_100g or per_100ml. Never convert between them.'
                ),
            },
            'serving_size': {
                'type': ['number', 'null'],
                'description': 'The stated serving size as a number, e.g. 30 for "30 g".',
            },
            'serving_unit': {
                'type': ['string', 'null'],
                'enum': ['g', 'ml', None],
                'description': 'The unit of serving_size.',
            },
            'serving_name': {
                'type': ['string', 'null'],
                'description': 'How the label describes one serving, e.g. "1 slice (40 g)".',
            },
            'kcal': {'type': ['number', 'null'], 'description': 'Energy in kcal, not kJ.'},
            'protein': {'type': ['number', 'null'], 'description': 'Grams.'},
            'carbs': {'type': ['number', 'null'], 'description': 'Grams of total carbohydrate.'},
            'fat': {'type': ['number', 'null'], 'description': 'Grams of total fat.'},
            'fibre': {'type': ['number', 'null'], 'description': 'Grams.'},
            'unreadable': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': (
                    'Field names you could not read - blurred, cropped or absent. '
                    'Leave those fields null rather than estimating them.'
                ),
            },
            'is_nutrition_label': {
                'type': 'boolean',
                'description': 'False if the photograph is not a nutrition panel at all.',
            },
        },
        'required': [
            'product_name', 'basis', 'serving_size', 'serving_unit', 'serving_name',
            'kcal', 'protein', 'carbs', 'fat', 'fibre', 'unreadable',
            'is_nutrition_label',
        ],
        'additionalProperties': False,
    },
}

INSTRUCTIONS = """\
You are reading a photograph of a food package's nutrition panel.

Report the numbers exactly as printed. Do not convert between per-serving and \
per-100 values - report which column you read and the numbers from it, and say \
what the serving size is. The conversion is done elsewhere and doing it here \
would hide an arithmetic error where nothing can catch it.

If the panel shows both a per-100 column and a per-serving column, read the \
per-100 one.

Energy is often printed as "kJ / kcal". Report the kcal figure. If only kJ is \
shown, divide by 4.184 and report that as kcal - this one conversion is exact \
and unambiguous.

A number you cannot read is null, and its field name goes in `unreadable`. Never \
estimate, never infer a typical value for the product: a missing number is \
honest and a guessed one becomes part of somebody's daily intake.

If the photograph is not a nutrition panel, set is_nutrition_label false and \
leave everything else null.
"""


class LabelError(Exception):
    """The photograph could not be turned into a food."""


def to_per_100g(extracted):
    """Normalise a transcribed panel to the per-100g the database stores.

    Pure and deterministic on purpose - see the module docstring. Every branch
    here is one the model was explicitly told not to take.

    Returns `(macros, notes)` where notes explains any conversion, so the
    confirmation card can show its working rather than just a number.
    """
    basis = extracted.get('basis')
    fields = ('kcal', 'protein', 'carbs', 'fat', 'fibre')

    def value(name):
        raw = extracted.get(name)
        return None if raw is None else float(raw)

    if basis in ('per_100g', 'per_100ml'):
        # Already per 100. Millilitres are taken as grams, which is the same
        # assumption the rest of the app makes for drinks - true to about 3% for
        # anything water-based, and well inside the error already in "one glass".
        return (
            {name: value(name) for name in fields},
            'Taken straight from the per-100 column.' if basis == 'per_100g'
            else 'Per 100 ml, stored as per 100 g - 1 ml is taken as 1 g for drinks.',
        )

    if basis == 'per_serving':
        size = extracted.get('serving_size')
        if not size or float(size) <= 0:
            raise LabelError(
                'The panel is per serving but the serving size is not readable, so '
                'the numbers cannot be scaled. Retake the photo including the '
                'serving size, or enter this one by hand.'
            )
        size = float(size)
        factor = 100.0 / size
        return (
            {name: None if value(name) is None else round(value(name) * factor, 2)
             for name in fields},
            f'Scaled from a {size:g} {extracted.get("serving_unit") or "g"} serving '
            f'to 100 g (x{factor:.2f}).',
        )

    raise LabelError(
        'Could not tell whether the panel is per serving or per 100 g, so the '
        'numbers cannot be trusted. Retake the photo with the column headings '
        'visible.'
    )


def build_food(extracted):
    """The `foods` payload a confirmed extraction becomes.

    Not written here - handed to the client, corrected by a person, and posted to
    `/api/foods` like any other custom food. The scanner is an input method, not
    a second way into the catalogue.
    """
    if not extracted.get('is_nutrition_label'):
        raise LabelError(
            'That does not look like a nutrition panel. Point the camera at the '
            'table of values on the back of the pack.'
        )

    macros, note = to_per_100g(extracted)

    if macros.get('kcal') is None:
        raise LabelError(
            'The energy value could not be read, and a food without calories is '
            'not much use. Retake the photo, or enter this one by hand.'
        )

    unit = 'ml' if extracted.get('serving_unit') == 'ml' \
        or extracted.get('basis') == 'per_100ml' else 'g'

    return {
        'name': (extracted.get('product_name') or '').strip() or 'Scanned product',
        'category': 'prepared',
        'unit': unit,
        'kcal_per_100g': macros['kcal'],
        'protein_per_100g': macros.get('protein') or 0,
        'carbs_per_100g': macros.get('carbs') or 0,
        'fat_per_100g': macros.get('fat') or 0,
        'fibre_per_100g': macros.get('fibre') or 0,
        'serving_name': extracted.get('serving_name'),
        'serving_grams': extracted.get('serving_size'),
        # Surfaced so the card can show its working and flag what to check.
        'conversion_note': note,
        'unreadable': extracted.get('unreadable') or [],
        'basis': extracted.get('basis'),
    }


def _data_url(image_bytes, media_type):
    return f'data:{media_type};base64,{base64.b64encode(image_bytes).decode("ascii")}'


def read_label(conn, user_id, image_bytes, media_type, client=None):
    """One vision call. Returns the food payload a person then confirms.

    Uses the extraction model rather than the chat one: this is transcription,
    not judgement, and the cheaper model is an order of magnitude less per scan.
    """
    allowed, refusal = usage.check_budget(conn, user_id)
    if not allowed:
        raise LabelError(refusal)
    if usage.rate_limited(conn, user_id):
        raise LabelError('That is a lot of scans at once - give it a few seconds.')

    if client is None:
        from . import agent
        try:
            client = agent.build_client()
        except agent.AssistantUnavailable as error:
            raise LabelError(str(error)) from error

    model = config.EXTRACTION_MODEL
    try:
        response = client.responses.create(
            model=model,
            instructions=INSTRUCTIONS,
            input=[{
                'role': 'user',
                'content': [
                    {'type': 'input_text',
                     'text': 'Read this nutrition panel.'},
                    {'type': 'input_image',
                     'image_url': _data_url(image_bytes, media_type)},
                ],
            }],
            tools=[EXTRACTION_TOOL],
            # One tool, and it must be used - there is nothing else this call is
            # for, and a chatty text reply would just have to be re-parsed.
            tool_choice='required',
            max_output_tokens=600,
            store=False,
        )
    except Exception as error:  # noqa: BLE001 - provider errors are not a fixed class
        usage.record(conn, user_id, 'label', model, ok=False, error=error)
        raise LabelError('The scanner is unreachable right now. Try again shortly.') from error

    from .agent import _usage_from
    usage.record(conn, user_id, 'label', model, _usage_from(response))

    call = next(
        (item for item in (getattr(response, 'output', None) or [])
         if getattr(item, 'type', None) == 'function_call'),
        None,
    )
    if call is None:
        raise LabelError('The scanner could not read that photo. Try again in better light.')

    try:
        extracted = json.loads(getattr(call, 'arguments', '') or '{}')
    except ValueError as error:
        raise LabelError('The scanner returned something unreadable. Try again.') from error

    return build_food(extracted)
