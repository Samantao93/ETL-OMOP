"""Funciones puras de limpieza/normalización. Cada una devuelve (valor, bandera)
donde la bandera explica qué se ha tenido que hacer (None = venía bien)."""
from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata

FORMATOS_FECHA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y")


def vacio(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip())


def texto(v) -> str | None:
    return None if vacio(v) else str(v).strip()


def sin_tildes(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def parse_fecha(v):
    """-> (date | None, None | 'texto' | 'vacia' | 'invalida')"""
    if vacio(v):
        return None, "vacia"
    if isinstance(v, dt.datetime):
        return v.date(), None
    if isinstance(v, dt.date):
        return v, None
    s = str(v).strip()
    for fmt in FORMATOS_FECHA:
        try:
            return dt.datetime.strptime(s, fmt).date(), "texto"
        except ValueError:
            pass
    return None, "invalida"


SEXO_SINONIMOS = {"H": "H", "HOMBRE": "H", "V": "H", "VARON": "H", "MASCULINO": "H",
                  "M": "M", "MUJER": "M", "F": "M", "FEMENINO": "M"}


def normalizar_sexo(v):
    """-> (código local 'H'/'M' | None, None | 'normalizado' | 'desconocido')"""
    if vacio(v):
        return None, "desconocido"
    clave = sin_tildes(str(v)).strip().upper()
    codigo = SEXO_SINONIMOS.get(clave)
    if codigo is None:
        return None, "desconocido"
    return codigo, (None if v in ("H", "M") else "normalizado")


VISITA_SINONIMOS = {"AMBULATORIA": "AMBULATORIA", "CONSULTA EXTERNA": "AMBULATORIA", "CONSULTA": "AMBULATORIA",
                    "URGENCIAS": "URGENCIAS", "URG.": "URGENCIAS", "URG": "URGENCIAS",
                    "HOSPITALIZACION": "HOSPITALIZACION", "INGRESO": "HOSPITALIZACION"}
VISITA_CANONICA = {"Ambulatoria", "Urgencias", "Hospitalización"}


def normalizar_tipo_visita(v):
    """-> (código local | clave sin sinónimo, None | 'normalizado')"""
    if vacio(v):
        return None, None
    clave = " ".join(sin_tildes(str(v)).upper().split())
    codigo = VISITA_SINONIMOS.get(clave, clave)
    return codigo, (None if v in VISITA_CANONICA else "normalizado")


def normalizar_cp(v):
    """Códigos postales españoles: 5 dígitos, prefijo 01-52."""
    if vacio(v):
        return None, "invalido"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        s, bandera = str(int(v)).zfill(5), "cero_inicial"
    else:
        s, bandera = str(v).strip(), None
    if re.fullmatch(r"\d{5}", s) and 1 <= int(s[:2]) <= 52:
        return s, (bandera if s != str(v) else None)
    return None, "invalido"


RE_CIE10 = re.compile(r"^[A-Z]\d{2}(\.[0-9A-Z]{1,4})?$")


def normalizar_cie10(v):
    """'e119 ' -> 'E11.9'. Devuelve (código, None | 'formato' | 'vacio')."""
    if vacio(v):
        return None, "vacio"
    original = str(v)
    s = original.strip().upper()
    if "." not in s and len(s) > 3 and re.fullmatch(r"[A-Z]\d{2}[0-9A-Z]+", s):
        s = s[:3] + "." + s[3:]
    return s, (None if s == original else "formato")


def normalizar_codigo(v):
    if vacio(v):
        return None, "vacio"
    s = str(v).strip().upper()
    return s, (None if s == str(v) else "formato")


RE_VALOR = re.compile(r"^\s*(<=|>=|<|>|=)?\s*(-?\d+(?:[.,]\d+)?)\s*$")


def parse_valor(v):
    """-> (número | None, operador | None, None | 'coma' | 'operador' | 'no_numerico' | 'vacio')"""
    if vacio(v):
        return None, None, "vacio"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v), "=", None
    m = RE_VALOR.match(str(v))
    if not m:
        return None, None, "no_numerico"
    operador, numero = m.group(1), m.group(2)
    bandera = "operador" if operador else ("coma" if "," in numero else "texto")
    return float(numero.replace(",", ".")), operador or "=", bandera


UNIDAD_SINONIMOS = {"MG/DL": "mg/dL", "%": "%", "G/DL": "g/dL", "MMOL/L": "mmol/L", "KG": "kg",
                    "CM": "cm", "MM[HG]": "mm[Hg]", "MMHG": "mm[Hg]", "MM HG": "mm[Hg]"}


def normalizar_unidad(v):
    if vacio(v):
        return None
    return UNIDAD_SINONIMOS.get(str(v).strip().upper(), str(v).strip())
