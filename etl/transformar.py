"""
Transformación hoja de Excel -> tabla OMOP CDM v5.4.

Principios OHDSI que sigue el código:
  * Un código que no se puede mapear NO se descarta: se carga con concept_id = 0
    y el código original en *_source_value (así se puede mapear más tarde).
  * Sólo se rechaza lo que rompe el modelo: persona sin año de nacimiento, eventos
    sin fecha, eventos de personas inexistentes, fechas imposibles.
  * Los nombres y apellidos NO se cargan: OMOP no tiene sitio para identificadores
    directos de la persona.
  * Cada decisión queda registrada en etl_incidencias (CORREGIDO / AVISO / RECHAZO).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from . import limpieza as L
from . import reglas as R
from .vocabulario import Vocabulario

CORREGIDO, AVISO, RECHAZO = "CORREGIDO", "AVISO", "RECHAZO"


@dataclass
class Incidencias:
    filas: list[dict] = field(default_factory=list)

    def add(self, tabla, id_origen, nivel, tipo, detalle=""):
        self.filas.append(dict(tabla_origen=tabla, id_origen=str(id_origen), nivel=nivel,
                               tipo=tipo, detalle=str(detalle)))

    def df(self) -> pd.DataFrame:
        return pd.DataFrame(self.filas, columns=["tabla_origen", "id_origen", "nivel", "tipo", "detalle"])


@dataclass
class Contexto:
    vocab: Vocabulario
    inc: Incidencias = field(default_factory=Incidencias)
    personas: dict[str, dict] = field(default_factory=dict)        # id_paciente -> {person_id, nacimiento}
    pacientes_rechazados: set[str] = field(default_factory=set)
    visitas: dict[str, dict] = field(default_factory=dict)         # id_visita -> {id, person_id, inicio}
    visitas_rechazadas: set[str] = field(default_factory=set)


def _iso(d: dt.date | None):
    return d.isoformat() if d else None


def _persona_de(ctx: Contexto, tabla: str, rid: str, pid: str | None):
    """Devuelve la persona del evento o registra el rechazo."""
    if pid in ctx.personas:
        return ctx.personas[pid]
    if pid in ctx.pacientes_rechazados:
        ctx.inc.add(tabla, rid, RECHAZO, "cascada_paciente_rechazado", pid)
    else:
        ctx.inc.add(tabla, rid, RECHAZO, "paciente_inexistente", pid)
    return None


def _fecha_evento(ctx, tabla, rid, valor, persona, nombre="fecha"):
    """Parsea y valida una fecha de evento. None => rechazado."""
    f, bandera = L.parse_fecha(valor)
    if f is None:
        ctx.inc.add(tabla, rid, RECHAZO, f"{nombre}_{bandera}", valor)
        return None
    if bandera == "texto":
        ctx.inc.add(tabla, rid, CORREGIDO, f"{nombre}_en_texto", valor)
    if f > R.FECHA_CORTE:
        ctx.inc.add(tabla, rid, RECHAZO, "fecha_futura", f)
        return None
    if f < persona["nacimiento"]:
        ctx.inc.add(tabla, rid, RECHAZO, "evento_antes_nacimiento", f)
        return None
    return f


# --------------------------------------------------------------------- PERSON
def personas(df: pd.DataFrame, ctx: Contexto):
    T = "pacientes"
    filas_person, locations = [], {}
    firmas: dict[str, tuple] = {}
    for row in df.to_dict("records"):
        rid = L.texto(row.get("id_paciente"))
        if not rid:
            ctx.inc.add(T, "(vacío)", RECHAZO, "id_vacio")
            continue
        firma = tuple(str(row.get(c)) for c in df.columns)
        if rid in firmas:
            if firmas[rid] == firma:
                ctx.inc.add(T, rid, CORREGIDO, "duplicado_exacto", "fila repetida eliminada")
            else:
                ctx.inc.add(T, rid, RECHAZO, "duplicado_conflictivo", "se conserva la primera fila")
            continue
        firmas[rid] = firma

        nac, bandera = L.parse_fecha(row.get("fecha_nacimiento"))
        if nac is None:
            ctx.inc.add(T, rid, RECHAZO, f"fecha_nacimiento_{bandera}", row.get("fecha_nacimiento"))
            ctx.pacientes_rechazados.add(rid)
            continue
        if nac > R.FECHA_CORTE:
            ctx.inc.add(T, rid, RECHAZO, "fecha_nacimiento_futura", nac)
            ctx.pacientes_rechazados.add(rid)
            continue
        if nac.year < R.ANIO_MINIMO_NACIMIENTO:
            ctx.inc.add(T, rid, RECHAZO, "fecha_nacimiento_implausible", nac)
            ctx.pacientes_rechazados.add(rid)
            continue
        if bandera == "texto":
            ctx.inc.add(T, rid, CORREGIDO, "fecha_nacimiento_en_texto", row.get("fecha_nacimiento"))

        sexo_raw = row.get("sexo")
        sexo, b_sexo = L.normalizar_sexo(sexo_raw)
        m_sexo = ctx.vocab.mapear("LOCAL_SEXO", sexo)
        if not m_sexo.mapeado:
            ctx.inc.add(T, rid, AVISO, "sexo_desconocido", repr(sexo_raw))
        elif b_sexo:
            ctx.inc.add(T, rid, CORREGIDO, "sexo_normalizado", f"{sexo_raw!r} -> {sexo}")

        cp_raw = row.get("codigo_postal")
        cp, b_cp = L.normalizar_cp(cp_raw)
        if b_cp == "cero_inicial":
            ctx.inc.add(T, rid, CORREGIDO, "cp_sin_cero_inicial", f"{cp_raw} -> {cp}")
        elif b_cp == "invalido":
            ctx.inc.add(T, rid, AVISO, "cp_invalido", repr(cp_raw))
        provincia = L.texto(row.get("provincia"))
        location_id = None
        if cp or provincia:
            clave = (cp, provincia)
            location_id = locations.setdefault(clave, len(locations) + 1)

        person_id = len(filas_person) + 1
        ctx.personas[rid] = dict(person_id=person_id, nacimiento=nac)
        filas_person.append(dict(
            person_id=person_id, gender_concept_id=m_sexo.target_concept_id,
            year_of_birth=nac.year, month_of_birth=nac.month, day_of_birth=nac.day,
            birth_datetime=f"{nac.isoformat()} 00:00:00",
            race_concept_id=0, ethnicity_concept_id=0,          # no se registra en el origen
            location_id=location_id, person_source_value=rid,
            gender_source_value=None if L.vacio(sexo_raw) else str(sexo_raw),
            gender_source_concept_id=0))

    loc = pd.DataFrame([dict(location_id=i, zip=cp, county=(prov or "")[:20] or None,
                             location_source_value=f"{prov}|{cp}", country_source_value="ES",
                             country_concept_id=0)
                        for (cp, prov), i in locations.items()])
    return pd.DataFrame(filas_person), loc


# ----------------------------------------------------------- VISIT_OCCURRENCE
def visitas(df: pd.DataFrame, ctx: Contexto) -> pd.DataFrame:
    T = "visitas"
    filas = []
    for row in df.to_dict("records"):
        rid = L.texto(row.get("id_visita")) or "(vacío)"
        persona = _persona_de(ctx, T, rid, L.texto(row.get("id_paciente")))
        if persona is None:
            ctx.visitas_rechazadas.add(rid)
            continue
        ini = _fecha_evento(ctx, T, rid, row.get("fecha_inicio"), persona, "fecha_inicio")
        if ini is None:
            ctx.visitas_rechazadas.add(rid)
            continue
        fin, b_fin = L.parse_fecha(row.get("fecha_fin"))
        if fin is None:
            ctx.inc.add(T, rid, CORREGIDO, "fecha_fin_vacia", "fin = inicio")
            fin = ini
        elif fin < ini:
            ctx.inc.add(T, rid, CORREGIDO, "fin_anterior_a_inicio", f"{fin} -> {ini}")
            fin = ini
        elif fin > R.FECHA_CORTE:
            ctx.inc.add(T, rid, CORREGIDO, "fecha_fin_futura", f"{fin} -> {R.FECHA_CORTE}")
            fin = R.FECHA_CORTE

        tipo_raw = row.get("tipo_visita")
        tipo, b_tipo = L.normalizar_tipo_visita(tipo_raw)
        m = ctx.vocab.mapear("LOCAL_VISITA", tipo)
        if not m.mapeado:
            ctx.inc.add(T, rid, AVISO, "tipo_visita_sin_mapeo", repr(tipo_raw))
        elif b_tipo:
            ctx.inc.add(T, rid, CORREGIDO, "tipo_visita_normalizado", f"{tipo_raw!r} -> {tipo}")

        vo_id = len(filas) + 1
        ctx.visitas[rid] = dict(id=vo_id, person_id=persona["person_id"], inicio=ini)
        filas.append(dict(
            visit_occurrence_id=vo_id, person_id=persona["person_id"], visit_concept_id=m.target_concept_id,
            visit_start_date=_iso(ini), visit_end_date=_iso(fin), visit_type_concept_id=R.TIPO_EHR,
            visit_source_value=None if L.vacio(tipo_raw) else str(tipo_raw), visit_source_concept_id=0,
            admitted_from_concept_id=0, discharged_to_concept_id=0))
    return pd.DataFrame(filas)


def _visita_de(ctx, tabla, rid, vid, persona):
    """visit_occurrence_id del evento (o None con aviso)."""
    if not vid:
        return None
    v = ctx.visitas.get(vid)
    if v is None:
        tipo = "cascada_visita_rechazada" if vid in ctx.visitas_rechazadas else "visita_inexistente"
        ctx.inc.add(tabla, rid, AVISO, tipo, f"{vid}: se carga sin visit_occurrence_id")
        return None
    if v["person_id"] != persona["person_id"]:
        ctx.inc.add(tabla, rid, AVISO, "visita_de_otro_paciente", vid)
        return None
    return v


# ------------------------------------------------------- CONDITION_OCCURRENCE
def diagnosticos(df: pd.DataFrame, ctx: Contexto) -> pd.DataFrame:
    T = "diagnosticos"
    filas = []
    for row in df.to_dict("records"):
        rid = L.texto(row.get("id_diagnostico")) or "(vacío)"
        persona = _persona_de(ctx, T, rid, L.texto(row.get("id_paciente")))
        if persona is None:
            continue
        raw = row.get("codigo_cie10")
        codigo, b_cod = L.normalizar_cie10(raw)
        if codigo is None:
            ctx.inc.add(T, rid, RECHAZO, "codigo_vacio")
            continue
        visita = _visita_de(ctx, T, rid, L.texto(row.get("id_visita")), persona)
        if L.vacio(row.get("fecha_diagnostico")) and visita:
            ctx.inc.add(T, rid, CORREGIDO, "fecha_vacia", "se usa la fecha de la visita")
            fecha = visita["inicio"]
        else:
            fecha = _fecha_evento(ctx, T, rid, row.get("fecha_diagnostico"), persona)
            if fecha is None:
                continue
        m = ctx.vocab.mapear("ICD10CM", codigo)
        if not m.mapeado:
            ctx.inc.add(T, rid, AVISO, "cie10_sin_mapeo", codigo)
        elif b_cod:
            ctx.inc.add(T, rid, CORREGIDO, "cie10_formato", f"{raw!r} -> {codigo}")
        if m.mapeado and m.domain_id not in (None, "Condition"):
            # En un proyecto real se enrutaría a la tabla del dominio (OBSERVATION, PROCEDURE...)
            ctx.inc.add(T, rid, AVISO, "dominio_distinto", f"{codigo} -> {m.domain_id}")
        filas.append(dict(
            condition_occurrence_id=len(filas) + 1, person_id=persona["person_id"],
            condition_concept_id=m.target_concept_id, condition_start_date=_iso(fecha),
            condition_type_concept_id=R.TIPO_EHR, condition_status_concept_id=0,
            visit_occurrence_id=visita["id"] if visita else None,
            condition_source_value=str(raw).strip(), condition_source_concept_id=m.source_concept_id,
            condition_status_source_value=L.texto(row.get("principal"))))
    return pd.DataFrame(filas)


# -------------------------------------------------------------- DRUG_EXPOSURE
def medicamentos(df: pd.DataFrame, ctx: Contexto) -> pd.DataFrame:
    T = "medicamentos"
    filas = []
    for row in df.to_dict("records"):
        rid = L.texto(row.get("id_prescripcion")) or "(vacío)"
        persona = _persona_de(ctx, T, rid, L.texto(row.get("id_paciente")))
        if persona is None:
            continue
        ini = _fecha_evento(ctx, T, rid, row.get("fecha_inicio"), persona, "fecha_inicio")
        if ini is None:
            continue
        fin, _ = L.parse_fecha(row.get("fecha_fin"))
        verbatim_fin = fin
        if fin is None:
            ctx.inc.add(T, rid, CORREGIDO, "fecha_fin_vacia", "fin = inicio (end_date es obligatorio)")
            fin = ini
        elif fin < ini:
            ctx.inc.add(T, rid, CORREGIDO, "fin_anterior_a_inicio", f"{fin} -> {ini}")
            fin = ini

        nombre = L.texto(row.get("nombre_medicamento"))
        atc, _ = L.normalizar_codigo(row.get("codigo_atc"))
        if atc is None:
            atc = ctx.vocab.codigo_por_nombre("ATC", nombre)
            if atc:
                ctx.inc.add(T, rid, CORREGIDO, "atc_desde_nombre", f"{nombre} -> {atc}")
        m = ctx.vocab.mapear("ATC", atc)
        if not m.mapeado:
            ctx.inc.add(T, rid, AVISO, "atc_sin_mapeo", atc or nombre)

        dosis, _, b_dosis = L.parse_valor(row.get("dosis"))
        unidad = L.texto(row.get("unidad_dosis"))
        if dosis is not None and dosis <= 0:
            ctx.inc.add(T, rid, AVISO, "dosis_no_positiva", dosis)
            dosis = None
        partes = [f"{dosis:g} {unidad or ''}".strip() if dosis is not None else None,
                  L.texto(row.get("frecuencia"))]
        filas.append(dict(
            drug_exposure_id=len(filas) + 1, person_id=persona["person_id"], drug_concept_id=m.target_concept_id,
            drug_exposure_start_date=_iso(ini), drug_exposure_end_date=_iso(fin),
            verbatim_end_date=_iso(verbatim_fin), drug_type_concept_id=R.TIPO_EHR,
            days_supply=(fin - ini).days + 1, sig=" ".join(p for p in partes if p) or None,
            route_concept_id=0,
            visit_occurrence_id=(_visita_de(ctx, T, rid, L.texto(row.get("id_visita")), persona) or {}).get("id"),
            drug_source_value=atc or nombre, drug_source_concept_id=m.source_concept_id,
            dose_unit_source_value=unidad))
    return pd.DataFrame(filas)


# ---------------------------------------------------------------- MEASUREMENT
def laboratorio(df: pd.DataFrame, ctx: Contexto) -> pd.DataFrame:
    T = "laboratorio"
    filas = []
    for row in df.to_dict("records"):
        rid = L.texto(row.get("id_resultado")) or "(vacío)"
        persona = _persona_de(ctx, T, rid, L.texto(row.get("id_paciente")))
        if persona is None:
            continue
        fecha = _fecha_evento(ctx, T, rid, row.get("fecha_resultado"), persona)
        if fecha is None:
            continue
        loinc, _ = L.normalizar_codigo(row.get("codigo_loinc"))
        m = ctx.vocab.mapear("LOINC", loinc)
        if not m.mapeado:
            ctx.inc.add(T, rid, AVISO, "loinc_sin_mapeo", loinc)

        valor_raw = row.get("valor")
        valor, operador, b_val = L.parse_valor(valor_raw)
        if b_val == "coma":
            ctx.inc.add(T, rid, CORREGIDO, "decimal_con_coma", valor_raw)
        elif b_val == "operador":
            ctx.inc.add(T, rid, CORREGIDO, "valor_con_operador", valor_raw)
        elif b_val in ("no_numerico", "vacio"):
            ctx.inc.add(T, rid, AVISO, f"valor_{b_val}", valor_raw)

        unidad_raw = row.get("unidad")
        unidad = L.normalizar_unidad(unidad_raw)
        regla = R.LAB.get(loinc)
        if regla and unidad and unidad != regla["unidad"]:
            factor = regla["conversion"].get(unidad)
            if factor and valor is not None:
                ctx.inc.add(T, rid, CORREGIDO, "unidad_convertida",
                            f"{valor:g} {unidad} -> {valor * factor:.1f} {regla['unidad']}")
                valor, unidad = round(valor * factor, 2), regla["unidad"]
            else:
                ctx.inc.add(T, rid, AVISO, "unidad_inesperada", unidad)
        if unidad is None:
            ctx.inc.add(T, rid, AVISO, "unidad_vacia")
        m_unidad = ctx.vocab.mapear("LOCAL_UNIDAD", unidad)
        if regla and valor is not None and not (regla["rango"][0] <= valor <= regla["rango"][1]):
            ctx.inc.add(T, rid, AVISO, "valor_implausible", f"{valor:g} {unidad or ''}")

        filas.append(dict(
            measurement_id=len(filas) + 1, person_id=persona["person_id"],
            measurement_concept_id=m.target_concept_id, measurement_date=_iso(fecha),
            measurement_type_concept_id=R.TIPO_EHR,
            operator_concept_id=R.OPERADORES.get(operador) if valor is not None else None,
            value_as_number=valor, value_as_concept_id=None, unit_concept_id=m_unidad.target_concept_id,
            visit_occurrence_id=(_visita_de(ctx, T, rid, L.texto(row.get("id_visita")), persona) or {}).get("id"),
            measurement_source_value=loinc, measurement_source_concept_id=m.source_concept_id,
            unit_source_value=None if L.vacio(unidad_raw) else str(unidad_raw),
            value_source_value=None if L.vacio(valor_raw) else str(valor_raw)))
    return pd.DataFrame(filas)


# --------------------------------------------------------- OBSERVATION_PERIOD
def periodos_observacion(person: pd.DataFrame, eventos: list[tuple[pd.DataFrame, str, str]],
                         ctx: Contexto) -> pd.DataFrame:
    """Un periodo por persona: desde su primer evento hasta el último."""
    trozos = []
    for df, c_ini, c_fin in eventos:
        if len(df):
            trozos.append(df[["person_id", c_ini]].rename(columns={c_ini: "f"}))
            trozos.append(df[["person_id", c_fin]].rename(columns={c_fin: "f"}).dropna())
    fechas = pd.concat(trozos).groupby("person_id")["f"].agg(["min", "max"])
    sin_eventos = set(person.person_id) - set(fechas.index)
    for pid in sorted(sin_eventos):
        src = person.loc[person.person_id == pid, "person_source_value"].iloc[0]
        ctx.inc.add("pacientes", src, AVISO, "persona_sin_eventos", "sin observation_period")
    fechas = fechas.reset_index()
    return pd.DataFrame(dict(
        observation_period_id=range(1, len(fechas) + 1), person_id=fechas.person_id,
        observation_period_start_date=fechas["min"], observation_period_end_date=fechas["max"],
        period_type_concept_id=R.TIPO_EHR))
