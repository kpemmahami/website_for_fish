
"""Paginated views over the original farm activity and evidence records."""
import csv
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO, StringIO
from typing import Literal
from xml.sax.saxutils import escape

from fastapi import HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, false, func, literal, or_, select, union_all

from .evidence import RecordEvidence, evidence_view
from .feeding import FeedLedger, FeedProduct, FeedReconciliation
from .main import AuditLog, CurrentUser, Db, Farm, ProductionUnit, User, app, owned_farm
from .operations import (FarmInspection, FishSample, FishTransfer, FishTreatment, Mortality, StockingCycle,
                         WaterQuality, has_supervisor_access)
from .sales import FishSale, HarvestLot

ROOT = '/farms/{farm_id}/activity-history'
TAG = ['Farm activity history']
KIND = Literal['all', 'feeding', 'water_quality', 'growth', 'mortality', 'water_exchange', 'stocking', 'harvest', 'evidence',
               'feed_delivery', 'feed_stock_count', 'fish_transfer', 'treatment', 'inspection', 'sale_dispatch']
MODELS = {
    'feeding': (FeedLedger, FeedLedger.occurred_on, 'feeding'),
    'water_quality': (WaterQuality, WaterQuality.observed_at, 'water_quality_record'),
    'growth': (FishSample, FishSample.sampled_on, 'fish_sample'),
    'mortality': (Mortality, Mortality.observed_on, 'mortality_record'),
    'stocking': (StockingCycle, StockingCycle.stocked_on, 'stocking_cycle'),
    'harvest': (HarvestLot, HarvestLot.harvested_on, 'harvest_lot'),
    'feed_delivery': (FeedLedger, FeedLedger.occurred_on, 'feed_receipt'),
    'feed_stock_count': (FeedLedger, FeedLedger.occurred_on, 'feed_inventory'),
    'fish_transfer': (FishTransfer, FishTransfer.transferred_on, 'fish_transfer'),
    'treatment': (FishTreatment, FishTreatment.treated_on, 'fish_treatment'),
    'inspection': (FarmInspection, FarmInspection.inspected_on, 'farm_inspection'),
    'sale_dispatch': (FishSale, FishSale.sold_on, 'fish_sale'),
}
LABELS = {'all':'All activities','feeding':'Feeding history','water_quality':'Water quality history',
          'growth':'Fish sampling history','mortality':'Mortality history','water_exchange':'Water exchange history',
          'stocking':'Stocking history','harvest':'Harvest history','evidence':'Evidence library'}
LABELS.update({kind: kind.replace('_',' ').capitalize() for kind in MODELS if kind not in LABELS})


class DateRange(BaseModel):
    start: date
    end: date


class HistoryFilters(BaseModel):
    kind: KIND = 'all'
    activity: str | None = Field(default=None, max_length=30)
    unit_ids: list[int] = Field(default_factory=list, max_length=100)
    cycle_id: int | None = None
    actor_id: int | None = None
    status: Literal['recorded','active','closed','scheduled','unscheduled','verified','pending','flagged','missing','archived','locked','unlinked'] | None = None
    periods: list[DateRange] = Field(default_factory=list, max_length=24)
    order: Literal['newest','oldest'] = 'newest'
    page: int = Field(default=1, ge=1, le=1000000)
    size: int = Field(default=25, ge=1, le=50)


def access(farm_id, user, db, evidence=False):
    if evidence:
        if not has_supervisor_access(farm_id, user, db):
            raise HTTPException(404, 'Farm not found')
        return None
    return owned_farm(farm_id, user, db)


def audit_actor(model, entity):
    return select(AuditLog.actor_id).where(AuditLog.entity_type == entity, AuditLog.entity_id == model.id,
                                          AuditLog.action == 'create').order_by(AuditLog.id).limit(1).scalar_subquery()


