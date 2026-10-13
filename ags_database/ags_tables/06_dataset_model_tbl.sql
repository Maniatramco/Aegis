-- Generated from ags_backend/ags_app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE dataset_model_tbl (
	dataset_id VARCHAR2(80 CHAR) NOT NULL,
	model_id VARCHAR2(80 CHAR) NOT NULL,
	category VARCHAR2(24 CHAR) NOT NULL,
	enabled BOOLEAN NOT NULL,
	is_default BOOLEAN NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (dataset_id, model_id, category),
	CONSTRAINT fk_dataset_model_category FOREIGN KEY(model_id, category) REFERENCES model_config_tbl (model_id, category),
	FOREIGN KEY(dataset_id) REFERENCES dataset_tbl (dataset_id) ON DELETE CASCADE,
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
