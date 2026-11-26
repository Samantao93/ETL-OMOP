"""
Resolución de códigos de origen -> conceptos estándar OMOP.

Dos fuentes, en este orden de prioridad:

1. Vocabularios oficiales de OHDSI descargados de Athena (https://athena.ohdsi.org)
   y descomprimidos en vocab/athena/ (CONCEPT.csv, CONCEPT_RELATIONSHIP.csv).
   Se usan las relaciones 'Maps to' (y 'ATC - RxNorm pr lat' para ATC), que es
   el mecanismo estándar de OHDSI.
2. vocab/source_to_concept_map.csv: la tabla SOURCE_TO_CONCEPT_MAP del CDM, que
   es donde OHDSI recomienda guardar los mapeos locales (p. ej. hechos con Usagi).
   Trae un mapeo mínimo para que el proyecto funcione sin descargar Athena, y
   los códigos locales (sexo, tipo de visita, unidades) que Athena no conoce.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

VOCABS_ATHENA = ("ICD10CM", "ATC", "LOINC")


@dataclass(frozen=True)
class Mapeo:
    target_concept_id: int
    source_concept_id: int
    domain_id: str | None

    @property
    def mapeado(self) -> bool:
        return self.target_concept_id != 0


SIN_MAPEO = Mapeo(0, 0, None)


def clave_nombre(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.upper().split())


class Vocabulario:
    def __init__(self, dir_vocab: Path, dir_athena: Path | None = None):
        self.concept = pd.read_csv(dir_vocab / "concept.csv")
        self.stcm = pd.read_csv(dir_vocab / "source_to_concept_map.csv", dtype={"source_code": str},
                                keep_default_na=False, na_values=[""])
        self._mapa: dict[tuple[str, str], Mapeo] = {}
        self._por_nombre: dict[tuple[str, str], str] = {}
        self.origen = "seed (source_to_concept_map.csv)"

        dominio = dict(zip(self.concept.concept_id, self.concept.domain_id))
        for r in self.stcm.itertuples(index=False):
            if isinstance(r.invalid_reason, str) and r.invalid_reason:
                continue
            self._mapa[(r.source_vocabulary_id, r.source_code)] = Mapeo(
                int(r.target_concept_id), int(r.source_concept_id), dominio.get(int(r.target_concept_id)))
            self._por_nombre[(r.source_vocabulary_id, clave_nombre(r.source_code_description))] = r.source_code

        if dir_athena and (dir_athena / "CONCEPT.csv").exists():
            self._cargar_athena(dir_athena)

        self._nombres = dict(zip(self.concept.concept_id, self.concept.concept_name))

    # ------------------------------------------------------------------ Athena
    def _cargar_athena(self, d: Path):
        cols = ["concept_id", "concept_name", "domain_id", "vocabulary_id", "concept_class_id",
                "standard_concept", "concept_code", "invalid_reason"]
        trozos = []
        for t in pd.read_csv(d / "CONCEPT.csv", sep="\t", usecols=cols, dtype=str, chunksize=500_000,
                             quoting=3, keep_default_na=False):
            trozos.append(t)
        concept = pd.concat(trozos)
        concept["concept_id"] = concept["concept_id"].astype(int)
        origen = concept[concept.vocabulary_id.isin(VOCABS_ATHENA)]
        ids_origen = set(origen.concept_id)

        rel = []
        for t in pd.read_csv(d / "CONCEPT_RELATIONSHIP.csv", sep="\t", dtype=str, chunksize=1_000_000,
                             usecols=["concept_id_1", "concept_id_2", "relationship_id", "invalid_reason"],
                             keep_default_na=False):
            t = t[t.relationship_id.isin(["Maps to", "ATC - RxNorm pr lat"]) & (t.invalid_reason == "")]
            t = t.astype({"concept_id_1": int, "concept_id_2": int})
            rel.append(t[t.concept_id_1.isin(ids_origen)])
        rel = pd.concat(rel)

        estandar = concept[concept.standard_concept == "S"].set_index("concept_id")
        info_origen = origen.set_index("concept_id")
        # 'Maps to' gana sobre la relación lateral ATC; nos quedamos con un destino por código
        rel["prioridad"] = (rel.relationship_id != "Maps to").astype(int)
        rel = rel[rel.concept_id_2.isin(estandar.index)].sort_values(["concept_id_1", "prioridad"])
        rel = rel.drop_duplicates("concept_id_1")
        for r in rel.itertuples(index=False):
            o = info_origen.loc[r.concept_id_1]
            self._mapa[(o.vocabulary_id, o.concept_code)] = Mapeo(
                int(r.concept_id_2), int(r.concept_id_1), estandar.loc[r.concept_id_2, "domain_id"])
        # Códigos de origen sin 'Maps to': al menos guardamos su source_concept_id
        for cid, o in info_origen.iterrows():
            self._mapa.setdefault((o.vocabulary_id, o.concept_code), Mapeo(0, int(cid), None))

        usados = set(rel.concept_id_2) | set(self.concept.concept_id) | set(rel.concept_id_1)
        extra = concept[concept.concept_id.isin(usados)][self.concept.columns]
        self.concept = pd.concat([self.concept, extra]).drop_duplicates("concept_id")
        self.origen = "Athena (CONCEPT / CONCEPT_RELATIONSHIP) + source_to_concept_map.csv"

    # ------------------------------------------------------------------- API
    def mapear(self, vocabulario: str, codigo: str | None) -> Mapeo:
        if not codigo:
            return SIN_MAPEO
        return self._mapa.get((vocabulario, codigo), SIN_MAPEO)

    def codigo_por_nombre(self, vocabulario: str, nombre: str | None) -> str | None:
        if not nombre:
            return None
        return self._por_nombre.get((vocabulario, clave_nombre(nombre)))

    def nombre(self, concept_id: int) -> str:
        return self._nombres.get(concept_id, "Sin mapear" if concept_id == 0 else f"concept {concept_id}")
