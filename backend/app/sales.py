"""Phase 0006: harvested fish inventory, customers, sales and payments (GHS)."""
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
import json
from fastapi import HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Float, select, func
from sqlalchemy.orm import Mapped, mapped_column
from .main import Base, app, Db, CurrentUser, audit, owned_farm
from .operations import StockingCycle, ProductionUnit, population


def now():
    return datetime.now(timezone.utc)


def cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def ghs(value):
    return round(value / 100, 2)


class Customer(Base):
    __tablename__ = 'sales_customers'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    name: Mapped[str] = mapped_column(String(150))
    customer_type: Mapped[str] = mapped_column(String(30))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class HarvestLot(Base):
    __tablename__ = 'harvest_lots'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey('stocking_cycles.id'), index=True)
    harvested_on: Mapped[date] = mapped_column(Date)
    quantity_kg: Mapped[float] = mapped_column(Float)
    fish_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loss_kg: Mapped[float] = mapped_column(Float, default=0)
    grade: Mapped[str | None] = mapped_column(String(80), nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FishSale(Base):
    __tablename__ = 'fish_sales'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    harvest_lot_id: Mapped[int] = mapped_column(ForeignKey('harvest_lots.id'), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('sales_customers.id'), index=True)
    sold_on: Mapped[date] = mapped_column(Date)
    quantity_kg: Mapped[float] = mapped_column(Float)
    unit_price_pesewas: Mapped[int] = mapped_column(Integer)
    total_pesewas: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evidence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SalePayment(Base):
    __tablename__ = 'sale_payments'
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey('farms.id'), index=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey('fish_sales.id'), index=True)
    paid_on: Mapped[date] = mapped_column(Date)
    amount_pesewas: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    customer_type: Literal['individual','retailer','wholesaler','restaurant','other'] = 'individual'
    phone: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=1000)


class HarvestIn(BaseModel):
    cycle_id: int = Field(gt=0)
    harvested_on: date
    quantity_kg: float = Field(gt=0, le=10000000)
    fish_count: int = Field(gt=0)
    loss_kg: float = Field(default=0, ge=0)
    grade: str | None = Field(default=None, max_length=80)
    buyer_name: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=1000)


