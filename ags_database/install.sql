-- OCI Autonomous Database application schema reference, verified against live agsora (ADMIN).
-- Connect to a separate, empty, prepared Oracle application schema using its own wallet/credentials.
-- Existing live schema: use ags_schema/verify_live_schema.sql only. Oracle DDL commits implicitly.
set echo off
whenever sqlerror exit failure rollback
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