def activity_branch(farm_id, kind, filters):
    model, day, entity = MODELS[kind]
    actor = audit_actor(model, entity)
    stamp = cast(day, String)
    media_link = select(RecordEvidence.id).where(
        RecordEvidence.farm_id == farm_id, RecordEvidence.record_type == kind, RecordEvidence.record_id == model.id,
    )
    first_media = media_link.order_by(RecordEvidence.archived_at.is_not(None),RecordEvidence.id.desc()).limit(1)
    evidence_unit = first_media.with_only_columns(RecordEvidence.unit_id).scalar_subquery()
    if kind == 'stocking':
        cycle_id = model.id
    elif kind in ('water_quality','inspection','feed_delivery','feed_stock_count'):
        cycle_id = first_media.with_only_columns(RecordEvidence.cycle_id).scalar_subquery()
    elif kind == 'fish_transfer':
        cycle_id = model.source_cycle_id
        actor = model.created_by
    elif kind == 'sale_dispatch':
        cycle_id = HarvestLot.cycle_id
    else:
        cycle_id = model.cycle_id
    if kind in ('treatment','inspection'):
        actor = model.created_by
    if kind == 'feed_stock_count':
        actor = select(FeedReconciliation.counted_by).where(FeedReconciliation.ledger_entry_id==model.id).scalar_subquery()
    if kind == 'feeding':
        actor = func.coalesce(FeedLedger.recorded_by, actor)
        stamp = func.coalesce(cast(FeedLedger.actual_fed_at, String), stamp)
    evidence = media_link
    status = filters.status
    query = select(literal(kind).label('kind'), model.id.label('id'), ProductionUnit.id.label('unit_id'),
                   ProductionUnit.name.label('unit_name'), cycle_id.label('cycle_id'),
                   func.substr(cast(day, String), 1, 10).label('day'), stamp.label('stamp'), actor.label('actor_id'))
    if kind in ('stocking','water_quality','inspection','treatment'):
        query = query.select_from(model).join(ProductionUnit, ProductionUnit.id == model.unit_id)
    elif kind in ('feed_delivery','feed_stock_count'):
        query = query.select_from(model).join(ProductionUnit, ProductionUnit.id == evidence_unit)
    elif kind == 'sale_dispatch':
        query = query.select_from(model).join(HarvestLot,HarvestLot.id==model.harvest_lot_id).join(
            StockingCycle,StockingCycle.id==HarvestLot.cycle_id).join(ProductionUnit,ProductionUnit.id==StockingCycle.unit_id)
    else:
        query = query.select_from(model).join(StockingCycle, StockingCycle.id == cycle_id).join(
            ProductionUnit, ProductionUnit.id == StockingCycle.unit_id)
    if kind in ('feeding','feed_delivery','feed_stock_count'):
        event = {'feeding':'feeding','feed_delivery':'receipt','feed_stock_count':'adjustment'}[kind]
        query = query.join(FeedProduct, FeedProduct.id == FeedLedger.feed_id).where(
            FeedProduct.farm_id == farm_id, FeedLedger.event_type == event)
    if kind in ('harvest','sale_dispatch'):
        query = query.where(model.farm_id == farm_id)
    query = query.where(ProductionUnit.farm_id == farm_id)
    if status in ('verified','pending','flagged','archived','missing','locked','unlinked'):
        if status == 'archived':
            query = query.where(evidence.where(RecordEvidence.archived_at.is_not(None)).exists())
        elif status == 'missing':
            query = query.where(~evidence.where(RecordEvidence.archived_at.is_(None)).exists())
        elif status == 'locked':
            query = query.where(evidence.where(RecordEvidence.archived_at.is_(None)).exists())
        elif status == 'unlinked':
            query = query.where(false())
        else:
            query = query.where(evidence.where(RecordEvidence.archived_at.is_(None),
                                               RecordEvidence.verification_status == status).exists())
    elif status in ('active','closed'):
        query = query.where((model.closed_at.is_(None) if status == 'active' else model.closed_at.is_not(None))
                            if kind == 'stocking' else false())
    elif status in ('scheduled','unscheduled'):
        query = query.where((FeedLedger.session_number.is_not(None) if status == 'scheduled' else FeedLedger.session_number.is_(None))
                            if kind == 'feeding' else false())
    return common_filters(query, filters, ProductionUnit.id, cycle_id, actor, day, kind == 'water_quality')


def common_filters(query, filters, unit, cycle, actor, day, timestamps):
    if filters.unit_ids:
        query = query.where(unit.in_(filters.unit_ids))
    if filters.cycle_id is not None:
        query = query.where(cycle == filters.cycle_id)
    if filters.actor_id is not None:
        query = query.where(actor == filters.actor_id)
    if filters.periods:
        for period in filters.periods:
            if period.start > period.end or period.end == date.max:
                raise HTTPException(422, 'Enter a valid reporting date range')
        ranges = [
            (day >= datetime.combine(row.start, time.min, timezone.utc)) &
            (day < datetime.combine(row.end + timedelta(days=1), time.min, timezone.utc))
            if timestamps else day.between(row.start, row.end)
            for row in filters.periods
        ]
        query = query.where(or_(*ranges))
    return query


