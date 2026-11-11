"""Events for the Google apps: a record announces what happened to it, and each Google app listens, so no app watches
the records itself (docs/architecture/google.md). Generic: the connector names no business model. The apps bring the
events and their records:

* ``_mtbg_google_events()``: each app adds the events it listens to, {event, model, on (create / write / unlink),
  fields (a write counts when one of them changes; None: any field written), when (record -> bool, after the change),
  target (a field leading to the record the event is about: a rider's booking)}. An event added by two apps counts
  once.
* The records of those models announce them: the app adds the mixin ``mtbg.google.broadcaster`` to the model
  (``_inherit = [model, 'mtbg.google.broadcaster']``; two apps adding it to the same model: it is applied once).
* ``_mtbg_google_notify(event, records, vals)`` receives them: each app extends it (super() first) and does its own
  part, quickly (a scheduled job for the calls to Google). An app's trouble never stops the record's change.

A change made with the context ``mtbg_google_silent`` (an app writing what it got from Google) announces nothing.
Moved here from the Tours' glue module mtbg_tours_google (retired into this connector, 19.0.1.5.0)."""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class MtbgGoogleBroadcast(models.AbstractModel):
    _name = 'mtbg.google.broadcast'
    _description = 'Events for the Google apps'

    @api.model
    def _mtbg_google_events(self):
        """The events the apps listen to: none of the connector's own. Each app that uses them adds its events and
        their records here (super() + its list); an event two apps add counts once (the first one listed)."""
        return []

    @api.model
    def _mtbg_google_notify(self, event, records, vals=None):
        """``event`` happened to ``records`` (``vals``: what was written, for a write). Each Google app extends it."""
        return True

    # ------------------------------------------------------------------ the records announce
    @api.model
    def _mtbg_google_specs(self, model, op):
        specs, seen = [], set()
        for spec in self._mtbg_google_events():
            if spec['event'] in seen:
                continue  # added by two apps: once
            seen.add(spec['event'])
            if spec['model'] == model and op in spec['on']:
                specs.append(spec)
        return specs

    @api.model
    def _mtbg_google_before(self, records, op, vals=None):
        """What a write or an unlink needs to know before it: the fields' values, the targets."""
        specs = self._mtbg_google_specs(records._name, op)
        if not specs or not records:
            return None
        names = {name for spec in specs for name in (spec.get('fields') or []) if name in records._fields}
        if vals is not None:
            names &= set(vals) | {name for spec in specs if spec.get('target') for name in [spec['target']]}
        return {
            'specs': specs,
            'values': {rec.id: {name: rec[name] for name in names} for rec in records} if names else {},
            'targets': {spec['target']: records.mapped(spec['target']) for spec in specs if spec.get('target')},
        }

    @api.model
    def _mtbg_google_after(self, records, op, before, vals=None):
        if not before or self.env.context.get('mtbg_google_silent'):
            return
        for spec in before['specs']:
            fields = [name for name in (spec.get('fields') or []) if name in records._fields]
            if op == 'write' and spec.get('fields') is not None:
                if not set(fields) & set(vals or {}):
                    continue
                hit = records.filtered(lambda rec: rec.exists() and any(
                    before['values'].get(rec.id, {}).get(name) != rec[name] for name in fields if name in (vals or {})))
            elif op == 'create' and fields:
                hit = records.filtered(lambda rec: any(rec[name] for name in fields))  # created with one of them
            else:
                hit = records if op != 'unlink' else records.browse(records.ids)
            if spec.get('when'):
                hit = hit.filtered(spec['when'])
            if spec.get('target'):
                target = before['targets'].get(spec['target'], self.env[records._fields[spec['target']].comodel_name])
                if op != 'unlink':
                    target |= hit.exists().mapped(spec['target'])
                elif not hit:
                    continue
                hit = target.exists()
            if hit:
                try:
                    self._mtbg_google_notify(spec['event'], hit, vals)
                except Exception:  # an app's trouble never stops the Tours' own change
                    _logger.exception("Google event %s on %s failed", spec['event'], hit)


class MtbgGoogleBroadcaster(models.AbstractModel):
    _name = 'mtbg.google.broadcaster'
    _description = 'Announces its changes to the Google apps'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Broadcast = self.env['mtbg.google.broadcast']
        Broadcast._mtbg_google_after(records, 'create', Broadcast._mtbg_google_before(records, 'create'))
        return records

    def write(self, vals):
        Broadcast = self.env['mtbg.google.broadcast']
        before = Broadcast._mtbg_google_before(self, 'write', vals)
        res = super().write(vals)
        Broadcast._mtbg_google_after(self, 'write', before, vals)
        return res

    def unlink(self):
        Broadcast = self.env['mtbg.google.broadcast']
        before = Broadcast._mtbg_google_before(self, 'unlink')
        ids = self.ids
        res = super().unlink()
        if before:
            Broadcast._mtbg_google_after(self.browse(ids), 'unlink', before)
        return res
