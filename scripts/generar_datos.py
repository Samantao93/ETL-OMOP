"""
Genera un Excel con pacientes 100% IMAGINARIOS (datos sintéticos) para practicar
una ETL hacia OMOP CDM v5.4.

La mayoría de registros están "bien"; a una parte se le inyectan errores típicos
de datos reales (fechas mal formadas, duplicados, códigos sin punto, unidades
distintas, huérfanos...). Cada error inyectado se apunta en
data/raw/errores_inyectados.csv junto con lo que la ETL debería hacer con él:

    CORREGIDO -> la ETL lo puede arreglar de forma segura
    AVISO     -> se carga, pero con concept_id 0 / valor nulo y queda registrado
    RECHAZO   -> no se puede cargar en OMOP y se descarta

Uso:  python scripts/generar_datos.py [--pacientes 1000] [--semilla 42]
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SALIDA_XLSX = RAIZ / "data" / "raw" / "pacientes_sinteticos.xlsx"
SALIDA_ERRORES = RAIZ / "data" / "raw" / "errores_inyectados.csv"

HOY = dt.date(2026, 11, 26)
INICIO_VISITAS = dt.date(2018, 1, 1)
FIN_VISITAS = dt.date(2026, 10, 31)

NOMBRES_H = ["Antonio", "José", "Manuel", "Francisco", "David", "Juan", "Javier", "Daniel",
             "Carlos", "Jesús", "Alejandro", "Miguel", "Rafael", "Pablo", "Sergio", "Iker",
             "Jordi", "Hugo", "Álvaro", "Adrián", "Mario", "Marc", "Unai", "Xabier"]
NOMBRES_M = ["María", "Carmen", "Ana", "Isabel", "Laura", "Cristina", "Marta", "Lucía",
             "Elena", "Pilar", "Sara", "Paula", "Raquel", "Nuria", "Irene", "Ainhoa",
             "Montserrat", "Alba", "Noelia", "Rocío", "Lorena", "Uxue", "Iria", "Julia"]
APELLIDOS = ["García", "Rodríguez", "González", "Fernández", "López", "Martínez", "Sánchez",
             "Pérez", "Gómez", "Martín", "Jiménez", "Ruiz", "Hernández", "Díaz", "Moreno",
             "Muñoz", "Álvarez", "Romero", "Alonso", "Gutiérrez", "Navarro", "Torres",
             "Domínguez", "Vázquez", "Ramos", "Gil", "Serrano", "Blanco", "Etxeberria", "Puig"]
PROVINCIAS = [("Madrid", "28"), ("Barcelona", "08"), ("Valencia", "46"), ("Sevilla", "41"),
              ("Zaragoza", "50"), ("Málaga", "29"), ("Murcia", "30"), ("Bizkaia", "48"),
              ("A Coruña", "15"), ("Asturias", "33"), ("Álava", "01"), ("Girona", "17")]

# (CIE-10-ES, descripción, ATC de su tratamiento típico o None)
DIAGNOSTICOS = [
    ("E11.9", "Diabetes mellitus tipo 2 sin complicaciones", "A10BA02"),
    ("I10", "Hipertensión esencial", "C09AA02"),
    ("J45.909", "Asma no especificada, sin complicaciones", "R03AC02"),
    ("E78.5", "Hiperlipidemia no especificada", "C10AA05"),
    ("J44.9", "EPOC no especificada", "R03AC02"),
    ("F32.9", "Episodio depresivo mayor no especificado", "N06AB06"),
    ("I48.91", "Fibrilación auricular no especificada", "B01AA03"),
    ("I21.9", "Infarto agudo de miocardio no especificado", "C10AA05"),
    ("I50.9", "Insuficiencia cardiaca no especificada", "C03CA01"),
    ("J18.9", "Neumonía no especificada", None),
    ("N18.9", "Enfermedad renal crónica no especificada", None),
    ("E66.9", "Obesidad no especificada", None),
    ("G43.909", "Migraña no especificada", "M01AE01"),
    ("E03.9", "Hipotiroidismo no especificado", "H03AA01"),
    ("M19.90", "Artrosis no especificada", "N02BE01"),
    ("K21.9", "Enfermedad por reflujo gastroesofágico sin esofagitis", "A02BC01"),
]
CRONICOS = ["E11.9", "I10", "J45.909", "E78.5", "J44.9", "F32.9", "I48.91", "I50.9",
            "N18.9", "E66.9", "G43.909", "E03.9", "M19.90", "K21.9"]
AGUDOS = ["J18.9", "I21.9"]

# (ATC, nombre, dosis habitual, unidad)
MEDICAMENTOS = {
    "A10BA02": ("Metformina", 850, "mg"),
    "C09AA03": ("Lisinopril", 10, "mg"),
    "C09AA02": ("Enalapril", 20, "mg"),
    "C10AA05": ("Atorvastatina", 40, "mg"),
    "C08CA01": ("Amlodipino", 5, "mg"),
    "A02BC01": ("Omeprazol", 20, "mg"),
    "R03AC02": ("Salbutamol", 100, "mcg"),
    "H03AA01": ("Levotiroxina", 75, "mcg"),
    "M01AE01": ("Ibuprofeno", 600, "mg"),
    "N02BE01": ("Paracetamol", 1000, "mg"),
    "C03CA01": ("Furosemida", 40, "mg"),
    "B01AA03": ("Warfarina", 5, "mg"),
    "N06AB06": ("Sertralina", 50, "mg"),
}

# (LOINC, nombre, unidad, media, desviación, decimales)
LABORATORIO = [
    ("2345-7", "Glucosa", "mg/dL", 105, 25, 0),
    ("4548-4", "Hemoglobina A1c", "%", 6.1, 0.9, 1),
    ("2093-3", "Colesterol total", "mg/dL", 195, 35, 0),
    ("13457-7", "Colesterol LDL", "mg/dL", 115, 30, 0),
    ("2085-9", "Colesterol HDL", "mg/dL", 52, 12, 0),
    ("2160-0", "Creatinina", "mg/dL", 0.95, 0.25, 2),
    ("718-7", "Hemoglobina", "g/dL", 13.8, 1.5, 1),
    ("2951-2", "Sodio", "mmol/L", 140, 2.5, 0),
    ("2823-3", "Potasio", "mmol/L", 4.2, 0.4, 1),
    ("29463-7", "Peso", "kg", 74, 14, 1),
    ("8302-2", "Talla", "cm", 168, 9, 0),
    ("8480-6", "Tensión arterial sistólica", "mm[Hg]", 128, 15, 0),
    ("8462-4", "Tensión arterial diastólica", "mm[Hg]", 79, 9, 0),
]
TIPOS_VISITA = ["Ambulatoria", "Urgencias", "Hospitalización"]
PESOS_VISITA = [0.75, 0.17, 0.08]


def fecha_aleatoria(rng: random.Random, desde: dt.date, hasta: dt.date) -> dt.date:
    return desde + dt.timedelta(days=rng.randint(0, max((hasta - desde).days, 0)))


class Inyector:
    """Reparte errores sobre índices distintos y apunta la 'verdad' esperada."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.errores: list[dict] = []

    def elegir(self, pool: list[int], n: int) -> list[int]:
        elegidos = self.rng.sample(pool, min(n, len(pool)))
        for i in elegidos:
            pool.remove(i)
        return elegidos

    def apuntar(self, hoja, id_registro, tipo, esperado, detalle=""):
        self.errores.append(dict(hoja=hoja, id_registro=id_registro, tipo_error=tipo,
                                 esperado=esperado, detalle=detalle))


