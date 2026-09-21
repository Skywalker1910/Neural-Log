"""Reading a nutrition panel off a photograph.

Most of this file is arithmetic, and that is the point. A label states its values
per 100 g, per 100 ml, or per serving, and getting that wrong scales every macro
by the serving factor while leaving numbers that look entirely plausible - a 30 g
cereal portion read as per-100 g understates the food by 70%, saves cleanly, and
misreports every meal it is ever used in.

So the model transcribes and declares its basis, and `to_per_100g` does the
conversion. That function is pure, so every basis can be tested exhaustively for
free, which is the trade the whole design exists to make.
"""
import io

import assistant.config as config
import assistant.label as label
import assistant.usage as usage
from conftest import register

# The smallest valid files of each kind, for the sniffer. Not real images - the
# endpoint only looks at the first bytes, which is the point of the test.
JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 40
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40
WEBP = b'RIFF\x00\x00\x00\x00WEBP' + b'\x00' * 40
GIF = b'GIF89a' + b'\x00' * 40


def panel(**overrides):
    base = {
        'product_name': 'Oat Drink Barista',
        'basis': 'per_100ml', 'serving_size': 200, 'serving_unit': 'ml',
        'serving_name': '1 glass (200 ml)',
        'kcal': 59, 'protein': 1.0, 'carbs': 6.6, 'fat': 3.0, 'fibre': 0.8,
        'unreadable': [], 'is_nutrition_label': True,
    }
    base.update(overrides)
    return base


# --- the arithmetic ------------------------------------------------------------

def test_a_per_100g_panel_is_taken_as_printed():
    macros, note = label.to_per_100g(panel(basis='per_100g'))

    assert macros == {'kcal': 59.0, 'protein': 1.0, 'carbs': 6.6, 'fat': 3.0, 'fibre': 0.8}
    assert 'per-100' in note


def test_a_per_serving_panel_is_scaled_to_100g():
    """The conversion that matters. A 30 g serving at 120 kcal is 400 per 100 g.

    Read as per-100 instead, the food would understate by 70% - and nothing about
    400 or 120 looks wrong on its own, which is why this is code rather than
    something the model was asked to do.
    """
    macros, note = label.to_per_100g(panel(
        basis='per_serving', serving_size=30, serving_unit='g',
        kcal=120, protein=3.0, carbs=20.0, fat=2.5, fibre=1.5,
    ))

    assert macros['kcal'] == 400.0
    assert macros['protein'] == 10.0
    assert macros['carbs'] == 66.67
    assert 'x3.33' in note, 'the card should be able to show its working'


def test_a_serving_larger_than_100g_scales_down():
    """The other direction, which is the one that silently inflates a food."""
    macros, _ = label.to_per_100g(panel(
        basis='per_serving', serving_size=250, serving_unit='g', kcal=200,
        protein=8.0, carbs=24.0, fat=7.0, fibre=2.0,
    ))

    assert macros['kcal'] == 80.0


def test_millilitres_are_stored_as_grams_and_the_note_says_so():
    """The same 1 ml = 1 g the rest of the app assumes for drinks, stated rather
    than done quietly."""
    macros, note = label.to_per_100g(panel(basis='per_100ml'))

    assert macros['kcal'] == 59.0
    assert 'ml' in note and '1 g' in note


def test_a_per_serving_panel_with_no_serving_size_is_refused():
    """Refusing beats guessing. There is no correct factor to apply, and an
    invented one produces a food that is wrong in a way nobody will notice."""
    try:
        label.to_per_100g(panel(basis='per_serving', serving_size=None))
        assert False, 'expected a LabelError'
    except label.LabelError as error:
        assert 'serving size' in str(error)
        assert 'Retake' in str(error), 'the refusal should say what to do next'


def test_a_zero_serving_size_is_refused_rather_than_dividing_by_it():
    try:
        label.to_per_100g(panel(basis='per_serving', serving_size=0))
        assert False, 'expected a LabelError'
    except label.LabelError:
        pass


def test_an_unknown_basis_is_refused():
    """If the model could not tell which column it read, the numbers mean
    nothing - and half of them would still be plausible."""
    try:
        label.to_per_100g(panel(basis='unknown'))
        assert False, 'expected a LabelError'
    except label.LabelError as error:
        assert 'per serving or per 100' in str(error)


def test_an_unreadable_macro_stays_null_rather_than_becoming_zero():
    """Zero protein and unknown protein are different claims.

    Zero would be carried into every meal as fact; null lets the card ask.
    """
    macros, _ = label.to_per_100g(panel(basis='per_100g', protein=None))

    assert macros['protein'] is None
    assert macros['kcal'] == 59.0


# --- turning that into a food --------------------------------------------------

def test_a_scanned_panel_becomes_a_food_payload():
    food = label.build_food(panel())

    assert food['name'] == 'Oat Drink Barista'
    assert food['kcal_per_100g'] == 59.0
    assert food['unit'] == 'ml', 'a drink should read in millilitres'
    assert food['serving_name'] == '1 glass (200 ml)'
    assert 'conversion_note' in food


def test_a_solid_food_reads_in_grams():
    food = label.build_food(panel(basis='per_100g', serving_unit='g'))

    assert food['unit'] == 'g'


