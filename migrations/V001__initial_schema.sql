-- =============================================================================
-- V001__initial_schema.sql
-- Healthcare AI Platform — initial PostgreSQL schema
--
-- Table creation order (respects FK dependencies):
--   1. tenants
--   2. facilities
--   3. users
--   4. patients
--   5. documents
--   6. reports
--   7. report_results
--   8. audit_logs
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. tenants
--    Top-level billing / account entity.
--    Every other table carries tenant_id for isolation.
-- ---------------------------------------------------------------------------
CREATE TABLE tenants (
    tenant_id  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    plan       TEXT        NOT NULL DEFAULT 'starter'
                           CHECK (plan IN ('starter', 'professional', 'enterprise')),
    status     TEXT        NOT NULL DEFAULT 'active'
                           CHECK (status IN ('active', 'suspended', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 2. facilities
--    Physical locations (hospitals, clinics, labs) owned by a tenant.
--    A tenant can have many facilities.
-- ---------------------------------------------------------------------------
CREATE TABLE facilities (
    facility_id UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID        NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    name        TEXT        NOT NULL,
    type        TEXT        NOT NULL
                            CHECK (type IN ('hospital', 'clinic', 'lab', 'imaging_center', 'pharmacy')),
    city        TEXT,
    address     TEXT,
    status      TEXT        NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'inactive')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_facilities_tenant ON facilities(tenant_id);

-- ---------------------------------------------------------------------------
-- 3. users
--    Platform users (doctors, analysts, ops, admins).
--    Scoped to a tenant; email is globally unique.
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    user_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID        NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    email      TEXT        NOT NULL UNIQUE,
    name       TEXT        NOT NULL,
    role       TEXT        NOT NULL
                           CHECK (role IN ('admin', 'doctor', 'analyst', 'ops', 'viewer')),
    status     TEXT        NOT NULL DEFAULT 'active'
                           CHECK (status IN ('active', 'inactive', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_tenant ON users(tenant_id);

-- ---------------------------------------------------------------------------
-- 4. patients
--    Patient registry. external_id is the ID in the hospital source system.
--    (tenant_id, external_id) is unique — same patient can exist across tenants.
-- ---------------------------------------------------------------------------
CREATE TABLE patients (
    patient_id  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID        NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    external_id TEXT        NOT NULL,
    name        TEXT        NOT NULL,
    dob         DATE        NOT NULL,
    gender      TEXT        CHECK (gender IN ('male', 'female', 'other', 'unknown')),
    status      TEXT        NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'inactive')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (tenant_id, external_id)
);

CREATE INDEX idx_patients_tenant  ON patients(tenant_id);
CREATE INDEX idx_patients_extid   ON patients(tenant_id, external_id);

-- ---------------------------------------------------------------------------
-- 5. documents
--    One row per uploaded file (PDF or JSON).
--    Tracks the full pipeline lifecycle via `status`.
--    patient_id is nullable — set after extraction links the doc to a patient.
-- ---------------------------------------------------------------------------
CREATE TABLE documents (
    document_id  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID        NOT NULL REFERENCES tenants(tenant_id)    ON DELETE RESTRICT,
    facility_id  UUID        NOT NULL REFERENCES facilities(facility_id) ON DELETE RESTRICT,
    patient_id   UUID                 REFERENCES patients(patient_id)   ON DELETE SET NULL,
    uploaded_by  UUID        NOT NULL REFERENCES users(user_id)         ON DELETE RESTRICT,
    report_type  TEXT        NOT NULL,
    source       TEXT        NOT NULL
                             CHECK (source IN ('pdf_upload', 'json_upload', 'hl7', 'fhir', 'api')),
    s3_path      TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'received'
                             CHECK (status IN (
                                 'received', 'ocr', 'extracting',
                                 'extracted', 'validated', 'loaded', 'failed'
                             )),
    error_reason TEXT,
    retry_count  INTEGER     NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_tenant   ON documents(tenant_id);
CREATE INDEX idx_documents_patient  ON documents(patient_id);
CREATE INDEX idx_documents_facility ON documents(facility_id);
CREATE INDEX idx_documents_status   ON documents(tenant_id, status);
CREATE INDEX idx_documents_created  ON documents(tenant_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 6. reports
--    Structured extraction output, created once a document reaches 'extracted'.
--    1:1 with documents (UNIQUE on document_id).
-- ---------------------------------------------------------------------------
CREATE TABLE reports (
    report_id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id          UUID         NOT NULL UNIQUE REFERENCES documents(document_id) ON DELETE CASCADE,
    patient_id           UUID         NOT NULL REFERENCES patients(patient_id)          ON DELETE RESTRICT,
    facility_id          UUID         NOT NULL REFERENCES facilities(facility_id)       ON DELETE RESTRICT,
    report_type          TEXT         NOT NULL,
    report_date          DATE,
    doctor               TEXT,
    extraction_status    TEXT         NOT NULL
                                      CHECK (extraction_status IN ('extracted', 'validated', 'failed')),
    extraction_confidence NUMERIC(5,4) CHECK (extraction_confidence BETWEEN 0 AND 1),
    s3_extracted_path    TEXT,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reports_patient  ON reports(patient_id);
CREATE INDEX idx_reports_facility ON reports(facility_id);
CREATE INDEX idx_reports_date     ON reports(patient_id, report_date DESC);

-- ---------------------------------------------------------------------------
-- 7. report_results
--    Individual test results extracted from a report (e.g. each row in a CBC).
--    Many per report.
-- ---------------------------------------------------------------------------
CREATE TABLE report_results (
    result_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id       UUID         NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
    test_name       TEXT         NOT NULL,
    value           NUMERIC,
    unit            TEXT,
    reference_range TEXT,
    flag            TEXT         CHECK (flag IN ('normal', 'high', 'low', 'critical', 'borderline')),
    confidence      NUMERIC(5,4) CHECK (confidence BETWEEN 0 AND 1),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_results_report ON report_results(report_id);
CREATE INDEX idx_results_flag   ON report_results(report_id, flag);

-- ---------------------------------------------------------------------------
-- 8. audit_logs
--    Immutable record of every user action.
--    Never updated or deleted — append-only.
-- ---------------------------------------------------------------------------
CREATE TABLE audit_logs (
    log_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(user_id)    ON DELETE RESTRICT,
    tenant_id   UUID        NOT NULL REFERENCES tenants(tenant_id) ON DELETE RESTRICT,
    action      TEXT        NOT NULL,
    resource    TEXT        NOT NULL,
    resource_id UUID,
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_tenant    ON audit_logs(tenant_id, created_at DESC);
CREATE INDEX idx_audit_user      ON audit_logs(user_id,   created_at DESC);
CREATE INDEX idx_audit_resource  ON audit_logs(resource_id);

COMMIT;
