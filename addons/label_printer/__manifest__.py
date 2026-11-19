{
    "name": "Label Printer",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "summary": "Print barcode labels from the browser on a Bluetooth label printer (MakeID E1): a label layout page "
               "with a live preview, and a Print label button any screen can use",
    "description": """
Barcode labels straight from Odoo to a MakeID label printer (E1 and the other models on the same protocol) over
Web Bluetooth: Chrome on Android, Windows, macOS, Linux (with Bluetooth on) or ChromeOS; not iPhone / iPad.

* Settings › Label layout (``bsx.label.layout``): print height, label length (automatic or fixed), margins,
  darkness, label roll (die-cut or continuous); barcode height, bar width and max length (40 mm), the code under it;
  name size and lines, price size and position. Live preview at real size and "Print a test label". The first
  active layout is the one every screen prints with.
* Code 128 barcodes (code set C for digit runs: the shortest barcode for a code).
* For other screens (JavaScript, ``@label_printer/label_print``): ``<LabelPrintButton product="{name, barcode,
  default_code, price_display}"/>`` (Print label + copies; the barcode is ``barcode`` or else ``default_code``),
  ``printProductLabels(orm, item, copies)``, ``renderLabel`` / ``labelRows`` and the printer itself
  (``@label_printer/makeid_printer``: status, chunks, the printer's own head width and chunk size).
* The protocol (from the MakeID-Life app, checked on an E1): BLE service ``abf0`` (write ``abf1``, notify
  ``abf2``), status ``66 06 00 10 00 84``, one ``0x1B`` frame per chunk of rows (1 bit per dot, LZO1X stream),
  the printer's status after every frame. See README.md.
""",
    "author": "MTBG Tours contributors",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/label_layout_data.xml",
        "views/label_layout_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "label_printer/static/src/code128.js",
            "label_printer/static/src/label_render.js",
            "label_printer/static/src/makeid_printer.js",
            "label_printer/static/src/label_print.js",
            "label_printer/static/src/label_print.xml",
            "label_printer/static/src/label_print.css",
        ],
    },
    "pre_init_hook": "pre_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
