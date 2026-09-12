"""Configuracion leida del entorno (ver .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def _req(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Falta la variable de entorno {name} (ver .env.example)")
    return value


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} debe ser un entero, no {raw!r}") from exc


def parse_user_ids(raw: str) -> frozenset[int]:
    """'123, 456' -> {123, 456}. Lista vacia es un error de configuracion."""
    ids = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError as exc:
            raise ConfigError(
                f"TELEGRAM_ALLOWED_USERS trae {chunk!r}, que no es un user id numerico"
            ) from exc
    if not ids:
        raise ConfigError(
            "TELEGRAM_ALLOWED_USERS esta vacio. Sin lista blanca, cualquiera que "
            "encuentre el bot puede gastar tus creditos de API."
        )
    return frozenset(ids)


@dataclass(frozen=True)
class Config:
    telegram_token: str
    allowed_users: frozenset[int]

    anthropic_model: str
    airtable_token: str
    airtable_base_id: str
    airtable_table: str
    # Base "Atenea": ahi vive la tabla Master, tu contabilidad.
    airtable_base_atenea: str
    airtable_tabla_master: str
    airtable_tabla_sumandos: str
    # Base "2026 Extraespecial": expedientes y recetas.
    airtable_base_consulta: str
    airtable_tabla_notas: str
    airtable_tabla_pacientes: str

    transcribe_base_url: str
    transcribe_api_key: str
    transcribe_model: str

    work_dir: Path
    cookies_file: Path | None
    max_frames: int
    frame_width: int
    # Arriba de esto no bajamos el video para muestrear cuadros: un video largo
    # casi siempre trae subtitulos, y bajarlo completo no se paga solo.
    max_video_seconds: int = 900

    @classmethod
    def from_env(cls) -> "Config":
        cookies = os.environ.get("COOKIES_FILE", "").strip()
        return cls(
            telegram_token=_req("TELEGRAM_TOKEN"),
            allowed_users=parse_user_ids(_req("TELEGRAM_ALLOWED_USERS")),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5").strip(),
            airtable_token=_req("AIRTABLE_TOKEN"),
            airtable_base_id=_req("AIRTABLE_BASE_ID"),
            airtable_table=os.environ.get("AIRTABLE_TABLE", "Recetas").strip(),
            airtable_base_atenea=os.environ.get("AIRTABLE_BASE_ATENEA", "").strip(),
            airtable_tabla_master=os.environ.get("AIRTABLE_TABLA_MASTER", "Master").strip(),
            airtable_tabla_sumandos=os.environ.get("AIRTABLE_TABLA_SUMANDOS", "Sumandos").strip(),
            airtable_base_consulta=os.environ.get("AIRTABLE_BASE_CONSULTA", "").strip(),
            airtable_tabla_notas=os.environ.get("AIRTABLE_TABLA_NOTAS", "Notas").strip(),
            airtable_tabla_pacientes=os.environ.get("AIRTABLE_TABLA_PACIENTES", "Pacientes").strip(),
            transcribe_base_url=os.environ.get(
                "TRANSCRIBE_BASE_URL", "https://api.openai.com/v1"
            ).strip().rstrip("/"),
            transcribe_api_key=os.environ.get("TRANSCRIBE_API_KEY", "").strip(),
            transcribe_model=os.environ.get("TRANSCRIBE_MODEL", "whisper-1").strip(),
            work_dir=Path(os.environ.get("WORK_DIR", "./work")).expanduser(),
            cookies_file=Path(cookies).expanduser() if cookies else None,
            max_frames=_int("MAX_FRAMES", 16),
            frame_width=_int("FRAME_WIDTH", 640),
        )

    @property
    def can_transcribe(self) -> bool:
        return bool(self.transcribe_api_key)

    @property
    def can_atenea(self) -> bool:
        return bool(self.airtable_base_atenea)

    @property
    def can_consulta(self) -> bool:
        return bool(self.airtable_base_consulta)
