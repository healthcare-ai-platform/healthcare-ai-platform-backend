-- =============================================================================
-- V002__seed_data.sql
-- Sample data for local development / testing
-- =============================================================================

BEGIN;

-- 1. tenants
INSERT INTO tenants (tenant_id, name, plan, status) VALUES
    ('11111111-0000-0000-0000-000000000001', 'City General Health System', 'enterprise', 'active'),
    ('11111111-0000-0000-0000-000000000002', 'Riverside Clinic Group',    'professional', 'active');

-- 2. facilities
INSERT INTO facilities (facility_id, tenant_id, name, type, city, address, status) VALUES
    ('22222222-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001',
     'City General Hospital',    'hospital',       'New York',  '1 Hospital Blvd, NY 10001', 'active'),
    ('22222222-0000-0000-0000-000000000002', '11111111-0000-0000-0000-000000000001',
     'Downtown Imaging Center',  'imaging_center', 'New York',  '22 Park Ave, NY 10002',     'active'),
    ('22222222-0000-0000-0000-000000000003', '11111111-0000-0000-0000-000000000002',
     'Riverside Primary Clinic', 'clinic',         'Brooklyn',  '5 River Rd, BK 11201',      'active');

-- 3. users
INSERT INTO users (user_id, tenant_id, email, name, role, status) VALUES
    ('33333333-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001',
     'admin@citygeneral.com',   'Alice Admin',    'admin',   'active'),
    ('33333333-0000-0000-0000-000000000002', '11111111-0000-0000-0000-000000000001',
     'dr.smith@citygeneral.com','Dr. John Smith', 'doctor',  'active'),
    ('33333333-0000-0000-0000-000000000003', '11111111-0000-0000-0000-000000000001',
     'analyst@citygeneral.com', 'Bob Analyst',    'analyst', 'active'),
    ('33333333-0000-0000-0000-000000000004', '11111111-0000-0000-0000-000000000002',
     'dr.jones@riverside.com',  'Dr. Mary Jones', 'doctor',  'active');

-- 4. patients
INSERT INTO patients (patient_id, tenant_id, external_id, name, dob, gender, status) VALUES
    ('44444444-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001',
     'EXT-001', 'James Wilson',   '1975-03-12', 'male',   'active'),
    ('44444444-0000-0000-0000-000000000002', '11111111-0000-0000-0000-000000000001',
     'EXT-002', 'Sarah Connor',   '1988-07-24', 'female', 'active'),
    ('44444444-0000-0000-0000-000000000003', '11111111-0000-0000-0000-000000000002',
     'EXT-001', 'Michael Brown',  '1960-11-05', 'male',   'active');

-- 5. documents
INSERT INTO documents (document_id, tenant_id, facility_id, patient_id, uploaded_by,
                        report_type, source, s3_path, status) VALUES
    ('55555555-0000-0000-0000-000000000001',
     '11111111-0000-0000-0000-000000000001',
     '22222222-0000-0000-0000-000000000001',
     '44444444-0000-0000-0000-000000000001',
     '33333333-0000-0000-0000-000000000002',
     'CBC', 'pdf_upload', 's3://healthcare-docs/tenant1/CBC_JWilson_2024.pdf', 'loaded'),

    ('55555555-0000-0000-0000-000000000002',
     '11111111-0000-0000-0000-000000000001',
     '22222222-0000-0000-0000-000000000002',
     '44444444-0000-0000-0000-000000000002',
     '33333333-0000-0000-0000-000000000002',
     'MRI_BRAIN', 'pdf_upload', 's3://healthcare-docs/tenant1/MRI_SConnor_2024.pdf', 'extracted'),

    ('55555555-0000-0000-0000-000000000003',
     '11111111-0000-0000-0000-000000000001',
     '22222222-0000-0000-0000-000000000001',
     '44444444-0000-0000-0000-000000000001',
     '33333333-0000-0000-0000-000000000003',
     'LIPID_PANEL', 'json_upload', 's3://healthcare-docs/tenant1/LIPID_JWilson_2024.json', 'received');

-- 6. reports (only for loaded/extracted docs)
INSERT INTO reports (report_id, document_id, patient_id, facility_id, report_type,
                     report_date, doctor, extraction_status, extraction_confidence) VALUES
    ('66666666-0000-0000-0000-000000000001',
     '55555555-0000-0000-0000-000000000001',
     '44444444-0000-0000-0000-000000000001',
     '22222222-0000-0000-0000-000000000001',
     'CBC', '2024-06-01', 'Dr. John Smith', 'validated', 0.9850),

    ('66666666-0000-0000-0000-000000000002',
     '55555555-0000-0000-0000-000000000002',
     '44444444-0000-0000-0000-000000000002',
     '22222222-0000-0000-0000-000000000002',
     'MRI_BRAIN', '2024-06-10', 'Dr. John Smith', 'extracted', 0.8720);

-- 7. report_results (CBC values for James Wilson)
INSERT INTO report_results (report_id, test_name, value, unit, reference_range, flag, confidence) VALUES
    ('66666666-0000-0000-0000-000000000001', 'WBC',        7.2,  '10^3/uL', '4.5–11.0',   'normal',   0.9900),
    ('66666666-0000-0000-0000-000000000001', 'RBC',        4.1,  '10^6/uL', '4.5–5.5',    'low',      0.9850),
    ('66666666-0000-0000-0000-000000000001', 'Hemoglobin', 11.8, 'g/dL',    '13.5–17.5',  'low',      0.9870),
    ('66666666-0000-0000-0000-000000000001', 'Hematocrit', 35.0, '%',        '41.0–53.0',  'low',      0.9800),
    ('66666666-0000-0000-0000-000000000001', 'Platelets',  310,  '10^3/uL', '150–400',    'normal',   0.9950),
    ('66666666-0000-0000-0000-000000000001', 'Neutrophils',72.0, '%',        '50–70',      'high',     0.9780);

-- 8. audit_logs
INSERT INTO audit_logs (user_id, tenant_id, action, resource, resource_id, ip_address) VALUES
    ('33333333-0000-0000-0000-000000000002', '11111111-0000-0000-0000-000000000001',
     'upload',  'document', '55555555-0000-0000-0000-000000000001', '192.168.1.10'),
    ('33333333-0000-0000-0000-000000000003', '11111111-0000-0000-0000-000000000001',
     'upload',  'document', '55555555-0000-0000-0000-000000000003', '192.168.1.11'),
    ('33333333-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001',
     'view',    'patient',  '44444444-0000-0000-0000-000000000001', '192.168.1.10'),
    ('33333333-0000-0000-0000-000000000002', '11111111-0000-0000-0000-000000000001',
     'validate','report',   '66666666-0000-0000-0000-000000000001', '192.168.1.10');

COMMIT;
