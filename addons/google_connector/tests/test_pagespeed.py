from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.google_connector.models import client as client_module
from odoo.addons.google_connector.models.client import GoogleError


@tagged('post_install', '-at_install')
class TestPageSpeedApp(TransactionCase):
    """1.4.0: the PageSpeed Insights app (Page Speed's speed log) on the connector's server API key."""

    def setUp(self):
        super().setUp()
        self.Connector = self.env['google.connector']
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.ICP.set_param('google_connector.server_key', False)

    def _app(self):
        self.Connector._google_sync_apps()
        return self.env['google.connector.app'].sudo().search([('code', '=', 'pagespeed')])

    def test_app_and_key(self):
        app = self._app()
        self.assertTrue(app, "a card (and the app, with Page Speed installed)")
        self.assertTrue(app.uses_server_key)
        self.assertFalse(app.needs_account)
        app.on = True
        self.assertEqual(app.status, 'no_key')
        self.assertFalse(self.Connector._google_pagespeed_ready())
        with self.assertRaises(GoogleError):
            self.Connector._google_pagespeed_run('https://example.com/')
        self.Connector._google_set_credentials(server_key=' SERVER-KEY ')
        app.invalidate_recordset(['status'])
        self.assertEqual(app.status, 'ready')
        self.assertTrue(self.Connector._google_pagespeed_ready())

    def test_run_uses_the_server_key(self):
        app = self._app()
        app.on = True
        self.Connector._google_set_credentials(server_key='SERVER-KEY', maps_key='MAPS-KEY')
        answer = MagicMock(status_code=200, content=b'{}')
        answer.json.return_value = {'lighthouseResult': {}}
        with patch.object(client_module.requests, 'request', return_value=answer) as request:
            self.assertEqual(self.Connector._google_pagespeed_run('https://example.com/', 'desktop'),
                             {'lighthouseResult': {}})
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs['params']['key'], 'SERVER-KEY', "the server key, not the Maps key")
        self.assertEqual((kwargs['params']['url'], kwargs['params']['strategy']), ('https://example.com/', 'desktop'))
        self.assertGreaterEqual(kwargs['timeout'], 120, "a measurement takes up to a minute or more")
        self.assertNotIn('Authorization', kwargs['headers'], "no Google account")

    def test_refusal_hides_the_key(self):
        app = self._app()
        app.on = True
        self.Connector._google_set_credentials(server_key='SECRET-KEY')
        answer = MagicMock(status_code=400, content=b'x', headers={})
        answer.json.return_value = {'error': {'message': 'API key not valid. key=SECRET-KEY'}}
        with patch.object(client_module.requests, 'request', return_value=answer):
            with self.assertRaises(GoogleError) as caught:
                self.Connector._google_pagespeed_run('https://example.com/')
        self.assertNotIn('SECRET-KEY', str(caught.exception))
