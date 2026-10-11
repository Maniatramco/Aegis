set echo off
whenever sqlerror exit failure rollback
-- Connect as AGS_OWNER in FREEPDB1 before running. DDL commits in Oracle.
@@tables/01_user_tbl.sql
@@tables/02_aegis_items.sql
@@tables/03_sessions_tbl.sql
@@tables/04_dataset_tbl.sql
@@tables/05_model_config_tbl.sql
@@tables/06_dataset_model_tbl.sql
@@tables/07_document_tbl.sql
@@tables/08_prompt_tbl.sql
@@tables/12_user_dataset_tbl.sql
@@tables/09_extract_tbl.sql
@@tables/10_job_tbl.sql
@@tables/11_review_tbl.sql
