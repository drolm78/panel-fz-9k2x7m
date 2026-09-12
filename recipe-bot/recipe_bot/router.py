"""A cuál de los tres caminos va un mensaje.

Se hace con una llamada al modelo en lugar de con palabras clave porque el
español real no coopera: "receta" es de cocina o es médica según el contexto, y
"dale 500" puede ser un gasto o una dosis. Una llamada de clasificación cuesta
centavos y evita mandar una receta médica al camino de gastos.
"""
from __future__ import annotations

import logging

import anthropic

from .models import Clasificacion, Intencion

log = logging.getLogger(__name__)

SISTEMA = """\
Clasificas mensajes de un médico paidopsiquiatra hacia uno de cuatro destinos.

- "receta": pide registrar una receta médica para un paciente. Suele traer un \
nombre de persona y un medicamento. Ej: "recétale Tradea 20 a Juan Pérez, una \
tableta en la mañana por 30 días".
- "gasto": registra un movimiento de dinero con un monto. Ej: "350 de gasolina \
con Inbursa", "pagué 1200 en Office Depot".
- "video": pide procesar un video de cocina para sacar la receta de comida.
- "otro": cualquier otra cosa. Una pregunta, un saludo, una nota suelta.

Ojo con la palabra "receta": en cocina es un platillo, en consulta es un \
medicamento para un paciente. Decide por el contenido, no por la palabra.

Ante la duda entre "receta" y "gasto", fíjate en qué hay: un nombre de persona \
más un medicamento es receta; un monto en pesos es gasto.\
"""


def clasificar(client: anthropic.Anthropic, modelo: str, texto: str) -> Intencion:
    respuesta = client.messages.parse(
        model=modelo,
        max_tokens=1000,
        system=SISTEMA,
        messages=[{"role": "user", "content": texto.strip()}],
        output_format=Clasificacion,
    )
    resultado = respuesta.parsed_output
    log.info("intención: %s (%s)", resultado.intencion, resultado.porque)
    return resultado.intencion
