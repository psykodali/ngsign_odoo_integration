# -*- coding: utf-8 -*-
{
    "name": "NGSIGN Integration V4",
    "version": "19.0.1.0.0",
    "summary": "Send Quotation for signature with NGSIGN.",
    "author": "NGSign",
    "website": "https://www.ngsign.tn",
    "license": "LGPL-3",
    "category": "Sign",
    "depends": ["base", "mail", "sale"],
    "data": [
        "views/ngsign_sale_order_views.xml",
        "views/ngsign_res_config_settings_views.xml",
    ],
    "application": True,
    "installable": True,
}