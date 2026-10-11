-- Generated from backend/app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE extract_tbl (
	extract_id VARCHAR2(80 CHAR) NOT NULL,
	dataset_id VARCHAR2(80 CHAR) NOT NULL,
	document_id VARCHAR2(80 CHAR),
	prompt_id VARCHAR2(80 CHAR),
	owner_id VARCHAR2(80 CHAR) NOT NULL,
	prompt_version INTEGER NOT NULL,
	version INTEGER NOT NULL,
	result_reference VARCHAR2(501 CHAR) NOT NULL,
	status VARCHAR2(32 CHAR) NOT NULL,
	filename VARCHAR2(251 CHAR) NOT NULL,
	error_message VARCHAR2(501 CHAR) NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (extract_id),
	FOREIGN KEY(extract_id) REFERENCES aegis_items (id) ON DELETE CASCADE,
	FOREIGN KEY(dataset_id) REFERENCES dataset_tbl (dataset_id),
	FOREIGN KEY(document_id) REFERENCES document_tbl (document_id) ON DELETE SET NULL,
	FOREIGN KEY(prompt_id) REFERENCES prompt_tbl (prompt_id) ON DELETE SET NULL,
	FOREIGN KEY(owner_id) REFERENCES user_tbl (id),
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
CREATE INDEX ix_extract_tbl_dataset_id ON extract_tbl (dataset_id);
CREATE INDEX ix_extract_tbl_document_id ON extract_tbl (document_id);
CREATE INDEX ix_extract_tbl_owner_id ON extract_tbl (owner_id);
CREATE INDEX ix_extract_tbl_prompt_id ON extract_tbl (prompt_id);
