"""Convierte subtitulos WebVTT en texto corrido legible.

Los subtitulos automaticos de YouTube repiten cada linea 2-3 veces (efecto
karaoke), asi que deduplicar no es cosmetico: sin esto le mandamos al modelo
el triple de tokens y con el texto entrecortado.
"""
from __future__ import annotations

import re

_TIMESTAMP = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->")
_TAGS = re.compile(r"<[^>]+>")
_ENTIDADES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&#39;": "'", "&quot;": '"'}
_IGNORAR = ("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE")


def vtt_a_texto(vtt: str) -> str:
    lineas: list[str] = []
    for cruda in vtt.splitlines():
        linea = cruda.strip()
        if not linea or linea.isdigit() or _TIMESTAMP.match(linea):
            continue
        if any(linea.startswith(p) for p in _IGNORAR):
            continue
        linea = _TAGS.sub("", linea)
        for ent, char in _ENTIDADES.items():
            linea = linea.replace(ent, char)
        linea = " ".join(linea.split())
        if not linea:
            continue
        # Los autogenerados repiten la linea previa, o la extienden.
        if lineas:
            previa = lineas[-1]
            if linea == previa or previa.endswith(linea):
                continue
            if linea.startswith(previa):
                lineas[-1] = linea
                continue
        lineas.append(linea)
    return " ".join(lineas).strip()
