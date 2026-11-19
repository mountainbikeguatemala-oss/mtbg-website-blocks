from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# what the label printers' screens read (printer_connector/static/src/label_render.js)
PRINT_FIELDS = (
    "tape_mm", "length_mm", "min_length_mm", "max_length_mm", "margin_mm", "darkness", "gap_mode",
    "show_barcode", "barcode_height_mm", "bar_module_dots", "barcode_max_mm", "show_code", "code_font_px",
    "show_name", "name_font_px", "name_lines", "show_price", "price_font_px", "price_position", "font_bold",
)


class BsxLabelLayout(models.Model):
    """Product label layout for the Bluetooth label printer (MakeID E1): what a label shows and how big.
    The first active layout is the one the shop screens print with."""

    _name = "bsx.label.layout"
    _description = "Label layout"
    _order = "sequence, id"

    name = fields.Char(required=True, default="Product label")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

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
    show_code = fields.Boolean("Code under the barcode", default=False)
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

    # preview sample (not printed on real labels)
    sample_name = fields.Char("Sample product", default="Trail helmet, size M")
    sample_code = fields.Char("Sample code", default="7501234567890")
    sample_price = fields.Char("Sample price", default="Q 1,250.00")

    @api.constrains("tape_mm", "darkness", "name_lines", "bar_module_dots", "min_length_mm", "max_length_mm",
                    "length_mm", "margin_mm", "barcode_height_mm", "barcode_max_mm", "code_font_px", "name_font_px", "price_font_px")
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

    def _print_dict(self):
        self.ensure_one()
        return {name: self[name] for name in PRINT_FIELDS} | {"id": self.id, "name": self.name}

    @api.model
    def get_print_layout(self):
        """The layout the shop screens print with: the first active one (a default one when there is none)."""
        layout = self.search([], limit=1)
        if not layout:
            return self.new({})._print_dict() | {"id": False}
        return layout._print_dict()
