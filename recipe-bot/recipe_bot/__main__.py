"""Punto de entrada:  python -m recipe_bot"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from .bot import Bot
from .config import Config, ConfigError


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
