-- Read-only verification of the deployed OCI application schema.
-- Verified reference: agsora / ADMIN / agsora_low / 2026-10-15T18:24:27.101837+00:00.
-- Run in a fresh connection to the intended Oracle application owner.
SET TRANSACTION READ ONLY;

SELECT USER AS connected_owner,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;

WITH expected_tables AS (
  SELECT 'AEGIS_ITEMS' table_name, 16 expected_columns FROM dual
  UNION ALL
  SELECT 'AEGIS_KNOWLEDGE_VECTORS' table_name, 12 expected_columns FROM dual
  UNION ALL
  SELECT 'DATASET_MODEL_TBL' table_name, 11 expected_columns FROM dual
  UNION ALL
  SELECT 'DATASET_TBL' table_name, 10 expected_columns FROM dual
  UNION ALL
  SELECT 'DOCUMENT_TBL' table_name, 14 expected_columns FROM dual
  UNION ALL
  SELECT 'EXTRACT_TBL' table_name, 17 expected_columns FROM dual
  UNION ALL
  SELECT 'JOB_TBL' table_name, 18 expected_columns FROM dual
  UNION ALL
  SELECT 'MODEL_CONFIG_TBL' table_name, 14 expected_columns FROM dual
  UNION ALL
  SELECT 'PROMPT_TBL' table_name, 12 expected_columns FROM dual
  UNION ALL
  SELECT 'REVIEW_TBL' table_name, 12 expected_columns FROM dual
  UNION ALL
  SELECT 'SESSIONS_TBL' table_name, 10 expected_columns FROM dual
  UNION ALL
  SELECT 'USER_DATASET_TBL' table_name, 9 expected_columns FROM dual
  UNION ALL
  SELECT 'USER_TBL' table_name, 10 expected_columns FROM dual
), column_counts AS (
  SELECT table_name, COUNT(*) actual_columns
  FROM user_tab_columns GROUP BY table_name
)
SELECT e.table_name, e.expected_columns, NVL(c.actual_columns,0) actual_columns,
       CASE WHEN t.table_name IS NULL THEN 'MISSING'
            WHEN c.actual_columns <> e.expected_columns THEN 'COLUMN_COUNT_DIFFERS'
            ELSE 'PRESENT' END AS schema_status
FROM expected_tables e
LEFT JOIN user_tables t ON t.table_name=e.table_name
LEFT JOIN column_counts c ON c.table_name=e.table_name
ORDER BY e.table_name;

SELECT table_name, column_id, column_name, data_type, char_length, char_used,
       data_precision, data_scale, nullable, data_default
FROM user_tab_columns
WHERE table_name IN (
  'AEGIS_ITEMS',
  'AEGIS_KNOWLEDGE_VECTORS',
  'DATASET_MODEL_TBL',
  'DATASET_TBL',
  'DOCUMENT_TBL',
  'EXTRACT_TBL',
  'JOB_TBL',
  'MODEL_CONFIG_TBL',
  'PROMPT_TBL',
  'REVIEW_TBL',
  'SESSIONS_TBL',
  'USER_DATASET_TBL',
  'USER_TBL'
)
ORDER BY table_name,column_id;

SELECT table_name, constraint_type, status, COUNT(*) constraint_count
FROM user_constraints
WHERE table_name IN (
  'AEGIS_ITEMS',
  'AEGIS_KNOWLEDGE_VECTORS',
  'DATASET_MODEL_TBL',
  'DATASET_TBL',
  'DOCUMENT_TBL',
  'EXTRACT_TBL',
  'JOB_TBL',
  'MODEL_CONFIG_TBL',
  'PROMPT_TBL',
  'REVIEW_TBL',
  'SESSIONS_TBL',
  'USER_DATASET_TBL',
  'USER_TBL'
)
GROUP BY table_name,constraint_type,status
ORDER BY table_name,constraint_type,status;

SELECT table_name,index_name,uniqueness,index_type
FROM user_indexes
WHERE table_name IN (
  'AEGIS_ITEMS',
  'AEGIS_KNOWLEDGE_VECTORS',
  'DATASET_MODEL_TBL',
  'DATASET_TBL',
  'DOCUMENT_TBL',
  'EXTRACT_TBL',
  'JOB_TBL',
  'MODEL_CONFIG_TBL',
  'PROMPT_TBL',
  'REVIEW_TBL',
  'SESSIONS_TBL',
  'USER_DATASET_TBL',
  'USER_TBL'
)
ORDER BY table_name,index_name;

SELECT column_name,data_type
FROM user_tab_columns
WHERE table_name='AEGIS_KNOWLEDGE_VECTORS' AND column_name='EMBEDDING';

SELECT VECTOR_DISTANCE(TO_VECTOR('[1,0]'),TO_VECTOR('[1,0]'),COSINE) AS identical_vector_distance
FROM dual;

ROLLBACK;
