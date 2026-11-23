from datetime import date
from decimal import Decimal
import hashlib
import json
from typing import Literal

from fastapi import HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import Date, ForeignKey, LargeBinary, Numeric, String, Text, UniqueConstraint, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .main import Base, CurrentUser, Db, Farm, User, app, audit, owned_farm
from .farm_expenses import ExpenseIn, ExpensePayment, FarmExpense, PaymentIn, add_payment, create_expense, expense_view, attachments_for, ExpenseAttachment, validate_attachment
from .sales import Customer, FishSale, HarvestLot, SalePayment, cents, ghs, paid_cents, remaining_kg, sale_view

ROOT = '/processing'
TAG = ['Processing and value addition']
METHODS = ('Freezing','Smoking','Filleting','Salting','Drying','Gutting and cleaning','Vacuum packing')
QTY = Numeric(14,4)
ACTIVITIES = ('production','processing','packaging','distribution','general')


class ProcessingBusiness(Base):
    __tablename__ = 'processing_businesses'
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    business_type: Mapped[str] = mapped_column(String(20))
    methods_json: Mapped[str] = mapped_column(Text, default='[]')


class Supplier(Base):
    __tablename__ = 'processing_suppliers'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('processing_businesses.id'), index=True)
    name: Mapped[str] = mapped_column(String(150))
    contact: Mapped[str | None] = mapped_column(String(150))


class Batch(Base):
    __tablename__ = 'processing_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('processing_businesses.id'), index=True)
    facility: Mapped[str] = mapped_column(String(150))
    method: Mapped[str] = mapped_column(String(150))
    started_on: Mapped[date] = mapped_column(Date)
    completed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default='draft')
    notes: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[str] = mapped_column(Text, default='[]')
    mass_balance: Mapped[str] = mapped_column(Text, default='{}')
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))


class RawLot(Base):
    __tablename__ = 'processing_raw_lots'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('processing_businesses.id'), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey('processing_suppliers.id'))
    expense_id: Mapped[int] = mapped_column(ForeignKey('farm_expenses.id'), unique=True)
    species: Mapped[str] = mapped_column(String(150))
    received_on: Mapped[date] = mapped_column(Date)
    quantity_kg: Mapped[Decimal] = mapped_column(QTY)
    storage: Mapped[str] = mapped_column(String(150))
    observations: Mapped[str | None] = mapped_column(Text)


class ProcessingInput(Base):
    __tablename__ = 'processing_inputs'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('processing_batches.id'), index=True)
    raw_lot_id: Mapped[int | None] = mapped_column(ForeignKey('processing_raw_lots.id'), index=True)
    harvest_id: Mapped[int | None] = mapped_column(ForeignKey('harvest_lots.id'), index=True)
    quantity_kg: Mapped[Decimal] = mapped_column(QTY)
    cost_pesewas: Mapped[int | None]
    allocated_on: Mapped[date] = mapped_column(Date)
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))


class Output(Base):
    __tablename__ = 'processing_outputs'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('processing_batches.id'), index=True)
    name: Mapped[str] = mapped_column(String(150))
    is_byproduct: Mapped[bool] = mapped_column(default=False)
    quantity_kg: Mapped[Decimal] = mapped_column(QTY)


class Material(Base):
    __tablename__ = 'processing_materials'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('processing_businesses.id'), index=True)
    name: Mapped[str] = mapped_column(String(150))


class MaterialReceipt(Base):
    __tablename__ = 'processing_material_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey('processing_materials.id'), index=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey('farm_expenses.id'), unique=True)
    quantity: Mapped[int]


class FinishedLot(Base):
    __tablename__ = 'processing_finished_lots'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('processing_businesses.id'), index=True)
    output_id: Mapped[int] = mapped_column(ForeignKey('processing_outputs.id'), index=True)
    material_id: Mapped[int | None] = mapped_column(ForeignKey('processing_materials.id'), index=True)
    material_used: Mapped[int]
    material_cost_pesewas: Mapped[int]
    units: Mapped[int]
    weight_per_unit_kg: Mapped[Decimal] = mapped_column(QTY)
    packaged_on: Mapped[date] = mapped_column(Date)
    best_before: Mapped[date | None] = mapped_column(Date)
    shelf_life_basis: Mapped[str | None] = mapped_column(Text)
    packaging: Mapped[str] = mapped_column(String(150))
    storage: Mapped[str] = mapped_column(String(150))
    label_details: Mapped[str] = mapped_column(Text,default='{}')
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))


class Quality(Base):
    __tablename__ = 'processing_quality'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('processing_batches.id'), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    checked_on: Mapped[date] = mapped_column(Date)
    observations: Mapped[str] = mapped_column(Text)
    checks: Mapped[str] = mapped_column(Text,default='[]')
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))


class Allocation(Base):
    __tablename__ = 'processing_expense_allocations'
    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey('farm_expenses.id'), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('processing_batches.id'), index=True)
    amount_pesewas: Mapped[int]
    basis: Mapped[str] = mapped_column(Text)


class Movement(Base):
    __tablename__ = 'processing_finished_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey('processing_finished_lots.id'), index=True)
    sale_id: Mapped[int | None] = mapped_column(ForeignKey('fish_sales.id'))
    quantity_delta: Mapped[int]
    credit_pesewas: Mapped[int] = mapped_column(default=0)
    occurred_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))


class ProcessingEvidence(Base):
    __tablename__ = 'processing_evidence'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('processing_businesses.id'), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('processing_batches.id'), index=True)
    stage: Mapped[str] = mapped_column(String(25))
    recorded_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    recorded_by: Mapped[int] = mapped_column(ForeignKey('users.id'))


