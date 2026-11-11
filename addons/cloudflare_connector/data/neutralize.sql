-- a copy of a site (neutralized): no Cloudflare token or R2 key left, so a copy can never write to the real bucket
DELETE FROM ir_config_parameter WHERE key IN ('cloudflare_connector.api_token',
                                              'cloudflare_connector.r2_access_key_id',
                                              'cloudflare_connector.r2_secret_access_key');