def evidence_branch(farm_id, filters):
    model = RecordEvidence
    actor = audit_actor(model, 'record_evidence')
    when = func.coalesce(model.captured_at, model.created_at)
    query = select(literal('evidence').label('kind'), model.id.label('id'), model.unit_id.label('unit_id'),
        ProductionUnit.name.label('unit_name'), model.cycle_id.label('cycle_id'),
        func.substr(cast(when, String), 1, 10).label('day'), cast(when, String).label('stamp'),
        actor.label('actor_id')).select_from(model).join(ProductionUnit, ProductionUnit.id == model.unit_id).where(
            model.farm_id == farm_id, ProductionUnit.farm_id == farm_id)
    if filters.activity:
        query = query.where(model.record_type == filters.activity)
    if filters.status == 'archived':
        query = query.where(model.archived_at.is_not(None))
    else:
        query = query.where(model.archived_at.is_(None))
    if filters.status in ('verified','pending','flagged'):
        query = query.where(model.verification_status == filters.status)
    if filters.status == 'locked':
        query = query.where(model.record_id.is_not(None))
    if filters.status == 'unlinked':
        query = query.where(model.record_id.is_(None))
    if filters.status in ('missing','active','closed','scheduled','unscheduled','recorded'):
        query = query.where(false())
    return common_filters(query, filters, model.unit_id, model.cycle_id, actor, when, True)


def matching(farm_id, filters):
    if filters.kind == 'evidence':
        return evidence_branch(farm_id, filters).subquery()
    kinds = list(MODELS) if filters.kind == 'all' else [filters.kind]
    if filters.activity:
        kinds = [kind for kind in kinds if kind == filters.activity]
    branches = [activity_branch(farm_id, kind, filters) for kind in kinds if kind in MODELS]
    return (union_all(*branches) if len(branches)>1 else branches[0] if branches else
            activity_branch(farm_id,'feeding',filters).where(false())).subquery()


def evidence_metadata(item):
    view = evidence_view(item)
    keys = ('id','record_type','record_id','cycle_id','unit_id','captured_at','created_at','media_type',
            'size_bytes','duration_seconds','verification_status','verification_notes','geofence_status','archived_at')
    return {key:view.get(key) for key in keys}


def hydrate(db, farm_id, rows):
    by_kind = {}
    for row in rows:
        by_kind.setdefault(row.kind, []).append(row.id)
    items = {}
    for kind, ids in by_kind.items():
        model = RecordEvidence if kind == 'evidence' else MODELS[kind][0]
        for item in db.scalars(select(model).where(model.id.in_(ids))):
            items[kind,item.id] = item
    actors = {user.id:user.full_name for user in db.scalars(select(User).where(
        User.id.in_({row.actor_id for row in rows if row.actor_id is not None})))}
    feeds = {row.id:row.name for row in db.scalars(select(FeedProduct).where(FeedProduct.farm_id == farm_id))}
    prices = {}
    if by_kind.get('feeding'):
        used = {items['feeding',record_id].feed_id for record_id in by_kind['feeding']}
        prices = dict(db.execute(select(FeedLedger.feed_id, func.sum(FeedLedger.cost_ghs)/func.sum(FeedLedger.quantity_delta_kg))
            .where(FeedLedger.feed_id.in_(used), FeedLedger.event_type == 'receipt',
                   FeedLedger.cost_ghs.is_not(None), FeedLedger.quantity_delta_kg > 0).group_by(FeedLedger.feed_id)).all())
    evidence_conditions = [(RecordEvidence.record_type == kind) & RecordEvidence.record_id.in_(ids)
                           for kind, ids in by_kind.items() if kind != 'evidence']
    linked = {}
    if evidence_conditions:
        for item in db.scalars(select(RecordEvidence).where(RecordEvidence.farm_id == farm_id, or_(*evidence_conditions))
                               .order_by(RecordEvidence.archived_at.is_not(None), RecordEvidence.id.desc())):
            linked.setdefault((item.record_type,item.record_id), []).append(evidence_metadata(item))
    result = []
    for row in rows:
        item = items[row.kind,row.id]
        details = activity_details(row.kind, item, feeds, prices)
        evidence = linked.get((row.kind,row.id), [])
        result.append({**dict(row), 'actor_name': actors.get(row.actor_id), 'details': details,
                       'evidence_status': ('archived' if evidence[0].get('archived_at') else evidence[0]['verification_status'])
                       if evidence else None, 'evidence': evidence})
    return result


