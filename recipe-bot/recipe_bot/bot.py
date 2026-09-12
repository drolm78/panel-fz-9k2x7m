"""Bot de Telegram: long polling contra la API HTTP, sin framework.

Para un bot de un solo proposito y un solo usuario, el polling crudo son ~150
lineas y no arrastra una dependencia asincrona que actualizar. Se procesa un
video a la vez a proposito: es mas simple y mas facil de depurar que una cola.
"""
from __future__ import annotations

import html
import logging
import tempfile
import time
from pathlib import Path

import requests

from .config import Config
from .models import Receta
from .pipeline.run import Procesador, Resultado, ResultadoMovimiento, ResultadoReceta
from .resolvers import ResolverError, extraer_url

log = logging.getLogger(__name__)

LIMITE_TELEGRAM = 4096
LIMITE_ARCHIVO_MB = 20  # tope de getFile para bots

AYUDA = (
    "Hago dos cosas:\n\n"
    "RECETAS DE COCINA\n"
    "Mándame la liga de un video de YouTube, TikTok, Instagram o Facebook y te "
    "regreso la receta ya guardada en Airtable. Si el link no jala (Instagram y "
    "Facebook a veces bloquean), comparte el archivo de video directo: funciona igual.\n\n"
    "GASTOS (a Atenea / Master)\n"
    "Dicta o escribe un movimiento y lo registro:\n"
    "  \"350 de gasolina en la Gasolinera, Inbursa, ayer\"\n"
    "  \"1200 en Office Depot del tóner, Amex Platinum\"\n"
    "Elijo lugar, categoría y cuenta de tus catálogos de Atenea; lo que no "
    "reconozca lo dejo vacío y te aviso.\n"
    "RECETAS MÉDICAS (a Notas de 2026 Extraespecial)\n"
    "Dicta el paciente y el medicamento:\n"
    "  \"Recétale Tradea LP 20 a Juan Pérez, una tableta en la mañana por 30 días\"\n"
    "  \"...y otra dentro de un mes\"  → llena Date2\n"
    "Si el nombre no es claro te muestro los parecidos y NO escribo nada.\n\n"
    "Las notas de voz sirven igual que el texto.\n\n"
    "Comandos: /start, /help"
)


class Telegram:
    def __init__(self, token: str) -> None:
        self.base = f"https://api.telegram.org/bot{token}"
        self.file_base = f"https://api.telegram.org/file/bot{token}"
        self.sesion = requests.Session()

    def _call(self, metodo: str, **params):
        r = self.sesion.post(f"{self.base}/{metodo}", json=params, timeout=60)
        r.raise_for_status()
        return r.json().get("result")

    def get_updates(self, offset: int | None, timeout: int = 30):
        r = self.sesion.get(
            f"{self.base}/getUpdates",
            params={"offset": offset, "timeout": timeout},
            timeout=timeout + 15,
        )
        r.raise_for_status()
        return r.json().get("result", [])

    def enviar(self, chat_id: int, texto: str, html_mode: bool = False) -> None:
        if len(texto) > LIMITE_TELEGRAM:
            texto = texto[: LIMITE_TELEGRAM - 40] + "\n\n… (completo en Airtable)"
        params = {"chat_id": chat_id, "text": texto, "disable_web_page_preview": True}
        if html_mode:
            params["parse_mode"] = "HTML"
        self._call("sendMessage", **params)

    def descargar(self, file_id: str, destino: Path) -> Path:
        info = self._call("getFile", file_id=file_id)
        ruta_remota = info["file_path"]
        destino = destino / Path(ruta_remota).name
        with self.sesion.get(f"{self.file_base}/{ruta_remota}", stream=True, timeout=300) as r:
            r.raise_for_status()
            with destino.open("wb") as fh:
                for trozo in r.iter_content(chunk_size=1 << 16):
                    fh.write(trozo)
        return destino


def _e(texto: str) -> str:
    return html.escape(texto or "")


def formatear(resultado: Resultado) -> str:
    r: Receta = resultado.receta
    lineas = [f"<b>{_e(r.titulo)}</b>"]

    meta = []
    if r.porciones:
        meta.append(f"{r.porciones} porciones")
    if r.tiempo_min:
        meta.append(f"{r.tiempo_min} min")
    meta.append("🥑 keto" if r.es_keto else "no keto")
    lineas.append(_e(" · ".join(meta)))

    macros = []
    if r.kcal_porcion:
        macros.append(f"{r.kcal_porcion} kcal")
    if r.proteina_g is not None:
        macros.append(f"P {r.proteina_g:g} g")
    if r.carbos_netos_g is not None:
        macros.append(f"C netos {r.carbos_netos_g:g} g")
    if r.grasa_g is not None:
        macros.append(f"G {r.grasa_g:g} g")
    if macros:
        lineas.append(f"<i>por porción: {_e(' · '.join(macros))}</i>")

    lineas.append("\n<b>Ingredientes</b>")
    for ing in r.ingredientes:
        partes = [p for p in (ing.cantidad, ing.nombre) if p]
        texto = " ".join(partes) if partes else ing.nombre
        if ing.nota:
            texto += f" ({ing.nota})"
        lineas.append(f"• {_e(texto)}")

    lineas.append("\n<b>Preparación</b>")
    for i, paso in enumerate(r.pasos, start=1):
        lineas.append(f"{i}. {_e(paso)}")

    if not r.es_keto and r.adaptacion_keto:
        lineas.append(f"\n<b>Para keto:</b> {_e(r.adaptacion_keto)}")
    if r.falta:
        lineas.append(f"\n⚠️ Quedó incompleto: {_e('; '.join(r.falta))}")

    lineas.append(f'\n<a href="{_e(resultado.airtable_url)}">Ver en Airtable</a>')
    return "\n".join(lineas)


