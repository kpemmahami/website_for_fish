"""Render the immutable appraisal snapshot as a paginated A4 document."""

from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
import os

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def report_fonts():
    windows = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    linux = Path('/usr/share/fonts/truetype/dejavu')
    bundled = Path(reportlab.__file__).parent / 'fonts'
    for regular, bold in (
        (windows / 'arial.ttf', windows / 'arialbd.ttf'),
        (linux / 'DejaVuSans.ttf', linux / 'DejaVuSans-Bold.ttf'),
        (bundled / 'Vera.ttf', bundled / 'VeraBd.ttf'),
    ):
        if regular.is_file() and bold.is_file():
            normal = TTFont('Appraisal', str(regular))
            pdfmetrics.registerFont(normal)
            pdfmetrics.registerFont(TTFont('Appraisal-Bold', str(bold)))
            return 'GH' + chr(0x20B5) if 0x20B5 in normal.face.charWidths else 'GHS '
    raise RuntimeError('No appraisal report fonts are installed')


CURRENCY = report_fonts()
MISSING = 'Not provided'


def display(value):
    return MISSING if value is None or value == '' else str(value)


def monetary(value):
    return MISSING if value is None else f'{CURRENCY}{Decimal(str(value)):,.2f}'


def status(value):
    return display(value).replace('_', ' ').capitalize()


def quantity(value, unit=''):
    return MISSING if value is None else f'{value:,}{unit}'