def generar(n_pacientes: int, semilla: int):
    rng = random.Random(semilla)
    inj = Inyector(rng)

    # ------------------------------------------------------------- pacientes
    pacientes = []
    for n in range(1, n_pacientes + 1):
        sexo = rng.choice("HM")
        provincia, prefijo = rng.choice(PROVINCIAS)
        nacimiento = fecha_aleatoria(rng, dt.date(1930, 1, 1), dt.date(2022, 12, 31))
        pacientes.append(dict(
            id_paciente=f"P{n:05d}",
            nombre=rng.choice(NOMBRES_H if sexo == "H" else NOMBRES_M),
            apellido1=rng.choice(APELLIDOS),
            apellido2=rng.choice(APELLIDOS),
            sexo=sexo,
            fecha_nacimiento=nacimiento,
            provincia=provincia,
            codigo_postal=f"{prefijo}{rng.randint(1, 999):03d}",
            cronicos=rng.sample(CRONICOS, rng.choice([0, 1, 1, 2, 2, 3])),
            _nac=nacimiento,
        ))

    pool = list(range(n_pacientes))
    rechazados = set()
    for i in inj.elegir(pool, 8):
        pacientes[i]["fecha_nacimiento"] = None
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "fecha_nacimiento_vacia", "RECHAZO")
        rechazados.add(i)
    for i in inj.elegir(pool, 6):
        pacientes[i]["fecha_nacimiento"] = rng.choice(["31/02/1975", "30/02/1988", "1964-13-05", "ayer"])
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "fecha_nacimiento_invalida", "RECHAZO",
                    pacientes[i]["fecha_nacimiento"])
        rechazados.add(i)
    for i in inj.elegir(pool, 5):
        pacientes[i]["fecha_nacimiento"] = dt.date(rng.randint(2027, 2035), rng.randint(1, 12), 15)
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "fecha_nacimiento_futura", "RECHAZO")
        rechazados.add(i)
    for i in inj.elegir(pool, 5):
        pacientes[i]["fecha_nacimiento"] = dt.date(rng.randint(1850, 1899), rng.randint(1, 12), 1)
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "fecha_nacimiento_implausible", "RECHAZO")
        rechazados.add(i)
    for i in inj.elegir(pool, 30):
        f = pacientes[i]["fecha_nacimiento"]
        pacientes[i]["fecha_nacimiento"] = rng.choice([f.strftime("%d/%m/%Y"), f.strftime("%Y-%m-%d"),
                                                       f.strftime("%d-%m-%Y")])
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "fecha_en_texto", "CORREGIDO",
                    pacientes[i]["fecha_nacimiento"])
    for i in inj.elegir(pool, 40):
        p = pacientes[i]
        p["sexo"] = rng.choice({"H": ["Hombre", "hombre", "V", "Varón", " H", "h"],
                                "M": ["Mujer", "mujer", "F", "m", "M "]}[p["sexo"]])
        inj.apuntar("pacientes", p["id_paciente"], "sexo_variante", "CORREGIDO", repr(p["sexo"]))
    for i in inj.elegir(pool, 12):
        pacientes[i]["sexo"] = rng.choice(["X", None, "?", "No consta"])
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "sexo_desconocido", "AVISO",
                    repr(pacientes[i]["sexo"]))
    for i in inj.elegir(pool, 20):
        # El clásico de Excel: el código postal se guarda como número y pierde el 0 inicial.
        provincia, prefijo = rng.choice([p for p in PROVINCIAS if p[1].startswith("0")])
        pacientes[i]["provincia"] = provincia
        pacientes[i]["codigo_postal"] = int(f"{prefijo}{rng.randint(1, 999):03d}")
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "cp_sin_cero_inicial", "CORREGIDO",
                    str(pacientes[i]["codigo_postal"]))
    for i in inj.elegir(pool, 8):
        pacientes[i]["codigo_postal"] = rng.choice(["ABCDE", "2801", "99999X", ""])
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "cp_invalido", "AVISO",
                    repr(pacientes[i]["codigo_postal"]))

    filas_pac = [dict(p) for p in pacientes]
    for i in inj.elegir(pool, 15):
        filas_pac.append(dict(pacientes[i]))
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "duplicado_exacto", "CORREGIDO")
    for i in inj.elegir(pool, 10):
        copia = dict(pacientes[i])
        copia["fecha_nacimiento"] = pacientes[i]["fecha_nacimiento"] + dt.timedelta(days=rng.randint(30, 3000))
        filas_pac.append(copia)
        inj.apuntar("pacientes", pacientes[i]["id_paciente"], "duplicado_conflictivo", "RECHAZO",
                    "misma id con distinta fecha de nacimiento")
    for _ in range(3):
        copia = dict(pacientes[rng.choice(pool)])
        copia["id_paciente"] = None
        filas_pac.append(copia)
        inj.apuntar("pacientes", "(vacío)", "id_vacio", "RECHAZO")
    rng.shuffle(filas_pac)

    # --------------------------------------------------------------- visitas
    def nacimiento_real(p):
        return p["_nac"]  # fecha "verdadera", antes de estropearla

    visitas = []
    for idx, p in enumerate(pacientes):
        desde = max(INICIO_VISITAS, nacimiento_real(p))
        if desde > FIN_VISITAS:
            desde = FIN_VISITAS - dt.timedelta(days=365)
        for _ in range(rng.randint(1, 6)):
            tipo = rng.choices(TIPOS_VISITA, PESOS_VISITA)[0]
            ini = fecha_aleatoria(rng, desde, FIN_VISITAS)
            fin = ini + dt.timedelta(days=rng.randint(1, 12)) if tipo == "Hospitalización" else ini
            visitas.append(dict(id_visita=None, id_paciente=p["id_paciente"], tipo_visita=tipo,
                                fecha_inicio=ini, fecha_fin=fin, servicio=rng.choice(
                                    ["Medicina Interna", "Cardiología", "Neumología", "Endocrinología",
                                     "Atención Primaria", "Urgencias", "Nefrología"]),
                                _idx_pac=idx))
    visitas.sort(key=lambda v: (v["fecha_inicio"], v["id_paciente"]))
    for n, v in enumerate(visitas, 1):
        v["id_visita"] = f"V{n:06d}"

    pool_v = [i for i, v in enumerate(visitas) if v["_idx_pac"] not in rechazados]
    visitas_rechazadas = set()
    for i in inj.elegir(pool_v, 8):
        visitas[i]["fecha_inicio"] = None
        inj.apuntar("visitas", visitas[i]["id_visita"], "fecha_inicio_vacia", "RECHAZO")
        visitas_rechazadas.add(i)
    for i in inj.elegir(pool_v, 8):
        p = pacientes[visitas[i]["_idx_pac"]]
        f = nacimiento_real(p) - dt.timedelta(days=rng.randint(30, 2000))
        visitas[i]["fecha_inicio"], visitas[i]["fecha_fin"] = f, f
        inj.apuntar("visitas", visitas[i]["id_visita"], "visita_antes_nacimiento", "RECHAZO")
        visitas_rechazadas.add(i)
    for i in inj.elegir(pool_v, 5):
        f = dt.date(rng.randint(2027, 2029), rng.randint(1, 12), 10)
        visitas[i]["fecha_inicio"], visitas[i]["fecha_fin"] = f, f
        inj.apuntar("visitas", visitas[i]["id_visita"], "visita_fecha_futura", "RECHAZO")
        visitas_rechazadas.add(i)
    for i in inj.elegir(pool_v, 25):
        v = visitas[i]
        v["fecha_fin"] = v["fecha_inicio"] - dt.timedelta(days=rng.randint(1, 20))
        inj.apuntar("visitas", v["id_visita"], "fin_anterior_a_inicio", "CORREGIDO")
    hosp = [i for i in pool_v if visitas[i]["tipo_visita"] == "Hospitalización"]
    for i in inj.elegir(hosp, 15):
        pool_v.remove(i)
        visitas[i]["fecha_fin"] = None
        inj.apuntar("visitas", visitas[i]["id_visita"], "fecha_fin_vacia", "CORREGIDO")
    for i in inj.elegir(pool_v, 40):
        v = visitas[i]
        v["tipo_visita"] = rng.choice({"Ambulatoria": ["ambulatoria", "Consulta externa", "AMBULATORIA "],
                                       "Urgencias": ["URGENCIAS ", "urgencias", "Urg."],
                                       "Hospitalización": ["Ingreso", "hospitalizacion", "HOSPITALIZACIÓN"]}
                                      [v["tipo_visita"]])
        inj.apuntar("visitas", v["id_visita"], "tipo_visita_variante", "CORREGIDO", repr(v["tipo_visita"]))
    for i in inj.elegir(pool_v, 15):
        visitas[i]["tipo_visita"] = rng.choice(["Telefónica", "Domicilio", "Videoconsulta"])
        inj.apuntar("visitas", visitas[i]["id_visita"], "tipo_visita_sin_mapeo", "AVISO",
                    visitas[i]["tipo_visita"])
    huerfanas = []
    for n in range(10):
        f = fecha_aleatoria(rng, INICIO_VISITAS, FIN_VISITAS)
        vid = f"V9{n:05d}"
        huerfanas.append(dict(id_visita=vid, id_paciente=f"P9{rng.randint(1000, 9999)}",
                              tipo_visita="Ambulatoria", fecha_inicio=f, fecha_fin=f,
                              servicio="Atención Primaria", _idx_pac=None))
        inj.apuntar("visitas", vid, "paciente_inexistente", "RECHAZO")

    # ------------------------------------------- diagnósticos / fármacos / lab
    diags, meds, labs = [], [], []
    for i, v in enumerate(visitas):
        if i in visitas_rechazadas:
            continue  # las visitas que se van a rechazar no tienen hijos (evita cascadas raras)
        p = pacientes[v["_idx_pac"]]
        fecha = v["fecha_inicio"]
        candidatos = p["cronicos"] + (AGUDOS if v["tipo_visita"] != "Ambulatoria" else [])
        for cod in rng.sample(candidatos, min(len(candidatos), rng.randint(0, 2))) if candidatos else []:
            desc = next(d for c, d, _ in DIAGNOSTICOS if c == cod)
            diags.append(dict(id_diagnostico=None, id_paciente=p["id_paciente"], id_visita=v["id_visita"],
                              codigo_cie10=cod, descripcion=desc, fecha_diagnostico=fecha,
                              principal=rng.choice(["S", "N"])))
            atc = next(a for c, _, a in DIAGNOSTICOS if c == cod)
            if atc and rng.random() < 0.6:
                nombre, dosis, unidad = MEDICAMENTOS[atc]
                dias = rng.choice([30, 30, 90, 180]) if cod in CRONICOS else rng.choice([7, 10, 14])
                meds.append(dict(id_prescripcion=None, id_paciente=p["id_paciente"], id_visita=v["id_visita"],
                                 codigo_atc=atc, nombre_medicamento=nombre, dosis=dosis, unidad_dosis=unidad,
                                 frecuencia=rng.choice(["c/24h", "c/12h", "c/8h"]),
                                 fecha_inicio=fecha, fecha_fin=fecha + dt.timedelta(days=dias - 1)))
        if rng.random() < 0.15:  # analgésico puntual
            atc = rng.choice(["N02BE01", "M01AE01", "A02BC01", "C08CA01", "C09AA03"])
            nombre, dosis, unidad = MEDICAMENTOS[atc]
            meds.append(dict(id_prescripcion=None, id_paciente=p["id_paciente"], id_visita=v["id_visita"],
                             codigo_atc=atc, nombre_medicamento=nombre, dosis=dosis, unidad_dosis=unidad,
                             frecuencia="c/8h", fecha_inicio=fecha, fecha_fin=fecha + dt.timedelta(days=6)))
        for loinc, nombre, unidad, media, sd, dec in rng.sample(LABORATORIO, rng.randint(0, 4)):
            valor = round(min(max(rng.gauss(media, sd), media * 0.6), media * 1.8), dec)
            labs.append(dict(id_resultado=None, id_paciente=p["id_paciente"], id_visita=v["id_visita"],
                             codigo_loinc=loinc, nombre_prueba=nombre, valor=int(valor) if dec == 0 else valor,
                             unidad=unidad, fecha_resultado=fecha))

    for prefijo, lista, campo in (("D", diags, "id_diagnostico"), ("M", meds, "id_prescripcion"),
                                  ("L", labs, "id_resultado")):
        for n, fila in enumerate(lista, 1):
            fila[campo] = f"{prefijo}{n:07d}"

    # Los hijos de pacientes que se van a rechazar caerán "en cascada": no les inyectamos más errores
    ids_rech = {pacientes[i]["id_paciente"] for i in rechazados}

    def limpios(lista):
        return [j for j, fila in enumerate(lista) if fila["id_paciente"] not in ids_rech]

    pool_d = limpios(diags)
    for i in inj.elegir([j for j in pool_d if "." in diags[j]["codigo_cie10"]], 40):
        pool_d.remove(i)
        diags[i]["codigo_cie10"] = diags[i]["codigo_cie10"].replace(".", "")
        inj.apuntar("diagnosticos", diags[i]["id_diagnostico"], "cie10_sin_punto", "CORREGIDO",
                    diags[i]["codigo_cie10"])
    for i in inj.elegir(pool_d, 30):
        diags[i]["codigo_cie10"] = rng.choice([diags[i]["codigo_cie10"].lower(), " " + diags[i]["codigo_cie10"] + " "])
        inj.apuntar("diagnosticos", diags[i]["id_diagnostico"], "cie10_minusculas_espacios", "CORREGIDO",
                    repr(diags[i]["codigo_cie10"]))
    for i in inj.elegir(pool_d, 20):
        diags[i]["codigo_cie10"] = rng.choice(["Z99.99X", "XYZ", "E11.999", "R69.X"])
        diags[i]["descripcion"] = "Código no válido"
        inj.apuntar("diagnosticos", diags[i]["id_diagnostico"], "cie10_sin_mapeo", "AVISO",
                    diags[i]["codigo_cie10"])
    for i in inj.elegir(pool_d, 10):
        diags[i]["codigo_cie10"] = None
        inj.apuntar("diagnosticos", diags[i]["id_diagnostico"], "codigo_vacio", "RECHAZO")
    for i in inj.elegir(pool_d, 10):
        diags[i]["id_visita"] = f"V8{rng.randint(10000, 99999)}"
        inj.apuntar("diagnosticos", diags[i]["id_diagnostico"], "visita_inexistente", "AVISO",
                    diags[i]["id_visita"])
    for i in inj.elegir(pool_d, 15):
        diags[i]["fecha_diagnostico"] = None
        inj.apuntar("diagnosticos", diags[i]["id_diagnostico"], "fecha_vacia", "CORREGIDO",
                    "se usa la fecha de la visita")

    pool_m = limpios(meds)
    for i in inj.elegir(pool_m, 25):
        meds[i]["codigo_atc"] = None
        inj.apuntar("medicamentos", meds[i]["id_prescripcion"], "atc_vacio_con_nombre", "CORREGIDO",
                    meds[i]["nombre_medicamento"])
    for i in inj.elegir(pool_m, 15):
        meds[i]["codigo_atc"] = rng.choice(["X99ZZ99", "A10", "N02BE99"])
        meds[i]["nombre_medicamento"] = "Fórmula magistral"
        inj.apuntar("medicamentos", meds[i]["id_prescripcion"], "atc_sin_mapeo", "AVISO",
                    meds[i]["codigo_atc"])
    for i in inj.elegir(pool_m, 10):
        meds[i]["dosis"] = -abs(meds[i]["dosis"])
        inj.apuntar("medicamentos", meds[i]["id_prescripcion"], "dosis_negativa", "AVISO")
    for i in inj.elegir(pool_m, 15):
        meds[i]["fecha_fin"] = meds[i]["fecha_inicio"] - dt.timedelta(days=rng.randint(1, 60))
        inj.apuntar("medicamentos", meds[i]["id_prescripcion"], "fin_anterior_a_inicio", "CORREGIDO")
    for i in inj.elegir(pool_m, 20):
        meds[i]["fecha_fin"] = None
        inj.apuntar("medicamentos", meds[i]["id_prescripcion"], "fecha_fin_vacia", "CORREGIDO")

    pool_l = limpios(labs)
    convertibles = [j for j in pool_l if labs[j]["codigo_loinc"] in ("2345-7", "2093-3")]
    for i in inj.elegir(convertibles, 25):
        pool_l.remove(i)
        factor = 18.016 if labs[i]["codigo_loinc"] == "2345-7" else 38.67
        labs[i]["valor"] = round(labs[i]["valor"] / factor, 1)
        labs[i]["unidad"] = rng.choice(["mmol/L", "mmol/l"])
        inj.apuntar("laboratorio", labs[i]["id_resultado"], "unidad_convertible", "CORREGIDO",
                    f"{labs[i]['valor']} {labs[i]['unidad']}")
    for i in inj.elegir([j for j in pool_l if isinstance(labs[j]["valor"], float)], 40):
        pool_l.remove(i)
        labs[i]["valor"] = str(labs[i]["valor"]).replace(".", ",")
        inj.apuntar("laboratorio", labs[i]["id_resultado"], "decimal_con_coma", "CORREGIDO", labs[i]["valor"])
    for i in inj.elegir(pool_l, 15):
        labs[i]["valor"] = rng.choice(["<", ">"]) + str(labs[i]["valor"])
        inj.apuntar("laboratorio", labs[i]["id_resultado"], "valor_con_operador", "CORREGIDO", labs[i]["valor"])
    for i in inj.elegir(pool_l, 15):
        labs[i]["valor"] = rng.choice(["pendiente", "hemolizada", "N/D", "ver informe"])
        inj.apuntar("laboratorio", labs[i]["id_resultado"], "valor_no_numerico", "AVISO", labs[i]["valor"])
    for i in inj.elegir(pool_l, 15):
        labs[i]["valor"] = rng.choice([9999, -5, 0.001, 123456])
        inj.apuntar("laboratorio", labs[i]["id_resultado"], "valor_implausible", "AVISO", str(labs[i]["valor"]))
    for i in inj.elegir(pool_l, 10):
        labs[i]["codigo_loinc"] = rng.choice(["99999-9", "LAB123", "2345"])
        labs[i]["nombre_prueba"] = "Prueba local"
        inj.apuntar("laboratorio", labs[i]["id_resultado"], "loinc_sin_mapeo", "AVISO", labs[i]["codigo_loinc"])
    for i in inj.elegir(pool_l, 10):
        labs[i]["unidad"] = None
        inj.apuntar("laboratorio", labs[i]["id_resultado"], "unidad_vacia", "AVISO")

    visitas_out = visitas + huerfanas
    for lista in (visitas_out,):
        for v in lista:
            v.pop("_idx_pac", None)
    for p in filas_pac:
        p.pop("cronicos", None)
        p.pop("_nac", None)
    return filas_pac, visitas_out, diags, meds, labs, inj.errores


