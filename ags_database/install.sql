-- Fresh schema installer for a separate OCI Autonomous AI Database destination.
-- Start SQLcl / SQL*Plus in ags_database, then connect to the NEW owner and run:
-- @install.sql EXPECTED_OWNER EXPECTED_FULL_SERVICE_NAME
-- Use the server SERVICE_NAME from SYS_CONTEXT, not the wallet's TNS alias.
-- Existing installations: use ags_schema/verify_live_schema.sql instead.
-- Oracle DDL commits implicitly. This installer never drops or upgrades objects.
SET ECHO OFF
SET VERIFY OFF
SET DEFINE ON
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT FAILURE ROLLBACK

DEFINE aegis_expected_owner = "&1"
DEFINE aegis_expected_service = "&2"

-- Keep the entire preflight here: no table script runs before these checks pass.
DECLARE
  expected_owner VARCHAR2(128) := UPPER('&&aegis_expected_owner');
  expected_service VARCHAR2(512) := LOWER('&&aegis_expected_service');
  object_count PLS_INTEGER;
  privilege_count PLS_INTEGER;
  quota_count PLS_INTEGER;
  default_space VARCHAR2(128);
  probe NUMBER;
BEGIN
  IF NOT REGEXP_LIKE(expected_owner, '^[A-Z][A-Z0-9_$#]{0,127}$')
     OR NOT REGEXP_LIKE(expected_service, '^[a-z0-9_.-]+$') THEN
    RAISE_APPLICATION_ERROR(-20001, 'Supply an unquoted expected owner and full server service name.');
  END IF;
  IF USER IN ('SYS', 'SYSTEM') OR USER <> expected_owner
     OR SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') <> expected_owner THEN
    RAISE_APPLICATION_ERROR(-20002, 'Wrong owner/current schema. Reconnect directly as the intended application owner.');
  END IF;
  IF LOWER(SYS_CONTEXT('USERENV', 'SERVICE_NAME')) <> expected_service THEN
    RAISE_APPLICATION_ERROR(-20003, 'Wrong database service. Check the destination wallet and connection.');
  END IF;
  SELECT COUNT(*) INTO object_count FROM user_objects;
  IF object_count <> 0 THEN
    RAISE_APPLICATION_ERROR(-20004, 'Destination schema is not empty. No installation or upgrade was attempted.');
  END IF;
  SELECT COUNT(*) INTO privilege_count FROM session_privs WHERE privilege = 'CREATE TABLE';
  IF privilege_count = 0 THEN
    RAISE_APPLICATION_ERROR(-20005, 'Destination owner needs CREATE TABLE privilege.');
  END IF;
  SELECT default_tablespace INTO default_space FROM user_users;
  SELECT COUNT(*) INTO quota_count FROM user_ts_quotas
    WHERE tablespace_name = default_space AND (max_bytes = -1 OR max_bytes > bytes);
  SELECT COUNT(*) INTO privilege_count FROM session_privs WHERE privilege = 'UNLIMITED TABLESPACE';
  IF quota_count = 0 AND privilege_count = 0 THEN
    RAISE_APPLICATION_ERROR(-20006, 'Destination owner needs available quota on its default tablespace.');
  END IF;
  BEGIN
    EXECUTE IMMEDIATE 'SELECT LENGTH(CAST(''x'' AS VARCHAR2(32767 BYTE))) FROM dual' INTO probe;
  EXCEPTION WHEN OTHERS THEN
    RAISE_APPLICATION_ERROR(-20007, 'Data-bound collations require MAX_STRING_SIZE=EXTENDED. Ask the destination DBA; this installer does not change it.');
  END;
  BEGIN
    EXECUTE IMMEDIATE 'SELECT CASE WHEN CAST(TRUE AS BOOLEAN) THEN 1 ELSE 0 END FROM dual' INTO probe;
    IF probe <> 1 THEN RAISE_APPLICATION_ERROR(-20008, 'SQL BOOLEAN probe failed.'); END IF;
    EXECUTE IMMEDIATE 'SELECT VECTOR_DISTANCE(TO_VECTOR(''[1,0]''), TO_VECTOR(''[1,0]''), COSINE) FROM dual' INTO probe;
    IF probe <> 0 THEN RAISE_APPLICATION_ERROR(-20009, 'Native VECTOR probe failed.'); END IF;
  EXCEPTION WHEN OTHERS THEN
    RAISE_APPLICATION_ERROR(-20010, 'Destination must support SQL BOOLEAN and native VECTOR: ' || SUBSTR(SQLERRM, 1, 300));
  END;
  DBMS_OUTPUT.PUT_LINE('Preflight passed: owner=' || USER || ', service=' || expected_service);
END;
/

