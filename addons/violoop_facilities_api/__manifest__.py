{
    "name": "Violoop Facilities API",
    "summary": "Headless Odoo 20 facilities, kiosk, edge and spatial integration layer",
    "version": "20.0.1.0.0",
    "category": "Operations/Facilities",
    "license": "LGPL-3",
    "depends": ["base", "mail", "maintenance", "crm", "eb_gym_management"],
    "data": [
        "security/security.xml",
        "views/facility_views.xml",
        'security/ir.access.csv',
    ],
    "installable": True,
    "application": True,
}
