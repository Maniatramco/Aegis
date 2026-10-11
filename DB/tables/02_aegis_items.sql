-- Generated from backend/app/core.py and relational.py. Run as AGS_OWNER on an empty schema.
CREATE TABLE aegis_items (
	id VARCHAR2(80 CHAR) NOT NULL,
	kind VARCHAR2(32 CHAR) NOT NULL,
	owner VARCHAR2(80 CHAR) NOT NULL,
	name VARCHAR2(251 CHAR) NOT NULL,
	status VARCHAR2(32 CHAR) NOT NULL,
	ref VARCHAR2(501 CHAR) NOT NULL,
	parent_id VARCHAR2(81 CHAR) NOT NULL,
	created_at BINARY_DOUBLE NOT NULL,
	updated_at BINARY_DOUBLE NOT NULL,
	"size" INTEGER NOT NULL,
	version INTEGER NOT NULL,
	error VARCHAR2(501 CHAR) NOT NULL,
	created_by VARCHAR2(80 CHAR),
	updated_by VARCHAR2(80 CHAR),
	created_via VARCHAR2(24 CHAR) NOT NULL,
	updated_via VARCHAR2(24 CHAR) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(owner) REFERENCES user_tbl (id),
	FOREIGN KEY(created_by) REFERENCES user_tbl (id),
	FOREIGN KEY(updated_by) REFERENCES user_tbl (id)
);
CREATE INDEX ix_aegis_items_kind ON aegis_items (kind);
CREATE INDEX ix_aegis_items_owner ON aegis_items (owner);
CREATE INDEX ix_aegis_items_parent_id ON aegis_items (parent_id);
