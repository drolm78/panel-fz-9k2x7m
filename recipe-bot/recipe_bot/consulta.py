"""Receta dictada -> registro nuevo en la tabla Notas de "2026 Extraespecial".

Tres catalogos, tres estrategias distintas, y no es capricho:

- Medicamentos (~280) y presentaciones (~319) caben en el prompt, asi que el
  modelo elige la cadena exacta y aqui se verifica que exista. Elegir bien entre
  "Tradea LP Tabletas 20 mg..." y "Tradea Tabletas 10 mg..." pide entender lo
  dictado, no parecido de letras.
- Pacientes (3166) no caben. Esos se buscan localmente por parecido, y cuando
  hay empate NO se adivina: se pregunta. Escribir en el expediente equivocado es
  el peor error posible de este flujo, y es silencioso.

Nada se crea: si lo dictado no esta en el catalogo, el campo se queda vacio.
"""
from __future__ import annotations

import calendar
import difflib
import logging
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date

import anthropic
import requests

from .models import LecturaReceta

log = logging.getLogger(__name__)

API = "https://api.airtable.com/v0"
TTL_CATALOGO = 3600  # 1 h: son 3166 pacientes, no conviene releerlos seguido

# Un solo candidato claramente mejor que el resto: se usa.
# Empate o parecido pobre: se pregunta.
UMBRAL_ACEPTAR = 0.72
VENTAJA_MINIMA = 0.08
CANDIDATOS = 4


def _normalizar(texto: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.lower().split())


def sumar_meses(desde: date, meses: int) -> date:
    """31 de enero + 1 mes = 28 de febrero, no 3 de marzo."""
    indice = desde.month - 1 + meses
    anio = desde.year + indice // 12
    mes = indice % 12 + 1
    return date(anio, mes, min(desde.day, calendar.monthrange(anio, mes)[1]))


@dataclass(frozen=True)
class Paciente:
    nombre: str
    record_id: str


@dataclass(frozen=True)
class Candidato:
    paciente: Paciente
    puntaje: float


@dataclass(frozen=True)
class CatalogoClinico:
    pacientes: tuple[Paciente, ...]
    medicamentos: tuple[str, ...]
    presentaciones: tuple[str, ...]
    momento: float = field(default_factory=time.time)

    @property
    def vigente(self) -> bool:
        return (time.time() - self.momento) < TTL_CATALOGO

    def buscar_pacientes(self, dictado: str) -> list[Candidato]:
        """Los mejores candidatos por parecido, de mayor a menor."""
        objetivo = _normalizar(dictado)
        if not objetivo:
            return []
        palabras = set(objetivo.split())

        puntuados: list[Candidato] = []
        for p in self.pacientes:
            nombre = _normalizar(p.nombre)
            parecido = difflib.SequenceMatcher(None, objetivo, nombre).ratio()
            # Whisper suele acertar los apellidos y fallar el nombre de pila (o al
            # reves); contar palabras completas rescata esos casos.
            comunes = palabras & set(nombre.split())
            cobertura = len(comunes) / len(palabras) if palabras else 0.0
            puntuados.append(Candidato(p, max(parecido, cobertura * 0.95)))

        puntuados.sort(key=lambda c: c.puntaje, reverse=True)
        return puntuados[:CANDIDATOS]

    def resolver_opcion(self, dictado: str, opciones: tuple[str, ...]) -> str | None:
        objetivo = _normalizar(dictado)
        for opcion in opciones:
            if _normalizar(opcion) == objetivo:
                return opcion
        return None


def hay_ganador(candidatos: list[Candidato]) -> Paciente | None:
    """Solo si uno destaca. Un empate se resuelve preguntando, no adivinando."""
    if not candidatos or candidatos[0].puntaje < UMBRAL_ACEPTAR:
        return None
    if len(candidatos) > 1 and (candidatos[0].puntaje - candidatos[1].puntaje) < VENTAJA_MINIMA:
        return None
    return candidatos[0].paciente


# --- carga del catálogo ----------------------------------------------------


def _paginar(url: str, token: str, params: dict) -> list[dict]:
    registros: list[dict] = []
    offset: str | None = None
    while True:
        consulta = dict(params)
        if offset:
            consulta["offset"] = offset
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                         params=consulta, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"Airtable respondió {r.status_code}: {r.text[:300]}")
        datos = r.json()
        registros.extend(datos.get("records", []))
        offset = datos.get("offset")
        if not offset:
            return registros


