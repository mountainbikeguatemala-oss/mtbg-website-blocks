-- a copy of a site (neutralized): no Google login, key or app left on
DELETE FROM ir_config_parameter WHERE key IN ('google_connector.client_secret', 'google_connector.maps_key',
                                       'google_connector.server_key');
UPDATE google_connector_account SET refresh_token = NULL, access_token = NULL, token_expiry = 0, state = 'draft';
UPDATE google_connector_app SET "on" = FALSE, writes_allowed = FALSE;
