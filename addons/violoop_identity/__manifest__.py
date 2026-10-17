{
    "name": "Violoop Identity and Capability",
    "summary": "Named operator identity, capability grants and revocable sessions",
    "version": "20.0.1.0.0",
    "category": "Administration",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "violoop_facilities_api",
    ],
    "data": [
        "security/security.xml",
        "views/identity_views.xml",
        'security/ir.access.csv',
    ],
    "installable": True,
    "application": True,
}
