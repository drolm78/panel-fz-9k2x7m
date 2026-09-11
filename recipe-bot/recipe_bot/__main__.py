"""Punto de entrada:  python -m recipe_bot"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

MIN_PYTHON = (3, 11)


def _exige_python() -> None:
    """macOS trae Python 3.9 de fábrica, y el esquema de la receta no carga ahí.

    Sin esto el error que sale es un TypeError de pydantic sobre anotaciones,
    que no le dice nada a nadie. Mejor avisar en español y con la solución.
    """
    if sys.version_info < MIN_PYTHON:
        actual = ".".join(str(n) for n in sys.version_info[:3])
        pedido = ".".join(str(n) for n in MIN_PYTHON)
        print(
            f"Este bot necesita Python {pedido} o mayor, y estas corriendo {actual}.\n\n"
            "En una Mac, la forma mas simple de arreglarlo es:\n"
            "    brew install python@3.12\n"
            "y despues volver a crear el entorno con ese Python:\n"
            "    rm -rf .venv\n"
            "    $(brew --prefix python@3.12)/bin/python3.12 -m venv .venv\n"
            "    source .venv/bin/activate\n"
            "    pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(1)


_exige_python()

from .bot import Bot  # noqa: E402  (despues del guardia de version, a proposito)
from .config import Config, ConfigError  # noqa: E402


def cargar_dotenv(ruta: Path) -> None:
    """Lector minimo de .env, para no depender de python-dotenv."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip().strip("'\""))


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cargar_dotenv(Path(".env"))
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 1

    Bot(cfg).correr()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
