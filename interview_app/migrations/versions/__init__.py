from collections.abc import Callable
import sqlite3

from . import (
    v0001_initial_schema,
    v0002_add_suggested_answer,
    v0003_add_topic_color,
)

Migration = tuple[str, Callable[[sqlite3.Connection], None]]

MIGRATIONS: tuple[Migration, ...] = (
    (v0001_initial_schema.VERSION, v0001_initial_schema.apply),
    (v0002_add_suggested_answer.VERSION, v0002_add_suggested_answer.apply),
    (v0003_add_topic_color.VERSION, v0003_add_topic_color.apply),
)
