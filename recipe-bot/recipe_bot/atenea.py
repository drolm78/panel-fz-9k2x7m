"""Movimientos dictados -> tabla Master de Atenea.

Los catalogos (formas de pago, lugares, categorias) se leen de Airtable en
caliente, no van escritos aqui. Dos razones: cambian seguido, y con ~190
lugares y ~54 categorias acumuladas, hardcodearlos seria condenar al usuario a
editar codigo cada vez que agregue una tienda.

El modelo elige de lo que existe. Nunca se manda `typecast`, asi que el bot no
puede crear opciones nuevas ni formas de pago nuevas por su cuenta: si dicta
algo que no esta en el catalogo, se deja el campo vacio y se dice.
"""
from __future__ import annotations

import logging
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date

import anthropic
import requests

from .models import LecturaMovimiento

log = logging.getLogger(__name__)

API = "https://api.airtable.com/v0"
TTL_CATALOGO = 600  # 10 min: cambia poco, y evita una llamada por gasto


class AteneaError(RuntimeError):
    pass


def _normalizar(texto: str) -> str:
    """Para comparar 'Súper', 'super' y 'SUPER' como lo mismo."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.lower().split())


@dataclass(frozen=True)
class Catalogo:
    formas_pago: dict[str, str]  # nombre -> record id de Sumandos
    lugares: tuple[str, ...]
    categorias: tuple[str, ...]
    momento: float = field(default_factory=time.time)

    @property
    def vigente(self) -> bool:
        return (time.time() - self.momento) < TTL_CATALOGO

    def resolver_forma_pago(self, dictado: str) -> str | None:
        """Devuelve el record id, o None si no coincide con ninguna cuenta."""
        objetivo = _normalizar(dictado)
        for nombre, rec_id in self.formas_pago.items():
            if _normalizar(nombre) == objetivo:
                return rec_id
        return None

    def resolver_opcion(self, dictado: str, opciones: tuple[str, ...]) -> str | None:
        """Devuelve la opcion existente exacta, o None si no hay ninguna igual."""
        objetivo = _normalizar(dictado)
        for opcion in opciones:
            if _normalizar(opcion) == objetivo:
                return opcion
        return None


def _get(url: str, token: str, params: dict | None = None) -> dict:
    r = requests.get(
        url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30
    )
    if r.status_code != 200:
        raise AteneaError(f"Airtable respondió {r.status_code}: {r.text[:300]}")
    return r.json()


def cargar_catalogo(token: str, base_id: str, tabla_master: str, tabla_sumandos: str) -> Catalogo:
    """Lee de Airtable las opciones vigentes de Lugar, Categoría y Forma de pago."""
    meta = _get(f"{API}/meta/bases/{base_id}/tables", token)
    master = next(
        (t for t in meta.get("tables", []) if t["name"].lower() == tabla_master.lower()), None
    )
    if master is None:
        raise AteneaError(f"No encuentro la tabla '{tabla_master}' en esa base de Airtable.")

    def opciones(nombre_campo: str) -> tuple[str, ...]:
        for campo in master["fields"]:
            if campo["name"].lower() == nombre_campo.lower():
                elecciones = (campo.get("options") or {}).get("choices") or []
                # Hay opciones vacias heredadas; no sirven para elegir.
                return tuple(c["name"] for c in elecciones if c["name"].strip())
        raise AteneaError(f"La tabla '{tabla_master}' no tiene un campo '{nombre_campo}'.")

    sumandos = _get(f"{API}/{base_id}/{requests.utils.quote(tabla_sumandos, safe='')}", token)
    formas: dict[str, str] = {}
    for reg in sumandos.get("records", []):
        nombre = (reg.get("fields") or {}).get("Forma de pago")
        if nombre:
            formas[nombre] = reg["id"]
    if not formas:
        raise AteneaError(f"La tabla '{tabla_sumandos}' no devolvió ninguna forma de pago.")

    cat = Catalogo(
        formas_pago=formas,
        lugares=opciones("Lugar"),
        categorias=opciones("Categoría"),
    )
    log.info(
        "catálogo de Atenea: %d formas de pago, %d lugares, %d categorías",
        len(cat.formas_pago), len(cat.lugares), len(cat.categorias),
    )
    return cat


# --- extracción ------------------------------------------------------------

SISTEMA = """\
Conviertes lo que el doctor dicta o escribe en un movimiento para su tabla de \
finanzas personales.

Contexto: es un médico paidopsiquiatra con consultorio en La Paz, BCS, y otro en \
Jardín Balbuena, CDMX. Los montos son pesos mexicanos.

Reglas:

1. Si el mensaje no registra un movimiento con un monto, pon es_movimiento en false \
y explica en `respuesta` qué entendiste. Una pregunta o un saludo no son movimientos.
2. Resuelve las fechas relativas contra la fecha de hoy que se te da. "Ayer", "el \
lunes", "antier" se convierten a YYYY-MM-DD. Si no se dice fecha, usa hoy.
3. El monto es solo el número, positivo. "Trescientos cincuenta" son 350.
4. `forma_pago`, `lugar` y `categoria` DEBEN ser una de las opciones que se te dan \
más abajo, copiada EXACTAMENTE como aparece, carácter por carácter. No inventes \
opciones nuevas ni corrijas su ortografía.
5. Las listas traen variantes del mismo concepto acumuladas con los años \
("WALMART" y "Walmart", "Súper" y "Super"). Elige la que esté mejor escrita: \
mayúscula inicial y acentuación correcta.
6. Si lo que dictó no corresponde a NINGUNA opción de la lista, deja ese campo \
como cadena vacía y anótalo en `falta`. No lo fuerces a la opción más parecida: \
es mejor un campo vacío que una categoría equivocada.
7. `detalles` es texto libre: qué se compró, para quién, cualquier cosa útil que \
no quepa en los otros campos.
8. No inventes. Lo que hayas tenido que suponer va en `falta`.

Responde en español de México.\
"""

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _dia_semana(d: date) -> str:
    return _DIAS[d.weekday()]


def leer(
    client: anthropic.Anthropic,
    modelo: str,
    texto: str,
    catalogo: Catalogo,
    hoy: date | None = None,
) -> LecturaMovimiento:
    hoy = hoy or date.today()
    mensaje = (
        f"Hoy es {hoy.isoformat()} ({_dia_semana(hoy)}).\n\n"
        f"--- FORMAS DE PAGO VÁLIDAS ---\n{' | '.join(sorted(catalogo.formas_pago))}\n\n"
        f"--- LUGARES VÁLIDOS ---\n{' | '.join(catalogo.lugares)}\n\n"
        f"--- CATEGORÍAS VÁLIDAS ---\n{' | '.join(catalogo.categorias)}\n\n"
        f"--- LO QUE DICTÓ ---\n{texto.strip()}"
    )
    log.info("leyendo movimiento de %d caracteres", len(texto))

    respuesta = client.messages.parse(
        model=modelo,
        max_tokens=4000,
        system=SISTEMA,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": mensaje}],
        output_format=LecturaMovimiento,
    )
    return respuesta.parsed_output
