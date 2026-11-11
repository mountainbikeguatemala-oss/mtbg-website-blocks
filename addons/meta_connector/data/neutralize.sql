-- a copy of a site (neutralized): no Meta app secret, Facebook login or Page token left
UPDATE meta_connector_app SET app_secret = NULL, user_token = NULL, manual_token = NULL, oauth_state = NULL,
                              user_token_expires = NULL, webhook_state = 'none';
UPDATE meta_connector_page SET page_token = NULL;
