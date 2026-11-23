
from datetime import date, datetime, timezone
from decimal import Decimal

from .test_api import client
from .test_operations import auth
from app.forecasting import CycleExpense, ProductionPlan
from app.main import SessionLocal
from app.operations import StockingCycle
from app.sales import Customer, FishSale, HarvestLot

TODAY = str(date.today())


def post(path, body, headers, status=None):
    reply=client.post('/processing'+path,json=body,headers=headers)
    assert reply.status_code==status if status else reply.is_success, reply.text
    return reply.json()


def workspace(headers):
    response=client.get('/processing/workspace',headers=headers)
    assert response.is_success,response.text
    return response.json()


def test_processor_only_workflow_uses_expense_and_sales_ledgers():
    email='processor-only@example.com'
    password='DedicatedProcessor123'
    registered=client.post('/auth/farmer/register',json={
        'full_name':'Processor Only','email':email,'password':password,'business_type':'processor',
    })
    assert registered.status_code==201,registered.text
    token=client.post('/auth/farmer/login',json={'email':email,'password':password}).json()['access_token']
    headers={'Authorization':'Bearer '+token}
    assert client.get('/farms',headers=headers).json()==[]
    supplier_id=post('/suppliers',{'name':'Tilapia supplier'},headers)['id']
    purchase={'supplier_id':supplier_id,'species':'Tilapia','received_on':TODAY,
        'quantity_kg':'100','unit_price':'10','storage':'Cold room','exception_reason':'Supplier receipt pending',
        'initial_payment':{'paid_on':TODAY,'amount_ghs':'200','method':'cash'},'request_key':'raw-receipt'}
    raw=post('/purchases',purchase,headers)['id']
    assert post('/purchases',purchase,headers)['id']==raw
    post('/purchases',{**purchase,'quantity_kg':'101'},headers,409)
    batch=post('/batches',{'method':'Smoking','facility':'Smoking shed','started_on':TODAY},headers)['id']
    batch_path=f'/batches/{batch}'
    allocation={'source':'purchased','source_id':raw,'quantity_kg':'60','request_key':'raw-allocation'}
    allocation_id=post(batch_path+'/inputs',allocation,headers)['id']
    assert post(batch_path+'/inputs',allocation,headers)['id']==allocation_id
    post(batch_path+'/inputs',{'source':'purchased','source_id':raw,'quantity_kg':'41'},headers,409)
    for category,amount in [('Fuel','50'),('Labour and wages','70')]:
        post('/expenses',{'activity':'processing','batch_id':batch,'category':category,'description':category,
            'occurred_on':TODAY,'amount_ghs':amount,'exception_reason':'Paper receipt retained'},headers)
    post(batch_path+'/steps',{'method':'Smoking','occurred_on':TODAY,'details':'Recorded oven and fuel use'},headers)
    post(batch_path+'/complete',{'completed_on':TODAY,'outputs':[{'name':'Smoked fish','quantity_kg':'30'},{'name':'Recoverable trimmings','quantity_kg':'5','is_byproduct':True}],
        'byproducts_kg':'5','waste_kg':'5','moisture_loss_kg':'20'},headers)
    output=workspace(headers)['batches'][0]['outputs'][0]['id']
    material=post('/materials',{'name':'Pouch'},headers)['id']
    post('/material-receipts',{'material_id':material,'quantity':80,'expense':{'category':'Packaging',
        'description':'Pouches','occurred_on':TODAY,'amount_ghs':'80','exception_reason':'Invoice held by store'}},headers)
    packaging={'output_id':output,'material_id':material,'packaging':'Pouch','storage':'Dry store','packaged_on':TODAY}
    lot=post('/packages',{**packaging,'units':20,'material_used':20,'weight_per_unit_kg':'0.5'},headers)['id']
    large=post('/packages',{**packaging,'units':20,'material_used':20,'weight_per_unit_kg':'1'},headers)['id']
    post('/packages',{**packaging,'units':1,'material_used':1,'weight_per_unit_kg':'1'},headers,409)
    data=workspace(headers)
    assert data['raw_lots'][0]['available_kg']==40
    assert data['expenses'][0]['outstanding_ghs']==800
    assert data['materials'][0]['available_units']==40
    cost=data['batches'][0]['cost']
    assert cost['raw_ghs']==600 and cost['total_cost_ghs']==760
    assert Decimal(str(cost['cost_per_kg']))==Decimal('25.3333')
    quote=client.get(f'/processing/lots/{lot}/pricing?margin=20&proposed=20',headers=headers).json()
    assert Decimal(str(quote['break_even']))==13 and Decimal(str(quote['suggested']))==Decimal('16.25')
    assert Decimal(client.get(f'/processing/lots/{large}/pricing',headers=headers).json()['break_even'])==25
    customer=post('/customers',{'name':'Local retailer'},headers)['id']
    sale_data={'lot_id':lot,'customer_id':customer,'units':5,'sold_on':TODAY,'unit_price':'20','request_key':'sale-test-key'}
    post('/sales',sale_data,headers,409)
    rule=client.put('/processing/quality-rules',headers=headers,json={
        'method':'Smoking','product':'Smoked fish','checks':['Packaging inspected','Process log reviewed'],
    })
    assert rule.status_code==200,rule.text
    release={'decision':'release','checked_on':TODAY,'observations':'Authorized quality review recorded'}
    post(batch_path+'/quality',release,headers,409)
    staff=auth('processing-review-staff@example.com')
    assigned=client.put('/processing/staff',headers=headers,json={
        'email':'processing-review-staff@example.com','permissions':['processing.create'],
    })
    assert assigned.status_code==200,assigned.text
    assert workspace(staff)['expenses']==[]
    assert workspace(staff)['batches'][0]['cost']=={'input_kg':60.0}
    assert client.get(f'/processing/lots/{lot}/pricing',headers=staff).status_code==403
    post(batch_path+'/quality',{**release,'checks':['Packaging inspected','Process log reviewed']},staff,403)
    post(batch_path+'/quality',{**release,'checks':['Packaging inspected','Process log reviewed']},headers)
    sale=post('/sales',sale_data,headers)
    assert post('/sales',sale_data,headers)['id']==sale['id']
    payment={'paid_on':TODAY,'amount_ghs':'50','method':'mobile_money','reference':'processor-customer-1'}
    post(f'/sales/{sale["id"]}/payments',payment,headers)
    post(f'/sales/{sale["id"]}/payments',payment,headers,409)
    state=workspace(headers)
    assert state['sales'][0]['outstanding_ghs']==50 and state['lots'][0]['available_units']==15
    report=client.get('/processing/report',headers=headers).json()
    assert report['revenue_ghs']==100 and report['cost_of_sales_ghs']==65 and report['gross_profit_ghs']==35
    for document in (f'/processing/lots/{lot}/label.pdf?qr=true',f'/processing/sales/{sale["id"]}/invoice.pdf'):
        pdf=client.get(document,headers=headers)
        assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    post(f'/lots/{lot}/movements',{'units':1,'sale_id':sale['id'],'reason':'Customer returned unopened product'},headers)
    assert workspace(headers)['lots'][0]['status']=='held'
    post('/sales',{**sale_data,'request_key':'held-sale'},headers,409)
    post(f'/lots/{lot}/movements',{'units':1,'sale_id':sale['id'],'reason':'Credit for returned package',
        'credit_ghs':'20','refund_ghs':'10','refund_method':'cash'},headers)
    credited=workspace(headers)['sales'][0]
    assert credited['credits_ghs']==20 and credited['paid_ghs']==40 and credited['outstanding_ghs']==40
    reports=client.get('/processing/report',headers=headers).json()
    assert reports['revenue_ghs']==80 and reports['gross_profit_ghs']==15
    assert client.get('/processing/report?format=pdf',headers=headers).content.startswith(b'%PDF-')
    import base64
    from io import BytesIO
    from PIL import Image
    content=BytesIO()
    Image.new('RGB',(1,1)).save(content,format='PNG')
    evidence=post('/evidence',{'batch_id':batch,'stage':'quality','recorded_on':TODAY,
        'media_type':'image/png','content':base64.b64encode(content.getvalue()).decode()},headers)['id']
    library=client.get('/processing/evidence',headers=headers).json()
    assert library['items'][0]['id']==evidence and 'content' not in library['items'][0]
    evidence_url=f'/processing/evidence/{evidence}/content'
    assert client.get(evidence_url,headers=headers).content==content.getvalue()
    outsider=auth('processing-outsider@example.com')
    assert client.get(evidence_url,headers=outsider).status_code==404
    checklist={**release,'checks':['Packaging inspected','Process log reviewed']}
    post(batch_path+'/quality',checklist,headers)
    byproduct=workspace(headers)['batches'][0]['outputs'][1]['id']
    recovery=post('/packages',{'output_id':byproduct,'packaging':'Bulk','storage':'Dry store','packaged_on':TODAY,
        'units':5,'weight_per_unit_kg':'1'},headers)['id']
    post(batch_path+'/quality',checklist,headers)
    post('/sales',{'lot_id':recovery,'customer_id':customer,'units':2,'sold_on':TODAY,'unit_price':'15',
        'request_key':'byproduct-credit'},headers)
    assert workspace(headers)['batches'][0]['cost']['recognized_byproduct_credit_ghs']==30
    credited_quote=client.get(f'/processing/lots/{lot}/pricing',headers=headers).json()
    assert Decimal(str(credited_quote['break_even']))==Decimal('12.5')
    adjusted_report=client.get('/processing/report',headers=headers).json()
    assert adjusted_report['revenue_ghs']==110 and adjusted_report['gross_profit_ghs']==45
    post(batch_path+'/quality',{'decision':'reject','checked_on':TODAY,'observations':'Release withdrawn after review'},headers)
    post('/sales',{**sale_data,'request_key':'rejected-sale'},headers,409)

    assert client.get(f'/processing/lots/{lot}/pricing',headers=outsider).status_code==404


