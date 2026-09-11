"""Objetos de ejemplo para las pruebas."""
from recipe_bot.models import Ingrediente, Receta
from recipe_bot.resolvers import Source


def receta(**overrides) -> Receta:
    base = dict(
        titulo="Huevos al albañil",
        porciones=2,
        tiempo_min=15,
        ingredientes=[
            Ingrediente(cantidad="4", nombre="huevo", nota=None),
            Ingrediente(cantidad="200 g", nombre="jitomate", nota="picado"),
        ],
        pasos=["Bate los huevos.", "Sofríe el jitomate.", "Mezcla y cuaja."],
        notas=None,
        kcal_porcion=310,
        proteina_g=22.0,
        carbos_netos_g=6.5,
        grasa_g=21.0,
        es_keto=True,
        adaptacion_keto=None,
        tags=["desayuno", "huevo"],
        confianza="alta",
        falta=[],
    )
    base.update(overrides)
    return Receta(**base)


def source(**overrides) -> Source:
    base = dict(
        plataforma="TikTok",
        url="https://www.tiktok.com/@chef/video/123",
        autor="@chef",
        caption="Huevos al albañil",
    )
    base.update(overrides)
    return Source(**base)