class SaleIn(BaseModel):
    harvest_lot_id: int = Field(gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    sold_on: date
    quantity_kg: float = Field(gt=0, le=10000000)
    price_ghs_per_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    notes: str | None = Field(default=None, max_length=1000)


class PaymentIn(BaseModel):
    paid_on: date
    amount_ghs: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: Literal['cash','mobile_money','bank_transfer','other']
    reference: str | None = Field(default=None, max_length=120)


def owned(db, model, farm_id, object_id):
    obj = db.scalar(select(model).where(model.id == object_id, model.farm_id == farm_id))
    if obj is None:
        raise HTTPException(404, f'{model.__tablename__} record not found in this farm')
    return obj


def remaining_kg(db, lot):
    sold = db.scalar(select(func.coalesce(func.sum(FishSale.quantity_kg), 0)).where(FishSale.harvest_lot_id == lot.id)) or 0
    return round(lot.quantity_kg - lot.loss_kg - sold, 4)


def paid_cents(db, sale_id):
    return int(db.scalar(select(func.coalesce(func.sum(SalePayment.amount_pesewas), 0)).where(SalePayment.sale_id == sale_id)) or 0)


def sale_view(db, sale):
    paid = paid_cents(db, sale.id)
    due = sale.total_pesewas - paid
    return {'id': sale.id, 'harvest_lot_id': sale.harvest_lot_id, 'customer_id': sale.customer_id,
            'evidence_id': sale.evidence_id,
            'sold_on': sale.sold_on, 'quantity_kg': sale.quantity_kg,
            'price_ghs_per_kg': ghs(sale.unit_price_pesewas), 'total_ghs': ghs(sale.total_pesewas),
            'paid_ghs': ghs(paid), 'outstanding_ghs': ghs(due),
            'payment_status': 'paid' if due == 0 else ('partial' if paid else 'unpaid'), 'notes': sale.notes}


@app.post('/farms/{farm_id}/sales/customers', status_code=201, tags=['Fish sales and payments'])
def create_customer(farm_id: int, data: CustomerIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    obj = Customer(farm_id=farm_id, **data.model_dump())
    db.add(obj); db.flush(); audit(db, user, 'create', 'sales_customer', obj.id); db.commit(); db.refresh(obj)
    return obj


@app.get('/farms/{farm_id}/sales/customers', tags=['Fish sales and payments'])
def list_customers(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    return db.scalars(select(Customer).where(Customer.farm_id == farm_id).order_by(Customer.id)).all()


@app.post('/farms/{farm_id}/sales/harvests', status_code=201, tags=['Fish sales and payments'])
def create_harvest(
    farm_id: int,
    data: HarvestIn,
    user: CurrentUser,
    db: Db,
    evidence_id: int = Query(gt=0),
):
    owned_farm(farm_id, user, db)
    cycle = db.scalar(select(StockingCycle).join(ProductionUnit, StockingCycle.unit_id == ProductionUnit.id).where(
        StockingCycle.id == data.cycle_id, ProductionUnit.farm_id == farm_id))
    if cycle is None: raise HTTPException(404, 'Stocking cycle not found in this farm')
    if data.loss_kg >= data.quantity_kg: raise HTTPException(422, 'Loss must be less than harvested weight')
    if data.harvested_on < cycle.stocked_on or data.harvested_on > date.today():
        raise HTTPException(422, 'Harvest date must be between stocking date and today')
    if data.fish_count > population(cycle, db).estimated_live_count:
        raise HTTPException(409, 'Harvest fish count exceeds estimated live fish')
    obj = HarvestLot(farm_id=farm_id, **data.model_dump())
    db.add(obj)
    db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(
        db, evidence_id, farm_id, cycle.unit_id, cycle.id,
        'harvest', obj.id, user,
    )
    audit(db, user, 'create', 'harvest_lot', obj.id, json.dumps({'evidence_id': evidence_id}))
    db.commit()
    db.refresh(obj)
    return {'id': obj.id, 'cycle_id': obj.cycle_id, 'quantity_kg': obj.quantity_kg,
            'fish_count': obj.fish_count, 'loss_kg': obj.loss_kg,
            'grade': obj.grade, 'buyer_name': obj.buyer_name,
            'available_kg': remaining_kg(db, obj), 'harvested_on': obj.harvested_on}


@app.get('/farms/{farm_id}/sales/harvests', tags=['Fish sales and payments'])
def list_harvests(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    lots = db.scalars(select(HarvestLot).where(HarvestLot.farm_id == farm_id).order_by(HarvestLot.id)).all()
    return [{'id': l.id, 'cycle_id': l.cycle_id, 'harvested_on': l.harvested_on,
             'quantity_kg': l.quantity_kg, 'fish_count': l.fish_count,
             'loss_kg': l.loss_kg, 'grade': l.grade, 'buyer_name': l.buyer_name,
             'available_kg': remaining_kg(db,l)} for l in lots]


@app.post('/farms/{farm_id}/sales/transactions', status_code=201, tags=['Fish sales and payments'])
def create_sale(
    farm_id: int,
    data: SaleIn,
    user: CurrentUser,
    db: Db,
    evidence_id: int = Query(gt=0),
):
    owned_farm(farm_id, user, db)
    lot = owned(db, HarvestLot, farm_id, data.harvest_lot_id)
    if data.customer_id is None:
        if data.quantity_kg >= 500:
            raise HTTPException(422, 'Sales of 500 kg or more require a registered customer')
        customer = db.scalar(select(Customer).where(
            Customer.farm_id == farm_id,
            Customer.name == 'Walk-in / small-quantity buyers',
            Customer.customer_type == 'other',
        ))
        if customer is None:
            customer = Customer(
                farm_id=farm_id,
                name='Walk-in / small-quantity buyers',
                customer_type='other',
                notes='Shared category for small sales; individual buyers are not registered.',
            )
            db.add(customer)
            db.flush()
    else:
        customer = owned(db, Customer, farm_id, data.customer_id)
    if data.sold_on < lot.harvested_on: raise HTTPException(422, 'Sale cannot predate harvest')
    if data.quantity_kg > remaining_kg(db, lot) + 1e-8: raise HTTPException(409, 'Insufficient harvested fish inventory')
    unit = cents(data.price_ghs_per_kg)
    total = cents(Decimal(str(data.quantity_kg)) * data.price_ghs_per_kg)
    cycle = db.get(StockingCycle, lot.cycle_id)
    obj = FishSale(farm_id=farm_id, harvest_lot_id=lot.id, customer_id=customer.id,
                   sold_on=data.sold_on, quantity_kg=data.quantity_kg,
                   unit_price_pesewas=unit, total_pesewas=total, notes=data.notes,
                   evidence_id=evidence_id)
    db.add(obj)
    db.flush()
    from .evidence import attach_record_evidence
    attach_record_evidence(
        db, evidence_id, farm_id, cycle.unit_id, cycle.id,
        'sale_dispatch', obj.id, user,
    )
    audit(db, user, 'create', 'fish_sale', obj.id, json.dumps({'evidence_id': evidence_id}))
    db.commit()
    db.refresh(obj)
    return sale_view(db, obj)


@app.get('/farms/{farm_id}/sales/transactions', tags=['Fish sales and payments'])
def list_sales(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    sales = db.scalars(select(FishSale).where(FishSale.farm_id == farm_id).order_by(FishSale.id)).all()
    return [sale_view(db,s) for s in sales]


@app.post('/farms/{farm_id}/sales/transactions/{sale_id}/payments', status_code=201, tags=['Fish sales and payments'])
def record_payment(farm_id: int, sale_id: int, data: PaymentIn, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    sale = owned(db, FishSale, farm_id, sale_id)
    amount = cents(data.amount_ghs)
    if amount > sale.total_pesewas - paid_cents(db, sale.id): raise HTTPException(409, 'Payment exceeds outstanding balance')
    if data.paid_on < sale.sold_on: raise HTTPException(422, 'Payment cannot predate sale')
    obj = SalePayment(farm_id=farm_id, sale_id=sale.id, amount_pesewas=amount,
                      paid_on=data.paid_on, method=data.method, reference=data.reference)
    db.add(obj); db.flush(); audit(db, user, 'create', 'sale_payment', obj.id); db.commit()
    return {'payment_id':obj.id, 'sale':sale_view(db,sale)}


@app.get('/farms/{farm_id}/sales/transactions/{sale_id}/payments', tags=['Fish sales and payments'])
def list_payments(farm_id: int, sale_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db); owned(db, FishSale, farm_id, sale_id)
    items = db.scalars(select(SalePayment).where(SalePayment.sale_id == sale_id).order_by(SalePayment.id)).all()
    return [{'id':x.id,'paid_on':x.paid_on,'amount_ghs':ghs(x.amount_pesewas),'method':x.method,'reference':x.reference} for x in items]


@app.get('/farms/{farm_id}/sales/summary', tags=['Fish sales and payments'])
def sales_summary(farm_id: int, user: CurrentUser, db: Db):
    owned_farm(farm_id, user, db)
    sales = db.scalars(select(FishSale).where(FishSale.farm_id == farm_id)).all()
    lots = db.scalars(select(HarvestLot).where(HarvestLot.farm_id == farm_id)).all()
    revenue = sum(s.total_pesewas for s in sales)
    received = int(db.scalar(select(func.coalesce(func.sum(SalePayment.amount_pesewas), 0)).where(SalePayment.farm_id == farm_id)) or 0)
    return {'currency':'GHS','sales_count':len(sales),'sold_kg':round(sum(s.quantity_kg for s in sales),4),
            'available_harvest_kg':round(sum(remaining_kg(db,l) for l in lots),4),
            'invoiced_revenue_ghs':ghs(revenue),'cash_received_ghs':ghs(received),
            'outstanding_receivables_ghs':ghs(revenue-received),
            'note':'Revenue is not profit. Full realized profit requires cost-of-goods allocation and other expenses.'}
