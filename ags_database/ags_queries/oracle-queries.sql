-- Saved VS Code connection: Aegis-Local, Oracle user AGS_OWNER.
-- Highlight a statement and press Ctrl+Enter.
SELECT USER AS connected_owner, SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name FROM dual;
SELECT table_name FROM user_tables ORDER BY table_name;
SELECT COUNT(*) AS application_table_count FROM user_tables;

SELECT table_name, column_id, column_name, data_type, char_length, nullable
FROM user_tab_columns ORDER BY table_name, column_id;

SELECT c.table_name, c.constraint_name, c.constraint_type, cc.column_name,
       c.r_constraint_name AS referenced_constraint
FROM user_constraints c
LEFT JOIN user_cons_columns cc ON cc.constraint_name=c.constraint_name
ORDER BY c.table_name,c.constraint_type,c.constraint_name,cc.position;

SELECT i.table_name,i.index_name,i.uniqueness,ic.column_name,ic.column_position
FROM user_indexes i JOIN user_ind_columns ic ON ic.index_name=i.index_name
ORDER BY i.table_name,i.index_name,ic.column_position;

SELECT dataset_id,dataset_name,owner_id,status,created_by,created_at,updated_by,updated_at,updated_via
FROM dataset_tbl ORDER BY created_at DESC;

SELECT d.dataset_name,m.category,m.model_name,m.provider_model,
       dm.enabled AS mapping_enabled,m.enabled AS model_enabled,dm.is_default,
       dm.updated_by,dm.updated_at
FROM dataset_model_tbl dm
JOIN dataset_tbl d ON d.dataset_id=dm.dataset_id
JOIN model_config_tbl m ON m.model_id=dm.model_id AND m.category=dm.category
ORDER BY d.dataset_name,m.category,m.model_name;

SELECT document_id,dataset_id,filename,is_merged,size_bytes,status,
       created_by,created_at,updated_by,updated_at,updated_via
FROM document_tbl ORDER BY created_at DESC;

SELECT prompt_id,dataset_id,filename,version,schema_reference,
       created_by,created_at,updated_by,updated_at
FROM prompt_tbl ORDER BY created_at DESC;

SELECT e.extract_id,d.dataset_name,e.filename,e.status,e.version,
       p.filename AS prompt_filename,e.prompt_version,e.result_reference,
       e.created_by,e.created_at,e.updated_by,e.updated_at,e.updated_via
FROM extract_tbl e
JOIN dataset_tbl d ON d.dataset_id=e.dataset_id
LEFT JOIN prompt_tbl p ON p.prompt_id=e.prompt_id
ORDER BY e.created_at DESC;

-- All jobs over an extraction's lifetime, including re-extraction runs.
SELECT e.extract_id,e.status AS extraction_status,e.version,
       j.id AS job_id,j.status AS job_status,j.progress,j.attempts,j.error,
       j.updated_by,j.updated_at,j.updated_via
FROM extract_tbl e LEFT JOIN job_tbl j ON j.extract_id=e.extract_id
ORDER BY e.created_at DESC,j.created_at DESC;

SELECT review_id,extract_id,extraction_version,review_version,status,
       reviewed_result_reference,created_by,created_at,updated_by,updated_at
FROM review_tbl ORDER BY created_at DESC;

-- Inspect the previously verified three-profile result.
SELECT e.extract_id,e.filename,e.status,e.version,j.id AS job_id,j.status AS job_status,j.progress
FROM extract_tbl e LEFT JOIN job_tbl j ON j.extract_id=e.extract_id
WHERE e.extract_id='6efc597a-01e6-445a-9372-aa7e2578f686';

-- Display a Unix epoch audit timestamp in India time.
SELECT dataset_name,
       (FROM_TZ(TIMESTAMP '1970-01-01 00:00:00','UTC') + NUMTODSINTERVAL(created_at,'SECOND'))
       AT TIME ZONE 'Asia/Kolkata' AS created_time_india
FROM dataset_tbl;
