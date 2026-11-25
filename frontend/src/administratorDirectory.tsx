import {useEffect, useState} from 'react';

interface Administrator {
  id: number;
  full_name: string;
  email: string;
  phone_number: string | null;
  created_at: string;
  role: string;
  is_suspended: boolean;
  pending_activation: boolean;
  contacts_verified_at: string | null;
}

interface DirectoryPage {
  total: number;
  items: Administrator[];
}

interface ActivityPage {
  items: {id: number; actor_name: string; action: string; reason: string | null; created_at: string}[];
  has_more: boolean;
}

const pageSize = 25;

type AccessAction = 'suspend' | 'reactivate' | 'revoke_sessions';

interface AdministratorDetails {
  full_name: string;
  email: string;
  phone_number: string;
}

const emptyDetails: AdministratorDetails = {full_name: '', email: '', phone_number: ''};

export function AdministratorDirectory({load, loadActivity, changeAccess, prepare, sendVerification}: {
  load: (path: string) => Promise<DirectoryPage>;
  loadActivity: (id: number, offset: number) => Promise<ActivityPage>;
  changeAccess: (id: number, action: AccessAction, reason: string) => Promise<unknown>;
  prepare: (details: AdministratorDetails) => Promise<unknown>;
  sendVerification: (id: number) => Promise<unknown>;
}) {
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<DirectoryPage | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [details, setDetails] = useState(emptyDetails);
  const [activityTarget, setActivityTarget] = useState<Administrator|null>(null);
  const [activityOffset, setActivityOffset] = useState(0);
  const [activity, setActivity] = useState<ActivityPage|null>(null);
  const [activityError, setActivityError] = useState('');

  useEffect(()=>{
    if (!activityTarget) return;
    let active = true;
    loadActivity(activityTarget.id, activityOffset)
      .then(page=>{if(active)setActivity(page)})
      .catch(problem=>{if(active)setActivityError(String(problem))});
    return ()=>{active=false};
  }, [activityTarget, activityOffset, loadActivity, revision]);

  function showActivity(row: Administrator, offset = 0) {
    if(activityTarget?.id===row.id&&activityOffset===offset)return;
    setActivity(null);
    setActivityError('');
    setActivityTarget(row);
    setActivityOffset(offset);
  }

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({search, offset: String(offset), limit: String(pageSize)});
    load('/admin/administrators?' + params).then(page => {
      if (active) setResult(page);
    }).catch(problem => {
      if (active) setError(String(problem));
    });
    return () => {active = false};
  }, [load, search, offset, revision]);

  async function updateAccess(row: Administrator, action: AccessAction) {
    const label = {suspend: 'Suspend', reactivate: 'Reactivate', revoke_sessions: 'Sign out'}[action];
    const reason = window.prompt(`${label} ${row.full_name}? Enter a reason to confirm.`)?.trim();
    if (!reason) return;
    setError('');
    setNotice('');
    setBusy(true);
    try {
      await changeAccess(row.id, action, reason);
      setResult(null);
      setRevision(value => value + 1);
      setNotice('Administrator access updated.');
    } catch (problem) {
      setError(String(problem));
    } finally {
      setBusy(false);
    }
  }

  function goTo(nextOffset: number) {
    if (nextOffset === offset) return;
    setError('');
    setResult(null);
    setOffset(nextOffset);
  }

  return <section className="panel">
    <h2>Manage administrators</h2>
    <details>
      <summary>Add Super Admin</summary>
      <p className="muted">The account will remain pending until secure activation is available.</p>
      <form className="farmform" onSubmit={async event => {
        event.preventDefault();
        setError('');
        setNotice('');
        setBusy(true);
        try {
          await prepare(details);
          setDetails(emptyDetails);
          setOffset(0);
          setQuery('');
          setSearch('');
          setRevision(value => value + 1);
          setNotice('Super Admin account prepared. Activation is pending.');
        } catch (problem) {
          setError(String(problem));
        } finally {
          setBusy(false);
        }
      }}>
        {([
          ['full_name', 'Full name', 'text', 120],
          ['email', 'Email', 'email', 255],
          ['phone_number', 'Mobile phone number', 'tel', 64],
        ] as const).map(([key, label, type, maxLength]) => <label key={key} className="field">
          <span>{label}</span>
          <input type={type} required maxLength={maxLength} value={details[key]}
            onChange={event => setDetails({...details, [key]: event.target.value})}/>
        </label>)}
        <button type="submit" className="primary" disabled={busy}>Prepare account</button>
      </form>
    </details>
    <form className="farmactions" onSubmit={event => {
      event.preventDefault();
      if (query.trim() === search && offset === 0) return;
      setError('');
      setResult(null);
      setOffset(0);
      setSearch(query.trim());
    }}>
      <label className="field"><span>Name or email</span>
        <input type="search" value={query} maxLength={255} onChange={event => setQuery(event.target.value)}/>
      </label>
      <button type="submit" className="outline">Search</button>
    </form>
    {error&&<p role="alert">{error}</p>}
    {notice&&<p role="status">{notice}</p>}
    {!result ? !error&&<p role="status">Loading administrators…</p> :
      result.items.length === 0 ? <p>No matching administrators.</p> : <>
        <div className="tablewrap"><table>
          <thead><tr><th>Name</th><th>Role</th><th>Email</th><th>Phone</th><th>Created</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>{result.items.map(row => <tr key={row.id}>
            <td>{row.full_name}</td><td>{row.role}</td><td>{row.email}</td>
            <td>{row.phone_number ?? '—'}</td><td>{new Date(row.created_at).toLocaleDateString()}</td>
            <td>{row.pending_activation ? (row.contacts_verified_at ? 'Contacts verified · Pending MFA' : 'Pending contact verification')
              : row.is_suspended ? 'Suspended' : 'Active'}</td>
            <td><button type="button" className="outline small" onClick={()=>showActivity(row)}>View activity</button>
            {row.pending_activation&&<button type="button" className="outline small" disabled={busy}
              onClick={async () => {
                if (!window.confirm(`Send an email link and SMS code to ${row.full_name}?`)) return;
                setBusy(true);setError('');setNotice('');
                try {
                  await sendVerification(row.id);
                  setNotice('Verification link and SMS code sent.');
                } catch (problem) {
                  setError(String(problem));
                } finally {
                  setBusy(false);
                }
              }}>{row.contacts_verified_at ? 'Restart setup' : 'Send verification'}</button>}
            {row.role !== 'Platform Owner'&&!row.pending_activation&&<div className="farmactions">
              <button type="button" className="outline small" disabled={busy}
                onClick={() => void updateAccess(row, row.is_suspended ? 'reactivate' : 'suspend')}>
                {row.is_suspended ? 'Reactivate' : 'Suspend'}
              </button>
              {!row.is_suspended&&<button type="button" className="outline small" disabled={busy}
                onClick={() => void updateAccess(row, 'revoke_sessions')}>Sign out all sessions</button>}
            </div>}</td>
          </tr>)}</tbody>
        </table></div>
        <div className="farmactions">
          <button type="button" className="outline" disabled={offset === 0} onClick={() => goTo(offset - pageSize)}>Previous</button>
          <button type="button" className="outline" disabled={offset + pageSize >= result.total} onClick={() => goTo(offset + pageSize)}>Next</button>
        </div>
      </>}
      {activityTarget&&<section>
        <div className="between"><h3>Account activity for {activityTarget.full_name}</h3>
          <button type="button" className="outline small" onClick={()=>setActivityTarget(null)}>Close activity</button>
        </div>
        {activityError&&<p role="alert">{activityError}</p>}
        {!activity&&!activityError&&<p role="status">Loading account activity…</p>}
        {activity?.items.length===0&&<p>No account activity recorded.</p>}
        {activity?.items.map(event=><div className="item" key={event.id}>
          <b>{event.action.replace(/_/g,' ')}</b>
          <small>{event.actor_name} · {new Date(event.created_at).toLocaleString()}</small>
          {event.reason&&<small>{event.reason}</small>}
        </div>)}
        <div className="farmactions">
          <button type="button" className="outline" disabled={activityOffset===0}
            onClick={()=>showActivity(activityTarget,activityOffset-25)}>Previous</button>
          <button type="button" className="outline" disabled={!activity?.has_more}
            onClick={()=>showActivity(activityTarget,activityOffset+25)}>Next</button>
        </div>
      </section>}
  </section>;
}
