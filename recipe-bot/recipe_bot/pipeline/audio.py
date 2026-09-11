"""Extraccion y transcripcion de audio.

La transcripcion va contra cualquier API compatible con el endpoint
/audio/transcriptions de OpenAI, asi que el mismo codigo sirve para OpenAI
(whisper-1) y para Groq (whisper-large-v3-turbo, mas barato y mas rapido).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import requests

log = logging.getLogger(__name__)

# 16 kHz mono es lo que Whisper usa internamente; mandar mas es pagar de mas.
LIMITE_BYTES = 25 * 1024 * 1024


class TranscripcionError(RuntimeError):
    pass


def cmd_extraer_audio(video: Path, salida: Path) -> list[str]:
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
        str(salida),
    ]


def extraer_audio(video: Path, workdir: Path) -> Path:
    if not shutil.which("ffmpeg"):
        raise TranscripcionError("Falta ffmpeg para extraer el audio.")
    salida = workdir / "audio.mp3"
    try:
        subprocess.run(cmd_extraer_audio(video, salida), capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise TranscripcionError(f"ffmpeg no pudo extraer el audio: {exc.stderr}") from exc
    if not salida.exists() or salida.stat().st_size == 0:
        raise TranscripcionError("El video no trae pista de audio.")
    return salida


def transcribir(audio: Path, base_url: str, api_key: str, modelo: str, timeout: float = 300.0) -> str:
    if audio.stat().st_size > LIMITE_BYTES:
        raise TranscripcionError(
            f"El audio pesa {audio.stat().st_size // 1_048_576} MB y el limite son 25 MB."
        )
    with audio.open("rb") as fh:
        r = requests.post(
            f"{base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio.name, fh, "audio/mpeg")},
            data={"model": modelo, "response_format": "text"},
            timeout=timeout,
        )
    if r.status_code != 200:
        raise TranscripcionError(f"La API de transcripcion respondio {r.status_code}: {r.text[:300]}")
    return r.text.strip()
