# Site Link Connector

Links two Odoo 19 sites of one business. Each side calls the other through Odoo's own external API
(`POST /json/2/<model>/<method>`, part of Odoo: the `rpc` module), with the API key of a technical user on the other
side as a bearer token and the database in the `X-Odoo-Database` header. No dependency on any other extension; the
inventory methods are offered only where Inventory (`stock`) is installed (soft check).

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

The API keys are only readable by administrators; a neutralized copy of a site has its keys removed and its links
archived.

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

## The protocol: `site.link.api`

Called as `POST /json/2/site.link.api/<method>` with a JSON body of named arguments. The caller (the API key's user)
needs the group *Site Link: calls from a linked site* (or to be an administrator), otherwise 403.

| Method | Arguments | Answer |
|---|---|---|
| `health()` | none | `{protocol: 1, module: "site_link_connector", module_version, odoo_version, database, user, company, methods: [...]}` |
| `part_lookup(barcode)` | `barcode` (text) | not found: `{found: false, barcode}`; found: `{found: true, id, name, default_code, barcode, qty_available, uom, unit_cost, sale_price, currency, vendor, image_url}` |
| `part_consume(product, qty, reference, note=None)` | `product`: product id (number) or barcode (text); `qty` > 0 (in the product's unit); `reference` (text, required, at most 200 characters); `note` (text) | `{reference, move_id, product_id, product_name, qty, uom, unit_cost, total_cost, currency, already_done}` |

- `methods` in `health()` lists what the side offers: always `health`; `part_lookup` and `part_consume` only where
  Inventory is installed (elsewhere they answer 422 "This site has no Inventory").
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

## Tests

`tests/test_call.py` (the helper, HTTP mocked), `tests/test_inventory.py` (lookup, consumption, idempotency; skipped
without Inventory), `tests/test_http_link.py` (the site linked to itself over real HTTP, a real API key).