def cargar_catalogo(
    token: str, base_id: str, tabla_notas: str, tabla_pacientes: str, campo_nombre: str
) -> CatalogoClinico:
    meta = requests.get(
        f"{API}/meta/bases/{base_id}/tables",
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    if meta.status_code != 200:
        raise RuntimeError(f"Airtable respondió {meta.status_code}: {meta.text[:300]}")

    notas = next(
        (t for t in meta.json().get("tables", []) if t["name"].lower() == tabla_notas.lower()),
        None,
    )
    if notas is None:
        raise RuntimeError(f"No encuentro la tabla '{tabla_notas}'.")

    def opciones(nombre_campo: str) -> tuple[str, ...]:
        for campo in notas["fields"]:
            if campo["name"].lower() == nombre_campo.lower():
                elecciones = (campo.get("options") or {}).get("choices") or []
                return tuple(c["name"] for c in elecciones if c["name"].strip())
        raise RuntimeError(f"La tabla '{tabla_notas}' no tiene un campo '{nombre_campo}'.")

    crudos = _paginar(
        f"{API}/{base_id}/{requests.utils.quote(tabla_pacientes, safe='')}",
        token,
        {"fields[]": campo_nombre, "pageSize": 100},
    )
    pacientes = tuple(
        Paciente(nombre=(r.get("fields") or {}).get(campo_nombre, ""), record_id=r["id"])
        for r in crudos
        if (r.get("fields") or {}).get(campo_nombre)
    )
    if not pacientes:
        raise RuntimeError(f"La tabla '{tabla_pacientes}' no devolvió pacientes.")

    cat = CatalogoClinico(
        pacientes=pacientes,
        medicamentos=opciones("Medicamento 1"),
        presentaciones=opciones("Presentación de medicamento 1"),
    )
    log.info(
        "catálogo clínico: %d pacientes, %d medicamentos, %d presentaciones",
        len(cat.pacientes), len(cat.medicamentos), len(cat.presentaciones),
    )
    return cat


# --- extracción ------------------------------------------------------------

SISTEMA = """\
Conviertes lo que un médico paidopsiquiatra dicta en una receta para el \
expediente de su paciente.

Reglas:

1. Si el mensaje no pide registrar una receta, pon es_receta en false y explica \
en `respuesta` qué entendiste.
2. `paciente` es el nombre TAL COMO SE DICTÓ. No lo corrijas ni lo completes: la \
búsqueda del expediente se hace aparte.
3. `medicamento` y `presentacion` DEBEN ser una de las opciones de las listas de \
abajo, copiada EXACTAMENTE, carácter por carácter, con sus mayúsculas, acentos, \
puntos y paréntesis. Si ninguna corresponde, deja cadena vacía.
4. Las listas traen variantes y erratas acumuladas con los años ("Aripiprazol" y \
"Aripirpazol", "Clozapina" y "Clozepina"). Elige la que esté mejor escrita y cuya \
dosis y presentación coincidan con lo dictado. Si dicta "Tradea 20", busca la \
entrada de Tradea con 20 mg, no la de 10.
5. NUNCA inventes un medicamento ni una presentación que no estén en las listas. \
Un campo vacío es aceptable; uno inventado no.
6. `indicacion` es cómo tomarlo, en las palabras del doctor, incluyendo la \
duración si la dijo.
7. Si pide otra receta "dentro de N días" o "dentro de N meses", llena \
`repetir_dias` o `repetir_meses`. "Dentro de un mes" es repetir_meses = 1. Si no \
lo menciona, los dos van en null.

Responde en español de México.\
"""


def leer(
    client: anthropic.Anthropic, modelo: str, texto: str, catalogo: CatalogoClinico
) -> LecturaReceta:
    mensaje = (
        "--- MEDICAMENTOS VÁLIDOS ---\n" + "\n".join(catalogo.medicamentos) + "\n\n"
        "--- PRESENTACIONES VÁLIDAS ---\n" + "\n".join(catalogo.presentaciones) + "\n\n"
        f"--- LO QUE DICTÓ ---\n{texto.strip()}"
    )
    log.info("leyendo receta de %d caracteres", len(texto))

    respuesta = client.messages.parse(
        model=modelo,
        max_tokens=4000,
        system=SISTEMA,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": mensaje}],
        output_format=LecturaReceta,
    )
    return respuesta.parsed_output
