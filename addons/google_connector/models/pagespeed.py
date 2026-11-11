"""PageSpeed Insights: the connector's "pagespeed" app measures the website's pages for Page Speed's nightly speed log
(owner, 2026-11-08: "the new pagespeed should get its api info from our main google connector there is no reason for
it to have its own google link"; a connector's API code lives in the connector). Page Speed asks these methods only
when the connector is installed; nothing here needs Page Speed.

The call needs no Google account: the connector's server API key (Set up Google › API keys), from a project with the
PageSpeed Insights API enabled."""
from odoo import api, models

APP = 'pagespeed'
RUN_URL = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
RUN_TIMEOUT = 150


class GoogleConnector(models.AbstractModel):
    _inherit = 'google.connector'

    @api.model
    def _google_app_specs(self):
        """The PageSpeed app, once Page Speed is installed (it keeps the log; this connector measures)."""
        specs = super()._google_app_specs()
        if self.env.get('mtbg.page.speed.log') is None:
            return specs
        return dict(specs, **{APP: {
            'label': 'PageSpeed Insights', 'module': 'mtbg_tours_page_speed', 'sequence': 60,
            'needs_account': False, 'uses_server_key': True,
            'settings_action': 'mtbg_tours_page_speed.action_page_speed_settings',
            'description': "The website's speed, measured every night by Google (Lighthouse) for Page Speed's speed "
                           "log.",
        }})

    @api.model
    def _google_pagespeed_ready(self):
        """The PageSpeed app is on, with the server API key."""
        app = self._google_app(APP)
        return bool(app) and app.status == 'ready'

    @api.model
    def _google_pagespeed_run(self, url, strategy='mobile', category='performance'):
        """PageSpeed Insights' answer for ``url`` (dict); a GoogleError when Google refuses (its message, the key
        hidden)."""
        # (a measurement takes 20 s to a minute or more: not the client's usual 30 s)
        return self.client(APP).get(RUN_URL, params={'url': url, 'strategy': strategy, 'category': category},
                                    timeout=RUN_TIMEOUT)
