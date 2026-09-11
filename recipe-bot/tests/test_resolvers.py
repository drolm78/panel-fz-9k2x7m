import pytest

from recipe_bot.resolvers import NO_SOPORTADA, ResolverError, construir, elegir, extraer_url


@pytest.mark.parametrize(
    "url,esperado",
    [
        ("https://www.youtube.com/watch?v=abc", "YouTube"),
        ("https://youtu.be/abc", "YouTube"),
        ("https://www.tiktok.com/@chef/video/123", "TikTok"),
        ("https://vm.tiktok.com/ZM1/", "TikTok"),
        ("https://www.instagram.com/reel/xyz/", "Meta"),
        ("https://fb.watch/abc/", "Meta"),
        ("https://www.facebook.com/reel/99", "Meta"),
    ],
)
def test_enruta_cada_plataforma(url, esperado):
    assert elegir(url, construir()).nombre == esperado


def test_plataforma_desconocida_sugiere_mandar_el_archivo():
    with pytest.raises(ResolverError) as exc:
        elegir("https://vimeo.com/123", construir())
    assert str(exc.value) == NO_SOPORTADA
    assert "archivo de video" in str(exc.value)


def test_instagram_y_facebook_reportan_su_propia_plataforma():
    meta = elegir("https://www.instagram.com/reel/xyz/", construir())
    assert meta._plataforma("https://www.instagram.com/reel/x/") == "Instagram"
    assert meta._plataforma("https://fb.watch/abc/") == "Facebook"


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("https://youtu.be/abc", "https://youtu.be/abc"),
        ("mira esto https://vm.tiktok.com/ZM1/ está bueno", "https://vm.tiktok.com/ZM1/"),
        ("(https://youtu.be/abc)", "https://youtu.be/abc"),
        ("sin liga", None),
        ("", None),
    ],
)
def test_extrae_la_url_del_mensaje(texto, esperado):
    assert extraer_url(texto) == esperado