class ProcessingRequest(Base):
    __tablename__ = 'processing_requests'
    __table_args__ = (UniqueConstraint('business_id','request_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('processing_businesses.id'))
    request_key: Mapped[str] = mapped_column(String(80))
    fingerprint: Mapped[str] = mapped_column(String(64))
    record_id: Mapped[int]


def request_token(db,biz,operation,data):
    if not data.request_key:
        return None,None
    fingerprint=hashlib.sha256((operation+':'+data.model_dump_json(exclude={'request_key'})).encode()).hexdigest()
    previous=db.scalar(select(ProcessingRequest).where(ProcessingRequest.business_id==biz.id,
                                                       ProcessingRequest.request_key==data.request_key))
    if previous and previous.fingerprint!=fingerprint:
        raise HTTPException(409,'This request key belongs to a different processing action')
    return (previous.record_id if previous else None),ProcessingRequest(
        business_id=biz.id,request_key=data.request_key,fingerprint=fingerprint)


def link_request(db,token,record_id):
    if token is not None:
        token.record_id=record_id
        db.add(token)


class ProcessingMember(Base):
    __tablename__ = 'processing_members'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('processing_businesses.id'),index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'),unique=True)
    permissions: Mapped[str] = mapped_column(Text)


class QualityRule(Base):
    __tablename__ = 'processing_quality_rules'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey('processing_businesses.id'),index=True)
    method: Mapped[str] = mapped_column(String(150))
    product: Mapped[str] = mapped_column(String(150))
    checks: Mapped[str] = mapped_column(Text)


PERMISSIONS = ('processing.view','processing.create','processing.complete','processing.quality_review',
               'packaging.create','inventory.adjust','pricing.view','finance.manage','sales.manage',
               'processing_reports.view')


def permissions_for(db,user,biz):
    if biz.owner_id==user.id:
        return set(PERMISSIONS)
    member=db.scalar(select(ProcessingMember).where(ProcessingMember.business_id==biz.id,ProcessingMember.user_id==user.id))
    return set(json.loads(member.permissions)) if member else set()


def view(row):
    return {column.name:getattr(row,column.name) for column in row.__table__.columns}


def rows(db,model,where):
    return list(db.scalars(select(model).where(where).order_by(model.id)))


def business_for(db,user):
    owner=db.scalar(select(ProcessingBusiness).where(ProcessingBusiness.owner_id==user.id))
    if owner and owner.business_type!='farmer':
        return owner
    member=db.scalar(select(ProcessingMember).where(ProcessingMember.user_id==user.id))
    return db.get(ProcessingBusiness,member.business_id) if member else owner


def business(db,user,lock=False,permission='processing.view'):
    biz=business_for(db,user)
    if biz is None or biz.business_type=='farmer':
        raise HTTPException(404,'Enable fish processing first')
    if lock:
        db.execute(update(ProcessingBusiness).where(ProcessingBusiness.id==biz.id).values(name=ProcessingBusiness.name))
        db.refresh(biz)
    if permission not in permissions_for(db,user,biz) or lock and permission=='processing.view':
        raise HTTPException(403,'You do not have permission for this processing action')
    return biz


def scoped(db,model,biz,record_id):
    obj=db.scalar(select(model).where(model.id==record_id,model.business_id==biz.id))
    if obj is None:
        raise HTTPException(404,'Processing record unavailable')
    return obj


def save(db,user,obj,event,token=None):
    db.add(obj)
    db.flush()
    audit(db,user,event,obj.__tablename__,obj.id)
    link_request(db,token,obj.id)
    db.commit()
    return {'id':obj.id}


def check_date(day,earliest=None):
    if day>date.today() or earliest and day<earliest:
        raise HTTPException(422,'Choose a date within the recorded workflow')


class BusinessIn(BaseModel):
    name: str = Field(min_length=1,max_length=150)
    business_type: Literal['farmer','processor','integrated']


class PartyIn(BaseModel):
    name: str = Field(min_length=1,max_length=150)
    contact: str | None = Field(default=None,max_length=150)


@app.get(ROOT+'/business',tags=TAG)
def get_business(user:CurrentUser,db:Db):
    biz=business_for(db,user)
    if biz is None:
        return {'business_type':'farmer','name':user.full_name}
    return {**view(biz),'is_owner':biz.owner_id==user.id,'permissions':sorted(permissions_for(db,user,biz))}


@app.put(ROOT+'/business',tags=TAG)
def set_business(data:BusinessIn,user:CurrentUser,db:Db):
    if user.account_type not in ('farmer','legacy') or user.is_platform_admin:
        raise HTTPException(403,'Use a farmer or processor account')
    if db.scalar(select(ProcessingMember.id).where(ProcessingMember.user_id==user.id)):
        raise HTTPException(403,'Processing staff cannot change business settings')
    db.execute(update(User).where(User.id==user.id).values(full_name=User.full_name))
    biz=db.scalar(select(ProcessingBusiness).where(ProcessingBusiness.owner_id==user.id))
    if biz and biz.business_type!='farmer' and data.business_type=='farmer':
        raise HTTPException(409,'Keep processing enabled to retain access to its records')
    biz=biz or ProcessingBusiness(owner_id=user.id)
    biz.name,biz.business_type=data.name,data.business_type
    return save(db,user,biz,'save')


@app.post(ROOT+'/suppliers',tags=TAG)
def supplier(data:PartyIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'processing.create')
    return save(db,user,Supplier(business_id=biz.id,**data.model_dump()),'create')


@app.post(ROOT+'/customers',tags=TAG)
def customer(data:PartyIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'sales.manage')
    row=Customer(business_id=biz.id,name=data.name,phone=(data.contact or '')[:40] or None,customer_type='individual')
    return save(db,user,row,'create')


@app.post(ROOT+'/methods',tags=TAG)
def add_method(data:PartyIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'processing.create')
    methods=json.loads(biz.methods_json)
    if data.name.casefold() in {method.casefold() for method in (*METHODS,*methods)}:
        raise HTTPException(409,'Processing method already exists')
    biz.methods_json=json.dumps([*methods,data.name])
    return save(db,user,biz,'add_method')


class PurchaseIn(BaseModel):
    request_key: str | None = Field(default=None,max_length=80)
    supplier_id: int
    species: str = Field(min_length=1,max_length=150)
    received_on: date
    quantity_kg: Decimal = Field(gt=0,max_digits=14,decimal_places=4)
    unit_price: Decimal = Field(gt=0,max_digits=11,decimal_places=2)
    acquisition_cost: Decimal = Field(default=Decimal(0),ge=0,max_digits=11,decimal_places=2)
    storage: str = Field(min_length=1,max_length=150)
    observations: str | None = Field(default=None,max_length=2000)
    attachments: list[str] = Field(default_factory=list,max_length=3)
    exception_reason: str | None = Field(default=None,max_length=1000)
    initial_payment: PaymentIn | None = None


@app.post(ROOT+'/purchases',status_code=201,tags=TAG)
def purchase(data:PurchaseIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'processing.create')
    previous,token=request_token(db,biz,'raw purchase',data)
    if previous:
        return {'id':previous}
    if 'finance.manage' not in permissions_for(db,user,biz):
        raise HTTPException(403,'Expense permissions are required to record purchases')
    vendor=scoped(db,Supplier,biz,data.supplier_id)
    total=cents(data.quantity_kg*data.unit_price+data.acquisition_cost)
    if not 0<total<=2_147_483_647:
        raise HTTPException(422,'Purchase total is outside the supported accounting range')
    exp=ExpenseIn(category='Processing',description='Raw fish purchase: '+data.species,supplier=vendor.name,
        occurred_on=data.received_on,amount_ghs=Decimal(total)/100,
        attachments=data.attachments,exception_reason=data.exception_reason,initial_payment=data.initial_payment)
    row,_,_=create_expense(None,exp,user,db,business_id=biz.id,activity='processing',usage='raw_inventory',
                           quantity=data.quantity_kg,unit_label='kg',unit_price_pesewas=cents(data.unit_price))
    raw=RawLot(business_id=biz.id,expense_id=row.id,**data.model_dump(
        include={'supplier_id','species','received_on','quantity_kg','storage','observations'}))
    return save(db,user,raw,'receive',token)


class BatchIn(BaseModel):
    request_key: str | None = Field(default=None,max_length=80)
    facility: str = Field(min_length=1,max_length=150)
    method: str = Field(min_length=1,max_length=150)
    started_on: date
    notes: str | None = Field(default=None,max_length=2000)


@app.post(ROOT+'/batches',status_code=201,tags=TAG)
def start(data:BatchIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'processing.create')
    previous,token=request_token(db,biz,'batch',data)
    if previous:
        return {'id':previous}
    check_date(data.started_on)
    if data.method not in (*METHODS,*json.loads(biz.methods_json)):
        raise HTTPException(422,'Select an existing processing method')
    return save(db,user,Batch(business_id=biz.id,recorded_by=user.id,**data.model_dump(exclude={'request_key'})),'create',token)


def raw_available(db,lot):
    used=db.scalar(select(func.coalesce(func.sum(ProcessingInput.quantity_kg),0)).where(ProcessingInput.raw_lot_id==lot.id))
    return lot.quantity_kg-used


def harvest_rate(db,lot):
    from .main import ProductionUnit
    from .operations import StockingCycle
    from .pricing_advisor import PricingIn, calculate_advisor

    cycle=db.get(StockingCycle,lot.cycle_id)
    unit=db.get(ProductionUnit,cycle.unit_id)
    report=calculate_advisor(db,lot.farm_id,cycle,unit,PricingIn())
    incurred=report['incurred_ghs']
    weight=report['saleable_weight_kg']
    if not incurred or not weight or any('no priced receipt' in text.lower() for text in report['warnings']):
        return None
    return Decimal(str(incurred))/Decimal(str(weight))


class InputIn(BaseModel):
    request_key: str | None = Field(default=None,max_length=80)
    source: Literal['purchased','harvest']
    source_id: int
    quantity_kg: Decimal = Field(gt=0,max_digits=14,decimal_places=4)


@app.post(ROOT+'/batches/{batch_id}/inputs',status_code=201,tags=TAG)
def allocate(batch_id:int,data:InputIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'processing.create')
    previous,token=request_token(db,biz,'allocation:'+str(batch_id),data)
    if previous:
        return {'id':previous}
    batch=scoped(db,Batch,biz,batch_id)
    if batch.status not in ('draft','allocated','in_progress'):
        raise HTTPException(409,'This batch no longer accepts raw material')
    raw_id,harvest_id=None,None
    if data.source=='purchased':
        lot=scoped(db,RawLot,biz,data.source_id)
        available=raw_available(db,lot)
        if data.quantity_kg>available:
            raise HTTPException(409,'Insufficient raw fish stock')
        if batch.started_on<lot.received_on:
            raise HTTPException(422,'Batch start cannot predate raw fish receipt')
        raw_id=lot.id
        expense=db.get(FarmExpense,lot.expense_id)
        used=lot.quantity_kg-available
        rate=Decimal(expense.amount_pesewas)/100/lot.quantity_kg
        cost=cents(rate*(used+data.quantity_kg))-cents(rate*used)
    else:
        if biz.business_type!='integrated':
            raise HTTPException(409,'Enable integrated farming and processing to use a harvest')
        lot=db.get(HarvestLot,data.source_id)
        if lot is None:
            raise HTTPException(404,'Harvest unavailable')
        owned_farm(lot.farm_id,db.get(User,biz.owner_id),db)
        if batch.started_on<lot.harvested_on:
            raise HTTPException(422,'Batch start cannot predate harvest')
        db.execute(update(HarvestLot).where(HarvestLot.id==lot.id).values(quantity_kg=HarvestLot.quantity_kg))
        if data.quantity_kg>Decimal(str(remaining_kg(db,lot))):
            raise HTTPException(409,'Insufficient harvested fish inventory')
        rate=harvest_rate(db,lot)
        cost=cents(rate*data.quantity_kg) if rate is not None else None
        harvest_id=lot.id
    if batch.status=='draft':
        batch.status='allocated'
    return save(db,user,ProcessingInput(batch_id=batch.id,raw_lot_id=raw_id,harvest_id=harvest_id,
        quantity_kg=data.quantity_kg,cost_pesewas=cost,allocated_on=date.today(),recorded_by=user.id),'allocate',token)


class StepIn(BaseModel):
    method: str = Field(min_length=1,max_length=150)
    occurred_on: date
    details: str = Field(min_length=1,max_length=3000)


@app.post(ROOT+'/batches/{batch_id}/steps',tags=TAG)
def step(batch_id:int,data:StepIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'processing.create')
    batch=scoped(db,Batch,biz,batch_id)
    check_date(data.occurred_on,batch.started_on)
    if batch.status not in ('allocated','in_progress'):
        raise HTTPException(409,'Allocate raw fish before recording processing steps')
    if data.method not in (*METHODS,*json.loads(biz.methods_json)):
        raise HTTPException(422,'Select an existing processing method')
    steps=json.loads(batch.steps)
    steps.append({**data.model_dump(mode='json'),'recorded_by':user.id})
    batch.steps=json.dumps(steps)
    batch.status='in_progress'
    return save(db,user,batch,'record_step')


class OutputIn(BaseModel):
    name: str = Field(min_length=1,max_length=150)
    is_byproduct: bool = False
    quantity_kg: Decimal = Field(gt=0,max_digits=14,decimal_places=4)


class CompleteIn(BaseModel):
    completed_on: date
    outputs: list[OutputIn] = Field(min_length=1,max_length=30)
    byproducts_kg: Decimal = Field(default=Decimal(0),ge=0,max_digits=14,decimal_places=4)
    waste_kg: Decimal = Field(default=Decimal(0),ge=0,max_digits=14,decimal_places=4)
    moisture_loss_kg: Decimal = Field(default=Decimal(0),ge=0,max_digits=14,decimal_places=4)
    spoilage_kg: Decimal = Field(default=Decimal(0),ge=0,max_digits=14,decimal_places=4)
    other_loss_kg: Decimal = Field(default=Decimal(0),ge=0,max_digits=14,decimal_places=4)
    additions_kg: Decimal = Field(default=Decimal(0),ge=0,max_digits=14,decimal_places=4)
    reconciliation_note: str | None = Field(default=None,max_length=1000)


@app.post(ROOT+'/batches/{batch_id}/complete',tags=TAG)
def complete(batch_id:int,data:CompleteIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'processing.complete')
    batch=scoped(db,Batch,biz,batch_id)
    check_date(data.completed_on,batch.started_on)
    inputs=rows(db,ProcessingInput,ProcessingInput.batch_id==batch.id)
    if batch.status not in ('allocated','in_progress') or not inputs:
        raise HTTPException(409,'Allocate raw fish before completing this batch')
    if any(data.completed_on.isoformat()<step['occurred_on'] for step in json.loads(batch.steps)):
        raise HTTPException(422,'Completion cannot predate a processing step')
    raw=sum(row.quantity_kg for row in inputs)
    finished=sum(row.quantity_kg for row in data.outputs if not row.is_byproduct)
    recoverable=sum(row.quantity_kg for row in data.outputs if row.is_byproduct)
    if not finished or recoverable>data.byproducts_kg:
        raise HTTPException(422,'Record a main finished output and reconcile recoverable by-product weight')
    accounted=finished+data.byproducts_kg+data.waste_kg+data.moisture_loss_kg+data.spoilage_kg+data.other_loss_kg
    difference=raw+data.additions_kg-accounted
    if data.additions_kg and not (data.reconciliation_note or '').strip():
        raise HTTPException(422,'Document additions to the batch mass balance')
    if finished>raw+data.additions_kg or abs(difference)>Decimal('0.0001') and not (data.reconciliation_note or '').strip():
        raise HTTPException(422,'Reconcile the batch mass balance and document any measurement difference')
    db.add_all([Output(batch_id=batch.id,**row.model_dump()) for row in data.outputs])
    batch.completed_on=data.completed_on
    batch.status='quality_review'
    batch.mass_balance=json.dumps({**data.model_dump(mode='json'),'difference_kg':str(difference),
                                   'yield_pct':str(round(finished*100/raw,2))})
    return save(db,user,batch,'complete')


class MaterialIn(BaseModel):
    request_key: str | None = Field(default=None,max_length=80)
    material_id: int
    quantity: int = Field(gt=0,le=10000000)
    expense: ExpenseIn


@app.post(ROOT+'/materials',tags=TAG)
def add_material(data:PartyIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'packaging.create')
    return save(db,user,Material(business_id=biz.id,name=data.name),'create')


@app.post(ROOT+'/material-receipts',tags=TAG)
def material_receipt(data:MaterialIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'packaging.create')
    previous,token=request_token(db,biz,'material receipt',data)
    if previous:
        return {'id':previous}
    if 'finance.manage' not in permissions_for(db,user,biz):
        raise HTTPException(403,'Expense permissions are required to record purchases')
    item=scoped(db,Material,biz,data.material_id)
    if data.expense.unit_id or data.expense.cycle_id:
        raise HTTPException(422,'Choose the processing material only')
    exp,_,_=create_expense(None,data.expense,user,db,business_id=biz.id,activity='packaging',
                           usage='material_inventory',quantity=data.quantity,unit_label='unit')
    return save(db,user,MaterialReceipt(material_id=item.id,expense_id=exp.id,quantity=data.quantity),'receive',token)


def material_stock(db,material_id):
    received,cost=db.execute(select(func.coalesce(func.sum(MaterialReceipt.quantity),0),
        func.coalesce(func.sum(FarmExpense.amount_pesewas),0)).join(FarmExpense,FarmExpense.id==MaterialReceipt.expense_id)
        .where(MaterialReceipt.material_id==material_id)).one()
    used,carried=db.execute(select(func.coalesce(func.sum(FinishedLot.material_used),0),
        func.coalesce(func.sum(FinishedLot.material_cost_pesewas),0)).where(FinishedLot.material_id==material_id)).one()
    balance=received-used
    return balance, Decimal(cost-carried)/balance if balance else None


def output_for(db,biz,key):
    output=db.get(Output,key)
    if output is None:
        raise HTTPException(404,'Processing output unavailable')
    return output,scoped(db,Batch,biz,output.batch_id)


class LabelDetails(BaseModel):
    brand: str | None = Field(default=None,max_length=120)
    ingredients: str | None = Field(default=None,max_length=1000)
    manufacturer: str | None = Field(default=None,max_length=150)
    manufacturer_address: str | None = Field(default=None,max_length=350)
    premises_address: str | None = Field(default=None,max_length=200)
    country_of_origin: str | None = Field(default=None,max_length=100)
    directions: str | None = Field(default=None,max_length=350)
    storage_instructions: str | None = Field(default=None,max_length=350)


class PackageIn(BaseModel):
    request_key: str | None = Field(default=None,max_length=80)
    output_id: int
    material_id: int | None = None
    material_used: int = Field(default=0,ge=0,le=10000000)
    units: int = Field(gt=0,le=10000000)
    weight_per_unit_kg: Decimal = Field(gt=0,max_digits=14,decimal_places=4)
    packaged_on: date
    best_before: date | None = None
    shelf_life_basis: str | None = Field(default=None,max_length=1000)
    packaging: str = Field(min_length=1,max_length=150)
    storage: str = Field(min_length=1,max_length=150)
    label_details: LabelDetails = Field(default_factory=LabelDetails)


@app.post(ROOT+'/packages',status_code=201,tags=TAG)
def package(data:PackageIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'packaging.create')
    previous,token=request_token(db,biz,'package',data)
    if previous:
        return {'id':previous}
    output,batch=output_for(db,biz,data.output_id)
    if batch.status not in ('quality_review','packaged','released'):
        raise HTTPException(409,'Complete the batch or resolve the quality hold before packaging')
    check_date(data.packaged_on,batch.completed_on)
    if data.best_before and (data.best_before<data.packaged_on or not (data.shelf_life_basis or '').strip()):
        raise HTTPException(422,'Enter a validated shelf-life basis and valid date')
    packed=db.scalar(select(func.coalesce(func.sum(FinishedLot.units*FinishedLot.weight_per_unit_kg),0))
                     .where(FinishedLot.output_id==output.id))
    if data.units*data.weight_per_unit_kg>output.quantity_kg-Decimal(str(packed)):
        raise HTTPException(409,'Packaging would exceed available finished weight')
    if bool(data.material_id)!=bool(data.material_used):
        raise HTTPException(422,'Enter both a material and its actual usage')
    material_cost=0
    if data.material_id:
        scoped(db,Material,biz,data.material_id)
        stock,unit_cost=material_stock(db,data.material_id)
        if data.material_used>stock:
            raise HTTPException(409,'Insufficient packaging stock')
        material_cost=cents(unit_cost*data.material_used/100)
    batch.status='packaged'
    return save(db,user,FinishedLot(business_id=biz.id,recorded_by=user.id,material_cost_pesewas=material_cost,
                                    label_details=data.label_details.model_dump_json(exclude_none=True),
                                    **data.model_dump(exclude={'label_details','request_key'})),'package',token)


class QualityIn(BaseModel):
    decision: Literal['hold','release','reject']
    checked_on: date
    observations: str = Field(min_length=5,max_length=4000)
    checks: list[str] = Field(default_factory=list,max_length=100)


@app.post(ROOT+'/batches/{batch_id}/quality',tags=TAG)
def quality(batch_id:int,data:QualityIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'processing.quality_review')
    batch=scoped(db,Batch,biz,batch_id)
    if batch.completed_on is None or batch.status=='rejected':
        raise HTTPException(409,'A completed, non-rejected batch is required')
    check_date(data.checked_on,batch.completed_on)
    previous=db.scalar(select(func.max(Quality.checked_on)).where(Quality.batch_id==batch.id))
    check_date(data.checked_on,previous)
    verified={value.strip().casefold() for value in data.checks}
    if data.decision=='release':
        if any(value.casefold() not in verified for value in quality_checks(db,biz,batch)):
            raise HTTPException(409,'Complete all configured quality checks before release')
        packaged=db.scalar(select(func.max(FinishedLot.packaged_on)).join(Output,Output.id==FinishedLot.output_id)
                           .where(Output.batch_id==batch.id))
        if packaged is None or data.checked_on<packaged:
            raise HTTPException(422,'Quality release must follow packaging')
    batch.status={'hold':'held','reject':'rejected','release':'released'}[data.decision]
    return save(db,user,Quality(batch_id=batch.id,recorded_by=user.id,checks=json.dumps(data.checks),**data.model_dump(exclude={'checks'})),data.decision)


class BusinessExpenseIn(ExpenseIn):
    request_key: str | None = Field(default=None,max_length=80)
    activity: Literal['production','processing','packaging','distribution','general']
    farm_id: int | None = None
    batch_id: int | None = None
    finished_lot_id: int | None = None
    quantity: Decimal | None = Field(default=None,gt=0,max_digits=14,decimal_places=4)
    unit_label: str | None = Field(default=None,max_length=30)
    unit_price: Decimal | None = Field(default=None,gt=0,max_digits=11,decimal_places=2)


@app.post(ROOT+'/expenses',status_code=201,tags=TAG)
def add_expense(data:BusinessExpenseIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'finance.manage')
    previous,token=request_token(db,biz,'expense',data)
    if previous:
        row=scoped(db,FarmExpense,biz,previous)
        return expense_view(row,rows(db,ExpensePayment,ExpensePayment.expense_id==row.id),
                            [(key,media,at) for _,key,media,at in attachments_for(db,[row.id])])
    batch_id=data.batch_id
    if batch_id:
        scoped(db,Batch,biz,batch_id)
    if data.finished_lot_id:
        lot=scoped(db,FinishedLot,biz,data.finished_lot_id)
        _,batch=output_for(db,biz,lot.output_id)
        if batch_id and batch.id!=batch_id:
            raise HTTPException(422,'Finished lot does not belong to the selected batch')
        batch_id=batch.id
    if batch_id and (data.classification!='operating' or data.activity not in ('processing','packaging','distribution')):
        raise HTTPException(422,'Only applicable operating costs may be charged to a batch')
    if data.farm_id is not None:
        owned_farm(data.farm_id,db.get(User,biz.owner_id),db)
    if data.unit_id or data.cycle_id:
        raise HTTPException(422,'Use Farm Expenses for production unit or cycle expenses')
    if data.quantity and data.unit_price and cents(data.quantity*data.unit_price)!=cents(data.amount_ghs):
        raise HTTPException(422,'The expense total must match its quantity and unit price')
    row,payments,files=create_expense(data.farm_id,ExpenseIn.model_validate(data.model_dump()),user,db,
        business_id=biz.id,activity=data.activity,usage='expense',processing_batch_id=batch_id,
        finished_lot_id=data.finished_lot_id,quantity=data.quantity,unit_label=data.unit_label,
        unit_price_pesewas=cents(data.unit_price) if data.unit_price is not None else None)
    link_request(db,token,row.id)
    db.commit()
    return expense_view(row,payments,files)


class AllocationIn(BaseModel):
    batch_id: int
    amount_ghs: Decimal = Field(gt=0,max_digits=11,decimal_places=2)
    basis: str = Field(min_length=5,max_length=1000)


@app.post(ROOT+'/expenses/{expense_id}/allocations',tags=TAG)
def allocate_expense(expense_id:int,data:AllocationIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'finance.manage')
    exp=scoped(db,FarmExpense,biz,expense_id)
    scoped(db,Batch,biz,data.batch_id)
    if exp.processing_batch_id or exp.usage!='expense' or exp.classification!='operating' or exp.activity=='production':
        raise HTTPException(409,'Choose an unassigned applicable operating expense')
    allocated=db.scalar(select(func.coalesce(func.sum(Allocation.amount_pesewas),0)).where(Allocation.expense_id==exp.id))
    if allocated+cents(data.amount_ghs)>exp.amount_pesewas:
        raise HTTPException(409,'Allocation exceeds the unallocated expense balance')
    return save(db,user,Allocation(expense_id=exp.id,batch_id=data.batch_id,amount_pesewas=cents(data.amount_ghs),
                                  basis=data.basis),'allocate')


@app.post(ROOT+'/expenses/{expense_id}/payments',tags=TAG)
def expense_payment(expense_id:int,data:PaymentIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'finance.manage')
    db.execute(update(FarmExpense).where(FarmExpense.id==expense_id,FarmExpense.business_id==biz.id)
               .values(amount_pesewas=FarmExpense.amount_pesewas))
    exp=scoped(db,FarmExpense,biz,expense_id)
    existing=rows(db,ExpensePayment,ExpensePayment.expense_id==exp.id)
    payment=add_payment(db,exp,data,user,existing)
    db.commit()
    return {'id':payment.id}


@app.get(ROOT+'/expenses/{expense_id}/attachments/{attachment_id}',tags=TAG)
def receipt(expense_id:int,attachment_id:int,user:CurrentUser,db:Db):
    biz=business(db,user,permission='finance.manage')
    exp=scoped(db,FarmExpense,biz,expense_id)
    item=db.get(ExpenseAttachment,attachment_id)
    if item is None or item.expense_id!=exp.id:
        raise HTTPException(404,'Receipt unavailable')
    return Response(item.content,media_type=item.media_type,headers={
        'Content-Disposition':'attachment; filename="processing-receipt"','Cache-Control':'private, no-store',
        'X-Content-Type-Options':'nosniff'})


def processing_credits(db,sale_id):
    return db.scalar(select(func.coalesce(func.sum(Movement.credit_pesewas),0)).where(Movement.sale_id==sale_id))


def lot_stock(db,lot):
    sold=db.scalar(select(func.coalesce(func.sum(FishSale.packages_sold),0)).where(FishSale.finished_lot_id==lot.id))
    movements=db.scalar(select(func.coalesce(func.sum(Movement.quantity_delta),0)).where(Movement.lot_id==lot.id))
    return lot.units-sold+movements


def batch_cost(db,batch):
    inputs=rows(db,ProcessingInput,ProcessingInput.batch_id==batch.id)
    outputs=rows(db,Output,Output.batch_id==batch.id)
    expenses=rows(db,FarmExpense,FarmExpense.processing_batch_id==batch.id)
    direct={activity:sum(row.amount_pesewas for row in expenses if row.activity==activity and not row.finished_lot_id)
            for activity in ACTIVITIES}
    shared=db.scalar(select(func.coalesce(func.sum(Allocation.amount_pesewas),0)).where(Allocation.batch_id==batch.id))
    raw=sum(row.cost_pesewas or 0 for row in inputs)
    missing=[row.id for row in inputs if row.cost_pesewas is None]
    finished=sum((row.quantity_kg for row in outputs if not row.is_byproduct),Decimal(0))
    byproducts={row.id for row in outputs if row.is_byproduct}
    lots=rows(db,FinishedLot,FinishedLot.output_id.in_([row.id for row in outputs]))
    material=sum(row.material_cost_pesewas for row in lots)
    total=raw+sum(row.amount_pesewas for row in expenses)+shared+material
    pool=raw+sum(direct.values())+shared
    book_costs={}
    pricing_costs={}
    byproduct_lots={lot.id for lot in lots if lot.output_id in byproducts}
    eligible_sales=rows(db,FishSale,FishSale.finished_lot_id.in_(byproduct_lots)) if byproduct_lots else []
    credit=max(0,sum(sale.total_pesewas-processing_credits(db,sale.id)-(sale.processing_cost_pesewas or 0)
                     for sale in eligible_sales))
    # Credits lower pricing estimates only. Posted sale costs and realized revenue stay gross.
    usable_credit=min(credit,pool)
    for lot in lots:
        explicit=Decimal(lot.material_cost_pesewas+sum(row.amount_pesewas for row in expenses
                    if row.finished_lot_id==lot.id))/lot.units
        if lot.id in byproduct_lots:
            book_costs[lot.id]=pricing_costs[lot.id]=explicit/100
        elif finished and not missing:
            share=lot.weight_per_unit_kg/finished
            book_costs[lot.id]=(Decimal(pool)*share+explicit)/100
            pricing_costs[lot.id]=(Decimal(pool-usable_credit)*share+explicit)/100
        else:
            book_costs[lot.id]=pricing_costs[lot.id]=None
    main_cost=pool+sum(lot.material_cost_pesewas for lot in lots if lot.id not in byproduct_lots)+sum(
        row.amount_pesewas for row in expenses if row.finished_lot_id and row.finished_lot_id not in byproduct_lots)
    return {'raw_ghs':ghs(raw),'direct_ghs':{key:ghs(value) for key,value in direct.items()},
            'material_ghs':ghs(material),'shared_ghs':ghs(shared),'total_cost_ghs':ghs(total),
            'recognized_byproduct_credit_ghs':ghs(usable_credit),'finished_kg':finished,
            'input_kg':sum((row.quantity_kg for row in inputs),Decimal(0)),'missing_input_costs':missing,
            'cost_per_kg':round(Decimal(main_cost-usable_credit)/100/finished,4) if finished and not missing else None,
            'book_lots':book_costs,'lots':pricing_costs}


def pricing(unit,weight,margin,proposed=None):
    from .pricing_advisor import scenario
    if unit is None:
        return {'break_even':None,'suggested':None,'scenario':None}
    target=unit/(1-margin/100)
    scenarios={label:scenario(unit,Decimal(1),value,margin) for label,value in {
        'below_break_even':unit*Decimal('.9'),'break_even':unit,'modest_profit':unit/Decimal('.9'),
        'target':target,'higher_profit':target*Decimal('1.1'),
    }.items()}
    return {'break_even':round(unit,4),'per_kg':round(unit/weight,4),'suggested':round(target,4),
            'scenarios':scenarios,'scenario':scenario(unit,Decimal(1),proposed,margin) if proposed is not None else None}


@app.get(ROOT+'/lots/{lot_id}/pricing',tags=TAG)
def price(lot_id:int,user:CurrentUser,db:Db,margin:Decimal=Decimal(20),proposed:Decimal|None=None):
    if not margin.is_finite() or not 0<=margin<100 or proposed is not None and (not proposed.is_finite() or proposed<0):
        raise HTTPException(422,'Use a margin below 100% and a non-negative proposed price')
    biz=business(db,user,permission='pricing.view')
    lot=scoped(db,FinishedLot,biz,lot_id)
    _,batch=output_for(db,biz,lot.output_id)
    return pricing(batch_cost(db,batch)['lots'][lot.id],lot.weight_per_unit_kg,margin,proposed)


class SaleIn(BaseModel):
    lot_id: int
    customer_id: int
    units: int = Field(gt=0,le=10000000)
    sold_on: date
    due_on: date | None = None
    unit_price: Decimal = Field(gt=0,max_digits=11,decimal_places=2)
    request_key: str | None = Field(default=None,max_length=80)


@app.post(ROOT+'/sales',status_code=201,tags=TAG)
def sell(data:SaleIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'sales.manage')
    total=cents(data.unit_price)*data.units
    if data.request_key:
        previous=db.scalar(select(FishSale).where(FishSale.business_id==biz.id,FishSale.processing_request_key==data.request_key))
        if previous:
            if (previous.finished_lot_id,previous.customer_id,previous.packages_sold,previous.sold_on,
                previous.due_on,previous.total_pesewas)!=(data.lot_id,data.customer_id,data.units,data.sold_on,data.due_on,total):
                raise HTTPException(409,'This request key belongs to a different sale')
            return sale_view(db,previous)
    lot=scoped(db,FinishedLot,biz,data.lot_id)
    scoped(db,Customer,biz,data.customer_id)
    _,batch=output_for(db,biz,lot.output_id)
    release=db.scalar(select(func.max(Quality.checked_on)).where(Quality.batch_id==batch.id,Quality.decision=='release'))
    if batch.status!='released' or release is None or lot.best_before and date.today()>lot.best_before:
        raise HTTPException(409,'Only released, in-date stock can be sold')
    check_date(data.sold_on,max(release,lot.packaged_on))
    if data.due_on and data.due_on<data.sold_on:
        raise HTTPException(422,'Payment due date cannot predate the sale')
    if data.units>lot_stock(db,lot):
        raise HTTPException(409,'Insufficient finished stock')
    per_kg=cents(data.unit_price/lot.weight_per_unit_kg)
    if total>2_147_483_647 or per_kg>2_147_483_647:
        raise HTTPException(422,'Sale total exceeds the supported invoice amount')
    cost=batch_cost(db,batch)['book_lots'][lot.id]
    obj=FishSale(business_id=biz.id,finished_lot_id=lot.id,packages_sold=data.units,
        processing_cost_pesewas=cents(cost*data.units) if cost is not None else None,
        processing_request_key=data.request_key,customer_id=data.customer_id,sold_on=data.sold_on,due_on=data.due_on,
        quantity_kg=float(lot.weight_per_unit_kg*data.units),unit_price_pesewas=per_kg,
        total_pesewas=total)
    save(db,user,obj,'create')
    return sale_view(db,obj)


@app.post(ROOT+'/sales/{sale_id}/payments',tags=TAG)
def sale_payment(sale_id:int,data:PaymentIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'sales.manage')
    sale=scoped(db,FishSale,biz,sale_id)
    check_date(data.paid_on,sale.sold_on)
    if cents(data.amount_ghs)>sale.total_pesewas-processing_credits(db,sale.id)-paid_cents(db,sale.id):
        raise HTTPException(409,'Payment exceeds outstanding invoice balance')
    if data.reference and db.scalar(select(SalePayment.id).where(SalePayment.sale_id==sale.id,SalePayment.reference==data.reference)):
        raise HTTPException(409,'This payment reference is already recorded')
    return save(db,user,SalePayment(sale_id=sale.id,amount_pesewas=cents(data.amount_ghs),paid_on=data.paid_on,
                  method=data.method,reference=data.reference),'create')


class MovementIn(BaseModel):
    units: int = Field(gt=0,le=10000000)
    reason: str = Field(min_length=5,max_length=1000)
    sale_id: int | None = None
    credit_ghs: Decimal = Field(default=Decimal(0),ge=0,max_digits=11,decimal_places=2)
    refund_ghs: Decimal = Field(default=Decimal(0),ge=0,max_digits=11,decimal_places=2)
    refund_method: Literal['cash','mobile_money','bank_transfer','cheque','other'] | None = None


@app.post(ROOT+'/lots/{lot_id}/movements',tags=TAG)
def stock_movement(lot_id:int,data:MovementIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'inventory.adjust')
    lot=scoped(db,FinishedLot,biz,lot_id)
    credit,refund=cents(data.credit_ghs),cents(data.refund_ghs)
    if (credit or refund) and 'sales.manage' not in permissions_for(db,user,biz):
        raise HTTPException(403,'Sales permissions are required for credits or refunds')
    if data.sale_id:
        sale=scoped(db,FishSale,biz,data.sale_id)
        returned=db.scalar(select(func.coalesce(func.sum(Movement.quantity_delta),0)).where(Movement.sale_id==sale.id))
        if sale.finished_lot_id!=lot.id or returned+data.units>sale.packages_sold:
            raise HTTPException(409,'Return exceeds original sale stock')
        applied=processing_credits(db,sale.id)
        if credit>sale.total_pesewas*data.units//sale.packages_sold or applied+credit>sale.total_pesewas:
            raise HTTPException(409,'Credit exceeds the original value of the returned packages')
        paid=paid_cents(db,sale.id)
        if refund>min(credit,paid) or paid-refund>sale.total_pesewas-applied-credit:
            raise HTTPException(409,'Enter the required refund or reduce the credit')
        if refund:
            if not data.refund_method:
                raise HTTPException(422,'Choose the method used for the refund')
            payment=SalePayment(sale_id=sale.id,amount_pesewas=-refund,paid_on=date.today(),method=data.refund_method,
                                reference='Processed product return')
            db.add(payment)
            db.flush()
            audit(db,user,'refund','sale_payment',payment.id)
        _,batch=output_for(db,biz,lot.output_id)
        if batch.status!='rejected':
            batch.status='held'
        delta=data.units
    else:
        if credit or refund:
            raise HTTPException(422,'A refund or credit requires the original invoice')
        if data.units>lot_stock(db,lot):
            raise HTTPException(409,'Adjustment exceeds available stock')
        delta=-data.units
    return save(db,user,Movement(lot_id=lot.id,sale_id=data.sale_id,quantity_delta=delta,credit_pesewas=credit,occurred_on=date.today(),
                                 recorded_by=user.id,reason=data.reason),'adjust')


def batch_view(db,batch):
    from .operations import StockingCycle
    from .main import ProductionUnit
    sources=[]
    for row in rows(db,ProcessingInput,ProcessingInput.batch_id==batch.id):
        info=view(row)
        if row.harvest_id:
            lot=db.get(HarvestLot,row.harvest_id)
            cycle=db.get(StockingCycle,lot.cycle_id)
            unit=db.get(ProductionUnit,cycle.unit_id)
            info.update(farm_id=lot.farm_id,unit_id=unit.id,unit_name=unit.name,cycle_id=cycle.id,
                        species=cycle.species,harvested_on=lot.harvested_on,harvest_kg=lot.quantity_kg)
        else:
            info['species']=db.get(RawLot,row.raw_lot_id).species
        sources.append(info)
    outputs=[]
    for row in rows(db,Output,Output.batch_id==batch.id):
        packaged=db.scalar(select(func.coalesce(func.sum(FinishedLot.units*FinishedLot.weight_per_unit_kg),0))
                           .where(FinishedLot.output_id==row.id))
        outputs.append({**view(row),'available_kg':row.quantity_kg-Decimal(str(packaged))})
    return {**view(batch),'reference':f'AQUA-PROC-{batch.started_on.year}-{batch.id:06d}',
            'steps':json.loads(batch.steps),'mass_balance':json.loads(batch.mass_balance),'sources':sources,
            'outputs':outputs,'cost':batch_cost(db,batch),
            'required_checks':quality_checks(db,db.get(ProcessingBusiness,batch.business_id),batch),
            'quality':[{**view(row),'checks':json.loads(row.checks)} for row in rows(db,Quality,Quality.batch_id==batch.id)]}


@app.get(ROOT+'/workspace',tags=TAG)
def workspace(user:CurrentUser,db:Db):
    from .farm_expenses import CATEGORIES
    biz=business(db,user)
    expenses=[]
    actors={}
    for row in rows(db,FarmExpense,FarmExpense.business_id==biz.id):
        payments=rows(db,ExpensePayment,ExpensePayment.expense_id==row.id)
        files=[(key,media,at) for _,key,media,at in attachments_for(db,[row.id])]
        if row.recorded_by not in actors:
            actors[row.recorded_by]=db.get(User,row.recorded_by).full_name
        expenses.append({**expense_view(row,payments,files),'recorded_by_name':actors[row.recorded_by],
                         'allocations':[view(item) for item in rows(db,Allocation,Allocation.expense_id==row.id)]})
    batches=[batch_view(db,batch) for batch in rows(db,Batch,Batch.business_id==biz.id)]
    by_batch={row['id']:row for row in batches}
    outputs={output['id']:output for row in batches for output in row['outputs']}
    lots=[]
    for lot in rows(db,FinishedLot,FinishedLot.business_id==biz.id):
        output=outputs[lot.output_id]
        batch=by_batch[output['batch_id']]
        current=lot_stock(db,lot)
        unit=batch['cost']['lots'][lot.id]
        carrying=batch['cost']['book_lots'][lot.id]
        status='expired' if lot.best_before and lot.best_before<date.today() else batch['status']
        lots.append({**view(lot),'label_details':json.loads(lot.label_details),'reference':f'AQUA-LOT-{lot.packaged_on.year}-{lot.id:06d}', 'product':output['name'],
                     'batch_id':batch['id'],'available_units':current,'status':status,'method':batch['method'],
                     'inventory_value_ghs':round(carrying*current,2) if carrying is not None else None,
                     'pricing':pricing(unit,lot.weight_per_unit_kg,Decimal(20)),
                     'movements':[view(item) for item in rows(db,Movement,Movement.lot_id==lot.id)]})
    farms=rows(db,Farm,(Farm.owner_id==biz.owner_id)&Farm.archived_at.is_(None))
    sales=[{**sale_view(db,row),'cost_ghs':ghs(row.processing_cost_pesewas) if row.processing_cost_pesewas is not None else None}
           for row in rows(db,FishSale,FishSale.business_id==biz.id)]
    harvests=[{**view(row),'available_kg':remaining_kg(db,row)} for row in rows(
        db,HarvestLot,HarvestLot.farm_id.in_([farm.id for farm in farms]))] if biz.business_type=='integrated' else []
    grants=permissions_for(db,user,biz)
    if biz.owner_id!=user.id and not grants.intersection({'finance.manage','processing_reports.view'}):
        expenses=[]
    if biz.owner_id!=user.id and not grants.intersection({'sales.manage','processing_reports.view'}):
        sales=[]
    if biz.owner_id!=user.id and not grants.intersection({'pricing.view','sales.manage','processing_reports.view'}):
        for lot in lots:
            lot['pricing']={}
            lot['inventory_value_ghs']=None
        for batch in batches:
            batch['cost']={'input_kg':batch['cost']['input_kg']}
            for source in batch['sources']:
                source.pop('cost_pesewas',None)
    return {'business':view(biz),'methods':[*METHODS,*json.loads(biz.methods_json)],'categories':CATEGORIES,
            'suppliers':[view(row) for row in rows(db,Supplier,Supplier.business_id==biz.id)],
            'raw_lots':[{**view(row),'available_kg':raw_available(db,row),'reference':f'AQUA-RAW-{row.received_on.year}-{row.id:06d}'}
                        for row in rows(db,RawLot,RawLot.business_id==biz.id)],
            'expenses':expenses,'batches':batches,'lots':lots,'sales':sales,'harvests':harvests,
            'farms':[{'id':row.id,'name':row.name} for row in farms],
            'materials':[{**view(row),'available_units':material_stock(db,row.id)[0]}
                         for row in rows(db,Material,Material.business_id==biz.id)],
            'quality_rules':[{**view(rule),'checks':json.loads(rule.checks)} for rule in rows(db,QualityRule,QualityRule.business_id==biz.id)],
            'customers':[view(row) for row in rows(db,Customer,Customer.business_id==biz.id)]
            if 'sales.manage' in grants else []}


@app.get(ROOT+'/sales/{sale_id}/invoice.pdf',tags=TAG)
def invoice(sale_id:int,user:CurrentUser,db:Db):
    from .sales_invoice import build_invoice_pdf
    biz=business(db,user,permission='sales.manage')
    sale=scoped(db,FishSale,biz,sale_id)
    lot=scoped(db,FinishedLot,biz,sale.finished_lot_id)
    output,_=output_for(db,biz,lot.output_id)
    customer_row=scoped(db,Customer,biz,sale.customer_id)
    data={**sale_view(db,sale),'product':output.name,'lot_reference':f'AQUA-LOT-{lot.packaged_on.year}-{lot.id:06d}',
          'price_ghs_per_package':float(Decimal(sale.total_pesewas)/100/sale.packages_sold)}
    return Response(build_invoice_pdf(biz,customer_row,data),media_type='application/pdf',
                    headers={'Content-Disposition':f'attachment; filename="{data["invoice_number"]}.pdf"',
                             'Cache-Control':'private, no-store'})


@app.get(ROOT+'/report',tags=TAG)
def report(user:CurrentUser,db:Db,start:date|None=None,end:date|None=None,
           batch_id:int|None=None,activity:str|None=None,method:str|None=None,product:str|None=None,
           farm_id:int|None=None,unit_id:int|None=None,species:str|None=None,format:Literal['json','csv','pdf']='json'):
    biz=business(db,user,permission='processing_reports.view')
    if start and end and start>end:
        raise HTTPException(422,'Enter a valid reporting date range')
    if farm_id is not None:
        owned_farm(farm_id,db.get(User,biz.owner_id),db)
    if batch_id:
        scoped(db,Batch,biz,batch_id)
    data=workspace(user,db)
    output_ids={output['id'] for batch in data['batches'] for output in batch['outputs']
                if not product or product.casefold() in output['name'].casefold()}
    batches=[row for row in data['batches'] if (not batch_id or row['id']==batch_id)
             and (not method or row['method']==method)
             and (not product or any(output['id'] in output_ids for output in row['outputs']))
             and (not (farm_id or unit_id or species) or any(
                 (not farm_id or source.get('farm_id')==farm_id) and
                 (not unit_id or source.get('unit_id')==unit_id) and
                 (not species or species.casefold() in source['species'].casefold()) for source in row['sources']))]
    batch_ids={row['id'] for row in batches}
    lot_ids={row['id'] for row in data['lots'] if row['batch_id'] in batch_ids and row['output_id'] in output_ids}
    def within(day):
        return (start is None or day>=start) and (end is None or day<=end)
    sales=[row for row in data['sales'] if row['finished_lot_id'] in lot_ids and within(row['sold_on'])]
    scoped_batches=bool(batch_id or method or product or farm_id or unit_id or species)
    expenses=[row for row in data['expenses'] if within(row['occurred_on']) and (not activity or row['activity']==activity)
              and (not scoped_batches or row['batch_id'] in batch_ids or any(a['batch_id'] in batch_ids for a in row['allocations']))]
    unallocated=Decimal(0)
    for row in expenses:
        if row['usage']=='expense' and not row['batch_id']:
            unallocated+=Decimal(str(row['amount_ghs']))-Decimal(sum(item['amount_pesewas'] for item in row['allocations']))/100
    returns=[]
    original={row['id']:row for row in data['sales'] if row['finished_lot_id'] in lot_ids}
    if original:
        for row in db.scalars(select(Movement).where(Movement.sale_id.in_(original),
                                                    Movement.credit_pesewas>0)):
            if within(row.occurred_on):
                returns.append({'invoice_number':original[row.sale_id]['invoice_number'],
                    'lot_id':row.lot_id,'occurred_on':row.occurred_on,'credit_ghs':ghs(row.credit_pesewas)})
    revenue=sum(row['gross_ghs'] for row in sales)-sum(row['credit_ghs'] for row in returns)
    cost=sum(row['cost_ghs'] or 0 for row in sales)
    complete=all(row['cost_ghs'] is not None for row in sales)
    grouped=[]
    for lot in data['lots']:
        matches=[row for row in sales if row['finished_lot_id']==lot['id']]
        credits=sum(row['credit_ghs'] for row in returns if row['lot_id']==lot['id'])
        if matches or credits:
            item_revenue=round(sum(row['gross_ghs'] for row in matches)-credits,2)
            item_cost=round(sum(row['cost_ghs'] or 0 for row in matches),2) if all(
                row['cost_ghs'] is not None for row in matches) else None
            grouped.append({'batch_id':lot['batch_id'],'lot':lot['reference'],'product':lot['product'],
                'revenue_ghs':item_revenue,'cost_ghs':item_cost,
                'gross_profit_ghs':round(item_revenue-item_cost,2) if item_cost is not None else None})
    by_batch=[]
    for batch in batches:
        products=[row for row in grouped if row['batch_id']==batch['id']]
        if products:
            product_cost=sum(row['cost_ghs'] or 0 for row in products) if all(
                row['cost_ghs'] is not None for row in products) else None
            batch_revenue=round(sum(row['revenue_ghs'] for row in products),2)
            by_batch.append({'batch_id':batch['id'],'reference':batch['reference'],'method':batch['method'],
                'revenue_ghs':batch_revenue,'gross_profit_ghs':round(batch_revenue-product_cost,2)
                if product_cost is not None else None})
    owned_ids=[row['id'] for row in data['farms']]
    if farm_id:
        owned_ids=[farm_id]
    legacy=[]
    fresh_revenue=0
    fresh_cost=Decimal(0)
    fresh_complete=True
    if owned_ids and not (batch_id or method or product or unit_id or species):
        for row in db.scalars(select(FarmExpense).where(
                FarmExpense.farm_id.in_(owned_ids),FarmExpense.business_id.is_(None))):
            if within(row.occurred_on):
                payments=rows(db,ExpensePayment,ExpensePayment.expense_id==row.id)
                files=[]
                legacy.append({**expense_view(row,payments,files),'activity':'production',
                               'recorded_by_name':db.get(User,row.recorded_by).full_name})
        for row in db.scalars(select(FishSale).where(FishSale.farm_id.in_(owned_ids),FishSale.harvest_lot_id.is_not(None))):
            if within(row.sold_on):
                fresh_revenue+=row.total_pesewas
                rate=harvest_rate(db,db.get(HarvestLot,row.harvest_lot_id))
                if rate is None:
                    fresh_complete=False
                else:
                    fresh_cost+=Decimal(str(row.quantity_kg))*rate
    if activity in (None,'production'):
        expenses.extend(legacy)
    consolidated=(round(Decimal(str(revenue-cost))+Decimal(fresh_revenue)/100-fresh_cost,2)
                  if complete and fresh_complete and not scoped_batches and not activity else None)
    reports={'sales':sales,'returns':returns,'expenses':expenses,'batches':[row for row in batches if within(row['started_on'])],
             'by_product':grouped,'by_batch':by_batch,'revenue_ghs':round(revenue,2),'cost_of_sales_ghs':round(cost,2) if complete else None,
             'gross_profit_ghs':round(revenue-cost,2) if complete else None,
             'unallocated_expenses_ghs':unallocated,'fresh_revenue_ghs':ghs(fresh_revenue),
             'consolidated_gross_profit_ghs':consolidated,
             'consolidated_result_ghs':round(consolidated-unallocated,2) if consolidated is not None else None,
             'processing_result_ghs':round(Decimal(str(revenue-cost))-unallocated,2)
             if complete and not scoped_batches and not activity else None}
    if format=='json':
        return reports
    heading=['Processing report',start or 'All dates',end or 'All dates',
             *(str(value) for value in (activity,batch_id,method,product,farm_id,unit_id,species) if value is not None)]
    totals=['Revenue',reports['revenue_ghs'],'Cost of sales',reports['cost_of_sales_ghs'],
            'Gross profit',reports['gross_profit_ghs'],'Unallocated expenses',unallocated]
    columns=['Type','Reference','Date','Activity','Amount GHS','Cost of sales GHS']
    body=[('Expense',row['reference'],row['occurred_on'],row['activity'],row['amount_ghs'],'') for row in expenses]
    body.extend(('Invoice',row['invoice_number'],row['sold_on'],'sales',row['gross_ghs'],row['cost_ghs']) for row in sales)
    body.extend(('Credit',row['invoice_number'],row['occurred_on'],'returns',-row['credit_ghs'],'') for row in returns)
    if format=='pdf':
        from io import BytesIO
        from xml.sax.saxutils import escape
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer
        from . import loan_appraisal_pdf
        stream=BytesIO()
        doc=SimpleDocTemplate(stream,pagesize=landscape(A4),title='Processing Report')
        text_style=ParagraphStyle('processing',fontName='Appraisal',fontSize=9)
        def cell(value):
            return Paragraph(escape(str(value if value is not None else 'Unavailable')),text_style)
        table=LongTable([[cell(value) for value in row] for row in [columns,*body]],repeatRows=1)
        doc.build([cell(' | '.join(map(str,heading))),cell(' | '.join(map(str,totals))),Spacer(1,10),table])
        return Response(stream.getvalue(),media_type='application/pdf',headers={
            'Content-Disposition':'attachment; filename="processing-report.pdf"','Cache-Control':'private, no-store'})
    import csv
    from io import StringIO
    stream=StringIO()
    writer=csv.writer(stream)
    def safe(value):
        return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value
    writer.writerow([safe(value) for value in heading])
    writer.writerow(totals)
    writer.writerow(columns)
    writer.writerows([safe(value) for value in row] for row in body)
    return Response(stream.getvalue(),media_type='text/csv',headers={
        'Content-Disposition':'attachment; filename="processing-report.csv"','Cache-Control':'private, no-store'})


@app.get(ROOT+'/lots/{lot_id}/label.pdf',tags=TAG)
def lot_label(lot_id:int,user:CurrentUser,db:Db,qr:bool=False):
    from io import BytesIO
    from xml.sax.saxutils import escape
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from . import loan_appraisal_pdf
    biz=business(db,user)
    lot=scoped(db,FinishedLot,biz,lot_id)
    output,batch=output_for(db,biz,lot.output_id)
    reference=f'AQUA-LOT-{lot.packaged_on.year}-{lot.id:06d}'
    species=', '.join(dict.fromkeys(row['species'] for row in batch_view(db,batch)['sources']))
    fields=json.loads(lot.label_details)
    complete=all((fields.get(key) or '').strip() for key in
                 ('ingredients','manufacturer','manufacturer_address','country_of_origin'))
    lines=[output.name,fields.get('brand'),reference,
           f'Batch AQUA-PROC-{batch.started_on.year}-{batch.id:06d} | {batch.method}',
           f'Fish species: {species}',f'Net weight: {lot.weight_per_unit_kg:g} kg',
           f'Manufactured: {batch.completed_on}',f'Packaged: {lot.packaged_on}']
    for key,label in (('ingredients','Ingredients'),('manufacturer','Manufacturer'),
                      ('manufacturer_address','Manufacturer address'),('premises_address','Premises location'),
                      ('country_of_origin','Country of origin'),('directions','Directions'),
                      ('storage_instructions','Storage and handling')):
        if fields.get(key):
            lines.append(f'{label}: {fields[key]}')
    if lot.best_before:
        lines.append(f'Best before: {lot.best_before}')
    if not complete:
        lines.insert(0,'DRAFT LABEL ? manufacturer or product information is incomplete')
    stream=BytesIO()
    document=SimpleDocTemplate(stream,pagesize=(310,460),title=reference,
                               topMargin=20,bottomMargin=20,leftMargin=20,rightMargin=20)
    style=ParagraphStyle('lot-label',fontName='Appraisal',fontSize=9,leading=12)
    story=[Paragraph(escape(value),style) for value in lines if value]
    if qr:
        widget=QrCodeWidget(reference,barWidth=70,barHeight=70)
        drawing=Drawing(70,70)
        drawing.add(widget)
        story.extend([Spacer(1,8),drawing])
    document.build(story)
    return Response(stream.getvalue(),media_type='application/pdf',headers={
        'Content-Disposition':f'attachment; filename="{reference}.pdf"','Cache-Control':'private, no-store'})


class EvidenceIn(BaseModel):
    batch_id: int
    stage: Literal['harvest_transfer','processing','packaging','quality','spoilage','stock_adjustment']
    recorded_on: date
    notes: str | None = Field(default=None,max_length=1000)
    media_type: Literal['video/webm','video/mp4','image/jpeg','image/png','image/webp','application/pdf']
    content: str = Field(min_length=1,max_length=41943040)


@app.post(ROOT+'/evidence',status_code=201,tags=TAG)
def attach_evidence(data:EvidenceIn,user:CurrentUser,db:Db):
    import base64
    import binascii
    from .evidence import MAX_VIDEO_BYTES
    biz=business(db,user,True,'processing.create')
    batch=scoped(db,Batch,biz,data.batch_id)
    check_date(data.recorded_on,batch.started_on)
    if data.media_type.startswith('video/'):
        try:
            content=base64.b64decode(data.content,validate=True)
        except (ValueError,binascii.Error):
            raise HTTPException(422,'Unable to read evidence file') from None
        if len(content)>MAX_VIDEO_BYTES:
            raise HTTPException(413,'Video exceeds the 30 MB size limit')
        valid=content.startswith(b'\x1a\x45\xdf\xa3') if data.media_type=='video/webm' else content[4:8]==b'ftyp'
        if not valid:
            raise HTTPException(415,'Video file content does not match its media type')
    else:
        actual,content=validate_attachment(data.content)
        if actual!=data.media_type:
            raise HTTPException(415,'Evidence file content does not match its media type')
    return save(db,user,ProcessingEvidence(business_id=biz.id,recorded_by=user.id,content=content,
        **data.model_dump(exclude={'content'})),'attach')


@app.get(ROOT+'/evidence',tags=TAG)
def evidence_list(user:CurrentUser,db:Db,farm_id:int|None=None,batch_id:int|None=None,
                  start:date|None=None,end:date|None=None,page:int=1):
    if page<1 or page>1000000 or start and end and start>end:
        raise HTTPException(422,'Enter a valid evidence page and date range')
    if farm_id is not None:
        owned_farm(farm_id,user,db)
    biz=business(db,user)
    media=ProcessingEvidence
    filters=[media.business_id==biz.id]
    if farm_id is not None:
        batch_ids=select(ProcessingInput.batch_id).join(HarvestLot,HarvestLot.id==ProcessingInput.harvest_id
            ).where(HarvestLot.farm_id==farm_id)
        filters.append(media.batch_id.in_(batch_ids))
    if batch_id is not None:
        scoped(db,Batch,biz,batch_id)
        filters.append(media.batch_id==batch_id)
    if start:
        filters.append(media.recorded_on>=start)
    if end:
        filters.append(media.recorded_on<=end)
    query=select(media.id,media.batch_id,media.stage,media.recorded_on,media.notes,media.media_type,
                 func.length(media.content).label('size_bytes'),User.full_name.label('recorded_by'),
                 Batch.started_on).join(User,User.id==media.recorded_by).join(Batch,Batch.id==media.batch_id).where(*filters)
    result=db.execute(query.order_by(media.recorded_on.desc(),media.id.desc()).offset((page-1)*25).limit(25)).mappings()
    return {'items':[{**dict(row),'batch_reference':f'AQUA-PROC-{row.started_on.year}-{row.batch_id:06d}'} for row in result],
            'total':db.scalar(select(func.count()).select_from(media).where(*filters)),'page':page,'size':25}


@app.get(ROOT+'/evidence/{evidence_id}/content',tags=TAG)
def evidence_content(evidence_id:int,user:CurrentUser,db:Db):
    biz=business(db,user)
    row=scoped(db,ProcessingEvidence,biz,evidence_id)
    ext={'video/mp4':'mp4','video/webm':'webm','image/jpeg':'jpg','image/png':'png','image/webp':'webp','application/pdf':'pdf'}
    return Response(row.content,media_type=row.media_type,headers={
        'Content-Disposition':f'attachment; filename="processing-evidence-{row.id}.{ext[row.media_type]}"',
        'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


class StaffIn(BaseModel):
    email: str = Field(min_length=3,max_length=255)
    permissions: list[str] = Field(max_length=len(PERMISSIONS))


@app.get(ROOT+'/staff',tags=TAG)
def staff_list(user:CurrentUser,db:Db):
    biz=business(db,user)
    if biz.owner_id!=user.id:
        raise HTTPException(403,'Only the business owner can manage processing staff')
    result=[]
    for member in rows(db,ProcessingMember,ProcessingMember.business_id==biz.id):
        account=db.get(User,member.user_id)
        result.append({'name':account.full_name,'email':account.email,'permissions':json.loads(member.permissions)})
    return result


@app.put(ROOT+'/staff',tags=TAG)
def assign_staff(data:StaffIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'finance.manage')
    if biz.owner_id!=user.id:
        raise HTTPException(403,'Only the business owner can manage processing staff')
    account=db.scalar(select(User).where(func.lower(User.email)==data.email.strip().lower(),
                                          User.account_type.in_(('farmer','legacy')),User.id!=user.id))
    if account is None:
        raise HTTPException(404,'Existing staff account unavailable')
    if set(data.permissions)-set(PERMISSIONS):
        raise HTTPException(422,'Select valid processing permissions')
    db.execute(update(User).where(User.id==account.id).values(full_name=User.full_name))
    member=db.scalar(select(ProcessingMember).where(ProcessingMember.user_id==account.id))
    if member and member.business_id!=biz.id or db.scalar(select(ProcessingBusiness.id).where(
            ProcessingBusiness.owner_id==account.id,ProcessingBusiness.business_type!='farmer')):
        raise HTTPException(409,'This account already has a processing workspace')
    if not data.permissions:
        if member:
            audit(db,user,'remove','processing_members',member.id)
            db.delete(member)
            db.commit()
        return {'message':'Processing access removed'}
    member=member or ProcessingMember(business_id=biz.id,user_id=account.id)
    member.permissions=json.dumps(sorted(set(data.permissions)|{'processing.view'}))
    return save(db,user,member,'assign')


class RuleIn(BaseModel):
    method: str = Field(min_length=1,max_length=150)
    product: str = Field(default='',max_length=150)
    checks: list[str] = Field(max_length=30)


def quality_checks(db,biz,batch):
    products={row.name.casefold() for row in rows(db,Output,Output.batch_id==batch.id)}
    checks={}
    methods={batch.method,*(step['method'] for step in json.loads(batch.steps))}
    for rule in rows(db,QualityRule,(QualityRule.business_id==biz.id)&QualityRule.method.in_(methods)):
        if not rule.product or rule.product.casefold() in products:
            for value in json.loads(rule.checks):
                checks[value.casefold()]=value
    return list(checks.values())


@app.put(ROOT+'/quality-rules',tags=TAG)
def save_quality_rule(data:RuleIn,user:CurrentUser,db:Db):
    biz=business(db,user,True,'processing.quality_review')
    if biz.owner_id!=user.id:
        raise HTTPException(403,'Only the business owner can configure quality checks')
    if data.method not in (*METHODS,*json.loads(biz.methods_json)):
        raise HTTPException(422,'Select an existing processing method')
    product=data.product.strip()
    checks=sorted({value.strip() for value in data.checks if value.strip()})
    if any(len(value)>120 for value in checks):
        raise HTTPException(422,'Quality check names must be 120 characters or fewer')
    rule=db.scalar(select(QualityRule).where(QualityRule.business_id==biz.id,
        QualityRule.method==data.method,func.lower(QualityRule.product)==product.lower()))
    rule=rule or QualityRule(business_id=biz.id,method=data.method,product=product)
    rule.checks=json.dumps(checks)
    return save(db,user,rule,'configure')
