-- Generated from backend/app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE user_dataset_tbl (
	user_id VARCHAR2(80 CHAR) NOT NULL,
	dataset_id VARCHAR2(80 CHAR) NOT NULL,
	enabled BOOLEAN NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (user_id, dataset_id),
	FOREIGN KEY(user_id) REFERENCES user_tbl (id) ON DELETE CASCADE,
	FOREIGN KEY(dataset_id) REFERENCES dataset_tbl (dataset_id) ON DELETE CASCADE,
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
