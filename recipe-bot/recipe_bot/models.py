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