def test_integrated_harvest_allocations_deduct_fresh_stock_and_transfer_cost():
    headers=auth('integrated-processor@example.com')
    assert client.put('/processing/business',json={'name':'Integrated fish','business_type':'integrated'},headers=headers).is_success
    farm=client.post('/farms',headers=headers,json={'name':'Pond Farm','region':'Northern','district':'Tamale',
        'farm_type':'pond','species':'Tilapia'}).json()
    fid=farm['id']
    unit=client.post(f'/farms/{fid}/units',headers=headers,json={'name':'Pond A','unit_type':'pond'}).json()
    with SessionLocal.begin() as db:
        cycle=StockingCycle(unit_id=unit['id'],species='Tilapia',stocked_count=1000,initial_average_weight_g=4,
                           stocked_on=date.today(),closed_at=datetime.now(timezone.utc))
        db.add(cycle)
        db.flush()
        lot=HarvestLot(farm_id=fid,cycle_id=cycle.id,harvested_on=date.today(),quantity_kg=100,fish_count=1000)
        plan=ProductionPlan(farm_id=fid,cycle_id=cycle.id,species='Tilapia',fingerling_count=1000,
            initial_weight_g=4,target_weight_g=100,survival_pct=100,expected_fcr=1,feed_price_ghs_per_kg=2,
            bag_size_kg=25,fingerling_cost_ghs=100,other_budget_ghs=0,desired_profit_pct=20,profit_method='margin')
        buyer=Customer(farm_id=fid,name='Fresh buyer',customer_type='individual')
        db.add_all([lot,plan,buyer])
        db.flush()
        lot_id=lot.id
        db.add(CycleExpense(plan_id=plan.id,category='labour',amount_ghs=400,occurred_on=date.today()))
        db.add(FishSale(farm_id=fid,customer_id=buyer.id,harvest_lot_id=lot.id,quantity_kg=30,
                        unit_price_pesewas=1000,total_pesewas=30000,sold_on=date.today()))
    for method,weight in [('Smoking',50),('Freezing',20)]:
        batch=post('/batches',{'method':method,'facility':'Processing room','started_on':TODAY},headers)['id']
        post(f'/batches/{batch}/inputs',{'source':'harvest','source_id':lot_id,'quantity_kg':weight},headers)
    state=workspace(headers)
    assert state['harvests'][0]['available_kg']==0
    assert state['batches'][0]['cost']['raw_ghs']==200
    assert state['batches'][1]['cost']['raw_ghs']==80
    assert state['batches'][0]['sources'][0]['unit_id']==unit['id']
    assert state['expenses']==[]
    post(f'/batches/{batch}/inputs',{'source':'harvest','source_id':lot_id,'quantity_kg':'0.5'},headers,409)


    first=state['batches'][0]['id']
    supplier=post('/suppliers',{'name':'Second raw supplier'},headers)['id']
    bought=post('/purchases',{'supplier_id':supplier,'species':'Tilapia','received_on':TODAY,'quantity_kg':'5',
        'unit_price':'10','storage':'Cold room','exception_reason':'Paper purchase record'},headers)['id']
    post(f'/batches/{first}/inputs',{'source':'purchased','source_id':bought,'quantity_kg':'5'},headers)
    for step in ('Smoking','Freezing'):
        post(f'/batches/{first}/steps',{'method':step,'occurred_on':TODAY,'details':'Processing conditions recorded'},headers)
    post(f'/batches/{first}/complete',{'completed_on':TODAY,'outputs':[{'name':'Value-added tilapia','quantity_kg':'35'}],
        'moisture_loss_kg':'20'},headers)
    final=workspace(headers)['batches'][0]
    assert final['cost']['input_kg']==55 and final['cost']['raw_ghs']==250
    assert len(final['sources'])==2 and len(final['steps'])==2
