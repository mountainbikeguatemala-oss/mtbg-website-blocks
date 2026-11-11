"""The Zoho page's sub-extensions: one card per Zoho integration (the Extensions panel keeps one Zoho tile).

A card is built in (part of an extension: ``owner``) or a glue module (installed by itself with the business
extension it links; the extensions say which module names are glues, ``_mtbg_card_module_patterns``). Each shows what it does, its installed version and the newest on GitHub, its status
(built in, installed, available, needs <extension>), its Zoho app's On / Writes allowed, and Install / Update through
the updater (never by hand: the updater's backup, dependencies and rollback apply).

A glue describes its card in its manifest, so the card shows even before it is installed (its code is not loaded then;
on a site the updater manages it is not even on disk, so the manifest comes from the update release)::

    'zoho_connector_card': {'key': 'shifts', 'title': 'Zoho Shifts', 'summary': '...', 'app': 'shifts', 'sequence': 50}

(``'mtbg_tours_zoho_card'`` is read too.) Optional keys: ``'sync': 'model:method'`` (its Sync now: a method taking no argument) and ``'links': [{'title',
'action': 'module.xmlid'}]`` (its pages: maps, directories... opened from the card, never from the menu). The cards
below are the defaults, translated: they win, and a manifest's card only fills what they lack (a new glue's whole
card). A glue with a card of its own and no block on the page shows under "More Zoho integrations".
"""
from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import parse_version
from odoo.tools.translate import LazyTranslate

from ..services.client import APPS, Zoho, truthy

_lt = LazyTranslate(__name__)

CARD_KEYS = ('key', 'title', 'summary', 'app', 'sequence', 'sync', 'links')
OWN = ('zoho_connector', 'base')
CARD_KEY = 'zoho_connector_card'
OLD_CARD_KEY = 'mtbg_tours_zoho_card'  # (the glues' manifests before 0.1 of the connector)


