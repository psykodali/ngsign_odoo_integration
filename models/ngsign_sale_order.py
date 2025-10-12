# models/sale_order.py
import base64
import io
import json
import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

# Import the PyPDF2 library. It's recommended to handle the case where it might not be installed.
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    ngsign_transaction_uuid = fields.Char(string='NGSIGN Transaction UUID', readonly=True, copy=False)
    ngsign_signature_url = fields.Char(string='NGSIGN Signature URL', readonly=True, copy=False)

    def _get_api_credentials(self):
        """Fetches API credentials from Odoo system parameters."""
        get_param = self.env['ir.config_parameter'].sudo().get_param
        api_url = get_param('ngsign_integration.api_url')
        bearer_token = get_param('ngsign_integration.bearer_token')
        if not api_url or not bearer_token:
            raise UserError(_('NGSIGN API URL and Bearer Token must be configured in settings.'))
        return api_url, bearer_token

    def action_send_with_ngsign(self):
        self.ensure_one()

        # --- Validations ---
        if not self.partner_id.email:
            raise UserError(_("Customer email is required to send the document for signature."))
        if not self.partner_id.name:
            raise UserError(_("Customer name is required to send the document for signature."))
        if not PyPDF2:
            raise UserError(_("The required library PyPDF2 is not installed. Please install it by running 'pip install PyPDF2'."))

        # --- PDF Generation ---
        pdf_content = self.env['ir.actions.report'].sudo()._render_qweb_pdf('sale.action_report_saleorder', self.ids)[0]
        if not pdf_content:
            raise UserError(_("Could not generate the quotation PDF. Please check your report configuration."))

        # --- Find Last Page for Signature ---
        last_page_number = 1
        try:
            pdf_stream = io.BytesIO(pdf_content)
            reader = PyPDF2.PdfReader(pdf_stream)
            last_page_number = len(reader.pages)
        except Exception:
            pass  # Fall back to page 1 if counting fails

        # --- Prepare Signer Information ---
        name_parts = self.partner_id.name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        signers = [{
            'first_name': first_name,
            'last_name': last_name,
            'email': self.partner_id.email,
            'phone': self.partner_id.phone or '',
            'sig_type': 'CERTIFIED_TIMESTAMP',
            'page': last_page_number, 'x_axis': 100, 'y_axis': 100,
        }]

        # --- API Interaction ---
        api_url, bearer_token = self._get_api_credentials()
        headers = {'Authorization': f'Bearer {bearer_token}', 'Content-Type': 'application/json'}
        file_name = f"{self.name}.pdf"

        try:
            # Step 1: Upload PDF
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            upload_payload = [{"fileName": file_name, "fileExtension": "pdf", "fileBase64": pdf_base64}]
            upload_response = requests.post(f"{api_url}/pdfs", headers=headers, data=json.dumps(upload_payload), timeout=30)
            upload_response.raise_for_status()
            upload_data = upload_response.json()
            
            transaction_uuid = upload_data['object']['uuid']
            pdf_identifier = upload_data['object']['pdfs'][0]['identifier']
            
            # Step 2: Configure and Launch Transaction
            signer = signers[0]
            launch_payload = {
                "sigConf": [{
                    "signer": {
                        "firstName": signer.get('first_name'), "lastName": signer.get('last_name'),
                        "email": signer.get('email'), "phoneNumber": signer.get('phone'),
                    },
                    "sigType": signer.get('sig_type'),
                    "docsConfigs": [{"page": signer.get('page'), "xAxis": signer.get('x_axis'), "yAxis": signer.get('y_axis'), "identifier": pdf_identifier}],
                    "mode": "BY_MAIL", "otp": "NONE"
                }],
                "message": "Invitation de signature de commande"
            }
            launch_response = requests.post(f"{api_url}/{transaction_uuid}/launch", headers=headers, data=json.dumps(launch_payload), timeout=30)
            launch_response.raise_for_status()
            launch_data = launch_response.json()
            
            # Extract Signature URL
            signature_url = None
            if launch_data.get('object', {}).get('signers'):
                first_signer = launch_data['object']['signers'][0]
                signature_url = first_signer.get('signatureUrl') or first_signer.get('url')

            # Update Sale Order and Log Activity
            self.write({
                'ngsign_transaction_uuid': transaction_uuid,
                'ngsign_signature_url': signature_url,
            })
            
            # Post message in chatter
            signer_name = f"{signer.get('first_name')} {signer.get('last_name')}"
            self.message_post(body=_('Document sent to %s (%s) for signature.') % (signer_name, signer.get('email')))

            # Schedule activity for the user
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Follow up on signature'),
                note=_('The document "%s" has been sent to %s for signature. You can follow the process via the NGSIGN platform.') % (self.name, signer.get('email')),
                user_id=self.user_id.id or self.env.uid,
            )

        except requests.exceptions.HTTPError as e:
            response_body = e.response.text
            try:
                response_body = json.dumps(e.response.json(), indent=2)
            except json.JSONDecodeError:
                pass
            error_msg = _("API Error: %(status_code)s\nResponse:\n%(response_body)s") % {
                'status_code': e.response.status_code, 'response_body': response_body,
            }
            self.message_post(body=_('Failed to send document: %s') % error_msg)
            raise UserError(_('Failed to send document to NGSIGN.\n\n%s') % error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            self.message_post(body=_('Failed to send document: %s') % error_msg)
            raise UserError(_('Failed to send document to NGSIGN: %s') % error_msg)

        return True