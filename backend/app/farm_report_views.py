"""Farm report views built from the existing analytics and transaction services."""

from collections import defaultdict
from datetime import date
from io import BytesIO
from typing import Literal
from xml.sax.saxutils import escape

from fastapi import HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from .dashboard import build_analytics
from .farm_expenses import FarmExpense, cash_activity
from .feeding import FeedLedger, FeedProduct
from .loan_servicing import LoanAccount
from .main import CurrentUser, Db, ProductionUnit, app, owned_farm
from .operations import Mortality, StockingCycle
from .sales import HarvestLot, FishSale, ghs

TAG = ['Dashboard and reporting']
ROOT = '/farms/{farm_id}/reports/complete'


def scope(db, farm_id, unit_ids, cycle_id):
    units = {row.id: row.name for row in db.scalars(select(ProductionUnit).where(ProductionUnit.farm_id==farm_id))}
    if set(unit_ids) - units.keys():
        raise HTTPException(404,'Production unit not found')
    selected = set(unit_ids) if unit_ids else units.keys()
    cycles = {row.id: row.unit_id for row in db.scalars(select(StockingCycle).where(StockingCycle.unit_id.in_(selected)))}
    if cycle_id is not None and cycle_id not in cycles:
        raise HTTPException(404,'Stocking cycle not found')
    return units, {id_:unit for id_,unit in cycles.items() if cycle_id is None or id_==cycle_id}


class ReportScope(BaseModel):
    start: date
    end: date
    unit_ids: list[int] = Field(default_factory=list)
    cycle_id: int | None = None


class FeedReportScope(ReportScope):
    feed_id: int | None = None


def valid_period(data):
    if data.start > data.end:
        raise HTTPException(422,'Enter a valid reporting date range')


@app.post('/farms/{farm_id}/reports/feed-activity',tags=TAG)
def feed_activity(farm_id: int, data: FeedReportScope, user: CurrentUser, db: Db):
    owned_farm(farm_id,user,db)
    valid_period(data)
    units, cycles = scope(db,farm_id,data.unit_ids,data.cycle_id)
    products = {row.id:row.name for row in db.scalars(select(FeedProduct).where(FeedProduct.farm_id==farm_id))}
    if data.feed_id is not None and data.feed_id not in products:
        raise HTTPException(404,'Feed product not found')
    selected_products = [data.feed_id] if data.feed_id is not None else list(products)
    restricted = bool(data.unit_ids or data.cycle_id is not None)
    query = select(FeedLedger).where(FeedLedger.feed_id.in_(selected_products), FeedLedger.occurred_on.between(data.start,data.end))
    if restricted:
        query = query.where(FeedLedger.cycle_id.in_(cycles))
    consumption = defaultdict(float)
    trends = defaultdict(float)
    purchases = sum_consumption = 0
    for row in db.scalars(query.order_by(FeedLedger.occurred_on)):
        if row.event_type=='feeding':
            amount = -row.quantity_delta_kg
            sum_consumption += amount
            consumption[(row.cycle_id,row.feed_id)] += amount
            trends[(row.occurred_on,row.feed_id)] += amount
        elif row.event_type=='receipt':
            purchases += row.quantity_delta_kg
    return {
        'purchased_kg':round(purchases,4) if not restricted else None,
        'consumed_kg':round(sum_consumption,4),
        'trends':[{'date':day,'feed':products[feed],'kg':round(value,4)} for (day,feed),value in trends.items()],
        'consumption':[{'unit':units.get(cycles.get(cycle),'Unassigned'),'cycle_id':cycle,'feed':products[feed],'kg':round(value,4)}
                       for (cycle,feed),value in consumption.items()],
    }


Section = Literal['production','feeding','growth','water','harvest','sales','expenses','cash','profitability','loans']


class CompleteScope(ReportScope):
    sections: list[Section] = Field(min_length=1,max_length=10)


