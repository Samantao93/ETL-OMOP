# ETL de pacientes sintéticos a OMOP CDM 5.4

Proyecto de práctica: un Excel con **pacientes 100 % inventados** (con errores a propósito),
una **ETL en Python** que los transforma al modelo **OMOP CDM v5.4** de [OHDSI](https://ohdsi.org),
y un **visor web local** para revisar el resultado.

> ⚠️ Todos los datos de `data/raw/` son sintéticos y se generan con `scripts/generar_datos.py`.
> No corresponden a ninguna persona real.

```
Excel (5 hojas)  ──►  limpieza + mapeo de vocabularios  ──►  OMOP CDM 5.4 (SQLite)  ──►  visor web (Flask)
                              │
                              └──► etl_incidencias: CORREGIDO / AVISO / RECHAZO
```

## Puesta en marcha

```powershell
python -m pip install -r requirements.txt
python scripts/generar_datos.py      # 1. crea data/raw/pacientes_sinteticos.xlsx (opcional: ya viene en el repo)
python -m etl                        # 2. ETL  -> output/omop_cdm.sqlite
python -m app.servidor               # 3. visor -> http://127.0.0.1:5000
python -m pytest                     # tests
```

`python -m app.servidor --red` lo publica en tu red local (0.0.0.0:5000) para verlo desde el móvil u otro equipo.

## Los datos de origen

`data/raw/pacientes_sinteticos.xlsx` (semilla fija, 1 000 pacientes):

| Hoja | Filas | Codificación de origen |
|---|---|---|
| pacientes | ~1 030 | sexo local `H`/`M` (¡`M` es *mujer*!), CP, provincia |
| visitas | ~3 500 | Ambulatoria / Urgencias / Hospitalización |
| diagnosticos | ~2 800 | CIE-10-ES |
| medicamentos | ~1 900 | ATC |
| laboratorio | ~6 900 | LOINC + unidades UCUM |

Se inyectan ~630 errores, todos listados en `data/raw/errores_inyectados.csv` junto a lo que la ETL debería hacer:

| Hoja | Errores |
|---|---|
| pacientes | fecha de nacimiento vacía / imposible (31/02) / futura / antes de 1900, fechas como texto en varios formatos, variantes de sexo (`Mujer`, `V`, `" H"`), sexo desconocido, CP sin el 0 inicial (`8001`), CP inválido, duplicados exactos y conflictivos, id vacío |
| visitas | paciente inexistente, fecha vacía, visita antes de nacer, fecha futura, fin < inicio, fin vacío, variantes del tipo (`Urg.`, `Ingreso`), tipos sin mapeo (`Telefónica`) |
| diagnosticos | CIE-10 sin punto (`E119`), minúsculas/espacios, códigos inexistentes, código vacío, visita inexistente, fecha vacía |
| medicamentos | ATC vacío con nombre, ATC desconocido, dosis negativa, fin < inicio, fin vacío |
| laboratorio | decimal con coma, valores `<5`, texto (`pendiente`), glucosa/colesterol en mmol/L, valores imposibles, LOINC desconocido, unidad vacía |

## Reglas de la ETL (estilo OHDSI)

* **Lo que no se puede mapear no se tira**: se carga con `concept_id = 0` y el código original en
  `*_source_value`. La página *Sin mapear* del visor es la lista de trabajo para [Usagi](https://github.com/OHDSI/Usagi).
* **Sólo se rechaza lo que rompe el modelo**: personas sin año de nacimiento válido, eventos sin fecha,
  antes del nacimiento, en el futuro o de pacientes inexistentes (y, en cascada, los eventos de pacientes rechazados).
* **Sin identificadores directos**: nombre y apellidos no pasan a OMOP; el id de origen queda en `person_source_value`.
* Laboratorio: se normaliza a una unidad por prueba (p. ej. glucosa mmol/L × 18,016 → mg/dL), guardando el valor
  y la unidad originales en `value_source_value` / `unit_source_value`; `<`/`>` van a `operator_concept_id`.
* `observation_period` = del primer al último evento de cada persona.
* Cada decisión queda en la tabla `etl_incidencias`; `etl_evaluacion` la compara con los errores inyectados
  (resultado actual: **628/628** tratados como se esperaba).

Las reglas de negocio (rangos plausibles, conversiones, fecha de corte) están en [`etl/reglas.py`](etl/reglas.py).

## Vocabularios

Por defecto se usa [`vocab/source_to_concept_map.csv`](vocab/source_to_concept_map.csv) (formato de la tabla
`SOURCE_TO_CONCEPT_MAP` del CDM) con los mapeos que necesitan estos datos y
[`vocab/concept.csv`](vocab/concept.csv) con los conceptos estándar destino (SNOMED, RxNorm, LOINC, UCUM...).
Los concept_id se han revisado a mano, pero **compruébalos en [Athena](https://athena.ohdsi.org)** antes de
usarlos para algo serio.

Para usar los vocabularios oficiales completos:

1. Descárgalos en Athena (gratis, con registro) incluyendo **SNOMED, ICD10CM, ATC, RxNorm, LOINC, UCUM**.
2. Descomprime `CONCEPT.csv` y `CONCEPT_RELATIONSHIP.csv` en `vocab/athena/` (está en `.gitignore`: la licencia
   de algunos vocabularios no permite redistribuirlos).
3. `python -m etl` los detecta y mapea con las relaciones `Maps to` (y `ATC - RxNorm pr lat` para ATC).
   Los códigos locales (sexo, tipo de visita, unidades) siguen saliendo de `source_to_concept_map.csv`.

> Nota: CIE-10-ES se mapea como ICD10CM, que es su base. Los fármacos se mapean a nivel de *Ingredient*
> de RxNorm porque el origen sólo trae el ATC.

## Estructura

```
data/raw/            Excel sintético + errores_inyectados.csv (la "verdad")
scripts/             generador de datos
etl/                 limpieza.py, vocabulario.py, transformar.py, reglas.py, DDL CDM 5.4, __main__.py
vocab/               concept.csv, source_to_concept_map.csv, athena/ (opcional, no versionado)
app/                 visor Flask (resumen, incidencias, sin mapear, evaluación, personas)
tests/               pytest: limpieza, integridad referencial, conceptos, periodos, evaluación
output/              omop_cdm.sqlite (se genera, no versionado)
```

## Siguientes pasos posibles

* Cargar en PostgreSQL con el [DDL oficial](https://github.com/OHDSI/CommonDataModel) y pasar
  [DataQualityDashboard](https://github.com/OHDSI/DataQualityDashboard) y [Achilles](https://github.com/OHDSI/Achilles).
* Levantar ATLAS con [Broadsea](https://github.com/OHDSI/Broadsea) (Docker) para definir cohortes.
* Enrutar por dominio (un diagnóstico cuyo concepto estándar es de dominio *Observation* debería ir a `OBSERVATION`).

## Licencia

MIT. Los datos son sintéticos y de dominio público.
