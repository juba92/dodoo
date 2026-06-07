import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS ir_module (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(128) NOT NULL UNIQUE,
    version          VARCHAR(64),
    state            VARCHAR(32) NOT NULL DEFAULT 'uninstalled',
    installed_version VARCHAR(64),
    depends          TEXT,
    application      BOOLEAN NOT NULL DEFAULT FALSE,
    create_date      TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    write_date       TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

ALTER TABLE ir_module ADD COLUMN IF NOT EXISTS application BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS ir_model (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(128) NOT NULL UNIQUE,
    table_name  VARCHAR(128) NOT NULL UNIQUE,
    module_id   INTEGER REFERENCES ir_module(id) ON DELETE RESTRICT,
    description TEXT,
    create_date TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    write_date  TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ir_model_field (
    id             SERIAL PRIMARY KEY,
    model_id       INTEGER NOT NULL REFERENCES ir_model(id) ON DELETE CASCADE,
    name           VARCHAR(64) NOT NULL,
    field_type     VARCHAR(32) NOT NULL,
    string         VARCHAR(128),
    required       BOOLEAN DEFAULT FALSE,
    readonly       BOOLEAN DEFAULT FALSE,
    default_val    TEXT,
    relation       VARCHAR(128),
    relation_field VARCHAR(64),
    relation_table VARCHAR(128),
    create_date    TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    write_date     TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ir_session (
    id          SERIAL PRIMARY KEY,
    token       VARCHAR(64) NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL,
    create_date TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
    expire_date TIMESTAMP WITHOUT TIME ZONE NOT NULL
);
"""


async def bootstrap(ddl_conn: AsyncConnection) -> None:
    for statement in _DDL.split(";"):
        stmt = statement.strip()
        if stmt:
            await ddl_conn.execute(text(stmt))


async def sec005_check(dml_conn: AsyncConnection) -> None:
    # SEC-005: warn if DML user holds DDL-level (TRIGGER) privileges
    result = await dml_conn.execute(
        text("SELECT has_table_privilege(current_user, 'ir_module', 'TRIGGER')")
    )
    row = result.fetchone()
    if row and row[0]:
        _log.warning(
            "SEC-005: DATABASE_URL user holds DDL-level privileges; "
            "use a least-privilege credential in production"
        )
