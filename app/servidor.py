"""
Visor web local de la base OMOP generada por la ETL.

    python -m app.servidor            -> http://127.0.0.1:5000
    python -m app.servidor --red      -> accesible desde otros equipos de tu red (0.0.0.0)
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from flask import Flask, abort, g, jsonify, render_template, request

RAIZ = Path(__file__).resolve().parents[1]
BD = RAIZ / "output" / "omop_cdm.sqlite"

app = Flask(__name__)

DOMINIOS = [  # (tabla, columna concept_id, columna source_value, etiqueta)
    ("person", "gender_concept_id", "gender_source_value", "Sexo"),
    ("visit_occurrence", "visit_concept_id", "visit_source_value", "Visitas"),
    ("condition_occurrence", "condition_concept_id", "condition_source_value", "Diagnósticos"),
    ("drug_exposure", "drug_concept_id", "drug_source_value", "Medicamentos"),
    ("measurement", "measurement_concept_id", "measurement_source_value", "Laboratorio"),
    ("measurement", "unit_concept_id", "unit_source_value", "Unidades"),
]


def bd():
    if "bd" not in g:
        if not BD.exists():
            abort(503, "No existe output/omop_cdm.sqlite. Ejecuta antes: python -m etl")
        g.bd = sqlite3.connect(f"file:{BD}?mode=ro", uri=True)
        g.bd.row_factory = sqlite3.Row
    return g.bd


@app.teardown_appcontext
def cerrar(_):
    con = g.pop("bd", None)
    if con:
        con.close()


def q(sql, *params):
    return bd().execute(sql, params).fetchall()


def q1(sql, *params):
    return bd().execute(sql, params).fetchone()[0]


def tabla_existe(nombre):
    return bool(q1("select count(*) from sqlite_master where type='table' and name=?", nombre))


def resumen():
    tablas = ["person", "observation_period", "visit_occurrence", "condition_occurrence",
              "drug_exposure", "measurement", "location"]
    conteos = {t: q1(f"select count(*) from {t}") for t in tablas}
    cobertura = []
    for tabla, col, _, etiqueta in DOMINIOS:
        total = q1(f"select count(*) from {tabla}")
        ok = q1(f"select count(*) from {tabla} where {col} <> 0")
        cobertura.append(dict(etiqueta=etiqueta, total=total, mapeados=ok,
                              pct=round(100 * ok / total, 1) if total else 0))
    niveles = {r["nivel"]: r["n"] for r in q("select nivel, count(*) n from etl_incidencias group by nivel")}
    evaluacion = None
    if tabla_existe("etl_evaluacion"):
        evaluacion = dict(total=q1("select count(*) from etl_evaluacion"),
                          detectados=q1("select sum(detectado) from etl_evaluacion"),
                          aciertos=q1("select sum(acierto) from etl_evaluacion"))
    return dict(conteos=conteos, cobertura=cobertura, niveles=niveles, evaluacion=evaluacion)


@app.route("/")
def inicio():
    r = resumen()
    top = {}
    for clave, tabla, col in (("Diagnósticos", "condition_occurrence", "condition_concept_id"),
                              ("Medicamentos", "drug_exposure", "drug_concept_id"),
                              ("Laboratorio", "measurement", "measurement_concept_id")):
        top[clave] = q(f"""select t.{col} id, coalesce(c.concept_name,'Sin mapear (0)') nombre, c.vocabulary_id voc,
                               count(*) n, count(distinct person_id) pacientes
                           from {tabla} t left join concept c on c.concept_id = t.{col}
                           group by t.{col} order by n desc limit 10""")
    sexo = q("""select coalesce(c.concept_name,'Desconocido (0)') nombre, count(*) n
                from person p left join concept c on c.concept_id=p.gender_concept_id group by 1 order by n desc""")
    edades = q("""select (cast(strftime('%Y', 'now') as int) - year_of_birth) / 10 * 10 grupo, count(*) n
                  from person group by grupo order by grupo""")
    fuente = q("select * from cdm_source")[0]
    return render_template("inicio.html", r=r, top=top, sexo=sexo, edades=edades, fuente=fuente)


@app.route("/incidencias")
def incidencias():
    tabla, nivel, tipo = (request.args.get(k, "") for k in ("tabla", "nivel", "tipo"))
    filtros, params = [], []
    for col, val in (("tabla_origen", tabla), ("nivel", nivel), ("tipo", tipo)):
        if val:
            filtros.append(f"{col} = ?")
            params.append(val)
    where = ("where " + " and ".join(filtros)) if filtros else ""
    agregado = q(f"select tabla_origen, nivel, tipo, count(*) n from etl_incidencias {where} "
                 f"group by 1,2,3 order by 1, case nivel when 'RECHAZO' then 0 when 'AVISO' then 1 else 2 end, n desc",
                 *params)
    filas = q(f"select * from etl_incidencias {where} limit 500", *params)
    total = q1(f"select count(*) from etl_incidencias {where}", *params)
    opciones = dict(tabla=[r[0] for r in q("select distinct tabla_origen from etl_incidencias")],
                    nivel=["RECHAZO", "AVISO", "CORREGIDO"])
    return render_template("incidencias.html", agregado=agregado, filas=filas, total=total,
                           f=dict(tabla=tabla, nivel=nivel, tipo=tipo), opciones=opciones)


@app.route("/sin-mapear")
def sin_mapear():
    """Lista de trabajo para mapear (lo que harías después en Usagi)."""
    bloques = []
    for tabla, col, src, etiqueta in DOMINIOS:
        filas = q(f"""select {src} codigo, count(*) n from {tabla} where {col} = 0
                      group by {src} order by n desc""")
        bloques.append(dict(etiqueta=etiqueta, tabla=tabla, filas=filas))
    return render_template("sin_mapear.html", bloques=bloques)


@app.route("/evaluacion")
def evaluacion():
    if not tabla_existe("etl_evaluacion"):
        abort(404)
    por_tipo = q("""select hoja, tipo_error, esperado, count(*) n, sum(detectado) det, sum(acierto) ok
                    from etl_evaluacion group by 1,2,3 order by 1,2""")
    fallos = q("select * from etl_evaluacion where acierto = 0")
    return render_template("evaluacion.html", por_tipo=por_tipo, fallos=fallos)


@app.route("/personas")
def personas():
    texto = request.args.get("q", "").strip()
    filas = q("""select p.person_id, p.person_source_value, p.year_of_birth, p.gender_source_value,
                        coalesce(c.concept_name,'—') sexo, l.zip, l.county,
                        (select count(*) from visit_occurrence v where v.person_id=p.person_id) visitas,
                        (select count(*) from condition_occurrence v where v.person_id=p.person_id) diags
                 from person p left join concept c on c.concept_id=p.gender_concept_id
                 left join location l on l.location_id=p.location_id
                 where p.person_source_value like ? order by p.person_id limit 200""", f"%{texto}%")
    return render_template("personas.html", filas=filas, texto=texto)


@app.route("/persona/<int:person_id>")
def persona(person_id):
    p = q("""select p.*, c.concept_name sexo, l.zip, l.county from person p
             left join concept c on c.concept_id=p.gender_concept_id
             left join location l on l.location_id=p.location_id where person_id=?""", person_id)
    if not p:
        abort(404)
    eventos = q("""
        select 'Visita' tipo, visit_start_date fecha, visit_end_date fin, visit_concept_id cid, visit_source_value src, null valor
          from visit_occurrence where person_id=:p
        union all select 'Diagnóstico', condition_start_date, null, condition_concept_id, condition_source_value, null
          from condition_occurrence where person_id=:p
        union all select 'Medicamento', drug_exposure_start_date, drug_exposure_end_date, drug_concept_id, drug_source_value, sig
          from drug_exposure where person_id=:p
        union all select 'Laboratorio', measurement_date, null, measurement_concept_id, measurement_source_value,
               coalesce(case operator_concept_id when 4171756 then '<' when 4172704 then '>' else '' end || value_as_number
                        || ' ' || coalesce(u.concept_name, ''), value_source_value)
          from measurement m left join concept u on u.concept_id = m.unit_concept_id where person_id=:p
        order by fecha, tipo""".replace(":p", str(person_id)))
    nombres = {r["concept_id"]: r["concept_name"] for r in q("select concept_id, concept_name from concept")}
    periodo = q("select * from observation_period where person_id=?", person_id)
    incid = q("select * from etl_incidencias where id_origen=?", p[0]["person_source_value"])
    return render_template("persona.html", p=p[0], eventos=eventos, nombres=nombres,
                           periodo=periodo[0] if periodo else None, incid=incid)


@app.route("/api/resumen")
def api_resumen():
    return jsonify(resumen())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=5000)
    ap.add_argument("--red", action="store_true", help="escuchar en 0.0.0.0 (visible en tu red local)")
    a = ap.parse_args()
    app.run(host="0.0.0.0" if a.red else "127.0.0.1", port=a.puerto, debug=False)


if __name__ == "__main__":
    main()
