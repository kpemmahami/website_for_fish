"""Farm expenses, private receipt attachments and dated supplier payments."""

import base64
import binascii
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
import json
import os
from typing import Literal

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .feeding import FeedLedger, FeedProduct
from .main import Base, CurrentUser, Db, ProductionUnit, app, audit, owned_farm
from .operations import owned_cycle, owned_unit
from .sales import FishSale, SalePayment, cents, ghs

TAG = ['Farm expenses']
ROOT = '/farms/{farm_id}/expenses'
CATEGORIES = ('Labour and wages', 'Electricity', 'Water', 'Fuel', 'Transportation', 'Equipment repairs',
              'Unit maintenance', 'Veterinary services', 'Water quality testing', 'Treatments',
              'Fingerlings', 'Harvesting labour', 'Processing', 'Packaging', 'Cold storage', 'Marketing',
              'Communication', 'Administration', 'Rent', 'Insurance', 'Permits', 'Bank charges',
              'Loan interest', 'Equipment purchases', 'Ice', 'Salt', 'Cleaning supplies', 'Other')


def now():
    return datetime.now(timezone.utc)


class FarmExpense(Base):
    __tablename__ = 'farm_expenses'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int | None] = mapped_column(ForeignKey('farms.id'), index=True)
    business_id: Mapped[int | None] = mapped_column(ForeignKey('processing_businesses.id'), index=True)
    processing_batch_id: Mapped[int | None] = mapped_column(ForeignKey('processing_batches.id'), index=True)
    finished_lot_id: Mapped[int | None] = mapped_column(ForeignKey('processing_finished_lots.id'))
    activity: Mapped[str | None] = mapped_column(String(20))
    usage: Mapped[str | None] = mapped_column(String(24))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14,4))
    unit_label: Mapped[str | None] = mapped_column(String(30))
    unit_price_pesewas: Mapped[int | None]
    unit_id: Mapped[int | None] = mapped_column(ForeignKey('production_units.id'))
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey('stocking_cycles.id'))
    category: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300))
    supplier: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(20))
    occurred_on: Mapped[date] = mapped_column(Date)
    amount_pesewas: Mapped[int] = mapped_column(Integer)
    exception_reason: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20))
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ExpensePayment(Base):
    __tablename__ = 'expense_payments'
    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey('farm_expenses.id'), index=True)
    paid_on: Mapped[date] = mapped_column(Date)
    amount_pesewas: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str | None] = mapped_column(String(120))
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))


class ExpenseAttachment(Base):
    __tablename__ = 'expense_attachments'
    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey('farm_expenses.id'), index=True)
    media_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PaymentIn(BaseModel):
    paid_on: date
    amount_ghs: Decimal = Field(gt=0, max_digits=11, decimal_places=2)
    method: Literal['cash','mobile_money','bank_transfer','cheque','other']
    reference: str | None = Field(default=None, max_length=120)


class ExpenseIn(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)
    supplier: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=1000)
    classification: Literal['operating','capital'] = 'operating'
    occurred_on: date
    amount_ghs: Decimal = Field(gt=0, max_digits=11, decimal_places=2)
    unit_id: int | None = None
    cycle_id: int | None = None
    attachments: list[str] = Field(default_factory=list, max_length=3)
    exception_reason: str | None = Field(default=None, max_length=1000)
    initial_payment: PaymentIn | None = None


class ReviewIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def validate_attachment(encoded):
    limit = int(os.getenv('AQUAFARM_EXPENSE_ATTACHMENT_BYTES', '5242880'))
    if len(encoded) > ((limit + 2) // 3) * 4:
        raise HTTPException(422, 'Receipt exceeds the upload limit')
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, 'Receipt file could not be read') from None
    if len(content) > limit:
        raise HTTPException(422, 'Receipt exceeds the upload limit')
    if content.startswith(b'%PDF-'):
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted or not reader.pages:
                raise ValueError
        except Exception:
            raise HTTPException(422, 'Upload a readable PDF receipt') from None
        return 'application/pdf', content
    from PIL import Image
    try:
        with Image.open(BytesIO(content)) as image:
            media = {'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}.get(image.format)
            image.verify()
        if media:
            return media, content
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        pass
    raise HTTPException(422, 'Upload a valid JPEG, PNG, WebP, or PDF receipt')


def expense_for(db, farm_id, expense_id):
    row = db.scalar(select(FarmExpense).where(FarmExpense.id == expense_id, FarmExpense.farm_id == farm_id))
    if row is None:
        raise HTTPException(404, 'Expense not found')
    return row


def expense_view(row, payments, attachments):
    paid = sum(payment.amount_pesewas for payment in payments)
    return {
        'id':row.id, 'reference':f'AQUA-EXP-{row.occurred_on.year}-{row.id:06d}',
        'occurred_on':row.occurred_on, 'category':row.category, 'description':row.description,
        'business_id':row.business_id, 'activity':row.activity, 'usage':row.usage,
        'batch_id':row.processing_batch_id, 'finished_lot_id':row.finished_lot_id,
        'quantity':row.quantity, 'unit_label':row.unit_label,
        'unit_price':ghs(row.unit_price_pesewas) if row.unit_price_pesewas is not None else None,
        'supplier':row.supplier, 'notes':row.notes, 'classification':row.classification,
        'unit_id':row.unit_id, 'cycle_id':row.cycle_id, 'recorded_by':row.recorded_by,
        'created_at':row.created_at, 'updated_at':row.updated_at,
        'amount_ghs':ghs(row.amount_pesewas), 'paid_ghs':ghs(paid),
        'outstanding_ghs':ghs(row.amount_pesewas-paid),
        'payment_status':'paid' if paid==row.amount_pesewas else 'partial' if paid else 'unpaid',
        'review_status':row.review_status, 'exception_reason':row.exception_reason,
        'attachments':[{'id':id_, 'media_type':media, 'created_at':at} for id_,media,at in attachments],
        'payments':[{'id':item.id,'paid_on':item.paid_on,'amount_ghs':ghs(item.amount_pesewas),
                     'method':item.method,'reference':item.reference} for item in payments],
    }


def attachments_for(db, expense_ids):
    return db.execute(select(ExpenseAttachment.expense_id, ExpenseAttachment.id, ExpenseAttachment.media_type,
                             ExpenseAttachment.created_at).where(ExpenseAttachment.expense_id.in_(expense_ids)))


def add_payment(db, row, data, user, existing):
    if data.paid_on < row.occurred_on or data.paid_on > date.today():
        raise HTTPException(422, 'Payment date must be between the expense date and today')
    remaining = row.amount_pesewas - sum(item.amount_pesewas for item in existing)
    amount = cents(data.amount_ghs)
    if amount > remaining:
        raise HTTPException(409, 'Payment exceeds outstanding balance')
    reference = (data.reference or '').strip() or None
    if reference and any(item.reference == reference for item in existing):
        raise HTTPException(409, 'This expense payment reference is already recorded')
    payment = ExpensePayment(expense_id=row.id, paid_on=data.paid_on, amount_pesewas=amount,
                             method=data.method, reference=reference, recorded_by=user.id)
    db.add(payment)
    db.flush()
    audit(db, user, 'record_payment', 'farm_expense', row.id, json.dumps({'payment_id':payment.id}))
    row.updated_at = now()
    return payment


@app.get(ROOT, tags=TAG)
def list_expenses(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id,user,db)
    rows = db.scalars(select(FarmExpense).where(FarmExpense.farm_id == farm_id)
                      .order_by(FarmExpense.occurred_on.desc(),FarmExpense.id.desc())).all()
    ids = [row.id for row in rows]
    payments, files = defaultdict(list), defaultdict(list)
    for payment in db.scalars(select(ExpensePayment).where(ExpensePayment.expense_id.in_(ids)).order_by(ExpensePayment.id)):
        payments[payment.expense_id].append(payment)
    for expense_id, id_, media, at in attachments_for(db, ids):
        files[expense_id].append((id_,media,at))
    return {'categories':CATEGORIES, 'expenses':[expense_view(row,payments[row.id],files[row.id]) for row in rows]}


@app.post(ROOT, status_code=201, tags=TAG)
def record_expense(farm_id: int, data: ExpenseIn, user: CurrentUser, db: Db):
    owned_farm(farm_id,user,db)
    if data.unit_id is not None:
        owned_unit(farm_id,data.unit_id,user,db)
    if data.cycle_id is not None:
        if data.unit_id is None:
            raise HTTPException(422, 'Select the production unit for the cycle')
        owned_cycle(farm_id,data.unit_id,data.cycle_id,user,db)
    row,payments,files = create_expense(farm_id,data,user,db)
    db.commit()
    return expense_view(row,payments,files)


def create_expense(farm_id,data,user,db,**context):
    reason = (data.exception_reason or '').strip() or None
    if not data.attachments and not reason:
        raise HTTPException(422, 'Supporting evidence or a documented exception is required')
    if data.category not in CATEGORIES or not data.description.strip() or data.occurred_on > date.today():
        raise HTTPException(422, 'Enter a valid expense category, description, and date')
    receipts = [validate_attachment(content) for content in data.attachments]
    row = FarmExpense(farm_id=farm_id, **context, amount_pesewas=cents(data.amount_ghs), recorded_by=user.id,
                      review_status='pending_review' if not receipts else 'submitted', exception_reason=reason if not receipts else None,
                      **data.model_dump(exclude={'amount_ghs','attachments','initial_payment','exception_reason'}))
    db.add(row)
    db.flush()
    files = []
    for media, content in receipts:
        attachment = ExpenseAttachment(expense_id=row.id, media_type=media, content=content, uploaded_by=user.id)
        db.add(attachment)
        db.flush()
        files.append((attachment.id,media,attachment.created_at))
    payments = [add_payment(db,row,data.initial_payment,user,[])] if data.initial_payment else []
    audit(db,user,'record','farm_expense',row.id,json.dumps({'evidence_count':len(files),'exception':bool(row.exception_reason)}))
    return row,payments,files


@app.post(ROOT+'/{expense_id}/payments', status_code=201, tags=TAG)
def record_supplier_payment(farm_id: int, expense_id: int, data: PaymentIn, user: CurrentUser, db: Db):
    owned_farm(farm_id,user,db)
    db.execute(update(FarmExpense).where(FarmExpense.id==expense_id,FarmExpense.farm_id==farm_id)
               .values(amount_pesewas=FarmExpense.amount_pesewas))
    row = expense_for(db,farm_id,expense_id)
    existing = list(db.scalars(select(ExpensePayment).where(ExpensePayment.expense_id==row.id)))
    add_payment(db,row,data,user,existing)
    db.commit()
    return {'message':'Payment recorded'}


@app.post(ROOT+'/{expense_id}/approve', tags=TAG)
def approve_expense(farm_id: int, expense_id: int, data: ReviewIn, user: CurrentUser, db: Db):
    owned_farm(farm_id,user,db)
    row = expense_for(db,farm_id,expense_id)
    if not data.reason.strip():
        raise HTTPException(422,'Enter an approval reason')
    changed = db.execute(update(FarmExpense).where(
        FarmExpense.id == row.id,FarmExpense.review_status.in_(('pending_review','submitted')),
    ).values(review_status='approved',updated_at=now()))
    if not changed.rowcount:
        raise HTTPException(409,'Expense has already been reviewed')
    audit(db,user,'approve','farm_expense',row.id,json.dumps({'reason':data.reason.strip()}))
    db.commit()
    return {'message':'Expense approved'}


@app.get(ROOT+'/{expense_id}/attachments/{attachment_id}', tags=TAG)
def download_receipt(farm_id: int, expense_id: int, attachment_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id,user,db)
    expense_for(db,farm_id,expense_id)
    attachment = db.get(ExpenseAttachment,attachment_id)
    if attachment is None or attachment.expense_id != expense_id:
        raise HTTPException(404,'Receipt not found')
    ext = {'application/pdf':'pdf','image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[attachment.media_type]
    return Response(attachment.content,media_type=attachment.media_type,headers={
        'Content-Disposition':f'attachment; filename="expense-{expense_id}-receipt-{attachment_id}.{ext}"',
        'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
    })


@app.get('/farms/{farm_id}/cash-activity',tags=TAG)
def cash_activity(farm_id: int, start: date, end: date, user: CurrentUser, db: Db,
                  grouping: Literal['weekly','monthly','quarterly','yearly','custom']='monthly'):
    owned_farm(farm_id,user,db)
    if end < start or start.year < 1900 or end.year > 2200:
        raise HTTPException(422,'Enter a valid reporting date range')
    if grouping == 'weekly' and (end-start).days > 3660:
        raise HTTPException(422,'Select up to ten years for weekly reporting')

    def bucket(day):
        if grouping == 'weekly':
            return str(day - timedelta(days=day.weekday()))
        if grouping == 'quarterly':
            return f'{day.year} Q{(day.month-1)//3+1}'
        if grouping == 'yearly':
            return str(day.year)
        if grouping == 'monthly':
            return day.strftime('%Y-%m')
        return f'{start} to {end}'

    periods = {}
    def item(day):
        key = bucket(day)
        return periods.setdefault(key,{'period':key,'received':0,'feed_paid':0,'other_paid':0})

    day = start
    while day <= end:
        item(day)
        day += timedelta(days=1)
    recent_transactions = []
    for transaction in db.scalars(select(SalePayment).where(
        SalePayment.farm_id==farm_id, SalePayment.paid_on.between(start,end),
    )):
        item(transaction.paid_on)['received'] += transaction.amount_pesewas
        recent_transactions.append((transaction.paid_on,'Customer payment',transaction.amount_pesewas))
    for ledger in db.scalars(select(FeedLedger).join(FeedProduct,FeedProduct.id==FeedLedger.feed_id).where(
        FeedProduct.farm_id==farm_id,FeedLedger.event_type=='receipt',FeedLedger.occurred_on.between(start,end),
        FeedLedger.cost_ghs.is_not(None),
    )):
        paid = cents(ledger.cost_ghs)
        item(ledger.occurred_on)['feed_paid'] += paid
        recent_transactions.append((ledger.occurred_on,'Feed purchase',-paid))
    for payment in db.scalars(select(ExpensePayment).join(FarmExpense,FarmExpense.id==ExpensePayment.expense_id).where(
        FarmExpense.farm_id==farm_id,ExpensePayment.paid_on.between(start,end),
    )):
        item(payment.paid_on)['other_paid'] += payment.amount_pesewas
        recent_transactions.append((payment.paid_on,'Expense payment',-payment.amount_pesewas))

    def totals(row):
        cash_out = row['feed_paid'] + row['other_paid']
        return {'payments_received_ghs':ghs(row['received']),'feed_purchase_cash_outflow_ghs':ghs(row['feed_paid']),
                'recorded_expenses_ghs':ghs(row['other_paid']),'total_outflows_ghs':ghs(cash_out),
                'net_cash_ghs':ghs(row['received']-cash_out)}

    control = {key:sum(row[key] for row in periods.values()) for key in ('received','feed_paid','other_paid')}
    expenses = db.scalars(select(FarmExpense).where(FarmExpense.farm_id==farm_id,FarmExpense.occurred_on<=end)).all()
    paid_by_expense = defaultdict(int)
    for payment in db.scalars(select(ExpensePayment).where(
        ExpensePayment.expense_id.in_([row.id for row in expenses]), ExpensePayment.paid_on<=end,
    )):
        paid_by_expense[payment.expense_id] += payment.amount_pesewas
    sales = db.scalars(select(FishSale).where(FishSale.farm_id==farm_id,FishSale.sold_on<=end)).all()
    paid_by_sale = defaultdict(int)
    for payment in db.scalars(select(SalePayment).where(SalePayment.farm_id==farm_id,SalePayment.paid_on<=end)):
        paid_by_sale[payment.sale_id] += payment.amount_pesewas
    categories = defaultdict(int)
    for row in expenses:
        if row.occurred_on >= start:
            categories[row.category] += row.amount_pesewas
    return {
        'start':start, 'end':end, 'grouping':grouping,
        'periods':[{'period':row['period'],**totals(row)} for row in periods.values()],
        'summary':{**totals(control),
            'supplier_payables_ghs':ghs(sum(row.amount_pesewas-paid_by_expense[row.id] for row in expenses)),
            'customer_receivables_ghs':ghs(sum(max(0,row.total_pesewas-paid_by_sale[row.id]) for row in sales))},
        'recent_transactions':[{'date':day,'type':kind,'amount_ghs':ghs(amount)}
                               for day,kind,amount in sorted(recent_transactions,reverse=True)[:20]],
        'accrued_by_category':[{'category':key,'amount_ghs':ghs(value)} for key,value in sorted(categories.items())],
    }

@app.get('/farms/{farm_id}/cash-activity.csv',tags=TAG)
@app.get('/farms/{farm_id}/cash-activity.pdf',tags=TAG)
def cash_export(farm_id: int, start: date, end: date, user: CurrentUser, db: Db,
                request: Request, grouping: Literal['weekly','monthly','quarterly','yearly','custom']='monthly'):
    report = cash_activity(farm_id,start,end,user,db,grouping)
    columns = [
        ('period','Period'), ('payments_received_ghs','Payments received'),
        ('feed_purchase_cash_outflow_ghs','Feed purchases'),
        ('recorded_expenses_ghs','Other expenses paid'), ('total_outflows_ghs','Outflows'),
        ('net_cash_ghs','Net cash'),
    ]
    if request.url.path.endswith('.csv'):
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([label for _,label in columns])
        for period in report['periods']:
            writer.writerow([period[key] for key,_ in columns])
        return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="cash-activity.csv"','Cache-Control':'private, no-store'})

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    from .loan_appraisal_pdf import monetary

    pdf = BytesIO()
    document = SimpleDocTemplate(pdf,pagesize=A4,leftMargin=38,rightMargin=38,title='Cash activity statement')
    style = ParagraphStyle('cash_statement',fontName='Appraisal',fontSize=9,leading=12)
    header = ParagraphStyle('cash_header',parent=style,fontName='Appraisal-Bold')
    data = [[Paragraph(label,header) for _,label in columns]]
    for row in report['periods']:
        data.append([Paragraph(str(row[key]) if key=='period' else monetary(row[key]),style) for key,_ in columns])
    table = LongTable(data,colWidths=[document.width/len(columns)]*len(columns),repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DFEEE8')),
                               ('VALIGN',(0,0),(-1,-1),'TOP')]))
    document.build([Paragraph('AquaFarm Manager Ghana',header),Spacer(1,8),
                    Paragraph(f'{grouping.title()} cash activity | {start} to {end}',header),Spacer(1,12),table])
    return Response(pdf.getvalue(),media_type='application/pdf',headers={
        'Content-Disposition':'attachment; filename="cash-activity.pdf"','Cache-Control':'private, no-store',
    })