def activity_details(kind, item, feeds, prices):
    if kind == 'evidence':
        return evidence_metadata(item)
    data = {'notes': getattr(item,'notes',None)}
    if kind == 'feeding':
        quantity = -item.quantity_delta_kg
        unit_price = prices.get(item.feed_id)
        data.update(session_number=item.session_number, feed=feeds.get(item.feed_id), actual_kg=quantity,
                    actual_fed_at=item.actual_fed_at, response=item.feeding_response,
                    indicative_cost_ghs=round(quantity*unit_price,2) if unit_price is not None else None)
    elif kind == 'growth':
        data.update(sample_count=item.sample_count, average_weight_g=item.average_weight_g)
    elif kind == 'mortality':
        data.update(dead_count=item.dead_count, cause=item.cause)
    elif kind == 'water_quality':
        data.update(observed_at=item.observed_at, temperature_c=item.temperature_c, dissolved_oxygen_mg_l=item.dissolved_oxygen_mg_l,
                    ph=item.ph, ammonia_mg_l=item.ammonia_mg_l, nitrite_mg_l=item.nitrite_mg_l)
    elif kind == 'stocking':
        data.update(species=item.species, stocked_count=item.stocked_count, initial_average_weight_g=item.initial_average_weight_g,
                    fingerling_supplier=item.fingerling_supplier, expected_harvest_on=item.expected_harvest_on, closed_at=item.closed_at)
    elif kind == 'harvest':
        data.update(harvested_kg=item.quantity_kg, fish_count=item.fish_count, loss_kg=item.loss_kg, grade=item.grade)
    elif kind in ('feed_delivery','feed_stock_count'):
        data.update(feed=feeds.get(item.feed_id), quantity_change_kg=item.quantity_delta_kg,
                    receipt_cost_ghs=item.cost_ghs, supplier=item.supplier, reference=item.reference_number)
    elif kind == 'fish_transfer':
        data.update(target_cycle_id=item.target_cycle_id, fish_count=item.fish_count, loss_count=item.loss_count)
    elif kind == 'treatment':
        data.update(product=item.product, dose=item.dose, dose_unit=item.dose_unit, reason=item.reason,
                    withdrawal_period_days=item.withdrawal_period_days)
    elif kind == 'inspection':
        data.update(observations=item.observations, issues=item.issues, corrective_actions=item.corrective_actions)
    elif kind == 'sale_dispatch':
        data.update(dispatched_kg=item.quantity_kg, harvest_lot_id=item.harvest_lot_id)
    return data


@app.get(ROOT + '/options', tags=TAG)
def history_options(farm_id: int, user: CurrentUser, db: Db):
    farm = owned_farm(farm_id,user,db)
    units = db.execute(select(ProductionUnit.id,ProductionUnit.name).where(ProductionUnit.farm_id == farm_id)
                       .order_by(ProductionUnit.name)).all()
    cycles = db.execute(select(StockingCycle.id,StockingCycle.unit_id,StockingCycle.species,StockingCycle.stocked_on)
        .where(StockingCycle.unit_id.in_([row.id for row in units])).order_by(StockingCycle.stocked_on.desc())).all()
    timeline = matching(farm_id,HistoryFilters())
    media = matching(farm_id,HistoryFilters(kind='evidence'))
    staff_ids = select(timeline.c.actor_id).union(select(media.c.actor_id))
    staff = db.execute(select(User.id,User.full_name).where(User.id.in_(staff_ids)).order_by(User.full_name)).all()
    return {'farm_name':farm.name,'units':[dict(row._mapping) for row in units],
            'cycles':[dict(row._mapping) for row in cycles], 'staff':[dict(row._mapping) for row in staff]}


def ordered(rows, filters):
    if filters.order == 'oldest':
        return select(rows).order_by(rows.c.stamp, rows.c.kind, rows.c.id)
    return select(rows).order_by(rows.c.stamp.desc(), rows.c.kind, rows.c.id.desc())


@app.post(ROOT, tags=TAG)
def history(farm_id: int, filters: HistoryFilters, user: CurrentUser, db: Db):
    access(farm_id,user,db,evidence=filters.kind=='evidence')
    rows = matching(farm_id,filters)
    page = db.execute(ordered(rows,filters).offset((filters.page-1)*filters.size).limit(filters.size)).mappings().all()
    totals = []
    if filters.kind == 'feeding' and page:
        days = {row.day for row in page}
        totals = [dict(row._mapping) for row in db.execute(
            select(rows.c.day,func.sum(-FeedLedger.quantity_delta_kg).label('actual_kg')).join(
                FeedLedger, FeedLedger.id==rows.c.id).where(rows.c.day.in_(days)).group_by(rows.c.day))]
    return {'items':hydrate(db,farm_id,page),'total':db.scalar(select(func.count()).select_from(rows)),
            'page':filters.page,'size':filters.size,'daily_totals':totals}


