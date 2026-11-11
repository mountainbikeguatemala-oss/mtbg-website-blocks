{
    "name": "Meta Connector",
    "version": "19.0.1.4.1",
    "category": "Productivity/Connectors",
    "summary": "One Facebook login for every app using your Facebook Pages and Instagram accounts: setup, Pages and "
               "tokens, webhook; the website's Instagram Feed block",
    "description": """
One Meta connection for the apps that use Facebook Pages and Instagram accounts, like the Google connector does for
Google:

* Set up Meta (Settings › Meta): a step-by-step setup, the only place Meta keys are entered (your own Meta app, the
  Facebook login, the Pages and Instagram accounts this site uses). The login and the Pages' tokens are checked
  every day.
* One webhook address for every app; apps (e.g. Communication Flows' Messenger and Instagram channels) plug in.
* Settings › Meta: an Instagram and a Facebook block, each with its status and its uses switched on or off (the
  Feed block here; Communication Flows' chat and contact photos when its channel is installed), and a WhatsApp
  block when Communication Flows' WhatsApp Cloud channel is installed (its numbers can send with this login).
* Instagram Feed: a website block with your latest Instagram posts, kept here as light WebP copies and refreshed
  every hour (a page view never calls Instagram), in the colours of the section it sits in. Its options (website
  editor): header (profile photo, @username, name, followers and posts), number of posts, grid with its columns on
  desktop and on phone, or one row, tile shape and corners, spacing, max width, Follow button.
* Posting (for apps, e.g. Marketing; off by default): with Marketing installed, Set up Meta's Posting step (the
  use cases, the Instagram account linked, the permissions checked green / red) and the login's posting
  permissions; ``_meta_post(kind, caption, image_url)`` posts a picture with its caption on the Facebook Page or
  the Instagram account. Its permissions need Meta's app review.
* Secrets stay with administrators and are cleared on a copy of the site (neutralize).
""",
    "author": "MTBG Tours contributors",
    "license": "LGPL-3",
    "mtbg_github_source": {"repo": "git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git", "subdir": "addons"},
    "depends": ["base_setup", "web", "website"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/app_views.xml",
        "views/snippets.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "meta_connector/static/src/feed/feed.js",
            "meta_connector/static/src/feed/feed.scss",
        ],
        "website.assets_inside_builder_iframe": [
            "meta_connector/static/src/feed/feed.edit.js",
        ],
        "website.website_builder_assets": [
            "meta_connector/static/src/website_builder/**/*",
        ],
    },
    "installable": True,
}