def formatear_receta(resultado: ResultadoReceta) -> str:
    r = resultado.resuelta
    if r is None:
        return _e(resultado.lectura.respuesta or "No entendí eso como una receta.")

    if r.ambigua:
        # Escribir en el expediente equivocado es el peor error de este flujo, y
        # ademas es silencioso. Ante la duda se pregunta y no se escribe nada.
        lineas = [f"No estoy seguro de a quién te refieres con "
                  f"<b>{_e(resultado.lectura.paciente)}</b>. No guardé nada."]
        if r.candidatos:
            lineas.append("\n¿Es alguno de estos?")
            for c in r.candidatos:
                lineas.append(f"• {_e(c.paciente.nombre)}  <i>({c.puntaje:.0%})</i>")
            lineas.append("\nDíctamelo otra vez con el nombre completo.")
        else:
            lineas.append("No encontré ningún paciente parecido.")
        return "\n".join(lineas)

    lineas = [f"<b>{_e(r.paciente.nombre)}</b>", _e(f"Nota del {r.fecha.isoformat()}")]
    lineas.append(f"\n<b>{_e(r.medicamento or 'sin medicamento')}</b>")
    if r.lectura.indicacion:
        lineas.append(_e(r.lectura.indicacion))
    if r.presentacion:
        lineas.append(f"<i>{_e(r.presentacion)}</i>")
    if r.date2:
        lineas.append(f"\n📅 Siguiente receta: <b>{r.date2.isoformat()}</b>")
    if r.sin_resolver:
        lineas.append(f"\n⚠️ No están en tu catálogo: {_e('; '.join(r.sin_resolver))}")
    if resultado.airtable_url:
        lineas.append(f'\n<a href="{_e(resultado.airtable_url)}">Ver la nota</a>')
    return "\n".join(lineas)


def _voz_del_mensaje(mensaje: dict) -> dict | None:
    """Nota de voz (o un audio mandado como archivo)."""
    if "voice" in mensaje:
        return mensaje["voice"]
    audio = mensaje.get("audio")
    if audio:
        return audio
    doc = mensaje.get("document")
    if doc and str(doc.get("mime_type", "")).startswith("audio/"):
        return doc
    return None


def formatear_movimiento(resultado: ResultadoMovimiento) -> str:
    m = resultado.lectura.movimiento
    if m is None or resultado.resuelto is None:
        return _e(resultado.lectura.respuesta or "No entendí eso como un movimiento.")

    r = resultado.resuelto
    lineas = [f"<b>${m.monto:,.2f}</b> · {_e(r.lugar or 'sin lugar')}"]
    partes = [r.categoria or "sin categoría",
              m.forma_pago if r.forma_pago_id else "sin cuenta",
              m.fecha]
    lineas.append(_e(" · ".join(partes)))
    if m.detalles:
        lineas.append(_e(m.detalles))

    # Lo que no empató con el catálogo se avisa: el registro queda con huecos
    # a propósito, y hay que poder verlos sin abrir Airtable.
    if r.sin_resolver:
        lineas.append(f"⚠️ No están en tu catálogo: {_e('; '.join(r.sin_resolver))}")
    elif m.falta:
        lineas.append(f"⚠️ Lo supuse yo: {_e('; '.join(m.falta))}")

    if resultado.airtable_url:
        lineas.append(f'<a href="{_e(resultado.airtable_url)}">Ver en Master</a>')
    return "\n".join(lineas)


def _archivo_del_mensaje(mensaje: dict) -> dict | None:
    """Telegram manda el video en distintos campos segun como se comparta."""
    for clave in ("video", "video_note", "animation"):
        if clave in mensaje:
            return mensaje[clave]
    doc = mensaje.get("document")
    if doc and str(doc.get("mime_type", "")).startswith("video/"):
        return doc
    return None


