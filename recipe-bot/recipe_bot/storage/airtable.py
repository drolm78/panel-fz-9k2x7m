"""Guardado en Airtable.

`construir_campos` es puro a proposito: es lo unico que tiene que coincidir
exactamente con el esquema que crea scripts/setup_airtable.py, asi que conviene
poder probarlo sin red.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import requests

from ..consulta import Candidato, CatalogoClinico, Paciente, sumar_meses
from ..models import LecturaReceta, Movimiento, Receta
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


# --- Movimientos (Atenea / Master) ----------------------------------------

CAMPOS_MOVIMIENTO = {
    "fecha": "Fecha",
    "forma_pago": "Forma de pago",
    "monto": "Monto",
    "lugar": "Lugar",
    "categoria": "Categoría",
    "detalles": "Detalles",
}


@dataclass
class MovimientoResuelto:
    """El movimiento ya confrontado contra el catálogo real de Airtable."""

    movimiento: Movimiento
    forma_pago_id: str | None
    lugar: str | None
    categoria: str | None

    @property
    def sin_resolver(self) -> list[str]:
        faltantes = []
        if self.movimiento.forma_pago and self.forma_pago_id is None:
            faltantes.append(f"forma de pago «{self.movimiento.forma_pago}»")
        if self.movimiento.lugar and self.lugar is None:
            faltantes.append(f"lugar «{self.movimiento.lugar}»")
        if self.movimiento.categoria and self.categoria is None:
            faltantes.append(f"categoría «{self.movimiento.categoria}»")
        return faltantes


def resolver(movimiento: Movimiento, catalogo) -> MovimientoResuelto:
    """Confronta lo que dijo el modelo contra lo que de verdad existe en Atenea.

    Un campo que no empata se deja vacío a propósito: es preferible un hueco que
    llenas tú a una categoría equivocada enterrada en tu contabilidad.
    """
    return MovimientoResuelto(
        movimiento=movimiento,
        forma_pago_id=(
            catalogo.resolver_forma_pago(movimiento.forma_pago) if movimiento.forma_pago else None
        ),
        lugar=(
            catalogo.resolver_opcion(movimiento.lugar, catalogo.lugares)
            if movimiento.lugar else None
        ),
        categoria=(
            catalogo.resolver_opcion(movimiento.categoria, catalogo.categorias)
            if movimiento.categoria else None
        ),
    )


def construir_campos_movimiento(resuelto: MovimientoResuelto) -> dict:
    m = resuelto.movimiento
    detalles = m.detalles or ""

    avisos = list(resuelto.sin_resolver)
    if avisos:
        nota = "No están en tu catálogo: " + "; ".join(avisos)
        detalles = (detalles + "\n\n" if detalles else "") + nota

    campos: dict = {
        CAMPOS_MOVIMIENTO["fecha"]: m.fecha,
        CAMPOS_MOVIMIENTO["monto"]: m.monto,
        CAMPOS_MOVIMIENTO["detalles"]: detalles,
    }
    # Los campos que no se resolvieron se omiten: Airtable rechaza un id de
    # vinculo invalido, y una opcion inexistente no se puede escribir sin typecast.
    if resuelto.forma_pago_id:
        campos[CAMPOS_MOVIMIENTO["forma_pago"]] = [resuelto.forma_pago_id]
    if resuelto.lugar:
        campos[CAMPOS_MOVIMIENTO["lugar"]] = resuelto.lugar
    if resuelto.categoria:
        campos[CAMPOS_MOVIMIENTO["categoria"]] = resuelto.categoria
    return campos


def guardar_movimiento(resuelto: MovimientoResuelto, token: str, base_id: str, tabla: str) -> str:
    r = requests.post(
        f"{API}/{base_id}/{requests.utils.quote(tabla, safe='')}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        # Sin typecast: el bot no debe crear lugares, categorias ni cuentas nuevas.
        json={"fields": construir_campos_movimiento(resuelto)},
        timeout=30,
    )
    if r.status_code != 200:
        raise AirtableError(f"Airtable respondió {r.status_code}: {r.text[:400]}")
    return f"https://airtable.com/{base_id}/{r.json().get('id','')}"


# --- Recetas médicas (2026 Extraespecial / Notas) --------------------------

CAMPOS_RECETA = {
    "paciente": "Paciente",
    "fecha": "Fecha-Principal",
    "atencion": "Atención",
    "medicamento": "Medicamento 1",
    "indicacion": "Indicacion de medicamento 1",
    "presentacion": "Presentación de medicamento 1",
    "repeticion": "Date2",
}


@dataclass
class RecetaResuelta:
    lectura: LecturaReceta
    paciente: Paciente | None
    candidatos: list[Candidato]
    medicamento: str | None
    presentacion: str | None
    fecha: date
    date2: date | None

    @property
    def ambigua(self) -> bool:
        """Sin paciente claro no se escribe nada: se pregunta."""
        return self.paciente is None

    @property
    def sin_resolver(self) -> list[str]:
        faltantes = []
        if self.lectura.medicamento and self.medicamento is None:
            faltantes.append(f"medicamento «{self.lectura.medicamento}»")
        if self.lectura.presentacion and self.presentacion is None:
            faltantes.append(f"presentación «{self.lectura.presentacion}»")
        return faltantes


def resolver_receta(
    lectura: LecturaReceta, catalogo: CatalogoClinico, hoy: date | None = None
) -> RecetaResuelta:
    from ..consulta import hay_ganador

    hoy = hoy or date.today()
    candidatos = catalogo.buscar_pacientes(lectura.paciente)

    date2: date | None = None
    if lectura.repetir_meses:
        date2 = sumar_meses(hoy, lectura.repetir_meses)
    elif lectura.repetir_dias:
        date2 = hoy + timedelta(days=lectura.repetir_dias)

    return RecetaResuelta(
        lectura=lectura,
        paciente=hay_ganador(candidatos),
        candidatos=candidatos,
        medicamento=(
            catalogo.resolver_opcion(lectura.medicamento, catalogo.medicamentos)
            if lectura.medicamento else None
        ),
        presentacion=(
            catalogo.resolver_opcion(lectura.presentacion, catalogo.presentaciones)
            if lectura.presentacion else None
        ),
        fecha=hoy,
        date2=date2,
    )


def construir_campos_receta(r: RecetaResuelta) -> dict:
    if r.paciente is None:
        raise AirtableError("No se puede escribir una receta sin paciente resuelto.")

    campos: dict = {
        CAMPOS_RECETA["paciente"]: [r.paciente.record_id],
        CAMPOS_RECETA["fecha"]: r.fecha.isoformat(),
        CAMPOS_RECETA["atencion"]: ["Receta"],
    }
    if r.medicamento:
        campos[CAMPOS_RECETA["medicamento"]] = r.medicamento
    if r.lectura.indicacion:
        campos[CAMPOS_RECETA["indicacion"]] = r.lectura.indicacion
    if r.presentacion:
        campos[CAMPOS_RECETA["presentacion"]] = r.presentacion
    if r.date2:
        campos[CAMPOS_RECETA["repeticion"]] = r.date2.isoformat()
    return campos


def guardar_receta(r: RecetaResuelta, token: str, base_id: str, tabla: str) -> str:
    resp = requests.post(
        f"{API}/{base_id}/{requests.utils.quote(tabla, safe='')}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        # Sin typecast: jamas crear un medicamento ni una presentacion nuevos.
        json={"fields": construir_campos_receta(r)},
        timeout=30,
    )
    if resp.status_code != 200:
        raise AirtableError(f"Airtable respondió {resp.status_code}: {resp.text[:400]}")
    return f"https://airtable.com/{base_id}/{resp.json().get('id','')}"
