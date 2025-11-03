# -*- coding: utf-8 -*-
import base64
import io
import json
import requests
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None
    _logger.warning("PyPDF2 library is not installed. NGSIGN integration will not work.")

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    ngsign_transaction_uuid = fields.Char(string='NGSIGN Transaction UUID', readonly=True, copy=False)
    ngsign_signature_url = fields.Char(string='NGSIGN Signature URL', readonly=True, copy=False)
    ngsign_signature_status = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent for Signature'),
        ('signed', 'Signed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Signature Status', readonly=True, copy=False, default='draft')
    ngsign_signed_document_id = fields.Many2one(
        'ir.attachment',
        string='Signed Document',
        readonly=True,
        copy=False,
        help='The signed PDF document downloaded from NGSIGN'
    )

    def _get_api_credentials(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        base_url = get_param('ngsign_integration.api_url')
        bearer_token = get_param('ngsign_integration.bearer_token')
        
        _logger.info(f"API URL configured: {bool(base_url)}")
        _logger.info(f"Bearer token configured: {bool(bearer_token)}")
        
        if not base_url or not bearer_token:
            raise UserError(_('NGSIGN API URL and Bearer Token must be configured in settings.'))
        
        # Remove trailing slash if present
        base_url = base_url.rstrip('/')
        
        return base_url, bearer_token

    def _get_transaction_api_url(self, base_url):
        """Build the transaction API URL."""
        return f"{base_url}/server/protected/transaction"
    
    def _get_public_api_url(self, base_url):
        """Build the public API URL (no auth required)."""
        return f"{base_url}/server/any/transaction"

    def action_send_with_ngsign(self, signer_info=None, template_id=None):
        self.ensure_one()
        
        _logger.info(f"action_send_with_ngsign called for SO: {self.name}")
        _logger.info(f"Signer info received: {bool(signer_info)}")
        _logger.info(f"Template ID received: {template_id}")

        if not signer_info:
            _logger.info("No signer info, opening wizard")
            return {
                'name': _('Select Signer and Signature Template'),
                'type': 'ir.actions.act_window',
                'res_model': 'ngsign.signer.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_sale_order_id': self.id,
                    'default_partner_id': self.partner_id.id,
                }
            }

        # Validation
        if not signer_info.get('email'):
            raise UserError(_("Signer email is required to send the document for signature."))
        if not signer_info.get('name'):
            raise UserError(_("Signer name is required to send the document for signature."))
        if not template_id:
            raise UserError(_("A signature template must be selected to proceed."))
        if not PyPDF2:
            raise UserError(_("The required library PyPDF2 is not installed. Please install it by running 'pip install PyPDF2'."))

        _logger.info(f"Loading template ID: {template_id}")
        template = self.env['ngsign.signature.template'].browse(template_id)
        if not template.exists():
             raise UserError(_("The selected signature template (ID: %s) could not be found.") % template_id)

        _logger.info(f"Template loaded: {template.name}")

        # --- PDF Generation ---
        try:
            _logger.info("Attempting to generate PDF for sale order")
            
            # Use the simpler _render method which handles everything
            report = self.env['ir.actions.report']._get_report_from_name('sale.report_saleorder')
            
            if not report:
                _logger.warning("Standard report not found via report_name, trying by external ID")
                report = self.env.ref('sale.action_report_saleorder', raise_if_not_found=False)
            
            if not report or not report.exists():
                _logger.warning("Standard report still not found, searching for any sale.order PDF report")
                report = self.env['ir.actions.report'].search([
                    ('model', '=', 'sale.order'),
                    ('report_type', '=', 'qweb-pdf')
                ], limit=1)

            if not report or not report.exists():
                raise UserError(_("Could not find a valid PDF report for Sales Orders. Please check your report configuration."))

            _logger.info(f"Using report: {report.name} (ID: {report.id})")
            
            # Use _render_qweb_pdf with proper signature: (report_ref, res_ids)
            # Pass the report's xml_id or report_name as report_ref
            pdf_content, __ = report._render_qweb_pdf(report.report_name, res_ids=[self.id])
            
            if not pdf_content:
                raise UserError(_("Odoo failed to generate the quotation PDF. Please check your report configuration."))
                
            _logger.info(f"PDF generated successfully, size: {len(pdf_content)} bytes")

        except Exception as e:
            _logger.error(f"PDF generation failed: {str(e)}", exc_info=True)
            raise UserError(_("Failed to generate PDF: %s") % str(e))

        # Determine page to sign
        page_to_sign = 0
        try:
            if template.page_type == 'last':
                pdf_stream = io.BytesIO(pdf_content)
                reader = PyPDF2.PdfReader(pdf_stream)
                page_to_sign = len(reader.pages)
                _logger.info(f"PDF has {page_to_sign} pages, will sign last page")
            else:
                page_to_sign = template.page_number
                _logger.info(f"Will sign specific page: {page_to_sign}")
                if page_to_sign <= 0:
                    raise UserError(_("The template specifies an invalid page number: %s.") % page_to_sign)
        except Exception as e:
            _logger.error(f"Page determination failed: {str(e)}", exc_info=True)
            raise UserError(_("Could not determine the page for the signature: %s") % str(e))
        
        if page_to_sign == 0:
            raise UserError(_("Could not determine the page for the signature based on the template settings."))

        # Parse signer name
        name_parts = signer_info.get('name').split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        _logger.info(f"Signer: {first_name} {last_name} ({signer_info.get('email')})")
        
        api_url, bearer_token = self._get_api_credentials()
        api_url = self._get_transaction_api_url(api_url)
        headers = {'Authorization': f'Bearer {bearer_token}', 'Content-Type': 'application/json'}
        file_name = f"{self.name}"

        try:
            # Upload PDF
            _logger.info("Uploading PDF to NGSIGN")
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            upload_payload = [{"fileName": file_name, "fileExtension": "pdf", "fileBase64": pdf_base64}]
            
            upload_response = requests.post(f"{api_url}/pdfs", headers=headers, data=json.dumps(upload_payload), timeout=30)
            upload_response.raise_for_status()
            upload_data = upload_response.json()
            
            _logger.info(f"PDF uploaded successfully")
            
            transaction_uuid = upload_data['object']['uuid']
            pdf_identifier = upload_data['object']['pdfs'][0]['identifier']
            
            _logger.info(f"Transaction UUID: {transaction_uuid}")
            
            # Launch signature
            launch_payload = {
                "sigConf": [{
                    "signer": {
                        "firstName": first_name,
                        "lastName": last_name,
                        "email": signer_info.get('email'),
                        "phoneNumber": signer_info.get('phone') or '',
                    },
                    "sigType": template.signature_type,
                    "docsConfigs": [{
                        "page": page_to_sign,
                        "xAxis": template.x_axis,
                        "yAxis": template.y_axis,
                        "identifier": pdf_identifier
                    }],
                    "mode": "BY_MAIL",
                    "otp": template.otp
                }],
                "message": f"Signature request for your quotation {self.name}"
            }
            
            _logger.info("Launching signature request")
            launch_response = requests.post(f"{api_url}/{transaction_uuid}/launch", headers=headers, data=json.dumps(launch_payload), timeout=30)
            launch_response.raise_for_status()
            launch_data = launch_response.json()
            
            _logger.info("Signature request launched successfully")
            
            signature_url = None
            if launch_data.get('object', {}).get('signers'):
                first_signer_data = launch_data['object']['signers'][0]
                signature_url = first_signer_data.get('signatureUrl') or first_signer_data.get('url')

            self.write({'ngsign_transaction_uuid': transaction_uuid, 'ngsign_signature_url': signature_url, 'ngsign_signature_status': 'sent'})
            
            message_body = _('Document sent to <b>%s</b> (%s) for signature via NGSIGN.') % (signer_info.get('name'), signer_info.get('email'))
            self.message_post(body=message_body)

            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Sent via NGSIGN'),
                note=_('The document "%s" has been sent to %s for signature. You can follow the process via the NGSIGN platform.') % (self.name, signer_info.get('email')),
                user_id=self.user_id.id or self.env.uid,
            )
            
            _logger.info("Process completed successfully")

        except requests.exceptions.HTTPError as e:
            _logger.error(f"HTTP Error: {e.response.status_code}", exc_info=True)
            response_body = e.response.text
            try:
                response_body = json.dumps(e.response.json(), indent=2)
            except json.JSONDecodeError:
                pass
            error_msg = _("API Error: %(status_code)s\nResponse:\n%(response_body)s") % {'status_code': e.response.status_code, 'response_body': response_body}
            raise UserError(_('Failed to send document to NGSIGN.\n\n%s') % error_msg)

        except requests.exceptions.RequestException as e:
            _logger.error(f"Request Exception: {str(e)}", exc_info=True)
            error_msg = str(e)
            raise UserError(_('Failed to send document to NGSIGN: %s') % error_msg)

        except Exception as e:
            _logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            raise UserError(_('An unexpected error occurred: %s') % str(e))

        return True

    def action_check_signature_status(self):
        """Manually check signature status and download signed document if available."""
        self.ensure_one()
        
        if not self.ngsign_transaction_uuid:
            raise UserError(_('No signature transaction found for this order.'))
        
        return self._check_and_download_signed_document()

    def _check_and_download_signed_document(self):
        """Check if document is signed and download it."""
        self.ensure_one()
        
        if not self.ngsign_transaction_uuid:
            return False
        
        # If already downloaded, skip
        if self.ngsign_signed_document_id:
            _logger.info(f"Signed document already downloaded for SO: {self.name}")
            return True
        
        try:
            base_url, bearer_token = self._get_api_credentials()
            public_api_url = self._get_public_api_url(base_url)
            
            # Check transaction status (public endpoint, no auth needed)
            status_url = f"{public_api_url}/{self.ngsign_transaction_uuid}"
            _logger.info(f"Checking signature status at: {status_url}")
            
            status_response = requests.get(status_url, timeout=30)
            status_response.raise_for_status()
            status_data = status_response.json()
            
            if status_data.get('errorCode', 0) != 0:
                _logger.warning(f"Error checking status: {status_data.get('message')}")
                return False
            
            transaction_status = status_data.get('object', {}).get('status')
            _logger.info(f"Transaction status: {transaction_status}")
            
            # Update status field
            status_mapping = {
                'CONFIGURED': 'sent',
                'SIGNED': 'signed',
                'EXPIRED': 'expired',
                'CANCELLED': 'cancelled',
            }
            
            new_status = status_mapping.get(transaction_status, 'sent')
            if self.ngsign_signature_status != new_status:
                self.ngsign_signature_status = new_status
                _logger.info(f"Updated signature status to: {new_status}")
            
            # If signed, download the document
            if transaction_status == 'SIGNED':
                pdfs = status_data.get('object', {}).get('pdfs', [])
                if not pdfs:
                    _logger.warning("No PDFs found in signed transaction")
                    return False
                
                # Get the first PDF identifier
                document_uuid = pdfs[0].get('identifier')
                document_name = pdfs[0].get('name', self.name)
                
                if not document_uuid:
                    _logger.warning("No document identifier found")
                    return False
                
                # Download the signed document (public endpoint, no auth)
                download_url = f"{public_api_url}/{self.ngsign_transaction_uuid}/pdfs/{document_uuid}"
                _logger.info(f"Downloading signed document from: {download_url}")
                
                download_response = requests.get(download_url, timeout=60)
                download_response.raise_for_status()
                
                # Create attachment
                attachment = self.env['ir.attachment'].create({
                    'name': f'{document_name}_signed.pdf',
                    'type': 'binary',
                    'datas': base64.b64encode(download_response.content).decode('utf-8'),
                    'res_model': 'sale.order',
                    'res_id': self.id,
                    'mimetype': 'application/pdf',
                })
                
                self.ngsign_signed_document_id = attachment.id
                
                # Post message in chatter
                self.message_post(
                    body=_('✅ Signed document has been downloaded and attached.'),
                    attachment_ids=[attachment.id]
                )

                # Mark "Sent via NGSIGN" activity as done
                self._mark_signature_followup_done()
            
                 # Create new "Validate signed PO" activity
                self._create_validate_po_activity()

                _logger.info(f"Successfully downloaded and attached signed document for SO: {self.name}")
                return True
            
            return False
            
        except requests.exceptions.HTTPError as e:
            _logger.error(f"HTTP Error checking signature: {e.response.status_code}", exc_info=True)
            return False
        except requests.exceptions.RequestException as e:
            _logger.error(f"Request error checking signature: {str(e)}", exc_info=True)
            return False
        except Exception as e:
            _logger.error(f"Unexpected error checking signature: {str(e)}", exc_info=True)
            return False

    def read(self, fields=None, load='_classic_read'):
        """Override read to check signature status when order is opened."""
        result = super(SaleOrder, self).read(fields=fields, load=load)
        
        # Check signature status for orders with pending signatures
        for record_data in result:
            if record_data.get('ngsign_transaction_uuid') and not record_data.get('ngsign_signed_document_id'):
                # Get the record to call the check method
                record = self.browse(record_data['id'])
                # Run in background to avoid blocking the UI
                try:
                    record._check_and_download_signed_document()
                except Exception as e:
                    _logger.warning(f"Failed to check signature status for SO {record.name}: {str(e)}")
        
        return result
    def _mark_signature_followup_done(self):
        """Mark the 'Sent via NGSIGN' activity as done."""
        self.ensure_one()
        
        # Find pending activities related to signature follow-up
        activities = self.activity_ids.filtered(
            lambda a: a.summary == _('Sent via NGSIGN') and a.state in ['overdue', 'today', 'planned']
        )
        
        if activities:
            # Mark as done with a feedback note
            for activity in activities:
                activity.action_feedback(feedback=_('Document has been signed and downloaded.'))
            _logger.info(f"Marked {len(activities)} signature follow-up activity(ies) as done for SO: {self.name}")
        else:
            _logger.info(f"No pending signature follow-up activity found for SO: {self.name}")

    def _create_validate_po_activity(self):
        """Create a new 'Validate signed PO' activity."""
        self.ensure_one()
        
        # Check if this activity already exists to avoid duplicates
        existing_activity = self.activity_ids.filtered(
            lambda a: a.summary == _('Validate signed PO') and a.state in ['overdue', 'today', 'planned']
        )
        
        if not existing_activity:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Validate signed PO'),
                note=_('The document "%s" has been signed by the customer. Please review and validate this sales order to proceed.') % self.name,
                user_id=self.user_id.id or self.env.uid,
            )
            _logger.info(f"Created 'Validate signed PO' activity for SO: {self.name}")
        else:
            _logger.info(f"'Validate signed PO' activity already exists for SO: {self.name}")