-- copies never measure the live site's pages nor keep its PageSpeed key
UPDATE ir_config_parameter SET value = 'False' WHERE key = 'mtbg_page_speed.log';
DELETE FROM ir_config_parameter WHERE key = 'mtbg_page_speed.psi_key';
