-- Generated from backend/app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE job_tbl (
	id VARCHAR2(80 CHAR) NOT NULL,
	owner VARCHAR2(80 CHAR) NOT NULL,
	kind VARCHAR2(32 CHAR) NOT NULL,
	target_id VARCHAR2(80 CHAR) NOT NULL,
	document_id VARCHAR2(80 CHAR),
	extract_id VARCHAR2(80 CHAR),
	status VARCHAR2(32 CHAR) NOT NULL,
	progress INTEGER NOT NULL,
	attempts INTEGER NOT NULL,
	lease_until BINARY_DOUBLE NOT NULL,
	lease_token VARCHAR2(81 CHAR) NOT NULL,
	error VARCHAR2(501 CHAR) NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(owner) REFERENCES user_tbl (id),
	FOREIGN KEY(document_id) REFERENCES document_tbl (document_id) ON DELETE SET NULL,
	FOREIGN KEY(extract_id) REFERENCES extract_tbl (extract_id) ON DELETE SET NULL,
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id),
	CONSTRAINT ck_job_single_target CHECK (document_id IS NULL OR extract_id IS NULL)
);
CREATE INDEX ix_job_tbl_document_id ON job_tbl (document_id);
CREATE INDEX ix_job_tbl_extract_id ON job_tbl (extract_id);
CREATE INDEX ix_job_tbl_owner ON job_tbl (owner);
CREATE INDEX ix_job_tbl_status ON job_tbl (status);
CREATE INDEX ix_job_tbl_target_id ON job_tbl (target_id);
