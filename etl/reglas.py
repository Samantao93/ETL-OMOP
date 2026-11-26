"""Reglas de negocio de la ETL (separadas del código para revisarlas fácilmente)."""
import datetime as dt

FECHA_CORTE = dt.date(2026, 11, 26)        # "hoy" de la extracción: nada puede ser posterior
ANIO_MINIMO_NACIMIENTO = 1900

# Concept_ids de tipo (de dónde viene el dato) -> todos vienen de la historia clínica
TIPO_EHR = 32817
OPERADORES = {"=": 4172703, "<": 4171756, ">": 4172704, "<=": 4171754, ">=": 4171755}

# LOINC -> unidad en la que guardamos el valor, conversiones aceptadas y rango plausible
LAB = {
    "2345-7":  dict(unidad="mg/dL", conversion={"mmol/L": 18.016}, rango=(10, 1500)),
    "4548-4":  dict(unidad="%", conversion={}, rango=(3, 20)),
    "2093-3":  dict(unidad="mg/dL", conversion={"mmol/L": 38.67}, rango=(50, 700)),
    "13457-7": dict(unidad="mg/dL", conversion={"mmol/L": 38.67}, rango=(10, 500)),
    "2085-9":  dict(unidad="mg/dL", conversion={"mmol/L": 38.67}, rango=(5, 200)),
    "2160-0":  dict(unidad="mg/dL", conversion={}, rango=(0.1, 25)),
    "718-7":   dict(unidad="g/dL", conversion={}, rango=(3, 25)),
    "2951-2":  dict(unidad="mmol/L", conversion={}, rango=(100, 190)),
    "2823-3":  dict(unidad="mmol/L", conversion={}, rango=(1.5, 10)),
    "29463-7": dict(unidad="kg", conversion={}, rango=(0.5, 350)),
    "8302-2":  dict(unidad="cm", conversion={}, rango=(30, 250)),
    "8480-6":  dict(unidad="mm[Hg]", conversion={}, rango=(50, 300)),
    "8462-4":  dict(unidad="mm[Hg]", conversion={}, rango=(20, 200)),
}
