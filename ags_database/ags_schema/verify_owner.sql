SELECT USER AS connected_owner, SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name FROM dual;
SELECT table_name FROM user_tables ORDER BY table_name;
SELECT COUNT(*) AS application_table_count FROM user_tables;
