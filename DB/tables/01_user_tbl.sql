-- Generated from backend/app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE user_tbl (
	id VARCHAR2(80 CHAR) NOT NULL,
	username VARCHAR2(120 CHAR) NOT NULL,
	password_hash CLOB NOT NULL,
	role VARCHAR2(20 CHAR) DEFAULT 'user' NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_user_role CHECK (role IN ('user', 'administrator')),
	UNIQUE (username),
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