@@ags_tables/01_user_tbl.sql
@@ags_tables/02_aegis_items.sql
@@ags_tables/03_sessions_tbl.sql
@@ags_tables/04_dataset_tbl.sql
@@ags_tables/05_model_config_tbl.sql
@@ags_tables/06_dataset_model_tbl.sql
@@ags_tables/07_document_tbl.sql
@@ags_tables/08_prompt_tbl.sql
@@ags_tables/12_user_dataset_tbl.sql
@@ags_tables/09_extract_tbl.sql
@@ags_tables/10_job_tbl.sql
@@ags_tables/11_review_tbl.sql
@@ags_tables/13_aegis_knowledge_vectors.sql

-- Missing include files and partial DDL must not be reported as a successful install.
DECLARE
  actual_count PLS_INTEGER;
  mismatches PLS_INTEGER;
  PROCEDURE require_count(actual PLS_INTEGER, expected PLS_INTEGER, label VARCHAR2) IS
  BEGIN
    IF actual <> expected THEN
      RAISE_APPLICATION_ERROR(-20020, label || ': expected ' || expected || ', found ' || actual || '. Inspect this destination; DDL is already committed.');
    END IF;
  END;
BEGIN
  SELECT COUNT(*) INTO actual_count FROM user_tables;
  require_count(actual_count, 13, 'Application tables');
  WITH expected AS (
    SELECT 'USER_TBL' name, 10 cols FROM dual UNION ALL
    SELECT 'AEGIS_ITEMS', 16 FROM dual UNION ALL
    SELECT 'SESSIONS_TBL', 10 FROM dual UNION ALL
    SELECT 'DATASET_TBL', 10 FROM dual UNION ALL
    SELECT 'MODEL_CONFIG_TBL', 14 FROM dual UNION ALL
    SELECT 'DATASET_MODEL_TBL', 11 FROM dual UNION ALL
    SELECT 'DOCUMENT_TBL', 14 FROM dual UNION ALL
    SELECT 'PROMPT_TBL', 12 FROM dual UNION ALL
    SELECT 'USER_DATASET_TBL', 9 FROM dual UNION ALL
    SELECT 'EXTRACT_TBL', 17 FROM dual UNION ALL
    SELECT 'JOB_TBL', 18 FROM dual UNION ALL
    SELECT 'REVIEW_TBL', 12 FROM dual UNION ALL
    SELECT 'AEGIS_KNOWLEDGE_VECTORS', 12 FROM dual
  ), actual AS (
    SELECT table_name, COUNT(*) cols FROM user_tab_columns GROUP BY table_name
  )
  SELECT COUNT(*) INTO mismatches FROM expected e LEFT JOIN actual a ON a.table_name = e.name
    WHERE NVL(a.cols, 0) <> e.cols;
  require_count(mismatches, 0, 'Table column mismatches');
  SELECT COUNT(*) INTO actual_count FROM user_constraints WHERE constraint_type = 'P';
  require_count(actual_count, 13, 'Primary keys');
  SELECT COUNT(*) INTO actual_count FROM user_constraints WHERE constraint_type = 'U';
  require_count(actual_count, 2, 'Unique constraints');
  SELECT COUNT(*) INTO actual_count FROM user_constraints WHERE constraint_type = 'R';
  require_count(actual_count, 49, 'Foreign keys');
  SELECT COUNT(*) INTO actual_count FROM user_constraints WHERE constraint_type = 'C';
  require_count(actual_count, 131, 'Check and NOT NULL constraints');
  SELECT COUNT(*) INTO actual_count FROM user_constraints
    WHERE status <> 'ENABLED' OR validated <> 'VALIDATED';
  require_count(actual_count, 0, 'Disabled or unvalidated constraints');
  SELECT COUNT(*) INTO actual_count FROM user_indexes
    WHERE index_name LIKE 'IX\_%' ESCAPE '\' AND index_type = 'NORMAL' AND status = 'VALID';
  require_count(actual_count, 20, 'Application indexes');
  SELECT COUNT(*) INTO actual_count FROM user_tab_columns
    WHERE table_name = 'AEGIS_KNOWLEDGE_VECTORS' AND column_name = 'EMBEDDING' AND data_type = 'VECTOR';
  require_count(actual_count, 1, 'Native vector column');
  SELECT COUNT(*) INTO actual_count FROM user_objects WHERE status <> 'VALID';
  require_count(actual_count, 0, 'Invalid objects');
  DBMS_OUTPUT.PUT_LINE('AEGIS_SCHEMA_INSTALL_OK: 13 tables, 165 columns, 49 foreign keys, 20 application indexes.');
  DBMS_OUTPUT.PUT_LINE('Schema only. Configure destination application state, wallet, storage and model registrations separately.');
END;
/

UNDEFINE aegis_expected_owner
UNDEFINE aegis_expected_service
UNDEFINE 1
UNDEFINE 2
EXIT SUCCESS
