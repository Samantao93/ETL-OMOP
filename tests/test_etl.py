import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from etl import limpieza as L
from etl.__main__ import ejecutar

RAIZ = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------ limpieza
@pytest.mark.parametrize("entrada,esperado", [
    (dt.datetime(1980, 5, 1), (dt.date(1980, 5, 1), None)),
    ("01/05/1980", (dt.date(1980, 5, 1), "texto")),
    ("1980-05-01", (dt.date(1980, 5, 1), "texto")),
    ("31/02/1975", (None, "invalida")),
    (None, (None, "vacia")),
])
def test_parse_fecha(entrada, esperado):
    assert L.parse_fecha(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [
    ("H", ("H", None)), ("M", ("M", None)), ("Mujer", ("M", "normalizado")),
    (" H", ("H", "normalizado")), ("Varón", ("H", "normalizado")), ("X", (None, "desconocido")),
])
def test_sexo(entrada, esperado):
    assert L.normalizar_sexo(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [
    ("E11.9", ("E11.9", None)), ("E119", ("E11.9", "formato")),
    (" e11.9 ", ("E11.9", "formato")), ("I10", ("I10", None)), (None, (None, "vacio")),
])
def test_cie10(entrada, esperado):
    assert L.normalizar_cie10(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [
    (8001, ("08001", "cero_inicial")), ("28013", ("28013", None)), ("ABCDE", (None, "invalido")),
])
def test_cp(entrada, esperado):
    assert L.normalizar_cp(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [
    (6.5, (6.5, "=", None)), ("6,5", (6.5, "=", "coma")), ("<5", (5.0, "<", "operador")),
    ("pendiente", (None, None, "no_numerico")),
])
def test_valor(entrada, esperado):
    assert L.parse_valor(entrada) == esperado


# ----------------------------------------------------- ETL completa
@pytest.fixture(scope="module")
def cdm(tmp_path_factory):
    excel = RAIZ / "data" / "raw" / "pacientes_sinteticos.xlsx"
    if not excel.exists():
        pytest.skip("Genera antes los datos: python scripts/generar_datos.py")
    salida = tmp_path_factory.mktemp("cdm") / "omop.sqlite"
    return ejecutar(excel, salida, RAIZ / "vocab", None, verbose=False)


def test_todos_los_errores_inyectados_se_tratan_bien(cdm):
    ev = cdm["etl_evaluacion"]
    assert ev.detectado.all()
    assert ev.acierto.all(), ev[ev.acierto == 0]


def test_sin_falsos_positivos(cdm):
    """Lo único que aparece fuera de la lista de errores inyectados son rechazos en cascada."""
    inc, ev = cdm["etl_incidencias"], cdm["etl_evaluacion"]
    inyectados = set(zip(ev.hoja, ev.id_registro))
    extra = inc[[(t, i) not in inyectados for t, i in zip(inc.tabla_origen, inc.id_origen)]]
    assert set(extra.tipo) <= {"cascada_paciente_rechazado"}


def test_integridad_referencial(cdm):
    personas = set(cdm["person"].person_id)
    visitas = set(cdm["visit_occurrence"].visit_occurrence_id)
    for t in ("visit_occurrence", "condition_occurrence", "drug_exposure", "measurement", "observation_period"):
        assert set(cdm[t].person_id) <= personas, t
    for t in ("condition_occurrence", "drug_exposure", "measurement"):
        assert set(cdm[t].visit_occurrence_id.dropna().astype(int)) <= visitas, t


def test_conceptos_existen_o_son_cero(cdm):
    conocidos = set(cdm["concept"].concept_id) | {0}
    for t, c in (("person", "gender_concept_id"), ("visit_occurrence", "visit_concept_id"),
                 ("condition_occurrence", "condition_concept_id"), ("drug_exposure", "drug_concept_id"),
                 ("measurement", "measurement_concept_id"), ("measurement", "unit_concept_id")):
        assert set(cdm[t][c]) <= conocidos, (t, c)


def test_eventos_dentro_del_periodo_de_observacion(cdm):
    op = cdm["observation_period"].set_index("person_id")
    for t, ini, fin in (("visit_occurrence", "visit_start_date", "visit_end_date"),
                        ("drug_exposure", "drug_exposure_start_date", "drug_exposure_end_date"),
                        ("measurement", "measurement_date", "measurement_date")):
        df = cdm[t].join(op, on="person_id")
        assert (df[ini] >= df.observation_period_start_date).all(), t
        assert (df[fin] <= df.observation_period_end_date).all(), t
        assert (df[fin] >= df[ini]).all(), t


def test_no_hay_nombres_en_omop(cdm):
    columnas = set(pd.concat([cdm[t] for t in ("person", "location")], axis=1).columns)
    assert not {"nombre", "apellido1", "apellido2"} & columnas
