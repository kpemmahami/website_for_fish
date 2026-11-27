from datetime import date

from .test_api import client
from .test_operations import auth
from app.farm_expenses import FarmExpense
from app.main import SessionLocal
from app.operations import StockingCycle
from app.sales import Customer, FishSale, HarvestLot


def test_pricing_margin_harvest_allocation_and_access(monkeypatch):
    owner = auth('price-advisor-owner@example.com')
    other = auth('price-advisor-other@example.com')
    farmer = client.get('/auth/me', headers=owner).json()['id']
    farm = client.post('/farms', json={'name':'Pricing QA','region':'Northern','district':'Tamale',
        'farm_type':'pond','species':'Tilapia'}, headers=owner).json()['id']
    unit = client.post(f'/farms/{farm}/units', json={'name':'Pricing pond','unit_type':'pond'}, headers=owner).json()['id']
    today = date.today()
    with SessionLocal.begin() as db:
        cycle = StockingCycle(unit_id=unit,species='Tilapia',stocked_count=1000,initial_average_weight_g=10,
                              stocked_on=today,target_harvest_weight_g=1000)
        db.add(cycle)
        db.flush()
        cycle_id = cycle.id
    path = f'/farms/{farm}/cycles/{cycle_id}/pricing-advisor'
    assert client.post(path,json={},headers=owner).json()['break_even_ghs_per_kg'] is None
    with SessionLocal.begin() as db:
        for amount, allocation in [(800000,cycle_id),(100000,None)]:
            db.add(FarmExpense(farm_id=farm,cycle_id=allocation,category='Labour and wages',description='QA cost',
                classification='operating',occurred_on=today,amount_pesewas=amount,
                review_status='approved',recorded_by=farmer))
    response = client.post(path,json={'margin_pct':25,'proposed_price':11},headers=owner)
    assert response.status_code == 200, response.text
    quote = response.json()
    assert (quote['saleable_weight_kg'],quote['unallocated_ghs']) == (1000,1000)
    assert (quote['break_even_ghs_per_kg'],quote['target_ghs_per_kg']) == (8,10.67)
    assistant = f'/farms/{farm}/assistant'
    question = {'question': 'What price should I sell my fish for?', 'cycle_id': cycle_id}
    assert client.get(assistant, headers=owner).json()['cycles'][0]['id'] == cycle_id
    assert client.get(assistant, headers=other).status_code == 404
    assert client.post(assistant, json=question, headers=other).status_code == 404
    assert client.post(assistant, json={**question, 'cycle_id': cycle_id+100000}, headers=owner).status_code == 404
    answer = client.post(assistant, json=question, headers=owner).json()
    assert answer['source'] == 'Pricing advisor'
    assert 'GHS 10.67/kg' in answer['answer'] and 'GHS 8.00/kg' in answer['answer']
    cash = client.post(assistant, json={'question': 'Cash flow for the last 7 days'}, headers=owner).json()
    assert cash['source'] == 'Farm cash activity' and 'Net recorded cash' in cash['answer']

    monkeypatch.delenv('AQUAFARM_ASSISTANT_API_KEY', raising=False)
    assert client.get(assistant, headers=owner).json()['ai_enabled'] is False
    summary = client.post(assistant, json={'question': 'Summarize my farm'}, headers=owner).json()
    assert summary['source'] == 'Farm dashboard' and '1 active cycles' in summary['answer']
    guidance = client.post(assistant, json={'question': 'What should I record when feeding fish?'}, headers=owner).json()
    assert guidance['source_url'].startswith('https://www.fao.org/')

    from app import farm_assistant
    monkeypatch.setenv('AQUAFARM_ASSISTANT_API_KEY', 'mock-key')
    monkeypatch.setenv('AQUAFARM_ASSISTANT_MODEL', 'mock-model')

    def provider(url, *, headers, json, timeout):
        import httpx
        assert url == 'https://api.openai.com/v1/chat/completions'
        assert json['store'] is False
        context = json['messages'][-1]['content']
        assert 'farm_snapshot_ghs' in context
        assert 'Pricing pond' not in context and 'by_product' not in context
        return httpx.Response(200, request=httpx.Request('POST', url),
                              json={'choices': [{'message': {'content': 'Mock farm answer'}}]})

    monkeypatch.setattr(farm_assistant.httpx, 'post', provider)
    ai = client.post(assistant, json={'question': 'How can I improve growth?'}, headers=owner).json()
    assert ai['answer'] == 'Mock farm answer'
    proposal = quote['proposal']
    assert (proposal['revenue_ghs'],proposal['profit_ghs'],proposal['margin_pct']) == (11000,3000,27.27)
    assert client.post(path,json={'proposed_price':7},headers=owner).json()['proposal']['profit_ghs'] == -1000
    assert client.post(path,json={'margin_pct':100},headers=owner).status_code == 422
    assert client.post(path,json={},headers=other).status_code == 404
    pdf = client.post(path+'.pdf',json={'proposed_price':11},headers=owner)
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF-')
    assert client.post(path+'.pdf',json={},headers=other).status_code == 404
    with SessionLocal.begin() as db:
        lot = HarvestLot(farm_id=farm,cycle_id=cycle_id,harvested_on=today,quantity_kg=100,loss_kg=10,fish_count=100)
        buyer = Customer(farm_id=farm,name='QA buyer',customer_type='individual')
        db.add_all([lot,buyer])
        db.flush()
        db.add(FishSale(farm_id=farm,harvest_lot_id=lot.id,customer_id=buyer.id,sold_on=today,
                        quantity_kg=45,unit_price_pesewas=1000,total_pesewas=45000))
    result = client.post(path,json={'proposed_price':11,'sale_quantity_kg':20},headers=owner).json()
    assert (result['saleable_weight_kg'],result['forecast_harvest_kg'],result['unsold_harvest_kg']) == (990,900,45)
    assert result['cost_allocated_to_harvest_ghs'] == 727.27
    assert result['batch']['revenue_ghs'] == 220
    assert result['proposal']['revenue_ghs'] == 10845
