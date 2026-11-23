
from datetime import date, timedelta

from .test_api import client
from .test_foundation import upload_operation_evidence
from .test_operations import auth
from app.feeding import FeedLedger
from app.main import SessionLocal
from app.operations import StockingCycle


def test_history_filters_costs_exports_and_evidence_permissions():
    owner = auth('activity-owner@example.com')
    outsider = auth('activity-other@example.com')
    farm = client.post('/farms',headers=owner,json={
        'name':'History Farm','region':'Northern','district':'Tamale',
        'farm_type':'pond','species':'Tilapia','latitude':9.4,'longitude':-0.8,
    }).json()
    fid = farm['id']
    root = f'/farms/{fid}'
    unit = client.post(root+'/units',headers=owner,json={'name':'History Pond','unit_type':'pond'}).json()
    second = client.post(root+'/units',headers=owner,json={'name':'Second Pond','unit_type':'pond'}).json()
    product = client.post(root+'/feeds',headers=owner,json={'name':'History Feed'}).json()
    today = date.today()
    old_day = today-timedelta(days=740)
    with SessionLocal.begin() as db:
        cycle = StockingCycle(unit_id=unit['id'],species='Tilapia',stocked_count=100,initial_average_weight_g=4,stocked_on=old_day)
        other = StockingCycle(unit_id=second['id'],species='Tilapia',stocked_count=100,initial_average_weight_g=4,stocked_on=old_day)
        db.add_all([cycle,other])
        db.flush()
        first_id, second_id = cycle.id, other.id
        db.add_all([
            FeedLedger(feed_id=product['id'],event_type='receipt',quantity_delta_kg=10,cost_ghs=50,occurred_on=old_day),
            FeedLedger(feed_id=product['id'],event_type='receipt',quantity_delta_kg=10,cost_ghs=150,occurred_on=today),
            FeedLedger(feed_id=product['id'],event_type='feeding',quantity_delta_kg=-0.3,cycle_id=first_id,occurred_on=old_day,session_number=1),
            FeedLedger(feed_id=product['id'],event_type='feeding',quantity_delta_kg=-0.6,cycle_id=second_id,occurred_on=today,session_number=2),
        ])
    actor = client.get('/auth/me',headers=owner).json()['id']
    evidence = upload_operation_evidence(fid,unit,owner,'feeding',first_id)
    assert evidence.status_code==201,evidence.text
    evidence_id=evidence.json()['id']
    recorded = client.post(root+f'/units/{unit["id"]}/cycles/{first_id}/feeding',headers=owner,
        params={'evidence_id':evidence_id},json={'feed_id':product['id'],'quantity_kg':0.4,'fed_on':str(today)})
    assert recorded.status_code==201,recorded.text
    record_id = recorded.json()['id']
    path = root+'/activity-history'

    def view(**filters):
        response = client.post(path,headers=owner,json={'kind':'feeding',**filters})
        assert response.status_code==200,response.text
        return response.json()

    assert view()['total']==3
    assert view(unit_ids=[unit['id'],second['id']],cycle_id=first_id)['total']==2
    assert view(actor_id=actor)['total']==1
    assert view(status='unscheduled')['total']==1
    assert view(status=evidence.json()['verification_status'])['total']==1
    period = {'start':str(today),'end':str(today)}
    assert view(periods=[period])['total']==2
    separated = view(periods=[period,{'start':str(old_day),'end':str(old_day)}],size=1,page=1)
    assert separated['total']==3 and len(separated['items'])==1
    assert separated['daily_totals'][0]['actual_kg']==1
    oldest = view(order='oldest',size=1)['items'][0]
    assert oldest['details']['session_number']==1 and oldest['details']['indicative_cost_ghs']==3
    assert view(size=1,page=3)['items'][0]['id']==oldest['id']
    assert client.post(path,headers=owner,json={'periods':[{'start':str(today),'end':str(old_day)}]}).status_code==422

    details=client.get(path+f'/record/feeding/{record_id}',headers=owner)
    assert details.status_code==200,details.text
    record=details.json()
    assert record['details']['actual_kg']==0.4 and record['details']['indicative_cost_ghs']==4
    assert record['evidence'][0]['id']==evidence_id and record['audit'][0]['action']=='create'
    options=client.get(path+'/options',headers=owner)
    assert options.status_code==200,options.text
    assert options.json()['staff'][0]['id']==actor
    all_activities=client.post(path,headers=owner,json={})
    assert all_activities.status_code==200,all_activities.text
    assert {row['kind'] for row in all_activities.json()['items']}=={'feeding','stocking'}
    library=client.post(path,headers=owner,json={'kind':'evidence','status':'locked','periods':[period]})
    assert library.status_code==200,library.text
    assert library.json()['items'][0]['details']['record_id']==record_id
    library_item = client.get(path+f'/record/evidence/{evidence_id}',headers=owner)
    assert library_item.status_code==200,library_item.text
    media=root+f'/evidence/{evidence_id}/video'
    downloaded=client.get(media,headers=owner)
    assert downloaded.status_code==200 and downloaded.headers['cache-control']=='private, no-store'
    assert client.get(media,headers=outsider).status_code==404
    assert client.delete(root+f'/evidence/{evidence_id}',headers=owner).status_code==409
    filters={'kind':'feeding','unit_ids':[unit['id']],'periods':[period]}
    csv_doc=client.post(path+'/export/csv',json=filters,headers=owner)
    assert csv_doc.status_code==200 and 'History Pond' in csv_doc.text and 'actual kg: 0.4' in csv_doc.text
    pdf=client.post(path+'/export/pdf',json=filters,headers=owner)
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    assert client.post(path,headers=outsider,json={'kind':'evidence'}).status_code==404
    assert client.get(path+f'/record/feeding/{record_id}',headers=outsider).status_code==404
    assert client.post(path+'/export/pdf',json=filters,headers=outsider).status_code==404
