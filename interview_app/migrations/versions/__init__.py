from collections.abc import Callable
import sqlite3

from . import (
    v0001_initial_schema,
    v0002_add_suggested_answer,
    v0003_add_topic_color,
    v0004_add_subtopic,
    v0005_add_code_review,
    v0006_add_app_settings,
)

Migration = tuple[str, Callable[[sqlite3.Connection], None]]

MIGRATIONS: tuple[Migration, ...] = (
    (v0001_initial_schema.VERSION, v0001_initial_schema.apply),
    (v0002_add_suggested_answer.VERSION, v0002_add_suggested_answer.apply),
    (v0003_add_topic_color.VERSION, v0003_add_topic_color.apply),
    (v0004_add_subtopic.VERSION, v0004_add_subtopic.apply),
    (v0005_add_code_review.VERSION, v0005_add_code_review.apply),
    (v0006_add_app_settings.VERSION, v0006_add_app_settings.apply),
)
