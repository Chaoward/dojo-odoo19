{
    "name": "Dojang Odoo 20 Interaction Core",
    "summary": "Normalized interaction timeline and narrow platform API",
    "version": "20.0.1.0.0",
    "category": "Dojang/Platform",
    "author": "Dojang",
    "license": "LGPL-3",
    "depends": ["base", "mail", "contacts", "portal"],
    "data": [
        "security/ir.access.csv",
        "views/interaction_event_views.xml",
        "views/external_entity_link_views.xml"
    ],
    "installable": True,
    "application": False
}
