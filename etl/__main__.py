"""
ETL Excel -> OMOP CDM v5.4 (SQLite).

Uso:
    python -m etl                         # usa data/raw/pacientes_sinteticos.xlsx
    python -m etl --excel otro.xlsx --salida output/omop.sqlite
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import time
from pathlib import Path

import pandas as pd

from . import reglas as R
from . import transformar as X
from .vocabulario import Vocabulario

RAIZ = Path(__file__).resolve().parents[1]
DDL = Path(__file__).with_name("ddl_omop_cdm_54.sql")


def leer_excel(ruta: Path) -> dict[str, pd.DataFrame]:
    # dtype=object: queremos ver el dato tal cual viene (texto, número o fecha)
    hojas = pd.read_excel(ruta, sheet_name=None, dtype=object)
    return {k: v.astype(object).where(v.notna(), None) for k, v in hojas.items()}


def evaluar(incidencias: pd.DataFrame, ruta_errores: Path) -> pd.DataFrame | None:
    """Compara lo que ha detectado la ETL con los errores que se inyectaron a propósito."""
    if not ruta_errores.exists():
        return None
    esperados = pd.read_csv(ruta_errores, dtype=str, keep_default_na=False)
    por_registro = incidencias.groupby(["tabla_origen", "id_origen"])["nivel"].apply(set).to_dict()
    filas = []
    for e in esperados.itertuples(index=False):
        niveles = por_registro.get((e.hoja, e.id_registro), set())
        filas.append(dict(e._asdict(), detectado=int(bool(niveles)),
                          nivel_obtenido=",".join(sorted(niveles)), acierto=int(e.esperado in niveles)))
    return pd.DataFrame(filas)


def ejecutar(excel: Path, salida: Path, dir_vocab: Path, dir_athena: Path | None, verbose=True):
    t0 = time.time()
    log = print if verbose else (lambda *a, **k: None)
    vocab = Vocabulario(dir_vocab, dir_athena)
    log(f"Vocabulario: {vocab.origen}")
    hojas = leer_excel(excel)
    ctx = X.Contexto(vocab=vocab)

    person, location = X.personas(hojas["pacientes"], ctx)
    visit = X.visitas(hojas["visitas"], ctx)
    condition = X.diagnosticos(hojas["diagnosticos"], ctx)
    drug = X.medicamentos(hojas["medicamentos"], ctx)
    measurement = X.laboratorio(hojas["laboratorio"], ctx)
    obs = X.periodos_observacion(person, [
        (visit, "visit_start_date", "visit_end_date"),
        (condition, "condition_start_date", "condition_start_date"),
        (drug, "drug_exposure_start_date", "drug_exposure_end_date"),
        (measurement, "measurement_date", "measurement_date")], ctx)

    incidencias = ctx.inc.df()
    evaluacion = evaluar(incidencias, excel.with_name("errores_inyectados.csv"))
    cdm_source = pd.DataFrame([dict(
        cdm_source_name="Pacientes sinteticos (Excel)", cdm_source_abbreviation="SINT",
        cdm_holder="Proyecto de practica", source_description="Datos 100% inventados para practicar ETL",
        cdm_etl_reference="etl/", source_release_date=R.FECHA_CORTE.isoformat(),
        cdm_release_date=dt.date.today().isoformat(), cdm_version="5.4", cdm_version_concept_id=756265,
        vocabulary_version=vocab.origen)])

    salida.parent.mkdir(parents=True, exist_ok=True)
    if salida.exists():
        salida.unlink()
    con = sqlite3.connect(salida)
    con.executescript(DDL.read_text(encoding="utf-8"))
    tablas = dict(location=location, person=person, observation_period=obs, visit_occurrence=visit,
                  condition_occurrence=condition, drug_exposure=drug, measurement=measurement,
                  cdm_source=cdm_source, concept=vocab.concept, source_to_concept_map=vocab.stcm,
                  etl_incidencias=incidencias)
    if evaluacion is not None:
        tablas["etl_evaluacion"] = evaluacion
    for nombre, df in tablas.items():
        if len(df):
            df.to_sql(nombre, con, if_exists="append", index=False)
    con.commit()
    con.close()

    log("\nFilas cargadas en OMOP:")
    for nombre in ("person", "observation_period", "visit_occurrence", "condition_occurrence",
                   "drug_exposure", "measurement", "location"):
        log(f"  {nombre:<22}{len(tablas[nombre]):>7}")
    log("\nIncidencias:")
    for nivel, n in incidencias.nivel.value_counts().items():
        log(f"  {nivel:<22}{n:>7}")
    if evaluacion is not None:
        log(f"\nErrores inyectados detectados: {evaluacion.detectado.sum()}/{len(evaluacion)}"
            f"  |  tratados como se esperaba: {evaluacion.acierto.sum()}/{len(evaluacion)}")
    log(f"\n-> {salida}  ({time.time() - t0:.1f} s)")
    return tablas


def main():
    ap = argparse.ArgumentParser(description="ETL Excel -> OMOP CDM v5.4")
    ap.add_argument("--excel", type=Path, default=RAIZ / "data" / "raw" / "pacientes_sinteticos.xlsx")
    ap.add_argument("--salida", type=Path, default=RAIZ / "output" / "omop_cdm.sqlite")
    ap.add_argument("--vocab", type=Path, default=RAIZ / "vocab")
    ap.add_argument("--athena", type=Path, default=RAIZ / "vocab" / "athena",
                    help="carpeta con CONCEPT.csv y CONCEPT_RELATIONSHIP.csv de Athena (opcional)")
    a = ap.parse_args()
    ejecutar(a.excel, a.salida, a.vocab, a.athena)


if __name__ == "__main__":
    main()
