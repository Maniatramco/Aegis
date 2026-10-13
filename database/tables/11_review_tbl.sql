-- Generated from backend/app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE review_tbl (
	review_id VARCHAR2(80 CHAR) NOT NULL,
	extract_id VARCHAR2(80 CHAR) NOT NULL,
	extraction_version INTEGER NOT NULL,
	review_version INTEGER NOT NULL,
	reviewed_result_reference VARCHAR2(501 CHAR) NOT NULL,
	status VARCHAR2(32 CHAR) NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (review_id),
	CONSTRAINT uq_review_extract_version UNIQUE (extract_id, review_version),
	FOREIGN KEY(extract_id) REFERENCES extract_tbl (extract_id) ON DELETE CASCADE,
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
CREATE INDEX ix_review_tbl_extract_id ON review_tbl (extract_id);