class MtbgZohoSubextension(models.AbstractModel):
    _name = 'mtbg.zoho.subextension'
    _description = 'Zoho sub-extensions (the Zoho page\'s cards)'

    def _check(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only administrators can change the Zoho integrations."))

    # ------------------------------------------------------------------ the extensions' hooks
    @api.model
    def _mtbg_card_defaults(self):
        """[card]: the cards the installed extensions give (translated): key, module (False: built in its
        ``owner``), app, block, sequence, title, summary, sync, links."""
        return []

    @api.model
    def _mtbg_card_module_patterns(self):
        """The module name patterns (``=like``) of the glues the cards may come from."""
        return ['zoho\\_%']

    def _mtbg_glue_domain(self):
        patterns = [p for p in self._mtbg_card_module_patterns()]
        domain = ['|'] * (len(patterns) - 1) + [('name', '=like', p) for p in patterns]
        return ['&', ('name', '!=', 'zoho_connector')] + domain

    @api.model
    def _mtbg_card_of(self, manifest):
        own = manifest.get(CARD_KEY) or manifest.get(OLD_CARD_KEY)
        return own if isinstance(own, dict) else None

    # ------------------------------------------------------------------ where a glue's manifest comes from
    @api.model
    def _mtbg_newest_releases(self):
        """{module: newest release} of the update sources (empty without Updates from GitHub)."""
        if 'mtbg.github.release' not in self.env:
            return {}
        newest = {}
        sources = self.env['mtbg.github.source'].sudo().search([])
        patterns = self._mtbg_card_module_patterns()
        domain = ['|'] * (len(patterns) - 1) + [('module', '=like', p) for p in patterns]
        for release in self.env['mtbg.github.release'].sudo().search(
                domain + [('module', '!=', 'zoho_connector'), ('source_id', 'in', sources.ids)], order='version_sort desc'):
            newest.setdefault(release.module, release)
        return newest

    @api.model
    def _mtbg_manifest(self, module, release):
        """The glue's manifest: on the server (installed or not), else its newest update release's."""
        info = self.env['ir.module.module'].get_module_info(module)
        if info:
            return info
        if release:
            from odoo.addons.mtbg_github_updates.models import store
            try:
                return release._mtbg_manifest()
            except store.StoreError:
                return {}
        return {}

    # ------------------------------------------------------------------ the cards
    @api.model
    def _mtbg_cards(self):
        Module = self.env['ir.module.module'].sudo()
        releases = self._mtbg_newest_releases()
        cards = {card['module'] or card['key']: dict(card) for card in self._mtbg_card_defaults()}
        # glues the server or GitHub knows, with a card of their own (or one of the defaults)
        names = set(Module.search(self._mtbg_glue_domain()).mapped('name')) | set(releases)
        for name in sorted(names):
            manifest = self._mtbg_manifest(name, releases.get(name))
            own = self._mtbg_card_of(manifest)
            if own:
                card = cards.setdefault(name, {'module': name, 'block': False})
                # the defaults win (they are translated); a manifest's card fills what they lack (a new glue's card)
                card.update({k: own[k] for k in CARD_KEYS if own.get(k) and not card.get(k)})
            if name in cards:
                cards[name]['manifest'] = manifest
        installed = {m.name: m for m in Module.search([('state', 'in', ('installed', 'to upgrade'))])}
        updates = 'mtbg.github.update' in self.env
        Ref = self.env['mtbg.zoho.ref'].sudo()
        result = []
        for card in sorted(cards.values(), key=lambda c: (c.get('sequence') or 99, c['key'])):
            module, manifest = card['module'], card.pop('manifest', {})
            release = releases.get(module) if module else False
            needs = [dep for dep in (manifest.get('depends') or []) if dep not in OWN]
            missing = [dep for dep in needs if dep not in installed]
            record = installed.get(module) if module else False
            version = (record.latest_version or '') if record else ''
            if not module:
                status = 'built_in'
                owner = card.get('owner') or 'zoho_connector'
                version = installed[owner].latest_version if owner in installed else ''
            elif record:
                status = 'installed'
            elif missing:
                status = 'needs'
            elif manifest or release:
                status = 'available'
            else:
                status = 'unknown'
            newest = release.version if release else ''
            zoho = Zoho(self.env, card['app']) if card.get('app') in APPS else None
            usable = status in ('built_in', 'installed')
            links = [{'index': i, 'title': self._mtbg_text(link.get('title'))} for i, link in enumerate(card.get('links') or [])
                     if usable and link.get('action') and self.env.ref(link['action'], raise_if_not_found=False)]
            model, _sep, method = (card.get('sync') or '').partition(':')
            errors = Ref.search_count([('system', '=', card['app']), ('state', '=', 'error')]) if zoho else 0
            result.append({
                'key': card['key'], 'module': module or '', 'block': card.get('block') or '',
                'title': self._mtbg_text(card['title']), 'summary': self._mtbg_text(card.get('summary')),
                'app': card.get('app') or '',
                'app_label': APPS[card['app']]['label'] if zoho else '',
                'status': status, 'version': version, 'newest': newest,
                'needs': [{'name': dep, 'title': self._mtbg_title(dep)} for dep in missing],
                'on': truthy(zoho._param(f"zoho_{card['app']}_enabled")) if zoho else False,
                'writes': truthy(zoho._param(f"zoho_{card['app']}_writes")) if zoho else False,
                'has_writes': card.get('app') != 'expense',  # read only (Expense: Zoho 0.3.12)
                'links': links, 'can_sync': bool(usable and zoho and zoho.enabled and model in self.env and method),
                'errors': errors,
                'can_install': bool(updates and status == 'available' and release),
                'can_update': bool(updates and status == 'installed' and release
                                   and parse_version(newest) > parse_version(version or '0')),
            })
        return result

    @api.model
    def _mtbg_text(self, text):
        """A card's text in the user's language (the defaults are lazy translations; a manifest's is as written)."""
        return self.env._(text) if text and not isinstance(text, str) else (text or '')

    @api.model
    def _mtbg_title(self, module):
        record = self.env['ir.module.module'].sudo().search([('name', '=', module)], limit=1)
        name = record.shortdesc or self.env['ir.module.module'].get_module_info(module).get('name') or module
        return name.split('—')[-1].strip()

    # ------------------------------------------------------------------ the page's calls
    @api.model
    def mtbg_cards(self):
        self._check()
        return {'cards': self._mtbg_cards(), 'updates': 'mtbg.github.update' in self.env}

    @api.model
    def mtbg_card_switch(self, app, which, value):
        """An app's On or Writes allowed (shared by its cards)."""
        self._check()
        if app not in APPS or which not in ('enabled', 'writes'):
            raise UserError(_("Unknown switch."))
        self.env['ir.config_parameter'].sudo().set_param(f'mtbg_tours.zoho_{app}_{which}', '1' if value else '0')
        return self.mtbg_cards()

    @api.model
    def mtbg_card_install(self, key, kind='install'):
        """Install (or update) a glue through the updater: its progress screen, backup and rollback."""
        self._check()
        card = next((c for c in self._mtbg_cards() if c['key'] == key), None)
        if not card or not card['module'] or not (card['can_install'] if kind == 'install' else card['can_update']):
            raise UserError(_("This integration cannot be installed or updated from here now."))
        release = self._mtbg_newest_releases()[card['module']]
        return self.env['mtbg.github.update']._mtbg_start([(card['module'], release)],
                                                          kind='install' if kind == 'install' else 'update')

    @api.model
    def _mtbg_card_def(self, key):
        """The card's definition (defaults + its manifest), for its sync method and links."""
        Module = self.env['ir.module.module'].sudo()
        releases = self._mtbg_newest_releases()
        card = dict(next((c for c in self._mtbg_card_defaults() if c['key'] == key), {}))
        names = set(Module.search(self._mtbg_glue_domain()).mapped('name')) | set(releases)
        for name in names:
            own = self._mtbg_card_of(self._mtbg_manifest(name, releases.get(name)))
            if own and own.get('key') == key:
                card.update({k: own[k] for k in CARD_KEYS if own.get(k) and not card.get(k)}, module=name)
        return card

    @api.model
    def mtbg_card_sync(self, key):
        """The card's Sync now (its own method, from its definition only)."""
        self._check()
        view = next((c for c in self._mtbg_cards() if c['key'] == key), None)
        card = self._mtbg_card_def(key)
        model, _sep, method = (card.get('sync') or '').partition(':')
        if not view or not view['can_sync'] or not method or method.startswith('__'):
            raise UserError(_("This integration has no sync to run now (is its Zoho app On?)."))
        result = getattr(self.env[model].sudo(), method)()
        if isinstance(result, dict) and {'created', 'updated', 'removed'} <= set(result):
            message = _("%(created)s new, %(updated)s updated, %(removed)s removed.", **result)
        else:
            message = _("Done: see the sync log for what went to or came from Zoho.")
        return {'message': message, 'cards': self._mtbg_cards()}

    @api.model
    def mtbg_card_link(self, key, index):
        """One of the card's pages (a map, a directory), as an action."""
        self._check()
        links = self._mtbg_card_def(key).get('links') or []
        if not 0 <= int(index) < len(links):
            raise UserError(_("Unknown page."))
        return self.env['ir.actions.actions']._for_xml_id(links[int(index)]['action'])

    @api.model
    def mtbg_section_action(self, what, app=None):
        """The section's own pages: the sync log, the references (an app's errors with ``app``)."""
        self._check()
        if what == 'log':
            return self.env['ir.actions.actions']._for_xml_id('zoho_connector.action_zoho_log')
        action = self.env['ir.actions.actions']._for_xml_id('zoho_connector.action_zoho_refs')
        if app:
            action['domain'] = [('system', '=', app), ('state', '=', 'error')]
            action['name'] = _("Zoho sync errors")
        return action

