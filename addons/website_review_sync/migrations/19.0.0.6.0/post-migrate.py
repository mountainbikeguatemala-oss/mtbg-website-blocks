"""Google is reached only through a Google connection module now: the accounts' own OAuth client and sign-in
(client id, secret, refresh token) go, with their secrets."""


def migrate(cr, version):
    cr.execute("""
        ALTER TABLE review_account
            DROP COLUMN IF EXISTS google_client_id,
            DROP COLUMN IF EXISTS google_client_secret,
            DROP COLUMN IF EXISTS google_refresh_token
    """)