def test_a_photo_that_is_not_a_label_is_refused():
    try:
        label.build_food(panel(is_nutrition_label=False))
        assert False, 'expected a LabelError'
    except label.LabelError as error:
        assert 'not look like a nutrition panel' in str(error)


def test_a_panel_with_no_calories_is_refused():
    """Everything in this app is per-100g calories first. A food without them
    would save and then be useless."""
    try:
        label.build_food(panel(kcal=None))
        assert False, 'expected a LabelError'
    except label.LabelError as error:
        assert 'energy value' in str(error)


def test_unreadable_fields_are_passed_through_for_the_card():
    """So the confirmation card can point at what to check rather than showing
    a confident zero."""
    food = label.build_food(panel(fibre=None, unreadable=['fibre']))

    assert food['unreadable'] == ['fibre']
    assert food['fibre_per_100g'] == 0, 'the payload still needs a number'


def test_a_nameless_product_still_saves():
    food = label.build_food(panel(product_name=None))

    assert food['name'] == 'Scanned product'


# --- the endpoint --------------------------------------------------------------

def post_image(client, data, filename='label.jpg', content_type='image/jpeg'):
    return client.post(
        '/api/assistant/label',
        data={'image': (io.BytesIO(data), filename)},
        content_type='multipart/form-data',
    )


def test_a_scan_needs_an_image(client):
    register(client)

    assert post_image(client, b'').status_code == 400
    assert client.post('/api/assistant/label', data={},
                       content_type='multipart/form-data').status_code == 400


def test_a_non_image_is_refused_on_its_bytes_not_its_name(client):
    """The declared content type is whatever the client said it was.

    A photograph is the one thing this app accepts that it did not generate, so
    it is the one place worth looking at the actual bytes.
    """
    register(client)

    response = post_image(client, b'#!/bin/sh\nrm -rf /\n',
                          filename='label.jpg', content_type='image/jpeg')

    assert response.status_code == 400
    assert 'not a JPEG' in response.get_json()['error']


def test_a_gif_is_refused(client):
    """Not in the accept list - a camera will not produce one, and every extra
    format is another decoder to trust."""
    register(client)
    assert post_image(client, GIF, filename='label.gif').status_code == 400


def test_every_accepted_format_sniffs_correctly():
    assert label is not None  # imported for the module under test
    from assistant_api import _sniff_image

    assert _sniff_image(JPEG) == 'image/jpeg'
    assert _sniff_image(PNG) == 'image/png'
    assert _sniff_image(WEBP) == 'image/webp'
    assert _sniff_image(GIF) is None
    # RIFF also fronts .wav, so webp needs the second check.
    assert _sniff_image(b'RIFF\x00\x00\x00\x00WAVE' + b'\x00' * 8) is None


def test_a_scan_is_refused_over_budget(app_module, client, monkeypatch):
    register(client)
    conn = app_module.get_db_connection()
    monkeypatch.setattr(config, 'DAILY_BUDGET_USD', 0.001)
    usage.record(conn, 1, 'label', 'gpt-5.6-luna',
                 {'input_tokens': 900_000, 'output_tokens': 0})

    class Boom:
        def __init__(self):
            self.responses = self

        def create(self, **kwargs):
            raise AssertionError('the provider should not have been called')

    try:
        label.read_label(conn, 1, JPEG, 'image/jpeg', client=Boom())
        assert False, 'expected a LabelError'
    except label.LabelError as error:
        assert 'limit' in str(error)


def test_a_scan_is_metered_against_the_cheap_model(app_module, client):
    """Transcription, not judgement - so it runs on the extraction model, which
    is an order of magnitude less per scan."""
    from types import SimpleNamespace
    import json as _json

    register(client)
    conn = app_module.get_db_connection()

    class Fake:
        def __init__(self):
            self.responses = self
            self.model = None

        def create(self, **kwargs):
            self.model = kwargs['model']
            return SimpleNamespace(
                output=[SimpleNamespace(
                    type='function_call', name='record_nutrition_panel',
                    call_id='c1', arguments=_json.dumps(panel()),
                )],
                output_text='',
                usage=SimpleNamespace(
                    input_tokens=1400, output_tokens=120,
                    input_tokens_details=SimpleNamespace(cached_tokens=0),
                ),
            )

    fake = Fake()
    food = label.read_label(conn, 1, JPEG, 'image/jpeg', client=fake)

    assert fake.model == config.EXTRACTION_MODEL
    assert food['kcal_per_100g'] == 59.0

    report = usage.report(conn)
    assert report['by_feature'][0]['feature'] == 'label'
    # 1400 in / 120 out on Luna: pennies of a penny.
    assert report['totals']['estimated_cost_usd'] < 0.01


def test_a_provider_failure_is_recorded_and_explained(app_module, client):
    register(client)
    conn = app_module.get_db_connection()

    class Broken:
        def __init__(self):
            self.responses = self

        def create(self, **kwargs):
            raise RuntimeError('vision service down')

    try:
        label.read_label(conn, 1, JPEG, 'image/jpeg', client=Broken())
        assert False, 'expected a LabelError'
    except label.LabelError as error:
        assert 'unreachable' in str(error)

    assert usage.report(conn)['totals']['failures'] == 1
