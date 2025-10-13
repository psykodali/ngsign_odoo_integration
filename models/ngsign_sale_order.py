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

    def _get_api_credentials(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        api_url = get_param('ngsign_integration.api_url')
        bearer_token = get_param('ngsign_integration.bearer_token')
        
        _logger.info(f"API URL configured: {bool(api_url)}")
        _logger.info(f"Bearer token configured: {bool(bearer_token)}")
        
        if not api_url or not bearer_token:
            raise UserError(_('NGSIGN API URL and Bearer Token must be configured in settings.'))
        return api_url, bearer_token

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
            _logger.info("Attempting to find report action")
            report_action = self.env.ref('sale.action_report_saleorder', raise_if_not_found=False)
            
            if not report_action or not report_action.exists():
                _logger.warning("Standard report not found, searching for alternatives")
                bound_actions = self.env['ir.actions.report'].search([
                    ('model', '=', 'sale.order'),
                    ('binding_model_id.model', '=', 'sale.order'),
                    ('report_type', '=', 'qweb-pdf')
                ], limit=1)
                report_action = bound_actions

            if not report_action:
                raise UserError(_("Could not find a valid, printable report action for Sales Orders. Please check the configuration under Settings → Technical → Reports → Print Menu."))

            _logger.info(f"Using report: {report_action.name if hasattr(report_action, 'name') else 'Unknown'}")
            
            pdf_content, __ = report_action._render_qweb_pdf(self.id)
            
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
        headers = {'Authorization': f'Bearer {bearer_token}', 'Content-Type': 'application/json'}
        file_name = f"{self.name}.pdf"

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
                    "otp": "NONE"
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

            self.write({'ngsign_transaction_uuid': transaction_uuid, 'ngsign_signature_url': signature_url})
            
            message_body = _('Document sent to <b>%s</b> (%s) for signature via NGSIGN.') % (signer_info.get('name'), signer_info.get('email'))
            self.message_post(body=message_body)

            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Follow up on signature'),
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