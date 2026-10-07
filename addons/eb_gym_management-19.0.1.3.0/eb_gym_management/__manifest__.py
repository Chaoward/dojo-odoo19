# -*- coding: utf-8 -*-
{
    "name": "Advanced Gym Management | Diet Management | Trainer & Workout | Membership",
    "author": "echoBitz IT Solutions Pvt. Ltd.",
    "maintainer": "echoBitz IT Solutions Pvt. Ltd.",
    "price": "86.61",
    "currency": "EUR",
    "version": "20.0",
    "category": "Industries/Health & Fitness",
    "live_test_url": "https://www.echobitzit.com/contactus",
    "website": "https://www.echobitzit.com",
    "license": "OPL-1",
    "summary": """
           Gym Management and Diet Management in one Odoo app. Automate member
           enrollment, health assessments, workout plans, diet plans, attendance
           tracking, and membership renewal & billing in real time via a
           dedicated member portal.
           Gym Management | Diet Management | Nutrition Management | Odoo Gym
           Management | Fitness Club Management | Membership Management |
           Member Portal | Workout Plan | Diet Plan | Attendance Tracking |
           Health Assessment | Renewal Automation | Membership Lifecycle |
           Trainer & Nutritionist Assignment | Gym Analytics Dashboard
       """,
    "description": """
           Odoo Gym Management System Pro | Diet Management | Real Time Fitness Club Automation
           =========================================================================
           Connect Odoo with your gym and diet management operations to automate
           member enrollment, health assessments, workout plan generation, diet
           plan generation, attendance tracking, membership renewal, and billing.

           Gym Management: memberships, trainers, workout plans, attendance,
           renewal automation and analytics dashboard.

           Diet Management: nutritionist assignment, diet plan generation,
           health assessments and nutrition tracking via the member portal.
       """,
    "sequence": -110,
    "depends": [
        "base",
        "mail",
        "contacts",
        "sale_management",
        "account",
        "hr",
        "hr_attendance",
        "calendar",
        "product",
        "portal",
    ],
    "data": [
        "security/gym_security.xml",
        "security/ir.model.access.csv",
        "data/gym_sequence_data.xml",
        "data/mail_template_data.xml",
        "data/ir_cron_data.xml",
        "wizard/gym_membership_hold_wizard_views.xml",
        "wizard/gym_membership_renew_wizard_views.xml",
        "wizard/gym_staff_attendance_wizard_views.xml",
        "views/res_config_settings_views.xml",
        "views/gym_membership_plan_views.xml",
        "views/gym_master_data_views.xml",
        "views/gym_workout_template_views.xml",
        "views/gym_diet_template_views.xml",
        "views/res_partner_views.xml",
        "views/res_users_views.xml",
        "views/hr_employee_views.xml",
        "views/calendar_event_views.xml",
        "views/gym_membership_views.xml",
        "views/gym_health_assessment_views.xml",
        "views/gym_workout_plan_views.xml",
        "views/gym_diet_plan_views.xml",
        "views/gym_attendance_views.xml",
        "views/gym_staff_attendance_views.xml",
        "views/gym_dashboard_views.xml",
        "views/portal_templates.xml",
        "views/gym_menus.xml",
        # "demo/gym_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "eb_gym_management/static/src/scss/gym_kanban.scss",
            "eb_gym_management/static/lib/echarts/echarts.min.js",
            "eb_gym_management/static/src/css/gym_dashboard.css",
            "eb_gym_management/static/src/js/gym_dashboard.js",
            "eb_gym_management/static/src/xml/gym_dashboard.xml",
            "eb_gym_management/static/src/scss/gym_staff_attendance.scss",
        ],
        "web.assets_frontend": [
            "eb_gym_management/static/src/interactions/gym_portal.js",
        ],
    },
    "images": ["static/description/banner.gif"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