@app.get(ROOT + '/record/{kind}/{record_id}', tags=TAG)
def history_record(farm_id: int, kind: KIND, record_id: int, user: CurrentUser, db: Db):
    access(farm_id,user,db,evidence=kind=='evidence')
    if kind not in MODELS and kind != 'evidence':
        raise HTTPException(404,'Record unavailable')
    rows = matching(farm_id,HistoryFilters(kind=kind))
    if kind == 'evidence':
        rows = union_all(select(rows), select(matching(farm_id,HistoryFilters(kind=kind,status='archived')))).subquery()
    row = db.execute(select(rows).where(rows.c.id==record_id)).mappings().first()
    if row is None:
        raise HTTPException(404,'Record unavailable')
    item = hydrate(db,farm_id,[row])[0]
    entity = 'record_evidence' if kind=='evidence' else MODELS[kind][2]
    audit = db.execute(select(AuditLog.action,AuditLog.created_at,User.full_name).join(User,User.id==AuditLog.actor_id)
        .where(AuditLog.entity_type==entity,AuditLog.entity_id==record_id).order_by(AuditLog.id.desc()).limit(50)).all()
    return {**item,'audit':[dict(entry._mapping) for entry in audit]}


@app.post(ROOT + '/export/{format}', tags=TAG)
def export_history(farm_id: int, format: Literal['csv','pdf'], filters: HistoryFilters, user: CurrentUser, db: Db):
    access(farm_id,user,db,evidence=filters.kind=='evidence')
    farm = db.get(Farm,farm_id)
    rows = matching(farm_id,filters)
    selected = db.execute(ordered(rows,filters).limit(2001)).mappings().all()
    if len(selected) > 2000:
        raise HTTPException(422,'Narrow the filters to export 2,000 records or fewer')
    items = hydrate(db,farm_id,selected)
    periods = ', '.join(f'{p.start} to {p.end}' for p in filters.periods) or 'All dates'
    names = ', '.join(db.scalars(select(ProductionUnit.name).where(ProductionUnit.farm_id==farm_id,
                                                                   ProductionUnit.id.in_(filters.unit_ids))))
    cycle = f' | Cycle #{filters.cycle_id}' if filters.cycle_id else ''
    staff = f' | Staff #{filters.actor_id}' if filters.actor_id else ''
    heading = f'{LABELS[filters.kind]} | {farm.name} | {names or "All units"}{cycle}{staff} | {periods}'
    if filters.activity or filters.status:
        heading += ' | ' + ' | '.join(value for value in (filters.activity,filters.status) if value)
    columns = ['Date','Activity','Record','Unit','Cycle','Recorded by','Details']
    table = [[row['day'],row['details'].get('record_type',row['kind']),row['id'],row['unit_name'],row['cycle_id'],
              row['actor_name'], ' | '.join(f'{key.replace("_"," ")}: {value}' for key,value in row['details'].items()
                                           if value is not None)] for row in items]
    if format == 'csv':
        output = StringIO()
        writer = csv.writer(output)
        def safe(value):
            return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value
        writer.writerow([safe(heading)])
        writer.writerow(columns)
        writer.writerows([[safe(value) for value in row] for row in table])
        return Response(output.getvalue(),media_type='text/csv',headers={'Cache-Control':'private, no-store','Content-Disposition':'attachment; filename="farm-activity.csv"'})
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate
    from . import loan_appraisal_pdf  # Register the shared fonts.
    stream = BytesIO()
    style = ParagraphStyle('activity',fontName='Appraisal',fontSize=8,leading=11)
    def cell(value):
        return Paragraph(escape(str(value if value is not None else '')),style)
    document = SimpleDocTemplate(stream,pagesize=landscape(A4),title='Farm Activity History')
    body = [[cell(value) for value in row] for row in [columns,*table]]
    document.build([cell(heading),LongTable(body,colWidths=[62,75,42,80,38,77,document.width-374],repeatRows=1,splitInRow=1)])
    return Response(stream.getvalue(),media_type='application/pdf',headers={'Cache-Control':'private, no-store','Content-Disposition':'attachment; filename="farm-activity.pdf"'})
