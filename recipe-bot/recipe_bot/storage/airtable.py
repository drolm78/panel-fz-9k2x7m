"""Guardado en Airtable.

`construir_campos` es puro a proposito: es lo unico que tiene que coincidir
exactamente con el esquema que crea scripts/setup_airtable.py, asi que conviene
poder probarlo sin red.
"""
from __future__ import annotations

import logging
from datetime import date

import requests

from ..models import Receta
from ..resolvers import Source

log = logging.getLogger(__name__)

API = "https://api.airtable.com/v0"

CAMPOS = {
    "nombre": "Nombre",
    "plataforma": "Plataforma",
    "url": "URL",
    "autor": "Autor",
    "porciones": "Porciones",
    "tiempo": "Tiempo (min)",
    "ingredientes": "Ingredientes",
    "preparacion": "Preparación",
    "notas": "Notas",
    "kcal": "Kcal / porción",
    "proteina": "Proteína (g)",
    "carbos": "Carbos netos (g)",
    "grasa": "Grasa (g)",
    "keto": "Keto",
    "adaptacion": "Adaptación keto",
    "tags": "Tags",
    "confianza": "Confianza",
    "agregada": "Agregada",
}


class AirtableError(RuntimeError):
    pass


def formatear_ingredientes(receta: Receta) -> str:
    lineas = []
    for ing in receta.ingredientes:
        partes = [p for p in (ing.cantidad, ing.nombre) if p]
        linea = " ".join(partes) if partes else ing.nombre
        if ing.nota:
            linea += f" ({ing.nota})"
        lineas.append(f"- {linea}")
    return "\n".join(lineas)


def formatear_pasos(receta: Receta) -> str:
    return "\n".join(f"{i}. {paso}" for i, paso in enumerate(receta.pasos, start=1))


def construir_campos(receta: Receta, source: Source, hoy: date | None = None) -> dict:
    notas = receta.notas or ""
    if receta.falta:
        faltantes = "; ".join(receta.falta)
        notas = (notas + "\n\n" if notas else "") + f"⚠️ Quedó incompleto: {faltantes}"

    campos = {
        CAMPOS["nombre"]: receta.titulo,
        CAMPOS["plataforma"]: source.plataforma,
        CAMPOS["autor"]: source.autor or "",
        CAMPOS["ingredientes"]: formatear_ingredientes(receta),
        CAMPOS["preparacion"]: formatear_pasos(receta),
        CAMPOS["notas"]: notas,
        CAMPOS["keto"]: receta.es_keto,
        CAMPOS["adaptacion"]: receta.adaptacion_keto or "",
        CAMPOS["tags"]: receta.tags,
        CAMPOS["confianza"]: receta.confianza,
        CAMPOS["agregada"]: (hoy or date.today()).isoformat(),
    }

    # Airtable rechaza null en numericos si el campo tiene formato; mejor omitir.
    opcionales = {
        CAMPOS["url"]: source.url,
        CAMPOS["porciones"]: receta.porciones,
        CAMPOS["tiempo"]: receta.tiempo_min,
        CAMPOS["kcal"]: receta.kcal_porcion,
        CAMPOS["proteina"]: receta.proteina_g,
        CAMPOS["carbos"]: receta.carbos_netos_g,
        CAMPOS["grasa"]: receta.grasa_g,
    }
    campos.update({k: v for k, v in opcionales.items() if v is not None})
    return campos


def guardar(receta: Receta, source: Source, token: str, base_id: str, tabla: str) -> str:
    """Crea el registro y devuelve la liga directa al mismo."""
    r = requests.post(
        f"{API}/{base_id}/{requests.utils.quote(tabla, safe='')}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        # typecast deja que Airtable cree las opciones de Tags que no existan.
        json={"fields": construir_campos(receta, source), "typecast": True},
        timeout=30,
    )
    if r.status_code != 200:
        raise AirtableError(f"Airtable respondió {r.status_code}: {r.text[:400]}")

    record_id = r.json().get("id", "")
    return f"https://airtable.com/{base_id}/{record_id}"