def build_appraisal_pdf(application, snapshot, institution_name):
    stream = BytesIO()
    reference = application['reference']
    document = SimpleDocTemplate(
        stream, pagesize=A4, title='Farmer Loan Application and Farm Appraisal Report',
        author='AquaFarm Manager Ghana', leftMargin=42, rightMargin=42, topMargin=42, bottomMargin=44,
    )
    green, ink = colors.HexColor('#164B3F'), colors.HexColor('#243731')
    body = ParagraphStyle('report_body', fontName='Appraisal', fontSize=9, leading=13, textColor=ink)
    heading = ParagraphStyle('report_heading', parent=body, fontName='Appraisal-Bold', fontSize=12,
                             leading=16, textColor=green, spaceBefore=14, spaceAfter=6, keepWithNext=True)
    title = ParagraphStyle('report_title', parent=heading, fontSize=19, leading=23)
    header = ParagraphStyle('report_table_header', parent=body, fontName='Appraisal-Bold', textColor=colors.white)
    story = []

    def cell(value, style=body):
        return Paragraph(escape(display(value)).replace('\n', '<br/>'), style)

    def paragraph(value, style=body):
        story.append(cell(value, style))

    def table(labels, rows, widths=None, empty='No records in this snapshot.'):
        if not rows:
            paragraph(empty)
            return
        if widths is None:
            widths = [document.width / len(labels)] * len(labels)
        data = [[cell(label, header) for label in labels]]
        data.extend([[cell(value) for value in row] for row in rows])
        result = LongTable(data, colWidths=widths, repeatRows=1, splitInRow=1, hAlign='LEFT')
        result.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), green),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#EDF5F1')]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.extend([result, Spacer(1, 5)])

    def details(rows):
        table(['Field', 'Recorded value'], rows, [document.width * .40, document.width * .60])

    farmer = snapshot.get('farmer') or {}
    farm = snapshot.get('farm') or {}
    production = snapshot.get('production') or {}
    feed = snapshot.get('feed') or {}
    feed_costs = snapshot.get('feed_costs') or {}
    sales = snapshot.get('sales') or {}
    costs = snapshot.get('costs') or {}
    cash = snapshot.get('cash_flow') or {}
    completeness = snapshot.get('appraisal_data_completeness') or {}
    evidence = snapshot.get('application_video_evidence') or {}

    paragraph('AQUAFARM MANAGER GHANA', heading)
    paragraph('FARMER LOAN APPLICATION AND FARM APPRAISAL REPORT', title)
    paragraph(reference + '  |  PDF generated ' + datetime.now(timezone.utc).strftime('%d %b %Y UTC'))
    paragraph('A. Loan application details', heading)
    details([
        ('Application reference', reference), ('Application date', str(application['created_at'])[:10]),
        ('Application status', status(application['status'])), ('Requested amount', monetary(application['requested_ghs'])),
        ('Loan purpose', application['purpose']), ('Requested loan period', quantity(application['term_months'], ' months')),
        ('Selected institution', institution_name),
        ('Farmer-declared other monthly income', monetary(cash.get('farmer_declared_monthly_other_income_ghs'))),
    ])
    paragraph('B. Farmer information', heading)
    details([('Full name', farmer.get('full_name')), ('Authorized email', farmer.get('email')),
             ('Authorized phone', farmer.get('phone_number')), ('Farm association', farmer.get('farm_association'))])
    paragraph('C. Farm information', heading)
    details([
        ('Farm name', farm.get('name')), ('Region', farm.get('region')), ('District', farm.get('district')),
        ('Farm type', status(farm.get('farm_type'))), ('Fish species', farm.get('species')),
        ('Production units', production.get('total_units')), ('Active units', production.get('active_units')),
        ('Production cycles', production.get('total_cycles')), ('Active cycles', production.get('active_cycles')),
    ])
    paragraph('D. Production history', heading)
    cycles = snapshot.get('production_history') or []
    if not cycles:
        paragraph('No production cycles recorded.')
    for cycle in cycles:
        paragraph(display(cycle.get('production_unit')) + ' | ' + display(cycle.get('species')), heading)
        details([
            ('Stocking date', cycle.get('stocked_on')), ('Planned harvest date', cycle.get('planned_harvest_on')),
            ('Fingerlings stocked', cycle.get('fingerlings_stocked')), ('Initial average weight', quantity(cycle.get('initial_average_weight_g'), ' g')),
            ('Latest average weight', quantity(cycle.get('latest_average_weight_g'), ' g')),
            ('Weight sample date', cycle.get('latest_sampled_on')), ('Estimated surviving fish', cycle.get('estimated_live_fish')),
            ('Recorded mortality', cycle.get('cumulative_mortality')), ('Recorded harvested fish', cycle.get('total_harvested_fish')),
            ('Estimated biomass', quantity(cycle.get('estimated_live_biomass_kg'), ' kg')),
            ('Estimated survival', quantity(cycle.get('estimated_survival_pct'), '%')),
        ])
        samples = cycle.get('sampling_history') or []
        if samples:
            table(['Sample date', 'Fish sampled', 'Recorded mean weight'],
                  [(x.get('sampled_on'), x.get('sample_count'), quantity(x.get('average_weight_g'), ' g')) for x in samples])
        harvests = cycle.get('harvests') or []
        if harvests:
            table(['Harvest date', 'Fish harvested', 'Recorded harvest weight'],
                  [(x.get('harvested_on'), x.get('fish_count'), quantity(x.get('quantity_kg'), ' kg')) for x in harvests])
    estimates = snapshot.get('production_estimates') or []
    if estimates:
        table(['Production plan', 'Species', 'Projected harvest', 'Projected revenue'], [
            (row.get('plan_id'), row.get('species'), quantity(row.get('expected_harvest_kg'), ' kg'),
             monetary(row.get('expected_revenue_ghs'))) for row in estimates
        ])
    paragraph('E. Feed inventory and feed costs', heading)
    inventory = {}
    for entry in feed.get('by_product') or []:
        name = entry.get('name')
        inventory[name] = None if name in inventory else entry.get('stock_kg')
    products = feed_costs.get('by_product') or []
    details([
        ('Total feed inventory', quantity(feed.get('remaining_stock_kg'), ' kg')),
        ('Total recorded feed consumption', quantity(feed.get('consumed_kg'), ' kg')),
        ('Recorded feed purchases', monetary(sum(Decimal(str(row['purchase_cash_outflow_ghs'])) for row in products
                                                 if row.get('purchase_cash_outflow_ghs') is not None)) if products else MISSING),
        ('Estimated consumed feed cost', monetary(feed_costs.get('estimated_consumed_feed_cost_ghs'))),
    ])
    for entry in products:
        name = entry.get('feed_product')
        paragraph(name, heading)
        details([
            ('Received', quantity(entry.get('received_kg'), ' kg')), ('Consumed', quantity(entry.get('consumed_kg'), ' kg')),
            ('Remaining', quantity(inventory.get(name), ' kg')),
            ('Purchase cash outflow', monetary(entry.get('purchase_cash_outflow_ghs'))),
            ('Estimated consumed feed cost', monetary(entry.get('estimated_consumed_cost_ghs'))),
            ('Valuation method', entry.get('consumption_valuation')),
        ])
    if feed_costs.get('note'):
        paragraph(feed_costs['note'])
    paragraph('F. Sales and financial performance', heading)
    if sales.get('sales_count') == 0:
        paragraph('No sales recorded.')
    details([
        ('Recorded sales', sales.get('sales_count')), ('Harvested weight', quantity(sales.get('harvested_kg'), ' kg')),
        ('Fish sold', quantity(sales.get('sold_kg'), ' kg')),
        ('Invoiced revenue', monetary(sales.get('invoiced_sales_revenue_ghs', sales.get('invoiced_revenue_ghs')))),
        ('Payments received', monetary(sales.get('payments_received_ghs'))),
        ('Outstanding receivables', monetary(sales.get('outstanding_customer_credit_ghs', sales.get('outstanding_receivables_ghs')))),
        ('Recorded production costs', monetary(costs.get('recorded_costs_to_date_ghs'))),
    ])
    table(['Operating expense category', 'Recorded cost'], [
        (status(name), monetary(amount)) for name, amount in
        (feed_costs.get('recorded_operating_expenses_by_category_ghs') or {}).items()
    ])
    paragraph('G. Historical cash flow', heading)
    if not completeness.get('recent_cashflow_transaction_count'):
        paragraph('The snapshot contains insufficient recorded transaction activity to substantiate historical cash flow.')
    table(['Month', 'Sale payments', 'Feed purchases', 'Operating costs', 'Net cash flow'], [
        (row.get('month'), *(monetary(row.get(field)) for field in
          ('sales_payments_received_ghs', 'feed_purchase_cash_outflow_ghs',
           'recorded_operating_expenses_ghs', 'net_recorded_operating_cashflow_ghs')))
        for row in cash.get('historical_months') or []
    ])
    paragraph('H. Projected cash flow and repayment capacity', heading)
    details([
        ('Farmer-declared monthly other income', monetary(cash.get('farmer_declared_monthly_other_income_ghs'))),
        ('Farmer-declared monthly household expenses', monetary(cash.get('farmer_declared_monthly_household_expenses_ghs'))),
        ('Farmer-declared monthly external debt payments', monetary(cash.get('farmer_declared_monthly_external_debt_payments_ghs'))),
        ('Estimated monthly surplus', monetary(cash.get('estimated_monthly_surplus_after_obligations_ghs'))),
        ('Indicative monthly repayment capacity', monetary(cash.get('estimated_monthly_repayment_capacity_ghs'))),
        ('Principal-only monthly illustration, excluding interest and fees', monetary(cash.get('requested_principal_divided_by_term_ghs'))),
    ])
    table(['Month', 'Assumed farm cash flow', 'Scheduled loan repayments', 'Projected net after obligations'], [
        (row.get('month'), *(monetary(row.get(field)) for field in (
            'assumed_farm_operating_cashflow_ghs', 'tracked_loan_scheduled_payments_ghs',
            'projected_net_cashflow_after_obligations_ghs')))
        for row in cash.get('projected_months') or []
    ])
    paragraph('I. Existing loans and obligations', heading)
    table(['Tracked loan', 'Status', 'Outstanding principal', 'Scheduled balance', 'Overdue'], [
        (loan.get('loan_id'), status(loan.get('status')), monetary(loan.get('outstanding_principal_ghs')),
         monetary(loan.get('total_scheduled_balance_ghs')), monetary(loan.get('overdue_scheduled_amount_ghs')))
        for loan in snapshot.get('existing_loans') or []
    ], empty='No existing loans recorded in AquaFarm Manager Ghana.')
    paragraph('J. Data completeness', heading)
    declarations = [('External income information', 'external_income_provided'),
                    ('Household expenses', 'household_expenses_provided'),
                    ('External debt obligations', 'external_debt_obligations_provided')]
    counts = [('Production plans', 'production_plan_count'), ('Tracked loans', 'tracked_loan_count'),
              ('Recorded sales', 'sales_count'), ('Recorded customer payments', 'sales_payment_count'),
              ('Recent cash-flow transactions', 'recent_cashflow_transaction_count')]
    details([(label, 'Provided' if completeness.get(key) is True else MISSING) for label, key in declarations]
            + [(label, 'No records' if completeness.get(key) == 0 else display(completeness.get(key))) for label, key in counts])
    paragraph('K. Application evidence', heading)
    evidence_id = snapshot.get('application_video_evidence_id')
    if evidence_id:
        details([('Evidence', 'Loan application video'), ('Reference', f'Application evidence #{evidence_id}'),
                 ('Media type', snapshot.get('application_video_media_type')),
                 ('Recorded date', evidence.get('device_recorded_at')), ('Received date', evidence.get('server_received_at'))])
        paragraph('Use the authorized application view to access the video.')
    else:
        paragraph('No application evidence recorded in this snapshot.')
    paragraph('L. Warnings and disclaimer', heading)
    details([('Snapshot captured', snapshot.get('generated_at') or (snapshot.get('consent') or {}).get('granted_at')
              or str(application['created_at'])[:10]),
             ('Source', 'Submitted farmer-authorized appraisal snapshot')])
    paragraph('Invoiced revenue, cash received, and feed purchase costs are separate measures. Invoiced revenue is not profit.')
    for warning in [*(snapshot.get('warnings') or []), *(cash.get('notes') or []),
                    snapshot.get('disclaimer'), 'This report supports appraisal and does not constitute a loan approval.']:
        if warning:
            paragraph(warning)

    def footer(canvas, doc):
        canvas.setStrokeColor(green)
        canvas.line(42, 35, A4[0] - 42, 35)
        canvas.setFont('Appraisal', 8)
        canvas.setFillColor(ink)
        canvas.drawString(42, 23, reference + ' | Farmer-authorized appraisal')
        canvas.drawRightString(A4[0] - 42, 23, f'Page {doc.page}')

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
