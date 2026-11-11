-- A neutralized copy of a site never talks to Zoho: the shared login (also Invoices & Payments') and its tokens are
-- removed, every app's On and Writes allowed are switched off, and so is Invoices & Payments' Send to Zoho Books.
DELETE FROM ir_config_parameter
 WHERE key IN ('mtbg_tours.zoho_client_id', 'mtbg_tours.zoho_client_secret', 'mtbg_tours.zoho_refresh_token',
               'mtbg_tours.zoho_access_token', 'mtbg_tours.zoho_access_token_expires', 'mtbg_tours.zoho_webhook_token',
               'mtbg_tours.zoho_granted_scopes', 'mtbg_tours.zoho_access_check')
    OR (key LIKE 'mtbg\_tours.zoho\_%' AND key ~ '(secret|token)' AND key NOT LIKE 'mtbg\_tours.zoho\_cf\_%');
UPDATE ir_config_parameter SET value = '0'
 WHERE key IN ('mtbg_tours.zoho_sync', 'mtbg_tours.zoho_books_enabled', 'mtbg_tours.zoho_books_writes',
               'mtbg_tours.zoho_expense_enabled', 'mtbg_tours.zoho_expense_writes', 'mtbg_tours.zoho_shifts_enabled',
               'mtbg_tours.zoho_shifts_writes', 'mtbg_tours.zoho_crm_enabled');
