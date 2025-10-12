# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class NgsignSignerWizard(models.TransientModel):
    _name = 'ngsign.signer.wizard'
    _description = 'NGSIGN Signer Selection Wizard'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    partner_id = fields.Many2one('res.partner', string='Company', readonly=True)
    signer_id = fields.Many2one(
        'res.partner', 
        string='Signer', 
        required=True,
        domain="[('id', 'child_of', partner_id), ('type', '=', 'contact'), ('id', '!=', partner_id)]"
    )
    available_signers = fields.Many2many(
        'res.partner',
        compute='_compute_available_signers',
        string='Available Signers'
    )

    @api.depends('partner_id')
    def _compute_available_signers(self):
        for wizard in self:
            if wizard.partner_id:
                # Get all contacts of the company
                signers = self.env['res.partner'].search([
                    ('id', 'child_of', wizard.partner_id.id),
                    ('type', '=', 'contact'),
                    ('id', '!=', wizard.partner_id.id)
                ])
                wizard.available_signers = signers
            else:
                wizard.available_signers = False

    def action_confirm_signer(self):
        """Confirm signer selection and proceed with NGSIGN sending."""
        self.ensure_one()
        
        if not self.signer_id:
            raise UserError(_("Please select a signer."))
        
        # Call the send method with the selected signer
        return self.sale_order_id.action_send_with_ngsign(signer_partner=self.signer_id)