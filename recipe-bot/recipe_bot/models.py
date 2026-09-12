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


# --- Movimientos de Atenea -------------------------------------------------
#
# Aqui NO se usan Literal como en las recetas: las opciones de Lugar, Categoria
# y Forma de pago viven en Airtable, cambian, y son ~190 / ~54 / 27. Se validan
# contra el catalogo leido en caliente (ver atenea.py), no contra el esquema.


class Movimiento(BaseModel):
    fecha: str = Field(description="Fecha del movimiento en formato YYYY-MM-DD.")
    monto: float = Field(description="Monto en pesos mexicanos, positivo, solo el número.")
    forma_pago: str = Field(
        description="Cuenta o tarjeta, copiada exactamente de la lista de formas de pago "
        "válidas. Cadena vacía si lo dictado no corresponde a ninguna."
    )
    lugar: str = Field(
        description="Copiado exactamente de la lista de lugares válidos. "
        "Cadena vacía si lo dictado no corresponde a ninguno."
    )
    categoria: str = Field(
        description="Copiada exactamente de la lista de categorías válidas. "
        "Cadena vacía si lo dictado no corresponde a ninguna."
    )
    detalles: str | None = Field(
        description="Texto libre: qué se compró, para quién. null si no hay nada que agregar."
    )
    confianza: Confianza
    falta: list[str] = Field(
        description="Campos que quedaron vacíos o que tuviste que suponer. "
        "Lista vacía si todo venía en lo dictado."
    )


class LecturaMovimiento(BaseModel):
    """Clasificación y extracción en una sola llamada, para no pagar dos."""

    es_movimiento: bool = Field(
        description="True solo si el mensaje registra un movimiento con un monto. "
        "Una pregunta, un saludo o una nota suelta no lo son."
    )
    movimiento: Movimiento | None = Field(
        description="El movimiento extraído. null si es_movimiento es False."
    )
    respuesta: str | None = Field(
        description="Si es_movimiento es False, una frase breve diciendo qué entendiste. "
        "null si sí era un movimiento."
    )
