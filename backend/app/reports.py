"""Phase 0007: CSV exports backed by farm-scoped read-only dashboard data."""
import csv
import io
from datetime import date
import json
from typing import Literal
from fastapi import Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from .main import app, Db, CurrentUser, owned_farm
from .dashboard import build_analytics, build_dashboard, cycle_dashboard, monthly_dashboard
from .forecasting import ProductionPlan, forecast
from sqlalchemy import select


def csv_response(rows, filename):
    out = io.StringIO(newline='')
    if rows:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    else:
        out.write('no_records\n')
    return StreamingResponse(iter([out.getvalue()]), media_type='text/csv; charset=utf-8',
                             headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get('/farms/{farm_id}/reports/cycles.csv', tags=['Dashboard and reporting'])
def export_cycles(farm_id: int, user: CurrentUser, db: Db):
    return csv_response(cycle_dashboard(farm_id, user, db)['cycles'], f'aquafarm_{farm_id}_cycles.csv')


@app.get('/farms/{farm_id}/reports/monthly.csv', tags=['Dashboard and reporting'])
def export_monthly(farm_id: int, user: CurrentUser, db: Db, year: int = Query(ge=2000, le=2200)):
    return csv_response(monthly_dashboard(farm_id, user, db, year)['months'], f'aquafarm_{farm_id}_monthly_{year}.csv')


@app.get('/farms/{farm_id}/reports/summary.csv', tags=['Dashboard and reporting'])
def export_summary(farm_id: int, user: CurrentUser, db: Db):
    report = build_dashboard(farm_id, user, db)
    rows = [{'section': section, 'metric': key, 'value': value}
            for section in ('production', 'feed', 'sales', 'costs')
            for key, value in report[section].items()
            if not isinstance(value, (list, dict))]
    return csv_response(rows, f'aquafarm_{farm_id}_summary.csv')


@app.get('/farms/{farm_id}/reports/bank-ready.csv', tags=['Dashboard and reporting'])
def export_bank_ready(farm_id: int, user: CurrentUser, db: Db):
    farm = owned_farm(farm_id, user, db)
    dashboard = build_dashboard(farm_id, user, db)
    cycles = cycle_dashboard(farm_id, user, db)['cycles']
    year = date.today().year
    monthly = monthly_dashboard(farm_id, user, db, year)['months']
    plans = db.scalars(
        select(ProductionPlan).where(ProductionPlan.farm_id == farm_id).order_by(ProductionPlan.id)
    ).all()
    rows = []

    def add(section, period, metric, value, note=''):
        rows.append({
            'section': section,
            'period': period,
            'metric': metric,
            'value': value,
            'currency': 'GHS' if 'ghs' in metric.lower() or 'revenue' in metric.lower() or 'cost' in metric.lower() else '',
            'note': note,
        })

    add('farm', 'current', 'farmer_name', user.full_name)
    add('farm', 'current', 'farm_name', farm.name)
    add('farm', 'current', 'region', farm.region)
    add('farm', 'current', 'district', farm.district)
    add('farm', 'current', 'farm_type', farm.farm_type)
    add('farm', 'current', 'species', farm.species)
    add('report', 'current', 'generated_on', date.today().isoformat())

    for cycle in cycles:
        for key in ('cycle_id', 'unit_name', 'species', 'status', 'stocked_on', 'stocked_count',
                    'mortality_count', 'estimated_live_count', 'latest_average_weight_g',
                    'estimated_biomass_kg', 'latest_sampled_on'):
            add('production_history', str(cycle.get('cycle_id')), key, cycle.get(key))
    for plan in plans:
        result = forecast(plan, db)
        for key in ('expected_harvest_kg', 'expected_revenue_ghs', 'expected_profit_ghs'):
            add('production_estimate', f'plan_{plan.id}', key, result[key],
                'Planning estimate only; actual growth and harvest timing are not verified.')

    for key, value in dashboard['sales'].items():
        if not isinstance(value, (list, dict)):
            add('sales_and_receivables', 'all_time', key, value,
                'Invoiced sales, payments and receivables are distinct values.')
    for key, value in dashboard['costs'].items():
        if not isinstance(value, (list, dict)):
            add('production_costs', 'all_time', key, value, dashboard['costs'].get('note', ''))

    for month in monthly:
        for key, value in month.items():
            if key == 'month':
                continue
            add('monthly_cashflow', month['month'], key, value,
                'Feed purchases are cash outflows; recorded expenses may include the same purchase.')
        operating_cashflow = (
            month['payments_received_ghs']
            - month['feed_purchase_cash_outflow_ghs']
            - month['manual_expenses_ghs']
            - month['shared_allocations_ghs']
        )
        add('monthly_cashflow', month['month'], 'indicative_net_recorded_cashflow_ghs',
            round(operating_cashflow, 2),
            'Recorded cash indicators only; check expense categories for overlap before interpreting as profit.')

    add('disclaimer', 'all', 'verification_status',
        'Farmer-recorded report; not independently audited, certified, or a credit decision.')
    add('disclaimer', 'all', 'sensitive_data',
        'Customer identities, phone numbers, and farm GPS coordinates are excluded.')
    return csv_response(rows, f'aquafarm_{farm_id}_bank_ready_{year}.csv')


def report_sheets(analytics):
    farm = analytics['farm']
    summary = [
        {'metric': 'Farmer name', 'value': farm.get('owner_name')},
        {'metric': 'Farm name', 'value': farm['name']},
        {'metric': 'Region', 'value': farm['region']},
        {'metric': 'District', 'value': farm['district']},
        {'metric': 'Farm type', 'value': farm['farm_type']},
        {'metric': 'Species', 'value': farm['species']},
        {'metric': 'Generated on', 'value': analytics['generated_on']},
    ]
    summary.extend({'metric': key, 'value': value} for key, value in analytics['summary'].items())
    summary.extend({'metric': 'Note', 'value': note} for note in analytics['warnings'])
    sales = [
        {'metric': key, 'value': value}
        for key, value in analytics['finance']['sales'].items()
        if not isinstance(value, (list, dict))
    ]
    financial = [
        {'metric': key, 'value': value}
        for key, value in analytics['finance']['costs'].items()
        if not isinstance(value, (list, dict))
    ]
    return {
        'Summary': summary,
        'Production': analytics['production']['cycles'],
        'Growth History': analytics['production']['growth_trends'],
        'Harvest Forecasts': analytics['production']['harvest_forecasts'],
        'Unit Comparison': analytics['production']['unit_comparisons'],
        'Water Quality': analytics['water_quality']['history'],
        'Feed Inventory': analytics['feed']['inventory'],
        'Feed Forecast': analytics['feed']['forecast']['feeds'],
        'Sales': sales,
        'Financial Summary': financial,
        'Pricing Scenarios': analytics['finance']['pricing_by_plan'],
        'Monthly Cash Flow': analytics['finance']['monthly_cashflow'],
    }


def xlsx_response(analytics, farm_id, report_type):
    sheet_data = report_sheets(analytics)
    sheet_groups = {
        'summary': ('Summary',),
        'production': ('Production', 'Growth History', 'Harvest Forecasts', 'Unit Comparison', 'Water Quality'),
        'sales': ('Sales', 'Monthly Cash Flow'),
        'inventory': ('Feed Inventory', 'Feed Forecast'),
        'financial': ('Financial Summary', 'Pricing Scenarios', 'Sales', 'Monthly Cash Flow'),
        'bank-ready': tuple(sheet_data),
    }
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name in sheet_groups[report_type]:
        worksheet = workbook.create_sheet(sheet_name)
        rows = sheet_data[sheet_name]
        if not rows:
            worksheet.append(['No recorded data'])
            continue
        columns = list(rows[0].keys())
        worksheet.append(columns)
        for cell in worksheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='176B55')
        for row in rows:
            worksheet.append([
                json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict))
                else value.isoformat() if hasattr(value, 'isoformat') else value
                for value in (row.get(column) for column in columns)
            ])
        worksheet.freeze_panes = 'A2'
        worksheet.auto_filter.ref = worksheet.dimensions
        for index, column in enumerate(worksheet.columns, 1):
            width = min(max(max(len(str(cell.value or '')) for cell in column) + 2, 12), 48)
            worksheet.column_dimensions[get_column_letter(index)].width = width
    content = io.BytesIO()
    workbook.save(content)
    content.seek(0)
    return StreamingResponse(
        content,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="aquafarm_{farm_id}_{report_type}_{analytics["generated_on"]}.xlsx"'},
    )


