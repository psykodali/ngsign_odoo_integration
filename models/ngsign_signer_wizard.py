# -*- coding: utf-8 -*-
import re
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
    
    # Signature template
    template_id = fields.Many2one(
        'ngsign.signature.template',
        string='Signature Template',
        required=True,
        domain=[('active', '=', True)]
    )
    
    # Previous signature info
    has_previous_signature = fields.Boolean(
        string='Has Previous Signature',
        compute='_compute_previous_signature'
    )
    previous_signature_email = fields.Char(
        string='Previously Sent To',
        compute='_compute_previous_signature'
    )
    previous_signature_date = fields.Char(
        string='Previous Send Date',
        compute='_compute_previous_signature'
    )

    @api.model
    def default_get(self, fields_list):
        """Set default template when wizard opens."""
        res = super().default_get(fields_list)
        
        if 'template_id' in fields_list and not res.get('template_id'):
            # Find template marked as default
            default_template = self.env['ngsign.signature.template'].search([
                ('is_default', '=', True),
                ('active', '=', True),
                ('company_id', 'in', [self.env.company.id, False])
            ], limit=1)
            
            # If no default found, use first active template
            if not default_template:
                default_template = self.env['ngsign.signature.template'].search([
                    ('active', '=', True)
                ], limit=1)
            
            if default_template:
                res['template_id'] = default_template.id
        
        return res

    @api.depends('sale_order_id')
    def _compute_previous_signature(self):
        """Check if this order was already sent for signature."""
        for wizard in self:
            if wizard.sale_order_id and wizard.sale_order_id.ngsign_transaction_uuid:
                wizard.has_previous_signature = True
                # Try to extract email from chatter messages
                messages = wizard.sale_order_id.message_ids.filtered(
                    lambda m: 'Document sent to' in (m.body or '')
                )
                if messages:
                    # Get the most recent message
                    last_message = messages[0]
                    # Extract email from message body
                    email_pattern = r'\(([^)]+@[^)]+)\)'
                    match = re.search(email_pattern, last_message.body)
                    wizard.previous_signature_email = match.group(1) if match else 'Unknown'
                    wizard.previous_signature_date = last_message.create_date.strftime('%Y-%m-%d %H:%M') if last_message.create_date else ''
                else:
                    wizard.previous_signature_email = 'Unknown'
                    wizard.previous_signature_date = ''
            else:
                wizard.has_previous_signature = False
                wizard.previous_signature_email = ''
                wizard.previous_signature_date = ''

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
            
        if not self.template_id:
            raise UserError(_("Please select a signature template."))
        
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
        
        return self.sale_order_id.action_send_with_ngsign(
            signer_info=signer_info, 
            template_id=self.template_id.id
        )