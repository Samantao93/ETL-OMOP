-- Subconjunto de OMOP CDM v5.4 (columnas completas de cada tabla) adaptado a SQLite.
-- DDL oficial para otros motores: https://github.com/OHDSI/CommonDataModel

CREATE TABLE location (
  location_id INTEGER PRIMARY KEY, address_1 TEXT, address_2 TEXT, city TEXT, state TEXT,
  zip TEXT, county TEXT, location_source_value TEXT, country_concept_id INTEGER,
  country_source_value TEXT, latitude REAL, longitude REAL);

CREATE TABLE person (
  person_id INTEGER PRIMARY KEY, gender_concept_id INTEGER NOT NULL, year_of_birth INTEGER NOT NULL,
  month_of_birth INTEGER, day_of_birth INTEGER, birth_datetime TEXT,
  race_concept_id INTEGER NOT NULL, ethnicity_concept_id INTEGER NOT NULL,
  location_id INTEGER REFERENCES location(location_id), provider_id INTEGER, care_site_id INTEGER,
  person_source_value TEXT, gender_source_value TEXT, gender_source_concept_id INTEGER,
  race_source_value TEXT, race_source_concept_id INTEGER,
  ethnicity_source_value TEXT, ethnicity_source_concept_id INTEGER);

CREATE TABLE observation_period (
  observation_period_id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES person(person_id),
  observation_period_start_date TEXT NOT NULL, observation_period_end_date TEXT NOT NULL,
  period_type_concept_id INTEGER NOT NULL);

CREATE TABLE visit_occurrence (
  visit_occurrence_id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES person(person_id),
  visit_concept_id INTEGER NOT NULL, visit_start_date TEXT NOT NULL, visit_start_datetime TEXT,
  visit_end_date TEXT NOT NULL, visit_end_datetime TEXT, visit_type_concept_id INTEGER NOT NULL,
  provider_id INTEGER, care_site_id INTEGER, visit_source_value TEXT, visit_source_concept_id INTEGER,
  admitted_from_concept_id INTEGER, admitted_from_source_value TEXT,
  discharged_to_concept_id INTEGER, discharged_to_source_value TEXT, preceding_visit_occurrence_id INTEGER);

CREATE TABLE condition_occurrence (
  condition_occurrence_id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES person(person_id),
  condition_concept_id INTEGER NOT NULL, condition_start_date TEXT NOT NULL, condition_start_datetime TEXT,
  condition_end_date TEXT, condition_end_datetime TEXT, condition_type_concept_id INTEGER NOT NULL,
  condition_status_concept_id INTEGER, stop_reason TEXT, provider_id INTEGER,
  visit_occurrence_id INTEGER REFERENCES visit_occurrence(visit_occurrence_id), visit_detail_id INTEGER,
  condition_source_value TEXT, condition_source_concept_id INTEGER, condition_status_source_value TEXT);

CREATE TABLE drug_exposure (
  drug_exposure_id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES person(person_id),
  drug_concept_id INTEGER NOT NULL, drug_exposure_start_date TEXT NOT NULL, drug_exposure_start_datetime TEXT,
  drug_exposure_end_date TEXT NOT NULL, drug_exposure_end_datetime TEXT, verbatim_end_date TEXT,
  drug_type_concept_id INTEGER NOT NULL, stop_reason TEXT, refills INTEGER, quantity REAL,
  days_supply INTEGER, sig TEXT, route_concept_id INTEGER, lot_number TEXT, provider_id INTEGER,
  visit_occurrence_id INTEGER REFERENCES visit_occurrence(visit_occurrence_id), visit_detail_id INTEGER,
  drug_source_value TEXT, drug_source_concept_id INTEGER, route_source_value TEXT, dose_unit_source_value TEXT);

CREATE TABLE measurement (
  measurement_id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES person(person_id),
  measurement_concept_id INTEGER NOT NULL, measurement_date TEXT NOT NULL, measurement_datetime TEXT,
  measurement_time TEXT, measurement_type_concept_id INTEGER NOT NULL, operator_concept_id INTEGER,
  value_as_number REAL, value_as_concept_id INTEGER, unit_concept_id INTEGER, range_low REAL,
  range_high REAL, provider_id INTEGER,
  visit_occurrence_id INTEGER REFERENCES visit_occurrence(visit_occurrence_id), visit_detail_id INTEGER,
  measurement_source_value TEXT, measurement_source_concept_id INTEGER, unit_source_value TEXT,
  unit_source_concept_id INTEGER, value_source_value TEXT, measurement_event_id INTEGER,
  meas_event_field_concept_id INTEGER);

CREATE TABLE cdm_source (
  cdm_source_name TEXT NOT NULL, cdm_source_abbreviation TEXT NOT NULL, cdm_holder TEXT NOT NULL,
  source_description TEXT, source_documentation_reference TEXT, cdm_etl_reference TEXT,
  source_release_date TEXT NOT NULL, cdm_release_date TEXT NOT NULL, cdm_version TEXT,
  cdm_version_concept_id INTEGER NOT NULL, vocabulary_version TEXT NOT NULL);

CREATE TABLE concept (
  concept_id INTEGER PRIMARY KEY, concept_name TEXT NOT NULL, domain_id TEXT NOT NULL,
  vocabulary_id TEXT NOT NULL, concept_class_id TEXT NOT NULL, standard_concept TEXT);

CREATE TABLE source_to_concept_map (
  source_code TEXT NOT NULL, source_concept_id INTEGER NOT NULL, source_vocabulary_id TEXT NOT NULL,
  source_code_description TEXT, target_concept_id INTEGER NOT NULL, target_vocabulary_id TEXT NOT NULL,
  valid_start_date TEXT NOT NULL, valid_end_date TEXT NOT NULL, invalid_reason TEXT);

-- Tablas propias de la ETL (no son del CDM): trazabilidad y calidad
CREATE TABLE etl_incidencias (
  tabla_origen TEXT, id_origen TEXT, nivel TEXT, tipo TEXT, detalle TEXT);

CREATE TABLE etl_evaluacion (
  hoja TEXT, id_registro TEXT, tipo_error TEXT, esperado TEXT, detalle TEXT,
  detectado INTEGER, nivel_obtenido TEXT, acierto INTEGER);
