"""Gasto dictado -> registro en Airtable.

El hueco que esto llena: un estado de cuenta bancario nunca ve el efectivo.
Dictarlo en el momento es la única forma de que ese gasto exista.
"""
from __future__ import annotations

import logging
from datetime import date

import anthropic

from .models import LecturaGasto

log = logging.getLogger(__name__)

SISTEMA = """\
Conviertes lo que el doctor dicta o escribe en un registro de gasto.

Contexto: es un médico paidopsiquiatra con consultorio en La Paz, BCS, y otro en \
Jardín Balbuena, CDMX. Los montos son pesos mexicanos.

Reglas:

1. Si el mensaje no registra un gasto con un monto, pon es_gasto en false y explica \
en `respuesta` qué entendiste. Una pregunta, un saludo o una nota no son gastos.
2. Resuelve las fechas relativas contra la fecha de hoy que se te da. "Ayer", "el \
lunes", "antier" se convierten a YYYY-MM-DD. Si no se dice fecha, usa hoy.
3. El monto es solo el número. "Trescientos cincuenta" son 350. "Mil doscientos con \
cincuenta" son 1200.50. Si dicta "mil quinientos pesos de gasolina", el monto es 1500.
4. Si no se menciona la ciudad, usa "La Paz", que es donde trabaja la mayor parte del \
tiempo, y anótalo en `falta`.
5. Si no se menciona la forma de pago, usa "Efectivo" y anótalo en `falta`.
6. `tipo` es "Fijo" solo para gastos recurrentes comprometidos: renta, sueldos, \
suscripciones, servicios. Todo lo demás es "Variable".
7. `deducible` es true para gastos del consultorio (insumos, renta, software, cursos, \
equipo). La comida personal y los gastos personales van en false.
8. El concepto es corto y en minúsculas salvo nombres propios: "gasolina", \
"tóner impresora", "renta consultorio Balbuena".
9. No inventes. Lo que hayas tenido que suponer va en `falta`.

Responde en español de México.\
"""


def leer(client: anthropic.Anthropic, modelo: str, texto: str, hoy: date | None = None) -> LecturaGasto:
    hoy = hoy or date.today()
    mensaje = (
        f"Hoy es {hoy.isoformat()} ({_dia_semana(hoy)}).\n\n"
        f"--- LO QUE DICTÓ ---\n{texto.strip()}"
    )
    log.info("leyendo gasto de %d caracteres", len(texto))

    respuesta = client.messages.parse(
        model=modelo,
        max_tokens=4000,
        system=SISTEMA,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": mensaje}],
        output_format=LecturaGasto,
    )
    return respuesta.parsed_output


_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _dia_semana(d: date) -> str:
    return _DIAS[d.weekday()]
