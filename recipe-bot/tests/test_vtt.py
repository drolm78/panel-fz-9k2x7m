from recipe_bot.resolvers.vtt import vtt_a_texto

CABECERA = "WEBVTT\nKind: captions\nLanguage: es\n\n"


def test_quita_timestamps_y_etiquetas():
    vtt = CABECERA + "1\n00:00:01.000 --> 00:00:03.000\n<c>Pica</c> la cebolla\n"
    assert vtt_a_texto(vtt) == "Pica la cebolla"


def test_deduplica_lineas_repetidas_de_autosubs():
    vtt = CABECERA + (
        "00:00:01.000 --> 00:00:03.000\nvamos a hacer\n\n"
        "00:00:03.000 --> 00:00:05.000\nvamos a hacer unos huevos\n\n"
        "00:00:05.000 --> 00:00:07.000\nvamos a hacer unos huevos\n\n"
        "00:00:07.000 --> 00:00:09.000\ncon jitomate\n"
    )
    assert vtt_a_texto(vtt) == "vamos a hacer unos huevos con jitomate"


def test_decodifica_entidades_html():
    vtt = CABECERA + "00:00:01.000 --> 00:00:02.000\nsal &amp; pimienta\n"
    assert vtt_a_texto(vtt) == "sal & pimienta"


def test_vtt_vacio():
    assert vtt_a_texto(CABECERA) == ""
