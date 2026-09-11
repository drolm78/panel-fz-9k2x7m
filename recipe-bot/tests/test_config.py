import pytest

from recipe_bot.config import ConfigError, parse_user_ids


def test_acepta_varios_ids():
    assert parse_user_ids("123, 456;789") == frozenset({123, 456, 789})


def test_lista_vacia_es_error():
    # Sin lista blanca cualquiera que encuentre el bot gasta creditos de API.
    with pytest.raises(ConfigError, match="creditos"):
        parse_user_ids("  ,  ")


def test_id_no_numerico_es_error():
    with pytest.raises(ConfigError, match="user id"):
        parse_user_ids("123,@felipe")
