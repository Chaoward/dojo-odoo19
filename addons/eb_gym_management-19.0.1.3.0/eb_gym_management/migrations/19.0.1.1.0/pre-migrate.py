# -*- coding: utf-8 -*-
"""
Migration: 19.0.1.0.0 -> 19.0.1.1.0
Replace gym.exercise.category Selection field with Many2one model.
Replace gym.food.category Selection field with Many2one model.
Creates categories from existing selection values and links records.
"""
import logging

_logger = logging.getLogger(__name__)

EXERCISE_CATEGORY_LABELS = {
    "cardio": "Cardio",
    "strength": "Strength",
    "flexibility": "Flexibility",
    "balance": "Balance",
}

FOOD_CATEGORY_LABELS = {
    "protein": "Protein",
    "carb": "Carbohydrate",
    "fat": "Fat",
    "vegetable": "Vegetable",
    "fruit": "Fruit",
    "dairy": "Dairy",
    "beverage": "Beverage",
}


def _migrate_selection_to_many2one(cr, table, category_table, old_col, new_col, labels):
    """Generic helper to migrate a Selection field to a Many2one."""
    cr.execute(
        f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = '{table}' AND column_name = '{old_col}'
    """,
    )
    if not cr.fetchone():
        _logger.info("Column %s.%s not found, skipping.", table, old_col)
        return

    cr.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {category_table} (
            id SERIAL PRIMARY KEY,
            name VARCHAR NOT NULL,
            description TEXT,
            active BOOLEAN DEFAULT TRUE,
            CONSTRAINT {category_table}_name_uniq UNIQUE (name)
        )
    """,
    )

    for key, label in labels.items():
        cr.execute(
            f"""
            INSERT INTO {category_table} (name, active)
            VALUES (%s, TRUE)
            ON CONFLICT (name) DO NOTHING
        """,
            (label,),
        )

    cr.execute(
        f"""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = '{table}' AND column_name = '{new_col}'
    """,
    )
    if not cr.fetchone():
        cr.execute(f"ALTER TABLE {table} ADD COLUMN {new_col} INTEGER")

    for key, label in labels.items():
        cr.execute(
            f"""
            UPDATE {table} t
            SET {new_col} = c.id
            FROM {category_table} c
            WHERE t.{old_col} = %s AND c.name = %s
        """,
            (key, label),
        )

    cr.execute(
        f"""
        UPDATE {table}
        SET {new_col} = (SELECT id FROM {category_table} LIMIT 1)
        WHERE {new_col} IS NULL
    """,
    )
    _logger.info("Migrated %s.%s -> %s.%s done.", table, old_col, table, new_col)


def migrate(cr, version):
    if not version:
        return

    _migrate_selection_to_many2one(
        cr,
        "gym_exercise",
        "gym_exercise_category",
        "category",
        "category_id",
        EXERCISE_CATEGORY_LABELS,
    )
    _migrate_selection_to_many2one(
        cr,
        "gym_food",
        "gym_food_category",
        "category",
        "category_id",
        FOOD_CATEGORY_LABELS,
    )
