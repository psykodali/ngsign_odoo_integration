# NGSIGN Integration for Odoo

[![License: LGPL-3](https://img.shields.io/badge/License-LGPL%20v3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Odoo Version](https://img.shields.io/badge/Odoo-18.0-875A7B)](https://www.odoo.com/)
[![Python Version](https://img.shields.io/badge/Python-3.10+-3776AB)](https://www.python.org/)

Professional electronic signature integration for Odoo Sales, powered by NGSIGN platform.

## 📋 Overview

Transform your sales workflow with secure, legally-compliant electronic signatures. This module seamlessly integrates the NGSIGN electronic signature platform directly into Odoo, enabling you to send quotations and sales orders for digital signing with just one click.

Perfect for businesses that need to collect signatures from customers quickly and securely, whether they're individuals or companies with multiple contacts.

## ✨ Key Features

### 🚀 **One-Click Signature Requests**
Send sales orders for signature directly from Odoo with a single button click. No need to export PDFs or use external tools.

### 👥 **Smart Contact Management**
When sending to companies, intelligently select which specific contact should sign the document through an intuitive wizard interface.

### ✏️ **Inline Information Editing**
Edit contact email and phone numbers on the fly before sending, with the option to update the contact record permanently.

### 📝 **Flexible Signature Templates**
Create and manage multiple signature templates with customizable:
- **Position**: Define exact X/Y coordinates for signature placement
- **Page Selection**: Choose specific pages or automatically place on the last page
- **Signature Types**: Support for Simple, DigiGO, and Choose Later signature types
- **Default Templates**: Mark templates as default for quick selection

### 🔄 **Resend Capability**
Easily resend signature requests with full visibility of previous attempts, including recipient and timestamp information.

### 📊 **Complete Tracking & Status**
- Real-time signature status monitoring (Draft, Sent, Signed, Expired, Cancelled)
- Automatic status checks when opening sales orders
- Activity tracking with automatic follow-ups
- Chatter integration for complete audit trail

### 📥 **Automatic Document Download**
Signed documents are automatically downloaded and attached to the sales order when the signature is completed.

### 🔒 **Secure & Compliant**
Uses NGSIGN's qualified signature service  for legally binding electronic signatures that comply with international standards.

## 📦 Installation

### Prerequisites

1. **Odoo 18.0** or later
2. **Python 3.10+**
3. **PyPDF2** library for PDF processing

### Install Dependencies

```bash
pip install PyPDF2
```

### Install Module

1. Clone this repository into your Odoo addons directory:
```bash
cd /path/to/odoo/addons
git clone https://github.com/yourusername/ngsign_integration_v4.git
```

2. Restart your Odoo server

3. Update the Apps List:
   - Go to **Apps** → **Update Apps List**

4. Install the module:
   - Search for "NGSIGN Integration"
   - Click **Install**

## ⚙️ Configuration

### 1. API Credentials Setup

Navigate to **Settings → General Settings → NGSIGN Integration**

Configure the following:
- **Base URL**: Your NGSIGN API base URL
  - Production: `https://ngsign.app`
  - Sandbox: `https://sandbox.ng-sign.com`
- **Bearer Token**: Your NGSIGN API authentication token

Click **Save** to store your configuration.

### 2. Create Signature Templates

Go to **Settings → NGSIGN → Signature Templates**

Create one or more templates with:
- **Template Name**: Descriptive name (e.g., "Bottom Right", "Last Page Center")
- **Signature Type**: Choose between Simple, DigiGO, or Choose Later
- **Page Type**: 
  - **Last Page**: Automatically place signature on the last page
  - **Specific Page**: Define exact page number
- **Coordinates**: Set X and Y position for signature placement. We recommend using our developer tool to identify the appropriate signature position within your PDF template.
- **Default**: Mark one template as default for quick selection
- **Sequence**: Order templates by priority

## 🎯 Usage

### Sending a Document for Signature

1. **Open a Sales Order**
   - Go to **Sales** → **Orders** → Select or create an order
   - Ensure the order is in **Draft** or **Sent** state

2. **Click "Send with NGSIGN"**
   - Yellow button with signature icon in the header

3. **Select Signer** (Wizard opens)
   - Choose the contact who should sign
   - Email and phone auto-populate from contact
   - Edit contact information if needed
   - Toggle "Save changes to contact" to update the contact record in odoo

4. **Choose Signature Template**
   - Select from your configured templates
   - Default template is pre-selected if configured

5. **Send for Signature**
   - Click "Send for Signature" button
   - Contact receives email invitation from NGSIGN
   - Activity is created for follow-up

### Monitoring Signature Status

- **Automatic Check**: Status is checked when you open the sales order
- **Manual Check**: Click "Check Signature Status" button
- **Status Badge**: View current status directly on the sales order:
  - 🔵 **Sent**: Awaiting signature
  - 🟢 **Signed**: Document signed
  - 🟠 **Expired**: Signature request expired
  - ⚫ **Cancelled**: Request cancelled

### Accessing Signed Documents

Once signed, the document is automatically:
- Downloaded from NGSIGN
- Attached to the sales order
- Posted in the chatter with notification
- Accessible via the "Signed Document" field

## 📸 Screenshots

### Send for Signature Wizard
![Wizard Screenshot](docs/images/wizard.png)

### Signature Templates Management
![Templates Screenshot](docs/images/templates.png)

### Sales Order with Signature Status
![Status Screenshot](docs/images/status.png)

## 🔧 Technical Details

### Module Information
- **Technical Name**: `ngsign_integration_v4`
- **Version**: 18.0.1.0.0
- **Category**: Digital Signature
- **License**: LGPL-3
- **Dependencies**: `base`, `mail`, `sale`

### Database Models

#### `ngsign.signature.template`
Signature template configuration with position, page, and signature type settings.

**Key Fields:**
- `name`: Template name
- `x_axis`, `y_axis`: Signature coordinates
- `page_type`, `page_number`: Page placement
- `signature_type`: Type of signature
- `is_default`: Default template flag

#### `ngsign.signer.wizard`
Transient model for signer selection and configuration.

**Key Fields:**
- `signer_id`: Selected contact
- `signer_email`, `signer_phone`: Contact information
- `template_id`: Selected signature template
- `update_contact`: Update contact record flag

#### Extended `sale.order`
Additional fields for NGSIGN integration.

**New Fields:**
- `ngsign_transaction_uuid`: NGSIGN transaction identifier
- `ngsign_signature_url`: Signature URL for tracking
- `ngsign_signature_status`: Current signature status
- `ngsign_signed_document_id`: Attachment link to signed document

### API Integration

The module integrates with NGSIGN's REST API:
- **Transaction Creation**: `POST /server/protected/transaction/pdfs`
- **Signature Launch**: `POST /server/protected/transaction/{uuid}/launch`
- **Status Check**: `GET /server/any/transaction/{uuid}`
- **Document Download**: `GET /server/any/transaction/{uuid}/pdfs/{identifier}`

### Security

Access rights defined in `security/ir.model.access.csv`:
- Templates accessible by all internal users
- Wizard accessible by all internal users

## 🐛 Troubleshooting

### Common Issues

**Issue**: "PyPDF2 library is not installed"
```bash
# Solution: Install PyPDF2
pip install PyPDF2
# Restart Odoo server
```

**Issue**: "API Error: 401 Unauthorized"
```
Solution: Check your Bearer Token in Settings → NGSIGN Integration
Ensure the token is valid and has not expired
```

**Issue**: Signature button not appearing
```
Solution: 
- Ensure sales order is in Draft or Sent state
- Verify module is installed and up to date
- Check browser console for JavaScript errors
```

**Issue**: Signed document not downloading automatically
```
Solution:
- Manually click "Check Signature Status" button
- Verify API credentials are correct
- Check Odoo logs for errors
```

## 📝 Changelog

### Version 18.0.1.0.0 (2025-01-15)
- ✨ Initial release for Odoo 18
- ✅ One-click signature sending
- ✅ Contact selection wizard
- ✅ Customizable signature templates
- ✅ Automatic status tracking
- ✅ Signed document download
- ✅ Resend capability
- ✅ Activity tracking integration

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This module is licensed under the LGPL-3 License. See the [LICENSE](LICENSE) file for details.

## 🔗 Links

- **NGSIGN Website**: [https://www.ng-sign.com](https://www.ng-sign.com)
- **NGSIGN Documentation**: [https://docs.ng-sign.com](https://docs.ng-sign.com)
- **Odoo Apps Store**: [Coming Soon]
- **Issue Tracker**: [GitHub Issues](https://github.com/yourusername/ngsign_integration_v4/issues)

## 📧 Support

For technical support or questions:
- **Email**: support@ng-sign.com
- **Documentation**: Check our comprehensive docs
- **Issues**: Open a GitHub issue

## 👨‍💻 Author

**NGSign**
- Website: [https://www.ng-sign.com](https://www.ng-sign.com)

---

Made with ❤️ by NGSIGN for the Odoo community
