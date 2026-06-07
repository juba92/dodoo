from __future__ import annotations

from sqlalchemy import text

ACCOUNT_SEQUENCE_DDL = """
CREATE TABLE IF NOT EXISTS account_sequence (
    prefix  VARCHAR(32) NOT NULL,
    year    INTEGER     NOT NULL,
    last_no INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (prefix, year)
)
"""

_UPSERT = """
INSERT INTO account_sequence (prefix, year, last_no)
VALUES (:prefix, :year, 1)
ON CONFLICT (prefix, year)
DO UPDATE SET last_no = account_sequence.last_no + 1
RETURNING last_no
"""


async def get_next_sequence(conn, prefix: str, year: int) -> int:
    result = await conn.execute(text(_UPSERT), {"prefix": prefix, "year": year})
    return result.scalar_one()
