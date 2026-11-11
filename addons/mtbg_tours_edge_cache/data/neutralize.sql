-- copies never purge the live site's Cloudflare cache, nor keep its token
UPDATE ir_config_parameter SET value = 'False' WHERE key = 'mtbg_tours.edge_cache';
DELETE FROM ir_config_parameter WHERE key IN ('mtbg_tours.edge_cache_token', 'mtbg_tours.edge_cache_zone');
