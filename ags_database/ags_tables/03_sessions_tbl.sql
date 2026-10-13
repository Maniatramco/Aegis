-- Generated from ags_backend/ags_app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE sessions_tbl (
	id VARCHAR2(100 CHAR) NOT NULL,
	owner VARCHAR2(80 CHAR) NOT NULL,
	expires BINARY_DOUBLE NOT NULL,
	csrf VARCHAR2(100 CHAR) NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(owner) REFERENCES user_tbl (id),
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
