"""0.10.0: each row names its website (several websites on one database: each measured on its own). The rows logged
before get the website at their address' host, else the first website (the only one measured until now)."""
from urllib.parse import urlsplit


def _host(value):
    value = (value or '').strip().lower()
    return urlsplit(value if '://' in value else '//' + value).hostname or ''


def migrate(cr, version):
    cr.execute("SELECT id, domain FROM website ORDER BY sequence, id")
    websites = cr.fetchall()
    if not websites:
        return
    for website_id, domain in websites:
        host = _host(domain)
        if host:
            cr.execute("""UPDATE mtbg_page_speed_log SET website_id = %s
                           WHERE website_id IS NULL AND lower(substring(url from '^[a-zA-Z]+://([^/:?#]+)')) = %s""",
                       (website_id, host))
    cr.execute("UPDATE mtbg_page_speed_log SET website_id = %s WHERE website_id IS NULL", (websites[0][0],))
