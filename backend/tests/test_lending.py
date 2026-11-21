import os
from datetime import date, datetime, timedelta, timezone
from .test_api import client, upload_loan_video
from .test_foundation import signup
from app.automated_costing import CycleExpense
from app.feeding import FeedLedger, FeedProduct
from app.forecasting import ProductionPlan
from app.main import ProductionUnit, SessionLocal
from app.operations import FishSample, StockingCycle
from app.sales import Customer, FishSale, HarvestLot, SalePayment


def submit_application(farm_id,payload,headers,evidence_id=None):
    evidence_id=evidence_id or upload_loan_video(headers,farm_id,'loan_application')
    return client.post(f'/farms/{farm_id}/loan-applications',
        json={**payload,'evidence_id':evidence_id},headers=headers)

def test_lending_consent_roles_and_appraisal():
    farmer=signup('loan-farmer@example.com')
    lender=signup('loan-lender@example.com')
    officer=signup('loan-officer@example.com')
    reviewer=signup('loan-reviewer@example.com')
    stranger=signup('loan-stranger@example.com')
    admin=signup('loan-admin@example.com')
    os.environ['AQUAFARM_PLATFORM_ADMIN_EMAIL']='loan-admin@example.com'
    farm=client.post('/farms',json={'name':'Loan Test Farm','region':'North East','district':'Yunyoo','farm_type':'pond','species':'Tilapia'},headers=farmer)
    assert farm.status_code==201, farm.text
    fid=farm.json()['id']
    inst=client.post('/finance/institutions',json={'name':'Test Rural Bank','institution_type':'rural_bank','registration_number':'TEST-123'},headers=lender)
    assert inst.status_code==201,inst.text
    iid=inst.json()['id']
    assert inst.json()['status']=='pending'
    assert client.post(f'/finance/institutions/{iid}/members',json={'user_email':'loan-officer@example.com','role':'officer'},headers=lender).status_code==404
    payload={'institution_id':iid,'requested_ghs':'20000.00','term_months':12,'purpose':'Fingerlings and fish feed for next production cycle','monthly_other_income_ghs':'500.00','monthly_household_expenses_ghs':'250.00','monthly_external_debt_ghs':'100.00','share_report':True}
    assert client.post(f'/farms/{fid}/loan-applications',json=payload,headers=farmer).status_code==422
    timestamp=datetime.now(timezone.utc).isoformat()
    missing_duration=client.post(
        f'/farms/{fid}/loan-evidence',
        params={'record_type':'loan_application','captured_at':timestamp,
                'device_recorded_at':timestamp},
        content=b'\x1a\x45\xdf\xa3'+bytes(32),
        headers={**farmer,'Content-Type':'video/webm'},
    )
    assert missing_duration.status_code==422,missing_duration.text
    invalid_video=client.post(
        f'/farms/{fid}/loan-evidence',
        params={'record_type':'loan_application','captured_at':timestamp,
                'device_recorded_at':timestamp,'duration_seconds':14},
        content=b'\x1a\x45\xdf\xa3'+bytes(32),
        headers={**farmer,'Content-Type':'video/webm'},
    )
    assert invalid_video.status_code==422,invalid_video.text
    assert submit_application(fid,payload,farmer).status_code==404
    assert client.post(f'/finance/institutions/{iid}/verify',headers=lender).status_code==403
    assert client.post(f'/finance/institutions/{iid}/verify',headers=admin).status_code==200
    assert client.post(f'/finance/institutions/{iid}/members',json={'user_email':'loan-officer@example.com','role':'officer'},headers=lender).status_code==200
    assert client.post(f'/finance/institutions/{iid}/members',json={'user_email':'loan-reviewer@example.com','role':'reviewer'},headers=lender).status_code==200
    assert client.post(f'/finance/institutions/{iid}/members',json={'user_email':'loan-officer@example.com','role':'officer'},headers=lender).status_code==409
    assert client.post(f'/finance/institutions/{iid}/members',json={'user_email':'loan-stranger@example.com','role':'officer'},headers=stranger).status_code==404
    assert client.get('/finance/institutions/mine',headers=officer).json()[0]['role']=='officer'
    assert client.get('/finance/institutions/mine',headers=reviewer).json()[0]['role']=='reviewer'
    assert submit_application(fid,{**payload,'share_report':False},farmer).status_code==422
    assert client.post(f'/farms/{fid}/loan-applications',json={**payload,'evidence_id':1},headers=stranger).status_code==404
    evidence_id=upload_loan_video(farmer,fid,'loan_application')
    response=submit_application(fid,payload,farmer,evidence_id)
    assert response.status_code==201,response.text
    reused=client.post(f'/farms/{fid}/loan-applications',
        json={**payload,'requested_ghs':'15000.00','evidence_id':evidence_id},headers=farmer)
    assert reused.status_code==422,reused.text
    aid=response.json()['id']
    assert client.get(f'/finance/institutions/{iid}/applications/{aid}',headers=stranger).status_code==404
    detail=client.get(f'/finance/institutions/{iid}/applications/{aid}',headers=lender)
    assert detail.status_code==200,detail.text
    snapshot=detail.json()['shared_report_snapshot']
    assert snapshot['application_video_evidence']['duration_seconds']==15
    assert snapshot['application_video_evidence']['device_recorded_at']
    assert snapshot['application_video_evidence']['server_received_at']
    assert snapshot['farm']['farm_id']==fid
    assert snapshot['farmer']['email']=='loan-farmer@example.com'
    assert snapshot['cash_flow']['farmer_declared_monthly_external_debt_payments_ghs']==100
    assert snapshot['cash_flow']['estimated_monthly_repayment_capacity_ghs'] is None
    assert 'latitude' not in snapshot['farm']
    assert snapshot['sales']['outstanding_customer_credit_ghs']==0
    information={'decision':'more_information','rationale':'Please provide a current production plan and cost estimate'}
    assert client.post(f'/finance/institutions/{iid}/applications/{aid}/appraise',json=information,headers=officer).status_code==404
    requested=client.post(f'/finance/institutions/{iid}/applications/{aid}/appraise',json=information,headers=reviewer)
    assert requested.status_code==200,requested.text
    assert client.get(f'/farms/{fid}/loan-applications',headers=farmer).json()[0]['status']=='more_information'
    excessive={'decision':'approved','rationale':'Cash flow and production plan reviewed and accepted','approved_ghs':'25000.00'}
    assert client.post(f'/finance/institutions/{iid}/applications/{aid}/appraise',json=excessive,headers=reviewer).status_code==422
    decision={'decision':'approved','rationale':'Cash flow and production plan reviewed and accepted','approved_ghs':'18000.00'}
    assert client.post(f'/finance/institutions/{iid}/applications/{aid}/appraise',json=decision,headers=stranger).status_code==404
    approved=client.post(f'/finance/institutions/{iid}/applications/{aid}/appraise',json=decision,headers=reviewer)
    assert approved.status_code==200,approved.text
    assert approved.json()['status']=='approved'
    assert client.post(f'/finance/institutions/{iid}/applications/{aid}/appraise',json=decision,headers=reviewer).status_code==409
    assert client.get(f'/farms/{fid}/loan-applications',headers=farmer).json()[0]['status']=='approved'
    rejected_application=submit_application(fid,{**payload,'requested_ghs':'5000.00'},farmer)
    assert rejected_application.status_code==201,rejected_application.text
    rejected=client.post(f"/finance/institutions/{iid}/applications/{rejected_application.json()['id']}/appraise",json={'decision':'rejected','rationale':'Repayment capacity does not support this request'},headers=reviewer)
    assert rejected.status_code==200,rejected.text
    statuses={item['id']:item['status'] for item in client.get(f'/farms/{fid}/loan-applications',headers=farmer).json()}
    assert statuses[aid]=='approved'
    assert statuses[rejected_application.json()['id']]=='rejected'