LEEME = [
    ["Datos 100% sintéticos. Ninguna fila corresponde a una persona real."],
    [""],
    ["Hojas: pacientes, visitas, diagnosticos, medicamentos, laboratorio."],
    ["Códigos de origen: CIE-10-ES (diagnósticos), ATC (fármacos), LOINC (laboratorio)."],
    ["Sexo: H = hombre, M = mujer (¡ojo! 'M' NO es 'male')."],
    [""],
    ["Una parte de los registros tiene errores inyectados a propósito."],
    ["La lista completa y lo que la ETL debería hacer está en errores_inyectados.csv."],
]


def escribir(filas_pac, visitas, diags, meds, labs, errores):
    SALIDA_XLSX.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(SALIDA_XLSX, engine="openpyxl", date_format="DD/MM/YYYY",
                        datetime_format="DD/MM/YYYY") as xw:
        pd.DataFrame(LEEME, columns=["LEEME"]).to_excel(xw, sheet_name="LEEME", index=False)
        for nombre, filas in (("pacientes", filas_pac), ("visitas", visitas), ("diagnosticos", diags),
                              ("medicamentos", meds), ("laboratorio", labs)):
            df = pd.DataFrame(filas)
            df.to_excel(xw, sheet_name=nombre, index=False)
            hoja = xw.sheets[nombre]
            hoja.freeze_panes = "A2"
            for col in hoja.columns:
                hoja.column_dimensions[col[0].column_letter].width = max(
                    12, min(45, max(len(str(c.value or "")) for c in col[:200]) + 2))
        xw.sheets["LEEME"].column_dimensions["A"].width = 90
    pd.DataFrame(errores).to_csv(SALIDA_ERRORES, index=False, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pacientes", type=int, default=1000)
    ap.add_argument("--semilla", type=int, default=42)
    args = ap.parse_args()
    datos = generar(args.pacientes, args.semilla)
    escribir(*datos)
    nombres = ["pacientes", "visitas", "diagnosticos", "medicamentos", "laboratorio"]
    for nombre, filas in zip(nombres, datos[:5]):
        print(f"  {nombre:<13} {len(filas):>6} filas")
    print(f"  errores inyectados: {len(datos[5])}")
    print(f"-> {SALIDA_XLSX.relative_to(RAIZ)}\n-> {SALIDA_ERRORES.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