def report_rows(farm_id, data, user, db):
    farm = owned_farm(farm_id,user,db)
    valid_period(data)
    units, cycles = scope(db,farm_id,data.unit_ids,data.cycle_id)
    analytics = build_analytics(farm_id,user,db)
    rows = []
    restricted = bool(data.unit_ids or data.cycle_id is not None)

    def add(section, name, detail):
        rows.append({'section':section,'record':name,'detail':detail})

    def fmt(value, suffix=''):
        return 'Unavailable' if value is None else f'{value:,.2f}{suffix}'

    def in_period(value):
        return value is not None and data.start <= (value.date() if hasattr(value,'date') else value) <= data.end

    if 'production' in data.sections:
        mortality = db.scalars(select(Mortality).where(Mortality.cycle_id.in_(cycles),
                                                      Mortality.observed_on.between(data.start,data.end)))
        for row in mortality:
            add('Mortality',units[cycles[row.cycle_id]],f'{row.observed_on} | Cycle #{row.cycle_id} | Fish lost {row.dead_count}')
        for row in analytics['production']['cycles']:
            if row['cycle_id'] in cycles and in_period(row['stocked_on']):
                add('Production',row['unit_name'],
                    f'{row["species"]} | Cycle #{row["cycle_id"]} | Stocked {row["stocked_on"]} | Fish stocked {row["stocked_count"]} | Lifetime mortality {row["mortality_count"]} | Current estimated biomass {fmt(row["estimated_biomass_kg"]," kg")}')
    if 'feeding' in data.sections:
        feed = feed_activity(farm_id,FeedReportScope.model_validate(data.model_dump()),user,db)
        add('Feeding','Actual feeds in period',fmt(feed['consumed_kg'],' kg'))
        for line in feed['consumption']:
            add('Feeding',f'{line["unit"]} | {line["feed"]}',fmt(line['kg'],' kg'))
        if not restricted:
            for line in analytics['feed']['inventory']:
                add('Feed Inventory',line['feed_name'],f'Current farm stock {fmt(line["remaining_stock_kg"]," kg")}')
    if 'growth' in data.sections:
        for row in analytics['production']['growth_trends']:
            if row['cycle_id'] in cycles and in_period(row['sampled_on']):
                add('Growth',row['unit_name'],f'{row["sampled_on"]} | Average {fmt(row["average_weight_g"]," g")} | Sample size {row["sample_count"]}')
    if 'water' in data.sections:
        allowed_units = set(cycles.values()) if data.cycle_id is not None else set(data.unit_ids or units)
        for row in analytics['water_quality']['history']:
            if row['unit_id'] in allowed_units and in_period(row['observed_at']):
                add('Water Quality',row['unit_name'],f'{row["observed_at"]} | Oxygen {fmt(row["dissolved_oxygen_mg_l"]," mg/L")} | pH {fmt(row["ph"])} | Temperature {fmt(row["temperature_c"]," C")}')
    lots = list(db.scalars(select(HarvestLot).where(HarvestLot.farm_id==farm_id,HarvestLot.cycle_id.in_(cycles))))
    if 'harvest' in data.sections:
        for lot in lots:
            if in_period(lot.harvested_on):
                add('Harvest',f'Cycle #{lot.cycle_id}',f'{lot.harvested_on} | Harvested {fmt(lot.quantity_kg," kg")} | Recorded loss {fmt(lot.loss_kg," kg")}')
        for row in analytics['production']['harvest_forecasts']:
            if row['cycle_id'] in cycles and in_period(row['expected_harvest_on']):
                add('Harvest forecast',row['unit_name'],f'{row["expected_harvest_on"]} | Estimated {fmt(row["expected_harvest_kg"]," kg")}')
    if 'sales' in data.sections:
        sales = db.scalars(select(FishSale).where(FishSale.farm_id==farm_id, FishSale.harvest_lot_id.in_([lot.id for lot in lots]),
                                                FishSale.sold_on.between(data.start,data.end)))
        for sale in sales:
            add('Sales',f'Sale #{sale.id}',f'{sale.sold_on} | {fmt(sale.quantity_kg," kg")} | Invoiced GHS {fmt(ghs(sale.total_pesewas))}')
    if 'expenses' in data.sections:
        expenses = db.scalars(select(FarmExpense).where(FarmExpense.farm_id==farm_id,
                                                       FarmExpense.occurred_on.between(data.start,data.end)))
        for row in expenses:
            matches = (row.cycle_id==data.cycle_id if data.cycle_id is not None else
                       row.unit_id in data.unit_ids or row.cycle_id in cycles if data.unit_ids else True)
            if matches:
                add('Expenses',row.category,f'{row.occurred_on} | Accrued GHS {fmt(ghs(row.amount_pesewas))}')
    if 'cash' in data.sections:
        if restricted:
            add('Cash activity','Farm-wide only','Clear the unit and cycle filters to include whole-farm cash activity.')
        else:
            for row in cash_activity(farm_id,data.start,data.end,user,db,'monthly')['periods']:
                add('Cash activity',row['period'],f'Cash received GHS {fmt(row["payments_received_ghs"])} | Cash outflows GHS {fmt(row["total_outflows_ghs"])} | Net GHS {fmt(row["net_cash_ghs"])}')
    if 'profitability' in data.sections:
        for row in analytics['finance']['pricing_by_plan']:
            if row['cycle_id'] in cycles:
                add('Current plan profitability',f'Plan #{row["plan_id"]}',f'Projected revenue GHS {fmt(row["projected_revenue_ghs"])} | Projected profit GHS {fmt(row["projected_profit_ghs"])}')
    if 'loans' in data.sections:
        if restricted:
            add('Loan obligations','Farm-wide only','Clear unit and cycle filters to include farm loan accounts.')
        else:
            for row in db.scalars(select(LoanAccount).where(LoanAccount.farm_id==farm_id)):
                add('Current loan obligations',f'Loan #{row.id}',f'{row.status.replace("_"," ")} | Approved GHS {fmt(ghs(row.approved_pesewas))}')
    return {'farm_name':farm.name,'start':data.start,'end':data.end,'rows':rows,
            'note':'Stock and loan positions and plan profitability are current. Activity records are filtered by date. Estimates are based on recorded farm data.'}


