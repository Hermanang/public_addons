# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    "name":"Digital Signature on Invoice and Bill | eSignature on Invoice and Bill | eSign Invoice and Bill",
    "version":"16.0.0.0",
    "category":"Accounting",
    "summary":"eSign invoice eSign bill digital signature on invoice eSignature on invoice digital sign on bill eSignature on bill electronic signature on bill and invoice signing digitally invoice sign Digital invoice signing eSign document eSignature for invoice esign",
    "description":"""Digital Signature for Customer Invoice & Bill Odoo App is designed to enhance the invoicing and billing process by allowing secure and legally compliant digital signatures on customer invoices and vendor bills. This app enables businesses to electronically sign and process financial documents, ensuring authenticity, security, and validity. By integrating digital signatures, businesses can maintain a more secure, efficient, and transparent invoicing and billing process.""",
    "author": "BROWSEINFO",
    'website': 'https://www.browseinfo.com/demo-request?app=bi_invoice_digital_sign&version=16&edition=Community',
    "depends":["base",
               "account",
	          ],
    "currency": 'EUR',
    "data":[
            "views/account_move_inherit.xml",
	       ],
    'license': 'OPL-1',
    "auto_install": False,
    "installable": True,
    "live_test_url":'https://www.browseinfo.com/demo-request?app=bi_invoice_digital_sign&version=16&edition=Community',
    "images":["static/description/Banner.gif"],
}
