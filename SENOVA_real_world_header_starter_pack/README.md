# SENOVA Real-World Header Starter Pack

Purpose
- Reduce Antigravity's initial research effort by supplying a small, source-backed starter set of business headers.
- These are headers/field names described in official product documentation, not a guarantee that every report/export uses exactly the same column name.
- Treat proposed_role as a candidate for review, not an unconditional canonical mapping.

Contents
- verified_header_starter.csv: 80-ish documented header/field examples with source URL and review note.
- source_register.csv: source index and what each source can support.
- IMPLEMENTATION_NOTES.md: safe import rules and next steps.

Important limitations
1. This is a starter pack, not a complete business dictionary.
2. Some official pages describe UI fields rather than literal exported CSV headers. Verify exact CSV/XLSX headers with official downloadable templates or real sample exports before marking an entry production-verified.
3. Some names are context-sensitive (e.g. Name, Amount, Tax, Order Number, Party Name). Do not force a role when the header is ambiguous.
4. Do not add sample customer values or personal data. Headers only.
5. Do not invent aliases. Preserve source URL and verification status for every imported row.
6. Do not automatically overwrite the current dictionary. Compare against current entries, report conflicts, and stage a review file first.

Official sources:
- TallyPrime sample Excel files: https://help.tallysolutions.com/download-sample-excel-files-with-data-for-import/
- TallyPrime export data: https://help.tallysolutions.com/export-data-in-tally/
- ERPNext Sales Invoice: https://docs.frappe.io/erpnext/sales-invoice
- ERPNext Sales Order: https://docs.frappe.io/erpnext/sales-order
- Shopify order export: https://help.shopify.com/en/manual/fulfillment/managing-orders/exporting-orders
- Shopify inventory CSV: https://help.shopify.com/en/manual/sell-in-person/shopify-pos/inventory-management/export-import-inventory-csv-pos
- Zoho Books invoices: https://www.zoho.com/us/books/help/invoice/
- Zoho Books tax reports: https://www.zoho.com/us/books/help/reports/tax-reports.html
- Odoo export/import: https://www.odoo.com/documentation/17.0/applications/essentials/export_import_data.html
