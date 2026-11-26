"""Phase 0009 workflow, access restrictions, duplicate references, and balances."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from .test_api import client, upload_loan_video
from .test_foundation import signup
from .test_account_access import admin_headers, register_institution
from app.loan_servicing import LoanInstallment
from app.daily_reminders import LoanSmsReminder, deliver_loan_sms_reminders
from app.main import Farm, SessionLocal, User

def test_loan_servicing_permissions_and_balances():
    farmer=signup('servicing-farmer@example.com')
    officer=signup('servicing-officer@example.com')
    reviewer=signup('servicing-reviewer@example.com')
    stranger=signup('servicing-stranger@example.com')
    admin=admin_headers()
    farm=client.post('/farms',json={'name':'Servicing Farm','region':'North East','district':'Yunyoo','farm_type':'pond','species':'Tilapia'},headers=farmer)
    assert farm.status_code==201,farm.text
    fid=farm.json()['id']
    lender,inst=register_institution('servicing-lender@example.com',{'name':'Servicing Rural Bank','institution_type':'rural_bank','registration_number':'TEST-SERV-1'})
    assert inst.status_code==201,inst.text
    iid=inst.json()['id']
    assert client.post(f'/finance/institutions/{iid}/verify',headers=admin).status_code==200
    assert client.post(f'/finance/institutions/{iid}/members',json={'user_email':'servicing-officer@example.com','role':'officer'},headers=lender).status_code==200
    assert client.post(f'/finance/institutions/{iid}/members',json={'user_email':'servicing-reviewer@example.com','role':'reviewer'},headers=lender).status_code==200
    application_video=upload_loan_video(farmer,fid,'loan_application')
    application=client.post(f'/farms/{fid}/loan-applications',json={'institution_id':iid,'requested_ghs':'10000.00','term_months':12,'purpose':'Feed and fingerlings for tilapia farming','share_report':True,'evidence_id':application_video},headers=farmer)
    assert application.status_code==201,application.text
    assert client.get(f'/finance/loan-evidence/{application_video}/video',headers=farmer).status_code==200
    assert client.get(f'/finance/loan-evidence/{application_video}/video',headers=lender).status_code==200
    assert client.get(f'/finance/loan-evidence/{application_video}/video',headers=stranger).status_code==404
    aid=application.json()['id']
    approval=client.post(f'/finance/institutions/{iid}/applications/{aid}/appraise',json={'decision':'approved','rationale':'Farm plan and history evaluated','approved_ghs':'10000.00'},headers=lender)
    assert approval.status_code==200,approval.text
    first_due=(date.today()+timedelta(days=45)).isoformat()
    opening={'application_id':aid,'annual_flat_interest_percent':'12.00','repayment_frequency':'monthly','first_due_date':first_due}
    assert client.post(f'/finance/institutions/{iid}/loans',json=opening,headers=stranger).status_code==404
    assert client.post(f'/finance/institutions/{iid}/loans',json=opening,headers=officer).status_code==404
    opened=client.post(f'/finance/institutions/{iid}/loans',json=opening,headers=reviewer)
    assert opened.status_code==201,opened.text
    loan_id=opened.json()['id']
    assert opened.json()['status']=='offered'
    assert client.post(f'/finance/institutions/{iid}/loans',json=opening,headers=lender).status_code==409
    today=date.today().isoformat()
    first={'amount_ghs':'4000.00','reference':'BANK-TRX-1','transaction_date':today,'evidence_id':1}
    assert client.post(f'/finance/loans/{loan_id}/disbursements',json=first,headers=stranger).status_code==404
    assert client.post(f'/finance/loans/{loan_id}/disbursements',json=first,headers=reviewer).status_code==404
    offer_path = f'/finance/loans/{loan_id}/offer-response'
    assert client.post(f'/finance/loans/{loan_id}/disbursements', json=first, headers=officer).status_code == 409
    assert client.post(offer_path, json={'decision': 'accept'}, headers=officer).status_code == 404
    schedule = client.get(f'/finance/loans/{loan_id}/schedule', headers=farmer)
    assert len(schedule.json()) == 12
    assert client.post(offer_path, json={'decision': 'accept'}, headers=farmer).json()['status'] == 'awaiting_disbursement'
    assert client.post(offer_path, json={'decision': 'accept'}, headers=farmer).status_code == 409
    first['evidence_id']=upload_loan_video(officer,fid,'disbursement',loan_id)
    assert client.get(f"/finance/loan-evidence/{first['evidence_id']}/video",headers=farmer).status_code==200
    assert client.get(f"/finance/loan-evidence/{first['evidence_id']}/video",headers=stranger).status_code==404
    dis1=client.post(f'/finance/loans/{loan_id}/disbursements',json=first,headers=officer)
    assert dis1.status_code==201,dis1.text
    assert dis1.json()['status']=='awaiting_disbursement'
    assert client.post(f'/finance/loans/{loan_id}/disbursements',json=first,headers=lender).status_code==409
    assert client.post(f'/finance/loans/{loan_id}/repayments',json={'amount_ghs':'100.00','reference':'REPAY-1','transaction_date':today,'evidence_id':1},headers=lender).status_code==409
    disbursement_path = f'/finance/loans/{loan_id}/disbursements'
    competing = [
        {'amount_ghs': '4000.00', 'reference': f'BANK-RACE-{index}', 'transaction_date': today,
         'evidence_id': upload_loan_video(lender, fid, 'disbursement', loan_id)}
        for index in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as workers:
        attempts = [workers.submit(client.post, disbursement_path, json=entry, headers=lender)
                    for entry in competing]
        results = [attempt.result(timeout=15) for attempt in attempts]
    assert sorted(response.status_code for response in results) == [201, 422]
    rejected = next(response for response in results if response.status_code == 422)
    assert rejected.json()['detail'] == 'Disbursement exceeds approved amount'
    accepted = next(response for response in results if response.status_code == 201)
    assert accepted.json()['disbursed_ghs'] == 8000
    assert accepted.json()['undisbursed_ghs'] == 2000
    final_tranche = {'amount_ghs': '2000.00', 'reference': 'BANK-TRX-2', 'transaction_date': today,
                     'evidence_id': upload_loan_video(lender, fid, 'disbursement', loan_id)}
    dis2 = client.post(disbursement_path, json=final_tranche, headers=lender)
    assert dis2.status_code==201,dis2.text
    assert dis2.json()['status']=='active'
    assert dis2.json()['disbursed_ghs']==10000
    assert dis2.json()['scheduled_interest_ghs']==1200
    schedule=client.get(f'/finance/loans/{loan_id}/schedule',headers=farmer)
    assert schedule.status_code==200,schedule.text
    assert len(schedule.json())==12
    assert round(sum(x['total_ghs'] for x in schedule.json()),2)==11300
    assert round(sum(x['fees_ghs'] for x in schedule.json()),2)==100
    assert dis2.json()['insurance_fee_ghs']==100
    assert dis2.json()['total_contract_repayment_ghs']==11300
    assert client.get(f'/finance/loans/{loan_id}',headers=stranger).status_code==404
    repay={'amount_ghs':'1500.00','reference':'REPAY-1','transaction_date':today,'evidence_id':1}
    assert client.post(f'/finance/loans/{loan_id}/repayments',json=repay,headers=reviewer).status_code==404
    repay['evidence_id']=upload_loan_video(officer,fid,'repayment',loan_id)
    paid=client.post(f'/finance/loans/{loan_id}/repayments',json=repay,headers=officer)
    assert paid.status_code==201,paid.text
    assert paid.json()['interest_repaid_ghs']==1200
    assert paid.json()['fees_paid_ghs']==100
    assert paid.json()['principal_repaid_ghs']==200
    assert paid.json()['outstanding_principal_ghs']==9800
    assert paid.json()['total_scheduled_balance_ghs']==9800
    disbursements = f'/finance/institutions/{iid}/disbursements'
    assert client.get(disbursements, headers=stranger).status_code == 404
    report = client.get(disbursements, headers=lender)
    assert report.status_code == 200, report.text
    assert report.json()['totals'] == {
        'disbursed_ghs': 10000, 'recovered_ghs': 1500,
        'principal_recovered_ghs': 200, 'principal_recovery_percent': 2,
    }
    assert report.json()['items'][0]['customer_name']
    assert report.json()['items'][0]['loan_id'] == loan_id
    portfolio = client.get(f'/finance/institutions/{iid}/portfolio', headers=lender)
    assert portfolio.json()['principal_recovery_percent'] == 2
    customers = f'/finance/institutions/{iid}/collection-customers'
    daily = f'/finance/institutions/{iid}/collections?day={today}'
    assert client.get(customers, headers=stranger).status_code == 404
    assert client.get(daily, headers=reviewer).status_code == 404
    response = client.get(customers, params={'search': f'AQUA-LOAN-{loan_id:06d}'}, headers=officer)
    assert response.status_code == 200, response.text
    assert [row['loan_id'] for row in response.json()['items']] == [loan_id]
    response = client.get(daily, headers=officer)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['count'] == 1
    assert report['total_ghs'] == 1500
    assert report['items'][0]['evidence_id'] == repay['evidence_id']
    transaction_history=client.get(f'/finance/loans/{loan_id}/transactions',headers=farmer)
    assert transaction_history.status_code==200,transaction_history.text
    disbursement_record=next(item for item in transaction_history.json() if item['type']=='disbursement')
    assert disbursement_record['evidence_metadata']['device_recorded_at']
    assert disbursement_record['evidence_metadata']['server_received_at']
    assert client.post(f'/finance/loans/{loan_id}/repayments',json=repay,headers=lender).status_code==409
    assert client.post(f'/finance/loans/{loan_id}/repayments',json={'amount_ghs':'9800.01','reference':'REPAY-OVER','transaction_date':today,'evidence_id':1},headers=lender).status_code==422
    followup_video=upload_loan_video(farmer,fid,'loan_application')
    followup=client.post(f'/farms/{fid}/loan-applications',json={'institution_id':iid,'requested_ghs':'5000.00','term_months':12,'purpose':'Buy feed for the current tilapia production cycle','share_report':True,'evidence_id':followup_video},headers=farmer)
    assert followup.status_code==201,followup.text
    shared=client.get(f"/finance/institutions/{iid}/applications/{followup.json()['id']}",headers=lender)
    assert shared.status_code==200,shared.text
    assert shared.json()['shared_report_snapshot']['existing_loans'][0]['loan_id']==loan_id
    assert shared.json()['shared_report_snapshot']['existing_loans'][0]['outstanding_principal_ghs']==9800
    assert client.get(f'/farms/{fid}/loans',headers=farmer).json()[0]['id']==loan_id
    assert client.get(f'/farms/{fid}/loans',headers=stranger).status_code==404
    assert client.get(f'/finance/loans/{loan_id}/transactions',headers=farmer).status_code==200
    assert client.get(f'/farms/{fid}/loan-reminders',headers=farmer).status_code==200
    video_path = f'/finance/loans/{loan_id}/evidence'
    stamp = datetime.now(timezone.utc).isoformat()
    params = {'record_type': 'repayment', 'captured_at': stamp, 'device_recorded_at': stamp,
              'duration_seconds': 15, 'retry_upload': True}
    video = bytes.fromhex('1a45dfa3') + b'collection-evidence'
    video_headers = {**officer, 'Content-Type': 'video/webm'}
    upload = client.post(video_path, params=params, content=video, headers=video_headers)
    assert upload.status_code == 201, upload.text
    retry = client.post(video_path, params=params, content=video, headers=video_headers)
    assert retry.status_code == 201, retry.text
    final_video = upload.json()['id']
    assert retry.json()['id'] == final_video
    assert client.post(video_path, params=params, content=video,
                       headers={**lender, 'Content-Type': 'video/webm'}).status_code == 409
    path = f'/finance/loans/{loan_id}/field-repayments'
    payload = {'amount_ghs': '9850.00', 'transaction_date': today, 'evidence_id': final_video,
               'collection_id': '9e97bd6f-86d1-4a35-90cb-e47f96ac5243', 'customer_consented': True}
    assert client.post(path, json={**payload, 'customer_consented': False}, headers=officer).status_code == 422
    assert client.post(path, json=payload, headers=reviewer).status_code == 404
    with ThreadPoolExecutor(max_workers=2) as workers:
        requests = [workers.submit(client.post, path, json=payload, headers=officer) for _ in range(2)]
        final, concurrent_retry = [request.result(timeout=15) for request in requests]
    assert final.status_code == 200, final.text
    assert concurrent_retry.status_code == 200, concurrent_retry.text
    assert final.json() == concurrent_retry.json()
    assert final.json()['amount_ghs'] == 9850
    assert final.json()['applied_to_loan_ghs'] == 9800
    assert final.json()['deposited_ghs'] == 50
    balances = client.get('/finance/my-collection-deposits', headers=farmer).json()
    assert balances == [{'institution_id': iid, 'institution': 'Servicing Rural Bank', 'recorded_deposits_ghs': 50}]
    assert client.get('/finance/my-collection-deposits', headers=stranger).json() == []
    assert client.post(path, json=payload, headers=officer).json() == final.json()
    assert client.post(path, json=payload, headers=lender).status_code == 409
    assert client.post(path, json={**payload, 'amount_ghs': '9700.00'}, headers=officer).status_code == 409
    assert client.get(f'/finance/loans/{loan_id}', headers=officer).json()['status'] == 'repaid'
    posted = client.get(daily, headers=officer).json()
    assert posted['count'] == 2
    assert posted['total_ghs'] == 11300
    assert posted['deposited_ghs'] == 50
    assert posted['total_received_ghs'] == 11350
    matching = [row for row in posted['items'] if row['reference'] == final.json()['reference']]
    assert len(matching) == 1
    assert matching[0]['evidence_id'] == final_video
    protected_video = f'/finance/loan-evidence/{final_video}/video'
    assert client.get(protected_video, headers=stranger).status_code == 404
    download = client.get(protected_video, headers=officer)
    assert download.status_code == 200
    assert download.content == video
    final_totals = client.get(disbursements, headers=lender).json()['totals']
    assert final_totals == {
        'disbursed_ghs': 10000, 'recovered_ghs': 11300,
        'principal_recovered_ghs': 10000, 'principal_recovery_percent': 100,
    }

    available = client.get(customers, params={'deposits': True}, headers=officer)
    assert available.status_code == 200, available.text
    assert [item['loan_id'] for item in available.json()['items']] == [loan_id]
    assert client.get(customers, headers=officer).json()['items'] == []
    deposit_video = client.post(video_path, params={**params, 'record_type': 'deposit'},
                                content=video + b'-deposit', headers=video_headers)
    assert deposit_video.status_code == 201, deposit_video.text
    deposit_path = f'/finance/loans/{loan_id}/field-deposits'
    deposit_payload = {**payload, 'amount_ghs': '25.00', 'evidence_id': deposit_video.json()['id'],
                       'collection_id': str(uuid4())}
    assert client.post(deposit_path, json=deposit_payload, headers=reviewer).status_code == 404
    receipt = client.post(deposit_path, json=deposit_payload, headers=officer)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()['applied_to_loan_ghs'] == 0
    assert receipt.json()['deposited_ghs'] == 25
    assert client.post(deposit_path, json=deposit_payload, headers=officer).json() == receipt.json()
    assert client.get(disbursements, headers=lender).json()['totals'] == final_totals
    assert client.get('/finance/my-collection-deposits', headers=farmer).json()[0]['recorded_deposits_ghs'] == 75
    posted = client.get(daily, headers=officer).json()
    assert posted['standalone_count'] == 1
    assert posted['total_ghs'] == 11300
    assert posted['deposited_ghs'] == 75
    assert posted['total_received_ghs'] == 11375


    branch_root = f'/finance/institutions/{iid}/branches'
    branch = client.post(branch_root, headers=lender, json={
        'code': 'RECOVERY', 'name': 'Recovery branch', 'address': 'Tamale, Ghana',
    }).json()
    officer_id = client.get('/auth/me', headers=officer).json()['id']
    assignment = f'/finance/institutions/{iid}/staff/{officer_id}/branch'
    assert client.put(assignment, json={'branch_id': branch['id']}, headers=officer).status_code == 404
    assert client.put(assignment, json={'branch_id': branch['id']}, headers=lender).status_code == 200
    assert client.get(f'/finance/loans/{loan_id}', headers=officer).status_code == 404
    assert client.get(protected_video, headers=officer).status_code == 404
    assert client.get(daily, headers=officer).json()['total_received_ghs'] == 0
    assert client.get(f'/finance/institutions/{iid}/applications', headers=officer).json() == []
    application_branch = f'/finance/institutions/{iid}/applications/{aid}/branch'
    assert client.put(application_branch, json={'branch_id': branch['id']}, headers=lender).status_code == 200
    assert client.get(f'/finance/loans/{loan_id}', headers=officer).status_code == 200
    assert client.get(protected_video, headers=officer).status_code == 200
    assert client.get(daily, headers=officer).json()['total_received_ghs'] == 11375
    assert client.patch(branch_root+'/'+str(branch['id']), headers=lender, json={
        'name': branch['name'], 'address': branch['address'], 'active': False,
    }).status_code == 200
    assert client.get(f'/finance/loans/{loan_id}', headers=officer).status_code == 404
    assert client.get(f'/finance/loans/{loan_id}', headers=lender).status_code == 200


def test_custom_schedule_reminders_and_portfolio_metrics():
    farmer=signup('custom-schedule-farmer@example.com')
    admin=admin_headers()
    farm=client.post('/farms',json={'name':'Custom Schedule Farm','region':'North East','district':'Yunyoo','farm_type':'pond','species':'Tilapia'},headers=farmer)
    assert farm.status_code==201,farm.text
    farm_id=farm.json()['id']
    lender,institution=register_institution('custom-schedule-lender@example.com',{'name':'Custom Schedule Bank','institution_type':'rural_bank','registration_number':'TEST-CUSTOM-1'})
    assert institution.status_code==201,institution.text
    institution_id=institution.json()['id']
    assert client.post(f'/finance/institutions/{institution_id}/verify',headers=admin).status_code==200
    application_video=upload_loan_video(farmer,farm_id,'loan_application')
    application=client.post(f'/farms/{farm_id}/loan-applications',json={'institution_id':institution_id,'requested_ghs':'10000.00','term_months':12,'purpose':'Feed and fingerlings for tilapia farming','share_report':True,'evidence_id':application_video},headers=farmer)
    assert application.status_code==201,application.text
    application_id=application.json()['id']
    approved=client.post(f'/finance/institutions/{institution_id}/applications/{application_id}/appraise',json={'decision':'approved','rationale':'Farm plan and repayment history reviewed','approved_ghs':'10000.00'},headers=lender)
    assert approved.status_code==200,approved.text

    first_due=date.today()+timedelta(days=7)
    schedule=[
        {'due_on':first_due.isoformat(),'principal_ghs':'5000.00','interest_ghs':'600.00','fees_ghs':'50.00'},
        {'due_on':(first_due+timedelta(days=90)).isoformat(),'principal_ghs':'3000.00','interest_ghs':'360.00','fees_ghs':'25.00'},
        {'due_on':(first_due+timedelta(days=180)).isoformat(),'principal_ghs':'2000.00','interest_ghs':'240.00','fees_ghs':'25.00'},
    ]
    opening={'application_id':application_id,'annual_flat_interest_percent':'12.00',
             'insurance_fee_percent':'0.75','processing_fee_percent':'0.25','repayment_frequency':'custom','first_due_date':first_due.isoformat(),'custom_schedule':schedule}
    bad_schedule=[dict(item) for item in schedule]
    bad_schedule[0]['principal_ghs']='4999.00'
    invalid=client.post(f'/finance/institutions/{institution_id}/loans',json={**opening,'custom_schedule':bad_schedule},headers=lender)
    assert invalid.status_code==422,invalid.text

    opened=client.post(f'/finance/institutions/{institution_id}/loans',json=opening,headers=lender)
    assert opened.status_code==201,opened.text
    loan_id=opened.json()['id']
    assert opened.json()['repayment_frequency']=='custom'
    assert opened.json()['scheduled_interest_ghs']==0
    assert opened.json()['insurance_fee_percent']==0.75
    assert opened.json()['insurance_fee_ghs']==75
    assert opened.json()['processing_fee_percent']==0.25
    assert opened.json()['processing_fee_ghs']==25
    assert opened.json()['total_contract_repayment_ghs']==11300
    assert client.post(f'/finance/loans/{loan_id}/offer-response', json={'decision':'accept'}, headers=farmer).status_code == 200
    disbursement_video=upload_loan_video(lender,farm_id,'disbursement',loan_id)
    assert client.post(f'/finance/loans/{loan_id}/disbursements',json={'amount_ghs':'10000.00','reference':'CUSTOM-DISB-1','transaction_date':date.today().isoformat(),'evidence_id':disbursement_video},headers=lender).status_code==201
    assert client.get(f'/finance/loans/{loan_id}',headers=farmer).json()['scheduled_interest_ghs']==1200
    listed=client.get(f'/finance/loans/{loan_id}/schedule',headers=farmer)
    assert listed.status_code==200,listed.text
    assert [item['due_on'] for item in listed.json()]==[item['due_on'] for item in schedule]
    assert sum(item['principal_ghs'] for item in listed.json())==10000
    assert sum(item['interest_ghs'] for item in listed.json())==1200
    assert sum(item['fees_ghs'] for item in listed.json())==100
    reminders=client.get(f'/farms/{farm_id}/loan-reminders',headers=farmer)
    assert reminders.status_code==200,reminders.text
    assert reminders.json()[0]['status']=='upcoming'
    assert reminders.json()[0]['amount_due_to_date_ghs']==5650
    contact=client.patch('/auth/me',json={
        'phone_number':'+233545550172',
        'sms_daily_records_enabled':False,
        'sms_loan_reminders_enabled':True,
    },headers=farmer)
    assert contact.status_code==200,contact.text
    sent=[]
    def sender(phone_number,message):
        sent.append((phone_number,message))
        return 'loan-reminder-message-1'
    reminder_at=datetime.combine(first_due-timedelta(days=7),time(8),ZoneInfo('Africa/Accra'))
    with SessionLocal() as db:
        assert deliver_loan_sms_reminders(db,reminder_at,sender)==1
        assert deliver_loan_sms_reminders(db,reminder_at,sender)==0
        reminder=db.query(LoanSmsReminder).one()
        assert reminder.status=='sent'
        assert reminder.provider_message_id=='loan-reminder-message-1'
    assert len(sent)==1
    assert sent[0][0]=='+233545550172'
    assert 'is due' in sent[0][1]
    monthly_at = datetime.combine(first_due.replace(day=1), time(8), ZoneInfo('Africa/Accra'))
    with SessionLocal() as db:
        borrower = db.get(User, db.get(Farm, farm_id).owner_id)
        assert deliver_loan_sms_reminders(db, monthly_at, sender, monthly=True) == 0
        borrower.phone_verified_at = monthly_at
        db.commit()
        assert deliver_loan_sms_reminders(db, monthly_at, sender, monthly=True) == 1
        assert deliver_loan_sms_reminders(db, monthly_at + timedelta(hours=2), sender, monthly=True) == 0
        assert db.query(LoanSmsReminder).filter_by(reminder_type='monthly').count() == 1
    assert len(sent) == 2
    assert 'monthly loan reminder' in sent[1][1]
    with SessionLocal() as db:
        installment=db.query(LoanInstallment).filter_by(loan_id=loan_id,number=1).one()
        installment.due_on=date.today()-timedelta(days=1)
        db.commit()
    repayment_video=upload_loan_video(lender,farm_id,'repayment',loan_id)
    repayment=client.post(f'/finance/loans/{loan_id}/repayments',json={'amount_ghs':'1000.00','reference':'CUSTOM-REPAY-1','transaction_date':date.today().isoformat(),'evidence_id':repayment_video},headers=lender)
    assert repayment.status_code==201,repayment.text
    assert repayment.json()['total_scheduled_balance_ghs']==10300
    fee_payment_video=upload_loan_video(lender,farm_id,'repayment',loan_id)
    fee_payment=client.post(f'/finance/loans/{loan_id}/repayments',json={'amount_ghs':'300.00','reference':'CUSTOM-REPAY-2','transaction_date':date.today().isoformat(),'evidence_id':fee_payment_video},headers=lender)
    assert fee_payment.status_code==201,fee_payment.text
    assert fee_payment.json()['fees_paid_ghs']==100
    assert fee_payment.json()['total_scheduled_balance_ghs']==10000
    reminders=client.get(f'/farms/{farm_id}/loan-reminders',headers=farmer)
    assert reminders.json()[0]['status']=='overdue'
    assert reminders.json()[0]['amount_due_to_date_ghs']==4350
    portfolio=client.get(f'/finance/institutions/{institution_id}/portfolio',headers=lender)
    assert portfolio.status_code==200,portfolio.text
    assert portfolio.json()['total_disbursements_ghs']==10000
    assert portfolio.json()['outstanding_balance_ghs']==10000
    assert portfolio.json()['total_collections_ghs']==1300
    assert portfolio.json()['overdue_loans']==1
    assert portfolio.json()['arrears_ghs']==4350
    assert portfolio.json()['repayment_performance_pct']==23.01
