# -*- coding: utf-8 -*-
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ngsign_url = fields.Char(
        string="NGSIGN API URL",
        config_parameter='ngsign_integration.api_url'
    )
    ngsign_bearer_token = fields.Char(
        string="NGSIGN Bearer Token",
        config_parameter='ngsign_integration.bearer_token'
    )