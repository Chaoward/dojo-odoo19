# -*- coding: utf-8 -*-
"""
Pre-migration for 19.0.1.2.0
Fix Diet menu groups: remove group_gym_trainer so only nutritionists (and managers) see it.
Fix Fitness menu groups: remove group_gym_nutritionist so only trainers (and managers) see it.
This runs before the XML data is loaded, clearing stale group links so the
updated gym_menus.xml writes the correct state from scratch.
"""


def migrate(cr, version):
    # Get the module id
    cr.execute("SELECT id FROM ir_module_module WHERE name = 'eb_gym_management'")
    row = cr.fetchone()
    if not row:
        return
    row[0]

    # Resolve group external IDs
    cr.execute(
        """
        SELECT d.name, g.id
        FROM ir_model_data d
        JOIN res_groups g ON g.id = d.res_id
        WHERE d.module = 'eb_gym_management'
          AND d.name IN (
              'group_gym_trainer',
              'group_gym_nutritionist',
              'group_gym_branch_manager',
              'group_gym_manager'
          )
          AND d.model = 'res.groups'
    """,
    )
    groups = {row[0]: row[1] for row in cr.fetchall()}

    trainer_gid = groups.get("group_gym_trainer")
    nutritionist_gid = groups.get("group_gym_nutritionist")

    if not trainer_gid or not nutritionist_gid:
        return

    # Resolve menu external IDs that need patching
    diet_menu_xmlids = [
        "menu_gym_nutrition",
        "menu_gym_diet_plan",
    ]
    fitness_menu_xmlids = [
        "menu_gym_fitness",
        "menu_gym_health_assessment",
        "menu_gym_workout_plan",
    ]
    staff_menu_xmlids = [
        "menu_gym_staff_root",
        "menu_gym_staff_employees",
        "menu_gym_staff_checkin_checkout",
        "menu_gym_staff_attendance",
    ]

    def get_menu_ids(xmlids):
        cr.execute(
            """
            SELECT res_id FROM ir_model_data
            WHERE module = 'eb_gym_management'
              AND model = 'ir.ui.menu'
              AND name = ANY(%s)
        """,
            (xmlids,),
        )
        return [r[0] for r in cr.fetchall()]

    diet_menu_ids = get_menu_ids(diet_menu_xmlids)
    fitness_menu_ids = get_menu_ids(fitness_menu_xmlids)
    staff_menu_ids = get_menu_ids(staff_menu_xmlids)

    # Remove trainer from Diet menus
    if diet_menu_ids and trainer_gid:
        cr.execute(
            """
            DELETE FROM ir_ui_menu_group_rel
            WHERE menu_id = ANY(%s) AND gid = %s
        """,
            (diet_menu_ids, trainer_gid),
        )

    # Remove nutritionist from Fitness menus
    if fitness_menu_ids and nutritionist_gid:
        cr.execute(
            """
            DELETE FROM ir_ui_menu_group_rel
            WHERE menu_id = ANY(%s) AND gid = %s
        """,
            (fitness_menu_ids, nutritionist_gid),
        )

    # Remove trainer and nutritionist from Staff menus
    if staff_menu_ids:
        for gid in filter(None, [trainer_gid, nutritionist_gid]):
            cr.execute(
                """
                DELETE FROM ir_ui_menu_group_rel
                WHERE menu_id = ANY(%s) AND gid = %s
            """,
                (staff_menu_ids, gid),
            )
