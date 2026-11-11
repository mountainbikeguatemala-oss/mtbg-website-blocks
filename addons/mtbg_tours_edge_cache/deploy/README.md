# Keeping the site up during updates (Edge Cache 0.6.7)

Owner question, 2026-11-08: "is there anyway to keep the site live while we do backend updates? is it nessecary to
bring the entire site down to update extensions?"

During an update Odoo is unavailable for a few minutes: first while it upgrades the database (Updates answers its
own 503 "Updating"), then while it restarts (nothing answers, so Cloudflare shows a raw 502). With this:

| Who asks | During the update |
|---|---|
| A visitor on a page Cloudflare keeps (home, /es, tours, regions, blog, pages) | The page, from Cloudflare, as usual. A kept page whose time ran out is still answered (stale-if-error, up to a week). Prices and seats are live: they fill once the site is back. |
| A visitor on anything else (booking, checkout and payment, forms, the chat, a page not kept yet) | This folder's holding page: English and Spanish, the logo, "back in about 2 minutes"; HTTP 503 with Retry-After: 120 (search engines come back later, nothing is lost). It reloads by itself once the site answers. |
| You in the back office | The same holding page. The updater's own progress screen keeps working while it runs. |

Cloudflare's Free plan cannot replace its own 5xx pages (custom error pages are a paid feature), so the holding page
is served by nginx on the server.

## Owner steps

### 1. Cloudflare (dashboard › example.com)
1. **Caching › Configuration › Always Online:** turn it **off** if it is on. While it is on, Cloudflare ignores
   stale-if-error (it serves the Internet Archive's copy instead).
2. **Caching › Cache Rules › "Odoo: public pages":** nothing to change. Its Edge TTL already follows Odoo's
   Cache-Control header, which now carries `stale-if-error=604800`. If the rule shows "Serve stale content while
   revalidating", leave it as it is.

### 2. The server (mtbg-new), from your computer
1. Copy the page:
   ```
   ssh mtbg-new 'sudo mkdir -p /var/www/mtbg-updating'
   scp <this folder>/updating.html mtbg-new:/tmp/mtbg-updating.html
   ssh mtbg-new 'sudo mv /tmp/mtbg-updating.html /var/www/mtbg-updating/ && sudo chmod 644 /var/www/mtbg-updating/mtbg-updating.html'
   ```
2. Edit the site's nginx file (`sudo nano /etc/nginx/sites-available/<your site>`). In the HTTPS
   `server { ... }` block for www.example.com:
   - paste the `error_page` line and the `location = /mtbg-updating.html { ... }` block from
     `nginx-updating.conf`, next to the existing `location / {`;
   - inside `location / { ... }` (the one with `proxy_pass`), add the line `proxy_intercept_errors on;`.
3. Check, then reload (no restart, nobody is cut off):
   ```
   sudo nginx -t && sudo systemctl reload nginx
   ```
   If `nginx -t` reports an error, nothing changed: fix the edit or remove it.

### 3. Check
- `curl -sI https://www.example.com/` still answers 200, and `curl -sI https://www.example.com/shop`
  (a page Cloudflare does not keep) too.
- During the next Update all, open a booking page in a private window: the holding page, then the page itself
  once the update is done. `curl -sI` on it during the update shows `503` and `retry-after: 120`.

### Undo
Remove the added lines, then `sudo nginx -t && sudo systemctl reload nginx`.
