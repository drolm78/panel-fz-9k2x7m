"""Muestreo de cuadros del video.

En los reels de cocina buena parte de la receta esta *en pantalla* y nunca se
dice en voz alta ("2 tazas de harina" sobreimpreso, o simplemente se ve el
ingrediente). Transcribir solo el audio deja recetas con huecos.

Se usa deteccion de cambio de escena en vez de un intervalo fijo: en un video
de cocina cada corte suele ser un paso o un ingrediente nuevo, asi que da mas
informacion por cuadro y evita mandar 15 fotos casi identicas.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

UMBRAL_ESCENA = 0.25
MIN_CUADROS_UTILES = 4


class FFmpegNoDisponible(RuntimeError):
    pass


def _exige(binario: str) -> str:
    ruta = shutil.which(binario)
    if not ruta:
        raise FFmpegNoDisponible(
            f"No encuentro {binario} en el PATH. Instala ffmpeg "
            "(apt-get install ffmpeg / brew install ffmpeg)."
        )
    return ruta


def cmd_escenas(video: Path, salida: Path, max_cuadros: int, ancho: int) -> list[str]:
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video),
        "-vf", f"select='gt(scene,{UMBRAL_ESCENA})',scale={ancho}:-2",
        "-vsync", "vfr", "-frames:v", str(max_cuadros), "-q:v", "4",
        str(salida / "frame_%03d.jpg"),
    ]


def cmd_intervalo(video: Path, salida: Path, max_cuadros: int, ancho: int, duracion: float) -> list[str]:
    # Reparte los cuadros parejo a lo largo del video.
    fps = max(max_cuadros / max(duracion, 1.0), 0.05)
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video),
        "-vf", f"fps={fps:.4f},scale={ancho}:-2",
        "-frames:v", str(max_cuadros), "-q:v", "4",
        str(salida / "frame_%03d.jpg"),
    ]


def duracion_segundos(video: Path) -> float:
    _exige("ffprobe")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    )
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0.0


def _correr(cmd: list[str]) -> None:
    subprocess.run(cmd, capture_output=True, text=True, check=True)


def muestrear(video: Path, workdir: Path, max_cuadros: int = 16, ancho: int = 640) -> list[Path]:
    """Devuelve las rutas de los cuadros extraidos, en orden cronologico."""
    _exige("ffmpeg")
    salida = workdir / "frames"
    salida.mkdir(parents=True, exist_ok=True)

    try:
        _correr(cmd_escenas(video, salida, max_cuadros, ancho))
    except subprocess.CalledProcessError as exc:
        log.warning("deteccion de escenas fallo: %s", exc.stderr)

    cuadros = sorted(salida.glob("frame_*.jpg"))
    if len(cuadros) >= MIN_CUADROS_UTILES:
        return cuadros[:max_cuadros]

    # Un video de una sola toma (muy comun en reels) no tiene cortes que
    # detectar: caemos a intervalo fijo.
    log.info("solo %d cuadros por escena; uso intervalo fijo", len(cuadros))
    for f in cuadros:
        f.unlink(missing_ok=True)
    try:
        _correr(cmd_intervalo(video, salida, max_cuadros, ancho, duracion_segundos(video)))
    except subprocess.CalledProcessError as exc:
        log.warning("muestreo por intervalo fallo: %s", exc.stderr)
    return sorted(salida.glob("frame_*.jpg"))[:max_cuadros]
