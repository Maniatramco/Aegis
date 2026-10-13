set echo off
whenever sqlerror exit failure rollback
-- Connect as AGS_OWNER in FREEPDB1 before running. DDL commits in Oracle.
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
