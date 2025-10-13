# -*- coding: utf-8 -*-
from odoo import models, fields, api

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
    ngsign_default_template_id = fields.Many2one(
        'ngsign.signature.template',
        string="Default Signature Template",
        domain=[('active', '=', True)],
        help="Default template to use when sending documents for signature"
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()
        template_id = params.get_param('ngsign_integration.default_template_id', default=False)
        res.update(
            ngsign_default_template_id=int(template_id) if template_id else False,
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('ngsign_integration.default_template_id', 
                        self.ngsign_default_template_id.id if self.ngsign_default_template_id else False)