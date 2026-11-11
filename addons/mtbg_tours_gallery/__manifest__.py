{
    'name': 'MTBG Website — Tiled Gallery',
    'version': '19.0.0.6.1',
    # where the updater gets it (the website blocks pack's repo; owner, 2026-11-11: universal, from the Tours repo)
    'mtbg_github_source': {'repo': 'git@github.com:mountainbikeguatemala-oss/mtbg-website-blocks.git', 'subdir': 'addons'},
    # its section on the Extensions panel: Custom blocks (its main job is website editor blocks)
    'mtbg_tours_section': 'blocks',
    'category': 'Website',
    'summary': 'Tiled photo galleries (Jetpack "rectangular" style) for any website page, WebP-ready',
    'description': """
Photo galleries laid out like the old site's Jetpack Tiled Gallery: rows of one big photo beside two stacked ones,
then pairs, every photo cropped to fill its tile. Any Odoo website (no Tours needed).

* "Tiled Gallery" website block (inner content): pictures chosen in the editor, or a record's own gallery that another
  module offers (Tours: "A tour's gallery", searchable, the tour page's own tour first, "Add" puts pictures into the
  tour's gallery); options: the photos, rounded corners and spacing in px.
* Row heights and column widths kept within limits (the big photo takes 55-70 % of its row); phones get simpler rows.
* Focus point per photo (a form widget for a picture's mtbg_focus_x / y): every gallery crops around it.
* One full-screen lightbox for the page's photos (the website blocks base's shared viewer, PhotoSwipe 5): the Tiled
  Gallery photos, a page's own photos where it names them (data-mtbg-lightbox-photos), marked photo sets. Edge to
  edge, swipes follow the finger, pinch and double-tap zoom, swipe down to close, caption, "3 / 15"; full size.
* Laid out on the server from the photos' stored sizes, so nothing moves while they load; loaded when the page scrolls
  near the block.
* WebP: Odoo does not resize WebP, so the tiles use the pictures' screen-sized copies ("resize: 480/800/1280",
  made when a module adds a photo to a record's gallery, e.g. a tour's); JPEG and PNG are resized by Odoo.

Other modules offer record galleries through mtbg.gallery (_mtbg_gallery_sources, _mtbg_record_items,
_mtbg_record_add).
""",
    'author': 'MTBG Tours contributors',
    'license': 'LGPL-3',
    'depends': ['website', 'mtbg_tours_content_blocks'],
    # the shared photo viewer (@mtbg_tours_content_blocks/shared/lightbox, 0.11.1)
    'mtbg_tours_requires': {'mtbg_tours_content_blocks': '19.0.0.11.1'},
    'data': [
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'mtbg_tours_gallery/static/src/gallery/gallery.js',
            'mtbg_tours_gallery/static/src/gallery/gallery.scss',
            # the viewer is the base's shared one (@mtbg_tours_content_blocks/shared/lightbox), loaded on the first touch
            'mtbg_tours_gallery/static/src/lightbox/page_lightbox.js',
            'mtbg_tours_gallery/static/src/lightbox/page_lightbox.scss',
        ],
        'website.assets_inside_builder_iframe': [
            'mtbg_tours_gallery/static/src/gallery/gallery.edit.js',
        ],
        'website.website_builder_assets': [
            'mtbg_tours_gallery/static/src/website_builder/**/*',
        ],
        'web.assets_backend': [
            'mtbg_tours_gallery/static/src/focus_point/*',
        ],
    },
    'installable': True,
}
