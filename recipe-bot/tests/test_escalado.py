from recipe_bot.models import necesita_escalar
from tests.factories import receta


def test_receta_completa_no_escala():
    assert necesita_escalar(receta()) is False


def test_confianza_media_escala():
    assert necesita_escalar(receta(confianza="media")) is True


def test_sin_ingredientes_escala():
    assert necesita_escalar(receta(ingredientes=[])) is True


def test_un_solo_paso_escala():
    assert necesita_escalar(receta(pasos=["Mezcla todo."])) is True
