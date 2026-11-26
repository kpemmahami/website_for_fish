import {useEffect, useState} from 'react';

const categories = ['asset', 'liability', 'equity', 'income', 'expense', 'contra'] as const;
type Account = {id: number; code: string; name: string; category: typeof categories[number]; active: boolean};
const blank = {code: '', name: '', category: 'asset' as Account['category'], active: true};

export function InstitutionAccounts({institutionId, api}: {
  institutionId: number;
  api: (path: string, body?: object, method?: string) => Promise<any>;
}) {
  const root = '/finance/institutions/'+institutionId+'/accounting/accounts';
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [selection, setSelection] = useState<Account | 'new' | null>(null);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let current = true;
    api(root).then(rows => {if (current) setAccounts(rows)})
      .catch(problem => {if (current) setError(String(problem))});
    return () => {current = false};
  }, [api, root]);

  function open(account: Account | 'new') {
    setSelection(account);
    setForm(account === 'new' ? blank : account);
    setError('');
    setNotice('');
  }

  return <section className="panel">
    <h2>{selection === 'new' ? 'Add an accounting account' : selection ? 'Edit accounting account' : 'Chart of accounts'}</h2>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {selection ? <form className="farmform" onSubmit={async event => {
      event.preventDefault();
      if (busy) return;
      setBusy(true);
      setError('');
      try {
        const account: Account = selection === 'new'
          ? await api(root, {code: form.code, name: form.name, category: form.category})
          : await api(root+'/'+selection.id, {name: form.name, active: form.active}, 'PATCH');
        setAccounts(rows => [...(rows ?? []).filter(row => row.id !== account.id), account]
          .sort((a, b) => a.code.localeCompare(b.code)));
        setSelection(null);
        setNotice('Accounting account saved.');
      } catch (problem) {setError(String(problem))}
      finally {setBusy(false)}
    }}>
      <label className="field"><span>Account code</span><input required maxLength={32} readOnly={selection !== 'new'}
        value={form.code} onChange={event => setForm({...form, code:event.target.value})}/></label>
      <label className="field"><span>Account name</span><input required minLength={2} maxLength={160}
        value={form.name} onChange={event => setForm({...form, name:event.target.value})}/></label>
      <label className="field"><span>Category</span><select disabled={selection !== 'new'} value={form.category}
        onChange={event => setForm({...form, category:event.target.value as Account['category']})}>
        {categories.map(category => <option key={category} value={category}>{category}</option>)}
      </select></label>
      {selection !== 'new' && <label><input type="checkbox" checked={form.active}
        onChange={event => setForm({...form, active:event.target.checked})}/> Active account</label>}
      <div className="farmactions">
        <button className="primary" disabled={busy}>Save account</button>
        <button className="outline" type="button" disabled={busy} onClick={() => {setSelection(null);setError('')}}>Cancel</button>
      </div>
    </form> : <>
      <button type="button" className="primary" disabled={!accounts} onClick={() => open('new')}>Add account</button>
      {!accounts && !error && <p role="status">Loading accounts</p>}
      {accounts?.length === 0 && <p className="empty">No accounting accounts configured.</p>}
      {accounts?.map(account => <div className="item between" key={account.id}>
        <div><b>{account.code} · {account.name}</b><p>{account.category} · {account.active ? 'Active' : 'Inactive'}</p></div>
        <button className="outline" type="button" onClick={() => open(account)}>Edit account</button>
      </div>)}
    </>}
  </section>;
}
