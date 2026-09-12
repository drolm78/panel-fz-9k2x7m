"""Esquema de la receta. Es tambien el contrato de salida que le imponemos a Claude."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confianza = Literal["alta", "media", "baja"]


class Ingrediente(BaseModel):
    cantidad: str | None = Field(
        description="Cantidad normalizada, p.ej. '200 g', '2 tazas', '1 cda'. "
        "null si el video nunca la dice ni la muestra."
    )
    nombre: str = Field(description="Nombre del ingrediente, en singular y en español.")
    nota: str | None = Field(
        description="Aclaracion breve: 'picado fino', 'a temperatura ambiente'. null si no aplica."
    )


class Receta(BaseModel):
    titulo: str = Field(description="Nombre corto y descriptivo del platillo.")
    porciones: int | None = Field(description="Numero de porciones. null si no se puede saber.")
    tiempo_min: int | None = Field(description="Tiempo total en minutos. null si no se puede saber.")

    ingredientes: list[Ingrediente]
    pasos: list[str] = Field(description="Pasos en orden, uno por elemento, en imperativo.")
    notas: str | None = Field(description="Tips, sustituciones o advertencias. null si no hay.")

    kcal_porcion: int | None = Field(description="Kilocalorias estimadas por porcion.")
    proteina_g: float | None = Field(description="Gramos de proteina por porcion (estimado).")
    carbos_netos_g: float | None = Field(
        description="Carbohidratos netos por porcion (totales menos fibra), estimado."
    )
    grasa_g: float | None = Field(description="Gramos de grasa por porcion (estimado).")

    es_keto: bool = Field(
        description="True solo si la receta tal cual sale por debajo de ~10 g de carbos netos por porcion."
    )
    adaptacion_keto: str | None = Field(
        description="Como adaptarla a keto en una o dos frases. null si ya es keto."
    )
    tags: list[str] = Field(description="3-6 etiquetas cortas: 'desayuno', 'pollo', 'air fryer'.")

    confianza: Confianza = Field(
        description="Que tan completa quedo la receta con el material disponible."
    )
    falta: list[str] = Field(
        description="Que informacion falto o se tuvo que inferir. Lista vacia si no falto nada."
    )


def necesita_escalar(receta: Receta) -> bool:
    """¿La pasada barata (caption + subtitulos) alcanzo, o hay que bajar el video?"""
    return (
        receta.confianza != "alta"
        or len(receta.ingredientes) < 2
        or len(receta.pasos) < 2
    )


# --- Gastos ---------------------------------------------------------------
#
# Las categorías van como Literal, no como texto libre en el prompt: así el
# esquema mismo le impide al modelo inventar una categoría que no exista en
# Airtable. Si mañana agregas una opción allá, se agrega aquí y ya.

CategoriaGasto = Literal[
    "Renta consultorio",
    "Servicios (luz/agua/internet)",
    "Insumos y papelería",
    "Equipo y mobiliario",
    "Software y suscripciones",
    "Publicidad y marketing",
    "Sueldos y honorarios",
    "Impuestos y contador",
    "Cursos y educación continua",
    "Transporte y viajes",
    "Comida",
    "Otros",
]
CiudadGasto = Literal["La Paz", "CDMX", "Ambas / General"]
TipoGasto = Literal["Fijo", "Variable"]
FormaPago = Literal["Efectivo", "Transferencia", "Tarjeta débito", "Tarjeta crédito"]


class Gasto(BaseModel):
    concepto: str = Field(description="Descripción breve del gasto, 2-5 palabras.")
    monto: float = Field(description="Monto en pesos mexicanos, solo el número.")
    fecha: str = Field(description="Fecha del gasto en formato YYYY-MM-DD.")
    categoria: CategoriaGasto
    ciudad: CiudadGasto
    tipo: TipoGasto = Field(
        description="'Fijo' si es un gasto recurrente (renta, sueldos, suscripciones); "
        "'Variable' para todo lo demás."
    )
    forma_pago: FormaPago
    deducible: bool = Field(
        description="True si es un gasto del consultorio que normalmente se deduce."
    )
    notas: str | None = Field(description="Detalle que no cupo en el concepto. null si no hay.")
    confianza: Confianza
    falta: list[str] = Field(
        description="Campos que tuviste que suponer porque no se dijeron. Lista vacía si todo venía."
    )


class LecturaGasto(BaseModel):
    """Clasificación y extracción en una sola llamada, para no pagar dos."""

    es_gasto: bool = Field(
        description="True solo si el mensaje registra un gasto con un monto. "
        "Una pregunta, un saludo o una nota suelta no son gastos."
    )
    gasto: Gasto | None = Field(description="El gasto extraído. null si es_gasto es False.")
    respuesta: str | None = Field(
        description="Si es_gasto es False, una frase breve diciendo qué entendiste "
        "y qué te faltó. null si sí era un gasto."
    )