def test_loan_appraisal_snapshot_includes_production_cashflow_and_privacy_boundaries():
    farmer=signup('appraisal-data-farmer@example.com')
    lender=signup('appraisal-data-lender@example.com')
    admin=signup('appraisal-data-admin@example.com')
    os.environ['AQUAFARM_PLATFORM_ADMIN_EMAIL']='appraisal-data-admin@example.com'
    farm=client.post('/farms',json={'name':'Appraisal Data Farm','region':'North East','district':'Yunyoo','farm_type':'pond','species':'Tilapia'},headers=farmer)
    assert farm.status_code==201,farm.text
    farm_id=farm.json()['id']
    institution=client.post('/finance/institutions',json={'name':'Appraisal Data Bank','institution_type':'rural_bank','registration_number':'TEST-APPRAISAL-1'},headers=lender)
    assert institution.status_code==201,institution.text
    institution_id=institution.json()['id']
    assert client.post(f'/finance/institutions/{institution_id}/verify',headers=admin).status_code==200

    with SessionLocal() as db:
        unit=ProductionUnit(farm_id=farm_id,name='North Pond',unit_type='pond')
        db.add(unit);db.flush()
        cycle=StockingCycle(unit_id=unit.id,species='Tilapia',stocked_count=1000,initial_average_weight_g=10,
            stocked_on=date.today()-timedelta(days=60))
        db.add(cycle);db.flush()
        db.add(FishSample(cycle_id=cycle.id,sampled_on=date.today()-timedelta(days=1),
            weights_g_json='[20,30]',sample_count=2,average_weight_g=25))
        plan=ProductionPlan(farm_id=farm_id,cycle_id=cycle.id,species='Tilapia',fingerling_count=1000,
            initial_weight_g=10,target_weight_g=500,survival_pct=90,expected_fcr=1.5,
            feed_price_ghs_per_kg=2,bag_size_kg=25,fingerling_cost_ghs=100,
            other_budget_ghs=50,desired_profit_pct=20,profit_method='markup')
        db.add(plan);db.flush()
        db.add(CycleExpense(plan_id=plan.id,category='labour',amount_ghs=20,occurred_on=date.today()-timedelta(days=1)))
        customer=Customer(farm_id=farm_id,name='Private Buyer',customer_type='individual',phone='0240000000')
        db.add(customer);db.flush()
        harvest=HarvestLot(farm_id=farm_id,cycle_id=cycle.id,harvested_on=date.today()-timedelta(days=1),
            quantity_kg=10,fish_count=100)
        db.add(harvest);db.flush()
        sale=FishSale(farm_id=farm_id,harvest_lot_id=harvest.id,customer_id=customer.id,
            sold_on=date.today()-timedelta(days=1),quantity_kg=5,unit_price_pesewas=2000,total_pesewas=10000)
        db.add(sale);db.flush()
        db.add(SalePayment(farm_id=farm_id,sale_id=sale.id,paid_on=date.today()-timedelta(days=1),
            amount_pesewas=5000,method='cash'))
        feed=FeedProduct(farm_id=farm_id,name='Grower pellets')
        db.add(feed);db.flush()
        db.add_all([
            FeedLedger(feed_id=feed.id,event_type='receipt',quantity_delta_kg=50,cost_ghs=100,
                occurred_on=date.today()-timedelta(days=1)),
            FeedLedger(feed_id=feed.id,event_type='feeding',quantity_delta_kg=-10,
                occurred_on=date.today()-timedelta(days=1),cycle_id=cycle.id),
        ])
        db.commit()

    application=submit_application(farm_id,{
        'institution_id':institution_id,'requested_ghs':'1000.00','term_months':10,
        'purpose':'Purchase feed and fingerlings for this cycle','monthly_other_income_ghs':'500.00',
        'monthly_household_expenses_ghs':'200.00','monthly_external_debt_ghs':'50.00','share_report':True,
    },farmer)
    assert application.status_code==201,application.text
    lender_detail=client.get(f"/finance/institutions/{institution_id}/applications/{application.json()['id']}",headers=lender)
    assert lender_detail.status_code==200,lender_detail.text
    snapshot=lender_detail.json()['shared_report_snapshot']
    assert snapshot['production_history'][0]['latest_average_weight_g']==25
    assert snapshot['production_history'][0]['sampling_history'][0]['average_weight_g']==25
    assert snapshot['production_history'][0]['harvests'][0]['quantity_kg']==10
    assert snapshot['production_estimates'][0]['expected_harvest_kg']==450
    assert snapshot['sales']['invoiced_sales_revenue_ghs']==100
    assert snapshot['sales']['payments_received_ghs']==50
    assert snapshot['sales']['outstanding_customer_credit_ghs']==50
    assert snapshot['feed_costs']['by_product'][0]['estimated_consumed_cost_ghs']==20
    assert snapshot['cash_flow']['estimated_monthly_repayment_capacity_ghs'] is not None
    assert len(snapshot['cash_flow']['projected_months'])==12
    assert 'Private Buyer' not in str(snapshot)
    assert '0240000000' not in str(snapshot)
    report=client.get(f'/farms/{farm_id}/reports/bank-ready.csv',headers=farmer)
    assert report.status_code==200,report.text
    assert 'production_history' in report.text
    assert 'expected_harvest_kg' in report.text
    assert 'indicative_net_recorded_cashflow_ghs' in report.text
    assert 'Private Buyer' not in report.text
    assert '0240000000' not in report.text
    assert client.get(f'/farms/{farm_id}/reports/bank-ready.csv',headers=lender).status_code==404
