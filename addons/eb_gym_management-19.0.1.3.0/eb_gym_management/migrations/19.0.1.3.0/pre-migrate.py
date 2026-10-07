# -*- coding: utf-8 -*-
"""
Migration 19.0.1.3.0

1. Drop stored gym-role boolean columns from res_users (now compute-only).
2. Drop stored gym-role boolean columns from hr_employee (now compute-only).
3. Add is_member column to res_partner if it doesn't exist (was never created
   because the module failed to install previously).
"""


def migrate(cr, version):
    # --- res_users: drop stored compute columns ---
    for col in (
        "is_gym_receptionist",
        "is_gym_trainer",
        "is_gym_nutritionist",
        "is_gym_branch_manager",
        "is_gym_administrator",
    ):
        cr.execute("ALTER TABLE res_users DROP COLUMN IF EXISTS %s" % col)

    # --- hr_employee: drop stored compute columns ---
    for col in ("is_receptionist", "is_trainer", "is_nutritionist", "is_branch_manager"):
        cr.execute("ALTER TABLE hr_employee DROP COLUMN IF EXISTS %s" % col)

    # --- res_partner: add is_member if missing ---
    cr.execute(
        """
        ALTER TABLE res_partner
        ADD COLUMN IF NOT EXISTS is_member boolean DEFAULT false
    """,
    )
