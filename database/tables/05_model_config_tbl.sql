-- Generated from backend/app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE model_config_tbl (
	model_id VARCHAR2(80 CHAR) NOT NULL,
	category VARCHAR2(24 CHAR) NOT NULL,
	owner_id VARCHAR2(80 CHAR) NOT NULL,
	model_name VARCHAR2(251 CHAR) NOT NULL,
	provider_model VARCHAR2(251 CHAR) NOT NULL,
	config_reference VARCHAR2(501 CHAR) NOT NULL,
	version INTEGER NOT NULL,
	enabled BOOLEAN NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (model_id, category),
	CONSTRAINT ck_model_category CHECK (category IN ('chat','extraction','embedding')),
	FOREIGN KEY(model_id) REFERENCES aegis_items (id) ON DELETE CASCADE,
	FOREIGN KEY(owner_id) REFERENCES user_tbl (id),
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
CREATE INDEX ix_model_config_tbl_owner_id ON model_config_tbl (owner_id);
