-- a copy of a site (neutralized): no Cloudflare token or R2 key left, so a copy can never write to the real bucket
DELETE FROM ir_config_parameter WHERE key IN ('cloudflare_connector.api_token',
                                              'cloudflare_connector.r2_access_key_id',
                                              'cloudflare_connector.r2_secret_access_key',
                                              'cloudflare_connector.r2_photos_access_key_id',
                                              'cloudflare_connector.r2_photos_secret_access_key');
-- the page cache (formerly mtbg_tours_edge_cache): a copy never purges the live site's Cloudflare cache, nor keeps
-- its former token
UPDATE ir_config_parameter SET value = 'False' WHERE key = 'mtbg_tours.edge_cache';
DELETE FROM ir_config_parameter WHERE key IN ('mtbg_tours.edge_cache_token', 'mtbg_tours.edge_cache_zone');
