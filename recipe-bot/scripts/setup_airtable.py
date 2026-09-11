#!/usr/bin/env python3
"""Crea la tabla 'Recetas' en tu base de Airtable con el esquema que espera el bot.

Uso:
    export AIRTABLE_TOKEN=pat...   # necesita scope schema.bases:write
    export AIRTABLE_BASE_ID=app...
    python scripts/setup_airtable.py

Es idempotente: si la tabla ya existe, no la toca y te lo dice.
"""
from __future__ import annotations

import os
import sys

import requests

API = "https://api.airtable.com/v0/meta/bases"

PLATAFORMAS = ["YouTube", "TikTok", "Instagram", "Facebook", "Archivo"]
CONFIANZAS = ["alta", "media", "baja"]


def campos() -> list[dict]:
    entero = {"precision": 0}
    decimal = {"precision": 1}
    return [
        # El primero es el campo primario de la tabla.
        {"name": "Nombre", "type": "singleLineText"},
        {"name": "Plataforma", "type": "singleSelect",
         "options": {"choices": [{"name": p} for p in PLATAFORMAS]}},
        {"name": "URL", "type": "url"},
        {"name": "Autor", "type": "singleLineText"},
        {"name": "Porciones", "type": "number", "options": entero},
        {"name": "Tiempo (min)", "type": "number", "options": entero},
        {"name": "Ingredientes", "type": "multilineText"},
        {"name": "Preparación", "type": "multilineText"},
        {"name": "Notas", "type": "multilineText"},
        {"name": "Kcal / porción", "type": "number", "options": entero},
        {"name": "Proteína (g)", "type": "number", "options": decimal},
        {"name": "Carbos netos (g)", "type": "number", "options": decimal},
        {"name": "Grasa (g)", "type": "number", "options": decimal},
        {"name": "Keto", "type": "checkbox",
         "options": {"icon": "check", "color": "greenBright"}},
        {"name": "Adaptación keto", "type": "multilineText"},
        {"name": "Tags", "type": "multipleSelects", "options": {"choices": []}},
        {"name": "Confianza", "type": "singleSelect",
         "options": {"choices": [{"name": c} for c in CONFIANZAS]}},
        {"name": "Agregada", "type": "date",
         "options": {"dateFormat": {"name": "iso"}}},
    ]


def main() -> int:
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    base = os.environ.get("AIRTABLE_BASE_ID", "").strip()
    tabla = os.environ.get("AIRTABLE_TABLE", "Recetas").strip()
    if not token or not base:
        print("Faltan AIRTABLE_TOKEN y/o AIRTABLE_BASE_ID.", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    existentes = requests.get(f"{API}/{base}/tables", headers=headers, timeout=30)
    if existentes.status_code != 200:
        print(f"No pude leer la base ({existentes.status_code}): {existentes.text[:300]}",
              file=sys.stderr)
        return 1
    for t in existentes.json().get("tables", []):
        if t["name"].lower() == tabla.lower():
            print(f"La tabla '{t['name']}' ya existe (id {t['id']}). No toco nada.")
            return 0

    r = requests.post(
        f"{API}/{base}/tables",
        headers=headers,
        json={
            "name": tabla,
            "description": "Recetas extraídas de videos de YouTube, TikTok, Instagram y Facebook.",
            "fields": campos(),
        },
        timeout=30,
    )
    if r.status_code != 200:
        print(f"Airtable respondió {r.status_code}: {r.text[:500]}", file=sys.stderr)
        return 1

    print(f"Tabla '{tabla}' creada (id {r.json()['id']}).")
    print(f"https://airtable.com/{base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
