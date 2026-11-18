# Changelog

## 19.0.0.3.0 (2026-11-18)
- **Contact rules go global** (owner, 2026-11-18): the extension moves from the Tours repository to the universal one
  (technical name kept; its manifest names its new repository, so the updater takes it from there) and needs no Tours:
  it depends on Odoo (automation rules, discussions) and the admin look (`mtbg_backend_ui` 0.2.0: boards, cards, side
  bar, settings page). Rules on contacts and duplicates work on any site.
- Its own page and menu for a site without Tours: **Contact Rules** (Rules: the Contact rules and Changes tabs;
  Possible Duplicates). Who changes the rules: the admin look's managers (administrators; with Tours, its managers, as
  before). Access: internal users read (and mark duplicates), administrators change.
- The Tours parts go to the Alert Feed (`mtbg_tours_alerts` 0.4.0): the Contact rules and Changes tabs on its Rules &
  Alerts page, the Tours menus (Operations > Possible Duplicates, Configuration > Rules & Alerts), the Tours groups'
  access and the rules' two alert sources. Their records are handed over by a pre-migrate (same ids, nothing
  rebuilt); with Tours this extension's own menu is not shown. The tabs' templates and methods stay here
  (`@mtbg_tours_crm_rules/crm_tab/crm_tab`: `crmRulesMethods`), shared by both pages.
- Rules, runs, changes, the inbox and the possible duplicates are kept as they are (on or off as they were).

## 19.0.0.2.0 (2026-11-16)
- Its name is now **Contact Rules** (owner, 2026-11-16; the technical name `mtbg_tours_crm_rules` stays, so nothing
  is reinstalled): the extension, the Rules & Alerts page's tab, the list, the scheduled jobs' names on a new site.
- "Enquiry not answered" is no longer one of its own rules: Communications 19.0.0.8.0 brings it, on the website form
  messages (Odoo's CRM retired). The rule's record is kept, on or off as it was.

## 19.0.0.1.2
- Fix: the CRM Rules list (Tours > Configuration) opens again. Its side bar's Records section grouped by the model's
  name, a text Core 0.5.13 cannot group by; it groups by the model itself now (found on DEV2).

## 19.0.0.1.1
- The scheduled jobs (daily rules, messages received) are no longer switched back on by an update: switched off on a
  site, they stay off.

## 19.0.0.1.0
- New: CRM Rules, stock CRM helpers that keep contacts and leads tidy on their own, each off until switched on. They
  sit on the Alert Feed's page, now **Rules & Alerts** (Tours > Configuration): its **CRM rules** tab (by the
  records they look at: on/off, their days, Dry run) and its **Changes** tab (what the rules changed: undo, or mark
  an alert dealt with)
- Stock helpers: country and state from the phone (a US / Canadian area code gives the state); country and state
  from a message's number (when a message comes in); possible duplicates by phone or email (Possible Duplicates
  under Operations, never merged); enquiry not answered (with CRM: a to-do after the days set); Spanish for
  Spanish-speaking countries. Only empty fields are filled
- Every change is logged and can be undone; a field somebody changed since is left as it is
- Odoo's automation rules run them underneath (kept by the page; off when the rule is off); the daily rules and the
  messages received have their own crons; a copy of the database switches every rule off (neutralize)
- Extensions bring their own helpers with `_mtbg_crm_rule_sources()` on their own model (like the Alert Feed's
  sources); a channel tells the rules a message came in with `mtbg.crm.rule._mtbg_message_received(partner, phone,
  channel)` (the Communication glue, `mtbg_tours_crm_rules_cfd`, does it for every channel)
- With the Alert Feed: CRM rule alerts, Possible duplicates to check
