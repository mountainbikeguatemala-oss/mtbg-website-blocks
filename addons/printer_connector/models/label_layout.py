import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# what the label printers' screens read (printer_connector/static/src/label_render.js)
PRINT_FIELDS = (
    "usage", "tape_mm", "length_mm", "min_length_mm", "max_length_mm", "margin_mm", "darkness", "gap_mode",
    "show_barcode", "barcode_height_mm", "bar_module_dots", "barcode_max_mm", "show_code", "code_font_px",
    "code_position", "show_name", "name_font_px", "name_lines", "show_price", "price_font_px", "price_position",
    "font_bold", "logo_position", "logo_height_mm", "logo_rotation",
)

# the fonts a label can use: the ones Odoo itself ships (web/static/fonts, open licences), nothing loaded from
# outside the site; "custom": a font file uploaded on the layout (e.g. a font the business has a licence for)
WEB_FONTS = "/web/static/fonts/"
FONTS = {
    "sans": ("Arial / Helvetica (the device's own)", "Arial, Helvetica, sans-serif", []),
    "roboto": ("Roboto", "Roboto", [(400, "google/Roboto/Roboto-Regular.ttf"), (700, "google/Roboto/Roboto-Bold.ttf")]),
    "montserrat": ("Montserrat", "Montserrat", [(400, "google/Montserrat/Montserrat-Regular.ttf"),
                                                (700, "google/Montserrat/Montserrat-Bold.ttf")]),
    "montserrat_black": ("Montserrat Black", "Montserrat Black", [(400, "google/Montserrat/Montserrat-Black.ttf"),
                                                                  (700, "google/Montserrat/Montserrat-Black.ttf")]),
    "oswald": ("Oswald (tall, condensed)", "Oswald", [(400, "google/Oswald/Oswald-Regular.ttf"),
                                                      (700, "google/Oswald/Oswald-Bold.ttf")]),
    "lato": ("Lato", "Lato", [(400, "lato/Lato-Reg-webfont.ttf"), (700, "lato/Lato-Bol-webfont.ttf")]),
    "raleway": ("Raleway", "Raleway", [(400, "google/Raleway/Raleway-Regular.ttf"),
                                       (700, "google/Raleway/Raleway-Bold.ttf")]),
    "open_sans": ("Open Sans", "Open Sans", [(400, "google/Open_Sans/Open_Sans-Regular.ttf"),
                                             (700, "google/Open_Sans/Open_Sans-Bold.ttf")]),
    "fira_mono": ("Fira Mono (typewriter)", "Fira Mono", [(400, "google/Fira_Mono/Fira_Mono-Regular.ttf"),
                                                          (700, "google/Fira_Mono/Fira_Mono-Bold.ttf")]),
    "khand": ("Khand", "Khand", [(400, "sign/khand.ttf")]),
    "marck_script": ("Marck Script (handwritten)", "Marck Script", [(400, "sign/MarckScript-Regular.ttf")]),
    "shadows_into_light": ("Shadows Into Light (hand lettering)", "Shadows Into Light",
                           [(400, "sign/ShadowsIntoLight-Regular.ttf")]),
    "reenie_beanie": ("Reenie Beanie (handwritten)", "Reenie Beanie", [(400, "sign/ReenieBeanie-Regular.ttf")]),
    "la_belle_aurore": ("La Belle Aurore (signature)", "La Belle Aurore", [(400, "sign/LaBelleAurore-Regular.ttf")]),
    "custom": ("My own font (uploaded below)", "", []),
}


