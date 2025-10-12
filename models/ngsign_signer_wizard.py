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
        string='Contact', 
        required=True,
        domain="[('id', 'child_of', partner_id), ('type', '=', 'contact'), ('id', '!=', partner_id)]"
    )
    signer_email = fields.Char(string='Email', required=True)
    signer_phone = fields.Char(string='Phone')
    update_contact = fields.Boolean(
        string='Update contact information',
        default=False,
        help="If checked, the contact's email and phone will be updated with the values entered above"
    )

    @api.onchange('signer_id')
    def _onchange_signer_id(self):
        """Auto-fill email and phone when contact is selected."""
        if self.signer_id:
            self.signer_email = self.signer_id.email or ''
            self.signer_phone = self.signer_id.phone or ''
            # Auto-check update if email or phone is missing
            self.update_contact = not self.signer_id.email or not self.signer_id.phone
        else:
            self.signer_email = ''
            self.signer_phone = ''
            self.update_contact = False

    def action_confirm_signer(self):
        """Confirm signer selection and proceed with NGSIGN sending."""
        self.ensure_one()
        
        if not self.signer_id:
            raise UserError(_("Please select a contact."))
        
        if not self.signer_email:
            raise UserError(_("Email is required to send for signature."))
        
        # Update contact if checkbox is checked
        if self.update_contact:
            self.signer_id.write({
                'email': self.signer_email,
                'phone': self.signer_phone,
            })
        
        # Create a temporary partner-like dict with the signer info
        signer_info = {
            'id': self.signer_id.id,
            'name': self.signer_id.name,
            'email': self.signer_email,
            'phone': self.signer_phone or '',
        }
        
        # Call the send method with the signer info
        return self.sale_order_id.action_send_with_ngsign(signer_info=signer_info)