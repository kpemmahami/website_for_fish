import base64
from datetime import date
from io import BytesIO

from PIL import Image
from .test_api import client
from .test_operations import auth


def test_paid_unpaid_and_partial_expenses_with_private_receipt():
    farmer = auth('expense-owner@example.com')
    other = auth('expense-other@example.com')
    farm = client.post('/farms',json={'name':'Expense QA','region':'Northern','district':'Tamale',
                                     'farm_type':'pond','species':'Tilapia'},headers=farmer).json()
    root = f"/farms/{farm['id']}"
    today = date.today()
    image = BytesIO()
    Image.new('RGB',(8,8),'white').save(image,format='PNG')
    receipt = base64.b64encode(image.getvalue()).decode()
    common = {'category':'Transportation','description':'Supplier delivery','occurred_on':today.isoformat()}
    paid = client.post(root+'/expenses',json={**common,'amount_ghs':'250','attachments':[receipt],
                'initial_payment':{'paid_on':today.isoformat(),'amount_ghs':'250','method':'mobile_money'}},headers=farmer)
    assert paid.status_code == 201, paid.text
    row = paid.json()
    assert row['payment_status'] == 'paid'
    url = root+f"/expenses/{row['id']}/attachments/{row['attachments'][0]['id']}"
    assert client.get(url,headers=farmer).content == image.getvalue()
    assert client.get(url,headers=other).status_code == 404
    assert client.post(root+'/expenses',json={**common,'amount_ghs':'500'},headers=farmer).status_code == 422
    unpaid = client.post(root+'/expenses',json={**common,'amount_ghs':'500','exception_reason':'Paper receipt unavailable'},headers=farmer)
    assert unpaid.status_code == 201, unpaid.text
    assert unpaid.json()['review_status'] == 'pending_review'
    for grouping in ('weekly','monthly','quarterly','yearly','custom'):
        report = client.get(root+'/cash-activity',params={'start':today,'end':today,'grouping':grouping},headers=farmer).json()
        assert report['summary']['recorded_expenses_ghs'] == 250
        assert report['summary']['net_cash_ghs'] == -250
        assert report['summary']['supplier_payables_ghs'] == 500
    path = root+f"/expenses/{unpaid.json()['id']}/payments"
    data = {'paid_on':str(today),'amount_ghs':'200','method':'cash','reference':'DEP-01'}
    assert client.post(path,json=data,headers=farmer).status_code == 201
    assert client.post(path,json=data,headers=farmer).status_code == 409
    assert client.post(path,json={**data,'amount_ghs':'301','reference':'DEP-02'},headers=farmer).status_code == 409
    report = client.get(root+'/cash-activity',params={'start':today,'end':today},headers=farmer).json()
    assert report['summary']['total_outflows_ghs'] == 450
    assert report['summary']['supplier_payables_ghs'] == 300
    assert report['accrued_by_category'][0]['amount_ghs'] == 750
    assert client.get(root+'/dashboard',headers=farmer).json()['costs']['recorded_costs_to_date_ghs'] == 750
    assert client.get(root+'/cash-activity.pdf',params={'start':today,'end':today},headers=farmer).content.startswith(b'%PDF-')
    assert client.get(root+'/cash-activity.csv',params={'start':today,'end':today},headers=farmer).status_code == 200
    assert client.get(root+'/expenses',headers=other).status_code == 404
