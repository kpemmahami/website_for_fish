import csv
from datetime import date

import pytest
from sqlalchemy import func, select

from .test_account_access import admin_headers, register_institution
from .test_api import client
from app.institution_accounting import AccountingAccount, AccountingJournal, AccountingLine, PostingLine, post_journal
from app.lending import Institution
from app.main import SessionLocal


def test_journal_is_balanced_scoped_and_idempotent():
    owner, registration = register_institution('accounting-owner@example.com', {
        'name': 'Accounting Test Bank', 'institution_type': 'bank', 'account_number': 'TEST-ACCT',
    })
    other_owner, other_registration = register_institution('other-accounting-owner@example.com', {
        'name': 'Other Accounting Bank', 'institution_type': 'bank', 'account_number': 'TEST-ACCT-OTHER',
    })
    institution_id = registration.json()['id']
    other_id = other_registration.json()['id']
    admin = admin_headers()
    for bank in (institution_id, other_id):
        assert client.post(f'/finance/institutions/{bank}/verify', headers=admin).status_code == 200
    root = f'/finance/institutions/{institution_id}/accounting/accounts'
    cash_payload = {'code': 'cash-1000', 'name': 'Cash account', 'category': 'asset'}
    assert client.post(root, json=cash_payload, headers=other_owner).status_code == 404
    created = client.post(root, json=cash_payload, headers=owner)
    assert created.status_code == 201, created.text
    assert created.json()['code'] == 'CASH-1000'
    assert client.post(root, json={**cash_payload, 'code': 'CASH-1000'}, headers=owner).status_code == 409
    account_path = root+'/'+str(created.json()['id'])
    other_path = f'/finance/institutions/{other_id}/accounting/accounts/{created.json()["id"]}'
    change = {'name': 'Retired cash account', 'active': False}
    assert client.patch(other_path, json=change, headers=other_owner).status_code == 404
    assert client.patch(account_path, json=change, headers=owner).json()['active'] is False
    assert client.get(root, headers=owner).json()[0]['name'] == change['name']
    assert client.get(root, headers=other_owner).status_code == 404

    with SessionLocal.begin() as db:
        officer = db.get(Institution, institution_id).owner_user_id
        cash = AccountingAccount(institution_id=institution_id, code='1000', name='Cash', category='asset')
        savings = AccountingAccount(institution_id=institution_id, code='2000', name='Deposits', category='liability')
        foreign = AccountingAccount(institution_id=other_registration.json()['id'], code='1000', name='Cash', category='asset')
        db.add_all([cash, savings, foreign])
        db.flush()
        cash_id, savings_id, foreign_id = cash.id, savings.id, foreign.id

    args = {'institution_id': institution_id, 'source_type': 'deposit', 'source_reference': 'TEST-1',
            'effective_on': date(2026, 11, 26), 'posted_by': officer}
    lines = [PostingLine(cash_id, debit_pesewas=1000), PostingLine(savings_id, credit_pesewas=1000)]
    with SessionLocal() as db:
        with pytest.raises(ValueError, match='must balance'):
            post_journal(db, **args, lines=[lines[0], PostingLine(savings_id, credit_pesewas=999)])
        with pytest.raises(ValueError, match='active accounts'):
            post_journal(db, **args, lines=[lines[0], PostingLine(foreign_id, credit_pesewas=1000)])
        db.rollback()
        post_journal(db, **args, lines=lines)
        db.rollback()
        assert db.scalar(select(func.count()).select_from(AccountingJournal)
                         .where(AccountingJournal.institution_id == institution_id)) == 0

    with SessionLocal.begin() as db:
        journal = post_journal(db, **args, lines=lines)
        journal_id = journal.id
    with SessionLocal() as db:
        assert post_journal(db, **args, lines=list(reversed(lines))).id == journal_id
        with pytest.raises(ValueError, match='different details'):
            post_journal(db, **args, lines=[PostingLine(cash_id, debit_pesewas=2000),
                                           PostingLine(savings_id, credit_pesewas=2000)])
        persisted = db.scalars(select(AccountingLine).where(AccountingLine.journal_id == journal_id)).all()
        assert len(persisted) == 2
        assert sum(line.debit_pesewas for line in persisted) == sum(line.credit_pesewas for line in persisted) == 1000

    journal_root = f'/finance/institutions/{institution_id}/accounting'
    assert client.get(journal_root+'/journals', headers=other_owner).status_code == 404
    assert client.get(journal_root+'/journals', headers=owner, params={'end': '2026-11-25'}).json()['items'] == []
    listed = client.get(journal_root+'/journals', headers=owner).json()['items']
    assert [item['id'] for item in listed] == [journal_id]
    detail = client.get(journal_root+f'/journals/{journal_id}', headers=owner).json()
    assert detail['source_reference'] == 'TEST-1'
    assert [line['debit_ghs'] for line in detail['lines']] == ['10.00', '0.00']
    balance = client.get(journal_root+'/trial-balance', headers=owner, params={'as_of': '2026-11-26'}).json()
    assert balance['balanced'] is True
    assert balance['debit_total_ghs'] == balance['credit_total_ghs'] == '10.00'
    before = client.get(journal_root+'/trial-balance', headers=owner, params={'as_of': '2026-11-25'}).json()
    assert before['items'] == []
    other_root = f'/finance/institutions/{other_id}/accounting'
    assert client.get(other_root+f'/journals/{journal_id}', headers=other_owner).status_code == 404
    assert client.get(other_root+'/trial-balance', headers=other_owner).json()['items'] == []

    periods = journal_root+'/periods'
    closure = {'starts_on': '2026-11-01', 'closed': True, 'reason': 'Month reconciled'}
    assert client.put(periods, headers=other_owner, json=closure).status_code == 404
    assert client.put(periods, headers=owner, json={**closure, 'starts_on': '2026-11-02'}).status_code == 422
    assert client.put(periods, headers=owner, json=closure).json()['closed'] is True
    assert client.put(periods, headers=owner, json=closure).status_code == 409
    with SessionLocal() as db:
        assert post_journal(db, **args, lines=lines).id == journal_id
        with pytest.raises(ValueError, match='period is closed'):
            post_journal(db, **{**args, 'source_reference': 'AFTER-CLOSE'}, lines=lines)
    assert client.put(periods, headers=owner, json={
        **closure, 'closed': False, 'reason': 'Approved correction',
    }).json()['closed'] is False
    with SessionLocal.begin() as db:
        assert post_journal(db, **{**args, 'source_reference': 'AFTER-CLOSE'}, lines=lines).id != journal_id
    assert client.get(periods, headers=owner).json()[0]['starts_on'] == '2026-11-01'

    with SessionLocal.begin() as db:
        for index in range(25):
            post_journal(db, **{**args, 'source_reference': f'EXPORT-{index}'}, lines=lines)
        post_journal(db, **{**args, 'source_reference': 'OUTSIDE-RANGE',
                            'effective_on': date(2026, 11, 27)}, lines=lines)
        post_journal(db, **{**args, 'source_reference': '=1+1',
                            'effective_on': date(2026, 11, 25)}, lines=lines)
    export = journal_root+'/journals/export'
    dates = {'start': '2026-11-25', 'end': '2026-11-26'}
    assert client.get(export, headers=other_owner, params=dates).status_code == 404
    assert client.get(export, headers=owner, params={**dates, 'end': '2026-11-24'}).status_code == 422
    response = client.get(export, headers=owner, params=dates)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    assert 'journals-2026-11-25-to-2026-11-26.csv' in response.headers['content-disposition']
    rows = list(csv.DictReader(response.content.decode('utf-8-sig').splitlines()))
    assert len(rows) == 56
    assert len({row['Journal ID'] for row in rows}) == 28
    assert {row['Effective date'] for row in rows} == {'2026-11-25', '2026-11-26'}
    assert {row['Source reference'] for row in rows if row['Effective date'] == '2026-11-25'} == {"'=1+1"}
    assert {(row['Debit (GHS)'], row['Credit (GHS)']) for row in rows} == {('10.00', '0.00'), ('0.00', '10.00')}

    filters = {**dates, 'reference': ' test-1 '}
    listed = client.get(journal_root+'/journals', headers=owner, params=filters).json()['items']
    assert [item['id'] for item in listed] == [journal_id]
    matched = client.get(export, headers=owner, params=filters)
    assert matched.status_code == 200
    matched_rows = list(csv.DictReader(matched.content.decode('utf-8-sig').splitlines()))
    assert [row['Journal ID'] for row in matched_rows] == [str(journal_id)] * 2
    for wildcard in ('%', '_'):
        assert client.get(journal_root+'/journals', headers=owner,
                          params={'reference': wildcard}).json()['items'] == []

    account_filters = {**filters, 'account_code': ' 1000 '}
    listed = client.get(journal_root+'/journals', headers=owner, params=account_filters).json()['items']
    assert [item['id'] for item in listed] == [journal_id]
    account_export = client.get(export, headers=owner, params=account_filters)
    assert account_export.status_code == 200
    exported = list(csv.DictReader(account_export.content.decode('utf-8-sig').splitlines()))
    assert {row['Account code'] for row in exported} == {'1000', '2000'}
    unmatched = {**dates, 'account_code': 'cash-1000'}
    assert client.get(journal_root+'/journals', headers=owner, params=unmatched).json()['items'] == []
    empty_export = client.get(export, headers=owner, params=unmatched)
    assert empty_export.status_code == 200
    assert list(csv.DictReader(empty_export.content.decode('utf-8-sig').splitlines())) == []
