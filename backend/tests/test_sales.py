import os
os.environ.setdefault('SECRET_KEY', 'test-only-key-not-for-production-123456789')
from decimal import Decimal
from datetime import date
import pytest
from fastapi import HTTPException
from app.sales import cents, ghs, SaleIn, PaymentIn
from .test_api import client
from .test_foundation import signup, upload_operation_evidence


def test_money_roundtrip():
    assert cents('40.25') == 4025
    assert ghs(4025) == 40.25
    assert cents(Decimal('1.005')) == 101


def test_sale_schema():
    x = SaleIn(harvest_lot_id=1, customer_id=2, sold_on=date.today(),
               quantity_kg=12.5, price_ghs_per_kg='42.50')
    assert cents(Decimal(str(x.quantity_kg)) * x.price_ghs_per_kg) == 53125


def test_reject_negative_payment():
    with pytest.raises(ValueError):
        PaymentIn(paid_on=date.today(), amount_ghs='-1', method='cash')


def test_small_sales_use_walk_in_and_large_sales_require_registration():
    farmer = signup('walk-in-sales@example.com')
    farm = client.post('/farms', json={
        'name': 'Walk-in Sales Farm', 'region': 'Northern', 'district': 'Tamale',
        'farm_type': 'pond', 'species': 'Tilapia', 'latitude': 9.4, 'longitude': -0.8,
    }, headers=farmer)
    farm_id = farm.json()['id']
    unit = client.post(f'/farms/{farm_id}/units', json={
        'name': 'Sales Pond', 'unit_type': 'pond',
    }, headers=farmer)
    unit_id = unit.json()['id']
    unit_data = unit.json()
    evidence = upload_operation_evidence(farm_id, unit_data, farmer, 'stocking')
    assert evidence.status_code == 201, evidence.text
    cycle = client.post(f"/farms/{farm_id}/units/{unit_id}/cycles", params={
        'evidence_id': evidence.json()['id'],
    }, json={
        'species': 'Tilapia', 'stocked_count': 2000, 'initial_average_weight_g': 500,
        'stocked_on': date.today().isoformat(),
    }, headers=farmer)
    assert cycle.status_code == 201, cycle.text
    cycle_id = cycle.json()['id']
    harvest_evidence = upload_operation_evidence(farm_id, unit_data, farmer, 'harvest', cycle_id)
    assert harvest_evidence.status_code == 201, harvest_evidence.text
    harvest = client.post(f'/farms/{farm_id}/sales/harvests', json={
        'cycle_id': cycle_id, 'harvested_on': date.today().isoformat(),
        'quantity_kg': 1000, 'fish_count': 1000, 'loss_kg': 0,
    }, params={'evidence_id':harvest_evidence.json()['id']}, headers=farmer)
    assert harvest.status_code == 201, harvest.text
    lot_id = harvest.json()['id']
    customer = client.post(f'/farms/{farm_id}/sales/customers', json={
        'name': 'Bulk buyer', 'customer_type': 'wholesaler',
    }, headers=farmer)
    small_sale_evidence = upload_operation_evidence(farm_id, unit_data, farmer, 'sale_dispatch', cycle_id)
    assert small_sale_evidence.status_code == 201, small_sale_evidence.text
    small_sale = client.post(f'/farms/{farm_id}/sales/transactions', params={
        'evidence_id':small_sale_evidence.json()['id'],
    }, json={
        'harvest_lot_id': lot_id, 'sold_on': date.today().isoformat(),
        'quantity_kg': 25, 'price_ghs_per_kg': '35.00',
    }, headers=farmer)
    assert small_sale.status_code == 201, small_sale.text
    assert small_sale.json()['customer_id'] is not None
    large_sale_evidence = upload_operation_evidence(farm_id, unit_data, farmer, 'sale_dispatch', cycle_id)
    assert large_sale_evidence.status_code == 201, large_sale_evidence.text
    large_sale_params = {'evidence_id':large_sale_evidence.json()['id']}
    assert client.post(f'/farms/{farm_id}/sales/transactions', params=large_sale_params, json={
        'harvest_lot_id': lot_id, 'sold_on': date.today().isoformat(),
        'quantity_kg': 500, 'price_ghs_per_kg': '35.00',
    }, headers=farmer).status_code == 422
    large_sale = client.post(f'/farms/{farm_id}/sales/transactions', params=large_sale_params, json={
        'harvest_lot_id': lot_id, 'customer_id': customer.json()['id'],
        'sold_on': date.today().isoformat(), 'quantity_kg': 500,
        'price_ghs_per_kg': '35.00',
    }, headers=farmer)
    assert large_sale.status_code == 201, large_sale.text
    today = date.today().isoformat()
    evidence = upload_operation_evidence(farm_id, unit_data, farmer, 'sale_dispatch', cycle_id)
    sale = client.post(f'/farms/{farm_id}/sales/transactions', params={'evidence_id': evidence.json()['id']}, json={
        'harvest_lot_id': lot_id, 'customer_id': customer.json()['id'], 'sold_on': today, 'due_on': today,
        'quantity_kg': 100, 'price_ghs_per_kg': '30.00',
        'initial_payment': {'amount_ghs': '2000', 'paid_on': today, 'method': 'cash', 'reference': 'DEPOSIT'},
    }, headers=farmer)
    assert sale.status_code == 201, sale.text
    record = sale.json()
    assert (record['total_ghs'], record['paid_ghs'], record['outstanding_ghs']) == (3000, 2000, 1000)
    url = f"/farms/{farm_id}/sales/transactions/{record['id']}"
    invoice = client.get(url+'/invoice.pdf', headers=farmer)
    assert invoice.content.startswith(b'%PDF-')
    assert invoice.headers['content-type'] == 'application/pdf'
    assert record['invoice_number'] + '.pdf' in invoice.headers['content-disposition']
    stranger = signup('unauthorized-invoice@example.com')
    assert client.get(url+'/invoice.pdf', headers=stranger).status_code == 404
    payment = {'amount_ghs':'1000','paid_on':today,'method':'bank_transfer','reference':'FINAL'}
    assert client.post(url+'/payments', json={**payment, 'amount_ghs':'1001'}, headers=farmer).status_code == 409
    settled = client.post(url+'/payments', json=payment, headers=farmer)
    assert settled.json()['sale']['outstanding_ghs'] == 0
    assert client.post(url+'/payments', json=payment, headers=farmer).status_code == 409
    assert len(client.get(url+'/payments', headers=farmer).json()) == 2
    dashboard = client.get(f'/farms/{farm_id}/dashboard', headers=farmer).json()['sales']
    assert dashboard['payments_received_ghs'] == 3000
    assert dashboard['available_harvest_kg'] == 375
    assert dashboard['outstanding_receivables_ghs'] == 18375
