import sqlite3


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = db.execute(f"PRAGMA table_info({table})").fetchall()
    names = {row["name"] for row in cols}
    if column not in names:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

