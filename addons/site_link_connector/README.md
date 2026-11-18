# Site Link Connector

Links two Odoo 19 sites of one business. Each side calls the other through Odoo's own external API
(`POST /json/2/<model>/<method>`, part of Odoo: the `rpc` module), with the API key of a technical user on the other
side as a bearer token and the database in the `X-Odoo-Database` header. No dependency on any other extension; the
inventory methods are offered only where Inventory (`stock`) is installed, the repair methods only where Sales
(`sale`) is (soft checks). Repair (`repair`) and a customer bike model (`repair.bike`, from another extension) are
used where they are installed.

## Set up (on both sites as needed)

On the site that is **called** (e.g. the one with the inventory):

1. Install Site Link Connector.
2. Make a technical user (internal user), give it the group **Site Link: calls from a linked site** (no other rights
   are needed: the protocol methods work with the rights they need, in that user's company).
3. Make an API key for it (the user's Preferences › Account Security › New API Key; no expiry, or a long one).

On the site that **calls**: Settings › Site Link › Linked Sites › New: name, address (`https://…`, no path),
database, the API key, the other site's role (**Inventory source** for the site that owns products and stock).
**Test connection** shows the other side's health (database, versions, user, methods offered) and keeps the result.
Every failed call is in Settings › Site Link › Failed Calls (kept 90 days).

The API keys are only readable by administrators; a neutralized copy of a site has its keys removed, its links
archived and its single sign-on tickets removed.

Users the other site may sign in here (single sign-on) need the group **Site link: single sign-on allowed** on this
site (nobody has it by default). Settings › Site Link › Calls Answered and Sign-ins shows the customer and repair calls
this site answered and every sign-on ticket and sign-in, given or refused (kept 90 days).

## Calling a linked site (Python)

```python
Site = env['site.link']
part = Site._site_link_call('inventory_source', 'site.link.api', 'part_lookup', barcode='7501234567890')
```

`_site_link_call(site, model, method, *ids, **kwargs)`

- `site`: a `site.link` record, its id, or a role (`'inventory_source'`: the first active site with that role).
- `model`, `method`: any public method the other site's key user may call (Odoo's /json/2 rules).
- `*ids`: record ids (`/json/2` `ids`), as integers or one list. `/json/2` takes **named arguments only**.
- `**kwargs`: the method's named arguments; `context={...}` is the call's context.
- Returns the JSON answer. Raises `SiteLinkError` (a `UserError`; `.status` = HTTP status, 0 when no answer;
  `.remote` = the other side's error name) with a clear message: unreachable, time limit (the site's Time Limit,
  default 15 s), redirect (save the address it names), key refused (401), not allowed (403), method missing (404:
  the connector is not installed or not up to date there), the other side's own error (422 for its UserError, 500).
- Every failed call is logged in `site.link.log`, through a cursor of its own (kept when the caller rolls back).

One line per protocol method (`site` defaults to the role `'inventory_source'`; a record or an id works too):

```python
Site = env['site.link']
if Site._site_link_offers('repair_quote'):            # soft check: False when no site, unreachable or older
    quote = Site._site_link_repair_quote('WO-12', partner_id, [{'product': '7501234567890', 'qty': 1},
                                                              {'service': 'Brake bleed', 'price': 150, 'hours': 1}])
url = Site._site_link_sso_url('mechanic@example.com')  # full address of the one-time sign-in link
```

`_site_link_api(method, site, **kwargs)`, `_site_link_customer_search(query, limit)`,
`_site_link_customer_create(name, phone, email)`, `_site_link_customer_bikes(partner_id)`,
`_site_link_repair_quote(reference, partner_id, lines, note, bike)`, `_site_link_repair_status(reference)`,
`_site_link_repair_invoice(reference)`; each raises `SiteLinkError` like `_site_link_call`.

## The protocol: `site.link.api`

Called as `POST /json/2/site.link.api/<method>` with a JSON body of named arguments. The caller (the API key's user)
needs the group *Site Link: calls from a linked site* (or to be an administrator), otherwise 403.

| Method | Arguments | Answer |
|---|---|---|
| `health()` | none | `{protocol: 1, module: "site_link_connector", module_version, odoo_version, database, user, company, methods: [...]}` |
| `part_lookup(barcode)` | `barcode` (text) | not found: `{found: false, barcode}`; found: `{found: true, id, name, default_code, barcode, qty_available, uom, unit_cost, sale_price, currency, vendor, image_url}` |
| `part_consume(product, qty, reference, note=None)` | `product`: product id (number) or barcode (text); `qty` > 0 (in the product's unit); `reference` (text, required, at most 200 characters); `note` (text) | `{reference, move_id, product_id, product_name, qty, uom, unit_cost, total_cost, currency, already_done}` |
| `sso_ticket(login)` | `login` of a user of this site (case does not matter) | `{url: "/site_link/sso/<token>", expires_in: 60}` |
| `user_sync(users)` | `users`: `[{login, name, email, active, shop_access}]` (`shop_access`: true, false or null) | `[{login, user_id, created, updated}]` (and `skipped` for a protected or portal user) |
| `customer_search(query, limit=10)` | `query` (text, 2 characters at least): name, email or phone; `limit` at most 50 | `[{id, name, phone, email}]` |
| `customer_create(name, phone=None, email=None)` | `name` (text), `phone`, `email` | `{id, name, created}` |
| `customer_bikes(partner_id)` | a contact id | `[{id, name, serial}]` (`[]` where no bike model is installed) |
| `repair_quote(reference, partner_id, lines, note=None, bike=None)` | `reference` (text, at most 200 characters); `partner_id`; `lines`: `[{product: id or barcode, qty}]` (parts) and `[{service: name, price, hours}]` (labour); `note` (text); `bike`: a bike id (`customer_bikes`) or a description | `{order_id, name, state, amount_total, currency, portal_url}` |
| `repair_status(reference)` | `reference` | `{name, state, approved, invoiced, paid, amount_total, portal_url}` |
| `repair_invoice(reference)` | `reference` | `{invoice_id, name, state, amount_total, portal_url}` |

- `methods` in `health()` lists what the side offers: always `health`, `sso_ticket`, `customer_search`,
  `customer_create`, `customer_bikes`; `part_lookup` and `part_consume` only where Inventory is installed (elsewhere
  they answer 422 "This site has no Inventory"); `repair_quote`, `repair_status`, `repair_invoice` only where Sales
  is installed (elsewhere 422 "This site has no Sales").
- `part_lookup`: `qty_available` is the quantity on hand in the company's warehouses; `unit_cost` the product's cost;
  `sale_price` its sales price; `vendor` the first vendor on the product (its Purchase tab), or null; `image_url`
  `<site>/web/image/product.product/<id>/image_512` when the product has a picture (it needs a login on that site),
  or null.
- `part_consume`: one validated stock move, from the company's main warehouse stock to the location
  **Internal use (linked sites)** (an inventory-loss location like scrap, made on first use, one per company), the
  move's Source Document = `reference`, its description = `note`. The stock may go below zero (the part was taken).
  `total_cost` is the move's stock value where stock valuation is installed, else cost × qty; `unit_cost` is
  total / qty. Products tracked by lot or serial number, services and combos are refused (422).
  **Idempotent on `reference`**: a second call with the same reference consumes nothing and answers the first
  call's result with `already_done: true` (also when two calls run at the same moment: the second waits, fails to
  serialize, is retried by Odoo and then answers `already_done`). A call that fails consumes nothing and leaves the
  reference free.

- `sso_ticket`: the token is random (32 bytes), only its SHA-256 hash is kept; the link works **once**, within
  **60 seconds**, for an **active internal** user in the group *Site link: single sign-on allowed*, and never for
  user ids 1 and 2 (superuser, admin) or users with Settings or Access Rights rights: otherwise 422 with the
  reason. The same checks run again when the link is
  opened. `GET /site_link/sso/<token>` signs the user in (replacing any other session in that browser; two-factor
  authentication is not asked again: the user is signed in on the other site) and opens `/odoo`; a used, expired or
  unknown link, or a user no longer allowed, opens `/web/login`. Every ticket and sign-in, given or refused, is logged.
- `user_sync`: users matched by login (case does not matter); a missing one is made, as an internal user with no
  password (it signs in by single sign-on; no invitation email), **only when it is active and `shop_access` is
  true**: access to this site comes only with shop access. Otherwise only an existing user is updated; name and email follow; `active: false` archives
  the user here (true brings it back); `shop_access` true gives the group *Site link: single sign-on allowed* and the
  **Shop Access Groups** of this site's linked sites, false takes them away, null leaves them. User ids 1 and 2,
  administrators (Settings or Access Rights rights), the calling user and portal users are never changed (answered
  with `skipped` and the reason); users not in the list are left alone. Shop Access Groups may not be or imply the
  Settings or Access Rights groups (refused when saved).
- `customer_search`: name, email or phone contain the query; a query with 6 digits or more also finds the same phone
  number written another way (spaces, dashes, country code). `customer_create`: when a contact has this email (case
  does not matter) or this phone number (same digits), that contact is answered with `created: false`.
- `customer_bikes`: the bikes of the contact's company and its contacts; `serial` is the frame serial (or the lot).
- `repair_quote`: **one quotation per `reference`** (its Customer Reference). The same call again changes nothing;
  other lines change it while it is a quotation (draft or sent); once accepted (or cancelled) other lines are
  refused (use a new reference) and the same lines answer as before. Parts are priced by the site's prices; each
  labour line is one line at `price` (product "Repair labour", internal reference `SITE_LINK_LABOUR`, made on first
  use), its hours in the description ("Brake bleed (1.5 h)"); a `product` that is a service is a line of that service.
  `note` and a bike description go on the quotation as a note. Where Repair is installed, a repair order of the
  contact holds the parts (Repair puts them on the quotation; the bike is set where the bike model is installed) and
  the labour goes on the quotation (or on the repair's services where another extension adds them). The quotation
  stays a draft: **nothing is sent**, the customer follows nothing; sending stays with the site's own flows. The lines
  of the quotation are the ones sent: lines added on this site are replaced by the next change.
- `repair_status`: `state` is the quotation's (`draft`, `sent`, `sale`, `cancel`); `approved`: accepted (a sales
  order); `invoiced`: it has an invoice (draft or posted); `paid`: all its posted invoices are paid.
- `repair_invoice`: for an accepted quotation only; **one invoice per `reference`** (the same call again answers it;
  an invoice made on this site for that order counts). Where Repair is installed the repair order is finished first
  (its parts leave stock, the quotation's parts count as delivered). The invoice is a **draft**: it is never posted
  or sent here (`name` is null until it is posted; `portal_url` works once it is).
- The repair rows (`site.link.repair`) keep each reference's quotation, repair order and invoice ids; two calls with
  one reference at the same moment wait on that row.

## One employee list and "Log in with your staff account"

On the site whose employees are the list (e.g. the one with the Staff App): its link to the other site gets **Send
Employees**. Its internal users (archived ones too; never ids 1 and 2) go to the other site's `user_sync` on every
change of a user (the cron "Site Link: send employees to linked sites" is run right after), once a day, and with
**Sync employees now** (the result is kept on the link). Skipped when the other site offers no `user_sync`. Another
extension says who is sent and who has shop access by defining `res.users._site_link_employees()` (answering
`[{login, name, email, active, shop_access}]`; no dependency on this connector needed), or by overriding
`site.link._site_link_sync_users_list()`. Default: the internal users with `shop_access` null. User ids 1 and 2 and
the template and public users are never sent, whatever the list. Set Send Employees on one side only.

On the other site: its link back gets the role **Staff accounts** and the **Shop Access Groups**. Its login page then
shows **Log in with your staff account**: `<staff site>/site_link/sso/start?return=<this site's address>` signs the
employee in there (login page first), asks this site for a ticket for that login and sends them back signed in, to
the path of `return`. The staff site checks `return` is on a linked site's address (same scheme, host and port, no
user info: anything else is refused, 403) and that the employee is an internal user; this site opens only its own
paths after the sign-in (`/site_link/sso/<token>?redirect=<path>`, else `/odoo`).

## Tests

`tests/test_call.py` (the helper, HTTP mocked), `tests/test_inventory.py` (lookup, consumption, idempotency; skipped
without Inventory), `tests/test_http_link.py` (the site linked to itself over real HTTP, a real API key),
`tests/test_sso.py` (tickets: once, 60 seconds, who may not; the sign-in link, the start with its return address
check and the login page button over real HTTP),
`tests/test_user_sync.py` (match by login, no-password users, archive, protected users, the sending side),
`tests/test_customers.py`, `tests/test_repair.py` (quotation and invoice once per reference, nothing sent, without
Repair and without Sales; skipped without Sales; the bike test only where a bike model is installed).
