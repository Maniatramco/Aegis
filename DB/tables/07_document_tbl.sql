-- Generated from backend/app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE document_tbl (
	document_id VARCHAR2(80 CHAR) NOT NULL,
	dataset_id VARCHAR2(80 CHAR) NOT NULL,
	owner_id VARCHAR2(80 CHAR) NOT NULL,
	filename VARCHAR2(251 CHAR) NOT NULL,
	is_merged BOOLEAN NOT NULL,
	storage_reference VARCHAR2(501 CHAR) NOT NULL,
	status VARCHAR2(32 CHAR) NOT NULL,
	size_bytes INTEGER NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (document_id),
	FOREIGN KEY(document_id) REFERENCES aegis_items (id) ON DELETE CASCADE,
	FOREIGN KEY(dataset_id) REFERENCES dataset_tbl (dataset_id),
	FOREIGN KEY(owner_id) REFERENCES user_tbl (id),
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
CREATE INDEX ix_document_tbl_dataset_id ON document_tbl (dataset_id);
CREATE INDEX ix_document_tbl_owner_id ON document_tbl (owner_id);
