-- Generated from backend/app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE dataset_tbl (
	dataset_id VARCHAR2(80 CHAR) NOT NULL,
	owner_id VARCHAR2(80 CHAR) NOT NULL,
	dataset_name VARCHAR2(251 CHAR) NOT NULL,
	status VARCHAR2(32 CHAR) NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (dataset_id),
	FOREIGN KEY(dataset_id) REFERENCES aegis_items (id) ON DELETE CASCADE,
	FOREIGN KEY(owner_id) REFERENCES user_tbl (id),
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
CREATE INDEX ix_dataset_tbl_owner_id ON dataset_tbl (owner_id);