@app.get('/farms/{farm_id}/reports/analytics/{report_type}.csv', tags=['Dashboard and reporting'])
def export_analytics_csv(
    farm_id: int,
    report_type: Literal['production', 'sales', 'inventory', 'financial'],
    user: CurrentUser,
    db: Db,
):
    owned_farm(farm_id, user, db)
    sheets = report_sheets(build_analytics(farm_id, user, db))
    sheet_groups = {
        'production': ('Production', 'Growth History', 'Harvest Forecasts', 'Unit Comparison', 'Water Quality'),
        'sales': ('Sales', 'Monthly Cash Flow'),
        'inventory': ('Feed Inventory', 'Feed Forecast'),
        'financial': ('Financial Summary', 'Pricing Scenarios', 'Sales', 'Monthly Cash Flow'),
    }
    rows = [
        {'section': sheet_name, **row}
        for sheet_name in sheet_groups[report_type]
        for row in sheets[sheet_name]
    ]
    return csv_response(rows, f'aquafarm_{farm_id}_{report_type}_{date.today()}.csv')


@app.get('/farms/{farm_id}/reports/{report_type}.xlsx', tags=['Dashboard and reporting'])
def export_excel(
    farm_id: int,
    report_type: Literal['summary', 'production', 'sales', 'inventory', 'financial', 'bank-ready'],
    user: CurrentUser,
    db: Db,
):
    owned_farm(farm_id, user, db)
    analytics = build_analytics(farm_id, user, db)
    return xlsx_response(analytics, farm_id, report_type)
