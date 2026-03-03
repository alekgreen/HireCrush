def _sqlite_has_column(db, table: str, column: str) -> bool:
    cols = db.execute(f"PRAGMA table_info({table})").fetchall()
    names = {row["name"] for row in cols}
    return column in names


def ensure_column(db, table: str, column: str, definition: str) -> None:
    has_column_fn = getattr(db, "has_column", None)
    if callable(has_column_fn):
        exists = bool(has_column_fn(table, column))
    else:
        exists = _sqlite_has_column(db, table, column)
    if not exists:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