@app.post(ROOT,tags=TAG)
def view_report(farm_id: int, data: CompleteScope, user: CurrentUser, db: Db):
    return report_rows(farm_id,data,user,db)


@app.post(ROOT+'.pdf',tags=TAG)
def export_report(farm_id: int, data: CompleteScope, user: CurrentUser, db: Db):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    from . import loan_appraisal_pdf  # Registers the shared report fonts.

    report = report_rows(farm_id,data,user,db)
    file = BytesIO()
    doc = SimpleDocTemplate(file,pagesize=A4,leftMargin=36,rightMargin=36,title='Complete Farm Report')
    style = ParagraphStyle('complete_report',fontName='Appraisal',fontSize=9,leading=13)
    heading = ParagraphStyle('complete_heading',parent=style,fontName='Appraisal-Bold')
    def cell(value,kind=style):
        return Paragraph(escape(str(value)),kind)
    story = [cell('AquaFarm Manager Ghana | Complete Farm Report',heading),Spacer(1,8),
             cell(f'{report["farm_name"]} | {report["start"]} to {report["end"]}'),cell(report['note']),Spacer(1,10)]
    if report['rows']:
        data_rows = [[cell(label,heading) for label in ('Section','Record','Detail')]]
        data_rows.extend([[cell(row[key]) for key in ('section','record','detail')] for row in report['rows']])
        table = LongTable(data_rows,colWidths=[90,110,doc.width-200],repeatRows=1,splitInRow=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DFEEE8')),('VALIGN',(0,0),(-1,-1),'TOP')]))
        story.append(table)
    else:
        story.append(cell('No records match the report filters.'))
    doc.build(story)
    return Response(file.getvalue(),media_type='application/pdf',headers={
        'Content-Disposition':'attachment; filename="complete-farm-report.pdf"','Cache-Control':'private, no-store',
    })
