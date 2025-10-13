# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class NgsignSignatureTemplate(models.Model):
    _name = 'ngsign.signature.template'
    _description = 'NGSIGN Signature Template'
    _order = 'sequence, name'

    name = fields.Char(string='Template Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    
    # Signature position
    x_axis = fields.Integer(
        string='X Coordinate',
        required=True,
        default=100,
        help='Horizontal position of the signature on the page'
    )
    y_axis = fields.Integer(
        string='Y Coordinate',
        required=True,
        default=100,
        help='Vertical position of the signature on the page'
    )
    
    # Page selection
    page_type = fields.Selection([
        ('specific', 'Specific Page'),
        ('last', 'Last Page'),
    ], string='Page Type', required=True, default='last')
    
    page_number = fields.Integer(
        string='Page Number',
        default=1,
        help='Specific page number where the signature will be placed'
    )
    
    # Signature type
    signature_type = fields.Selection([
        ('CERTIFIED_TIMESTAMP', 'Simple'),
        ('DIGI_GO', 'DigiGO'),
        ('Later', 'Choose Later'),
    ], string='Signature Type', required=True, default='CERTIFIED_TIMESTAMP')
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    @api.constrains('page_number')
    def _check_page_number(self):
        """Validate page number is positive."""
        for template in self:
            if template.page_type == 'specific' and template.page_number < 1:
                raise ValidationError(_('Page number must be greater than 0.'))

    @api.constrains('x_axis', 'y_axis')
    def _check_coordinates(self):
        """Validate coordinates are non-negative."""
        for template in self:
            if template.x_axis < 0 or template.y_axis < 0:
                raise ValidationError(_('Coordinates must be non-negative values.'))

    def get_page_number(self, total_pages):
        """
        Get the actual page number based on template configuration.
        
        :param total_pages: Total number of pages in the document
        :return: Page number to place signature
        """
        self.ensure_one()
        if self.page_type == 'last':
            return total_pages
        else:
            return min(self.page_number, total_pages)  # Don't exceed total pages