class Bot:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.tg = Telegram(cfg.telegram_token)
        self.procesador = Procesador(cfg)

    def correr(self) -> None:
        log.info("bot arriba; usuarios permitidos: %s", sorted(self.cfg.allowed_users))
        offset: int | None = None
        while True:
            try:
                for update in self.tg.get_updates(offset):
                    offset = update["update_id"] + 1
                    self._manejar(update)
            except requests.RequestException as exc:
                log.warning("error de red con Telegram: %s", exc)
                time.sleep(5)
            except Exception:
                log.exception("error inesperado en el ciclo principal")
                time.sleep(5)

    def _manejar(self, update: dict) -> None:
        mensaje = update.get("message") or update.get("channel_post")
        if not mensaje:
            return
        chat_id = mensaje["chat"]["id"]
        user_id = (mensaje.get("from") or {}).get("id")

        if user_id not in self.cfg.allowed_users:
            log.warning("mensaje rechazado de user_id=%s", user_id)
            return

        texto = (mensaje.get("text") or "").strip()
        if texto.startswith("/start") or texto.startswith("/help"):
            self.tg.enviar(chat_id, AYUDA)
            return

        voz = _voz_del_mensaje(mensaje)
        archivo = _archivo_del_mensaje(mensaje)
        try:
            if voz:
                self._procesar_voz(chat_id, voz)
            elif archivo:
                self._procesar_archivo(chat_id, mensaje, archivo)
            elif texto:
                self._procesar_texto(chat_id, texto)
            else:
                self.tg.enviar(chat_id, AYUDA)
        except ResolverError as exc:
            self.tg.enviar(chat_id, str(exc))
        except Exception as exc:
            log.exception("fallo procesando el update")
            self.tg.enviar(chat_id, f"Se atoró: {exc}")

    def _procesar_voz(self, chat_id: int, voz: dict) -> None:
        tam_mb = (voz.get("file_size") or 0) / 1_048_576
        if tam_mb > LIMITE_ARCHIVO_MB:
            self.tg.enviar(chat_id, f"Ese audio pesa {tam_mb:.0f} MB y solo puedo bajar "
                                    f"{LIMITE_ARCHIVO_MB} MB.")
            return
        with tempfile.TemporaryDirectory(dir=self.cfg.work_dir) as tmp:
            ruta = self.tg.descargar(voz["file_id"], Path(tmp))
            texto = self.procesador.transcribir_archivo(ruta)

        if not texto.strip():
            self.tg.enviar(chat_id, "No se escuchó nada en esa nota de voz.")
            return
        # Enseñar la transcripción no es adorno: con dictado tienes que poder ver
        # qué entendió antes de confiar en el registro que generó.
        self.tg.enviar(chat_id, f"🎙 «{texto.strip()}»")
        self._procesar_texto(chat_id, texto)

    def _procesar_texto(self, chat_id: int, texto: str) -> None:
        url = extraer_url(texto)
        if url:
            self.tg.enviar(chat_id, "Viendo el video… esto toma entre 20 y 60 segundos.")
            self._responder(chat_id, self.procesador.desde_url(url))
            return
        intencion = self.procesador.clasificar(texto)
        if intencion == "receta":
            self._procesar_receta(chat_id, texto)
        elif intencion == "gasto":
            self._procesar_movimiento(chat_id, texto)
        else:
            self.tg.enviar(chat_id, AYUDA)

    def _procesar_receta(self, chat_id: int, texto: str) -> None:
        if not self.cfg.can_consulta:
            self.tg.enviar(chat_id, "Para las recetas me falta AIRTABLE_BASE_CONSULTA en el .env.")
            return
        self.tg.enviar(chat_id, "Buscando el expediente…")
        self.tg.enviar(chat_id, formatear_receta(self.procesador.receta_desde_texto(texto)),
                       html_mode=True)

    def _procesar_movimiento(self, chat_id: int, texto: str) -> None:
        if not self.cfg.can_atenea:
            self.tg.enviar(chat_id, "Para registrar gastos me falta AIRTABLE_BASE_ATENEA en el .env.")
            return
        resultado = self.procesador.movimiento_desde_texto(texto)
        if resultado.lectura.es_movimiento:
            self.tg.enviar(chat_id, formatear_movimiento(resultado), html_mode=True)
        else:
            self.tg.enviar(chat_id, formatear_movimiento(resultado) + "\n\n" + AYUDA)

    def _procesar_archivo(self, chat_id: int, mensaje: dict, archivo: dict) -> None:
        tam_mb = (archivo.get("file_size") or 0) / 1_048_576
        if tam_mb > LIMITE_ARCHIVO_MB:
            self.tg.enviar(
                chat_id,
                f"Ese video pesa {tam_mb:.0f} MB y Telegram solo me deja bajar "
                f"{LIMITE_ARCHIVO_MB} MB. Mándame mejor la liga.",
            )
            return

        self.tg.enviar(chat_id, "Viendo el video… esto toma entre 20 y 60 segundos.")
        with tempfile.TemporaryDirectory(dir=self.cfg.work_dir) as tmp:
            ruta = self.tg.descargar(archivo["file_id"], Path(tmp))
            caption = mensaje.get("caption") or ""
            self._responder(chat_id, self.procesador.desde_archivo(ruta, caption))

    def _responder(self, chat_id: int, resultado: Resultado) -> None:
        self.tg.enviar(chat_id, formatear(resultado), html_mode=True)
