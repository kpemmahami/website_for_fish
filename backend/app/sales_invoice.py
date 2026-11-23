"""Printable invoice for an already recorded sale."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .loan_appraisal_pdf import monetary


def build_invoice_pdf(farm, customer, sale):
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, title=sale['invoice_number'])
    body = ParagraphStyle('invoice_body', fontName='Appraisal', fontSize=10, leading=15)
    heading = ParagraphStyle('invoice_heading', parent=body, fontName='Appraisal-Bold', fontSize=20, leading=24)
    def paragraph(value, style=body):
        return Paragraph(escape(str(value)), style)

    rows = [
        ('Product', sale.get('product','Harvested fish')), ('Quantity', f'{sale["quantity_kg"]:g} kg'),
        ('Price per package' if sale.get('packages_sold') else 'Price per kg',
         monetary(sale.get('price_ghs_per_package',sale['price_ghs_per_kg']))), ('Invoice total', monetary(sale['total_ghs'])),
        ('Amount paid', monetary(sale['paid_ghs'])), ('Outstanding balance', monetary(sale['outstanding_ghs'])),
        ('Payment status', sale['payment_status'].capitalize()),
    ]
    if sale.get('packages_sold'):
        rows[1:1] = [('Lot', sale['lot_reference']), ('Packages', sale['packages_sold'])]
    table = Table([[paragraph(value) for value in row] for row in rows], colWidths=[155, doc.width - 155])
    table.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#edf5f1'), colors.white]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    doc.build([
        paragraph('AquaFarm Manager Ghana'), Spacer(1, 16), paragraph('Invoice', heading),
        paragraph(sale['invoice_number']), paragraph(f'Invoice date: {sale["sold_on"]}'),
        Spacer(1, 16), paragraph(f'{"Business" if sale.get("packages_sold") else "Farm"}: {farm.name}'), paragraph(f'Customer: {customer.name}'),
        Spacer(1, 16), table,
    ])
    return stream.getvalue()
