-- a copy of a site (neutralized): no photo server token or Immich key left, so a real server can't talk to the copy
DELETE FROM ir_config_parameter WHERE key IN ('immich_connector.nas_token_hash', 'immich_connector.api_key',
                                              'immich_connector.last_seen', 'immich_connector.office_ip',
                                              'immich_connector.office_tls', 'immich_connector.office_tls_watch',
                                              'immich_connector.office_tls_incident');