class BsxLabelLayout(models.Model):
    """A label layout for the Bluetooth label printer (MakeID E1): what a label shows, how big, its logo and font.
    Each screen prints with the first active layout of its use (``usage``), else the first "Every screen" one."""

    _name = "bsx.label.layout"
    _description = "Label layout"
    _order = "sequence, id"

    name = fields.Char(required=True, default="Product label")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    usage = fields.Selection([("general", "Every screen (the default)")], string="Used for", default="general",
                             required=True,
                             help="The screens that print with this layout. Extensions add their own uses (e.g. "
                                  "rental bike labels, client name tags); a screen with no layout of its own uses "
                                  "the first \"Every screen\" one.")

    # logo and font
    logo = fields.Image("Logo", max_width=512, max_height=512,
                        help="A small logo (a crown, a mark): printed in black and white, so a plain dark shape on a "
                             "light background prints best.")
    logo_position = fields.Selection([("left", "Left"), ("right", "Right"), ("top", "Above the rest")],
                                     string="Logo position", default="left", required=True)
    logo_height_mm = fields.Float("Logo size (mm)", default=8.0, help="Its height (above the rest: its height too).")
    logo_rotation = fields.Float("Logo rotation (degrees)", default=0.0,
                                 help="Turn the logo a little, e.g. -15 (counter-clockwise) or 10.")
    font = fields.Selection([(key, label) for key, (label, _family, _faces) in FONTS.items()], string="Font",
                            default="sans", required=True,
                            help="The font of the label's text. The fonts come with Odoo; \"My own font\" uses the "
                                 "font file uploaded on this layout.")
    font_file = fields.Binary("Font file", attachment=True,
                              help="A .ttf, .otf or .woff font file (one the business may use), for \"My own font\".")
    font_file_name = fields.Char("Font file name")

    # the label
    tape_mm = fields.Float("Print height (mm)", default=12.0,
                           help="Height of the printed area across the tape. The E1 head prints at most 12 mm.")
    length_mm = fields.Float("Label length (mm)", default=0.0,
                             help="Fixed length of every label. 0 = as long as the content needs, between the "
                                  "minimum and maximum below. The E1 cuts each label at the printed length.")
    min_length_mm = fields.Float("Minimum length (mm)", default=25.0)
    max_length_mm = fields.Float("Maximum length (mm)", default=60.0)
    margin_mm = fields.Float("Side margin (mm)", default=0.5,
                             help="Blank space inside the label ends. The printer adds its own ~1.5 mm border.")
    gap_mode = fields.Selection([("gap", "Die-cut labels (gap between labels)"), ("continuous", "Continuous tape")],
                                string="Label roll", default="gap", required=True)
    darkness = fields.Integer("Darkness", default=15, help="1 (light) to 31 (dark). The MakeID app uses 15.")

    # barcode
    show_barcode = fields.Boolean("Barcode", default=True)
    barcode_height_mm = fields.Float("Barcode height (mm)", default=7.0)
    bar_module_dots = fields.Integer("Bar width (dots)", default=3,
                                     help="Width of the thinnest bar, in printer dots (0.125 mm). Wider bars scan "
                                          "more easily; it is reduced automatically when the code is too long.")
    barcode_max_mm = fields.Float("Barcode max length (mm)", default=40.0,
                                  help="The bars get thinner (down to 1 dot) to keep the barcode this short.")
    show_code = fields.Boolean("Code in text", default=False)
    code_position = fields.Selection([("below", "Under the barcode"), ("right", "Right of the barcode")],
                                     string="Code position", default="below", required=True)
    code_font_px = fields.Integer("Code text size", default=14)

    # name and price
    show_name = fields.Boolean("Product name", default=True)
    name_font_px = fields.Integer("Name text size", default=18)
    name_lines = fields.Integer("Name lines", default=1)
    show_price = fields.Boolean("Price", default=True)
    price_font_px = fields.Integer("Price text size", default=20)
    price_position = fields.Selection([("below", "Under the name"), ("right", "Right of the name")],
                                      string="Price position", default="right", required=True)
    font_bold = fields.Boolean("Bold name", default=True)

    # the label's items, placed with the drag and drop editor (empty: made from the settings below, as before 1.2.0):
    # {"rows": [{"uid", "left": [item], "center": [item], "right": [item]}]} top to bottom (1.2.0's {"left", "center",
    # "right"} is still read); an item {"uid", "field": logo | barcode | code | name | price, "size" (logo / barcode:
    # mm; text: px), "bold", "lines" (name), "rotation", "pad_top" / "pad_right" / "pad_bottom" / "pad_left" (logo, mm)}
    elements = fields.Text("Items")

    # preview sample (not printed on real labels)
    sample_name = fields.Char("Sample product", default="Trail helmet, size M")
    sample_code = fields.Char("Sample code", default="7501234567890")
    sample_price = fields.Char("Sample price", default="Q 1,250.00")

    @api.constrains("tape_mm", "darkness", "name_lines", "bar_module_dots", "min_length_mm", "max_length_mm",
                    "length_mm", "margin_mm", "barcode_height_mm", "barcode_max_mm", "code_font_px", "name_font_px",
                    "price_font_px", "logo_height_mm", "logo_rotation")
    def _check_ranges(self):
        for layout in self:
            if not 3 <= layout.tape_mm <= 12:
                raise ValidationError(_("The print height must be between 3 and 12 mm."))
            if not 1 <= layout.darkness <= 31:
                raise ValidationError(_("Darkness goes from 1 to 31."))
            if not 1 <= layout.name_lines <= 3:
                raise ValidationError(_("The name takes 1 to 3 lines."))
            if not 1 <= layout.bar_module_dots <= 6:
                raise ValidationError(_("The bar width goes from 1 to 6 dots."))
            if layout.length_mm < 0 or layout.length_mm > 200:
                raise ValidationError(_("The label length goes up to 200 mm (0 = automatic)."))
            if not 10 <= layout.min_length_mm <= layout.max_length_mm <= 200:
                raise ValidationError(_("The minimum length must be at least 10 mm and not above the maximum "
                                        "(200 mm at most)."))
            if not 10 <= layout.barcode_max_mm <= 200:
                raise ValidationError(_("The barcode max length goes from 10 to 200 mm."))
            if layout.margin_mm < 0 or layout.barcode_height_mm < 2:
                raise ValidationError(_("The margin can't be negative and the barcode is at least 2 mm high."))
            if min(layout.code_font_px, layout.name_font_px, layout.price_font_px) < 8:
                raise ValidationError(_("Text sizes start at 8."))
            if not 2 <= layout.logo_height_mm <= 12:
                raise ValidationError(_("The logo size goes from 2 to 12 mm."))
            if not -90 <= layout.logo_rotation <= 90:
                raise ValidationError(_("The logo turns at most 90 degrees either way."))

    def _unique(self):
        """The last change, digits only: a new address for the logo / font file after each change."""
        return "".join(ch for ch in (fields.Datetime.to_string(self.write_date) or "") if ch.isdigit())

    def _font_dict(self):
        """{family, faces: [{weight, url}]}: what the screen loads before it draws (a family the device has: none)."""
        self.ensure_one()
        if self.font == "custom":
            if not self.id or not self.font_file:
                return {"family": FONTS["sans"][1], "faces": [], "missing": True}
            url = f"/web/content/bsx.label.layout/{self.id}/font_file?unique={self._unique()}"
            family = f"Label Font {self.id}"
            return {"family": family, "faces": [{"weight": 400, "url": url}, {"weight": 700, "url": url}]}
        _label, family, faces = FONTS.get(self.font) or FONTS["sans"]
        return {"family": family, "faces": [{"weight": weight, "url": WEB_FONTS + path} for weight, path in faces]}

    def _print_dict(self):
        self.ensure_one()
        logo_url = ""
        if self.id and self.logo:
            logo_url = f"/web/image/bsx.label.layout/{self.id}/logo?unique={self._unique()}"
        try:
            elements = json.loads(self.elements) if self.elements else None
        except ValueError:
            elements = None
        return {name: self[name] for name in PRINT_FIELDS} | {
            "id": self.id, "name": self.name, "logo_url": logo_url, "font_spec": self._font_dict(),
            "elements": elements if isinstance(elements, dict) else None}

    @api.model
    def get_print_layout(self, usage=None):
        """The layout a screen prints with: the first active one for ``usage``, else the first "Every screen" one,
        else the first one (a default one when there is none)."""
        layout = self.browse()
        if usage:
            layout = self.search([("usage", "=", usage)], limit=1)
        layout = layout or self.search([("usage", "=", "general")], limit=1) or self.search([], limit=1)
        if not layout:
            return self.new({})._print_dict() | {"id": False}
        return layout._print_dict()

    @api.model
    def get_font_specs(self):
        """{font key: {family, faces}} of the fonts that come with Odoo (the layout page's preview)."""
        return {key: {"family": family, "faces": [{"weight": w, "url": WEB_FONTS + p} for w, p in faces]}
                for key, (_label, family, faces) in FONTS.items() if key != "custom"}
