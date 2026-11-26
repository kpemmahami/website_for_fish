import {useEffect, useState} from 'react';

interface Branch {
  id: number;
  code: string;
  name: string;
  address: string;
  active: boolean;
}

type BranchForm = Omit<Branch, 'id'>;
const empty: BranchForm = {code: '', name: '', address: '', active: true};

export function InstitutionBranches({institutionId, api}: {
  institutionId: number;
  api: (path: string, body?: object, method?: string) => Promise<any>;
}) {
  const path = '/finance/institutions/'+institutionId+'/branches';
  const [rows, setRows] = useState<Branch[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    let current = true;
    api(path).then(result => {if (current) setRows(result)})
      .catch(problem => {if (current) setError(String(problem))});
    return () => {current = false};
  }, [api, path]);

  function begin(branch?: Branch) {
    setSelected(branch?.id ?? null);
    setForm(branch ?? empty);
    setError('');
    setNotice('');
    setEditing(true);
  }

  return <section className="panel">
    <h2>{editing ? selected == null ? 'Add an institution branch' : 'Edit institution branch' : 'Institution branches'}</h2>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {editing ? <form className="farmform" onSubmit={async event => {
      event.preventDefault();
      if (busy) return;
      setBusy(true);
      setError('');
      try {
        const details = {name: form.name, address: form.address};
        const branch: Branch = selected == null ? await api(path, {...details, code: form.code})
          : await api(path+'/'+selected, {...details, active: form.active}, 'PATCH');
        setRows(current => [...(current ?? []).filter(row => row.id !== branch.id), branch]
          .sort((a, b) => a.name.localeCompare(b.name) || a.id - b.id));
        setEditing(false);
        setNotice('Branch saved.');
      } catch (problem) {setError(String(problem))}
      finally {setBusy(false)}
    }}>
      <label className="field"><span>Branch code</span><input required minLength={2} maxLength={24} pattern="[A-Za-z0-9\-]+" readOnly={selected != null} value={form.code} onChange={e => setForm({...form, code: e.target.value})}/></label>
      <label className="field"><span>Branch name</span><input required minLength={2} maxLength={120} value={form.name} onChange={e => setForm({...form, name: e.target.value})}/></label>
      <label className="field"><span>Address</span><input required minLength={2} maxLength={260} value={form.address} onChange={e => setForm({...form, address: e.target.value})}/></label>
      {selected != null && <label><input type="checkbox" checked={form.active} onChange={e => setForm({...form, active: e.target.checked})}/> Active branch</label>}
      <div className="farmactions">
        <button className="primary" disabled={busy}>Save branch</button>
        <button type="button" className="outline" disabled={busy} onClick={() => {setEditing(false);setError('')}}>Cancel</button>
      </div>
    </form> : <>
      <button type="button" className="primary" disabled={!rows} onClick={() => begin()}>Add branch</button>
      {!rows && !error && <p role="status">Loading branches</p>}
      {rows?.length === 0 && <p className="empty">No branches registered.</p>}
      {rows?.map(branch => <div key={branch.id} className="item between">
        <div><b>{branch.name}</b><p>{branch.code} · {branch.active ? 'Active' : 'Inactive'}</p><p>{branch.address}</p></div>
        <button type="button" className="outline" onClick={() => begin(branch)}>Edit branch</button>
      </div>)}
    </>}
  </section>;
}


export function ApplicationBranch({id, institutionId, branchId, api, onChange}: {
  id: number;
  institutionId: number;
  branchId?: number | null;
  api: (path: string, body?: object, method?: string) => Promise<any>;
  onChange: (branchId: number | null) => void;
}) {
  const path = '/finance/institutions/'+institutionId;
  const [branches, setBranches] = useState<Branch[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => {
    let current = true;
    api(path+'/branches').then(rows => {if (current) setBranches(rows)})
      .catch(problem => {if (current) setMessage(String(problem))});
    return () => {current = false};
  }, [api, path]);

  return <div>
    <label className="field"><span>Processing branch</span>
      <select value={branchId ?? ''} disabled={busy} onChange={async event => {
        const value = event.target.value;
        setBusy(true);
        setMessage('');
        try {
          const result = await api(path+'/applications/'+id+'/branch', {branch_id:value ? Number(value) : null}, 'PUT');
          onChange(result.branch_id);
          setMessage('Branch assignment saved.');
        } catch (problem) {setMessage(String(problem))}
        finally {setBusy(false)}
      }}>
        <option value="">Unassigned</option>
        {branches.filter(branch => branch.active || branch.id === branchId).map(branch =>
          <option key={branch.id} value={branch.id} disabled={!branch.active}>{branch.name}</option>)}
      </select>
    </label>
    {message && <p role="status">{message}</p>}
  </div>;
}
