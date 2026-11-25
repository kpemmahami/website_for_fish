import {useEffect, useState} from 'react';

interface Administrator {
  id: number;
  full_name: string;
  email: string;
  phone_number: string | null;
  created_at: string;
  role: string;
  is_suspended: boolean;
}

interface DirectoryPage {
  total: number;
  items: Administrator[];
}

const pageSize = 25;

type AccessAction = 'suspend' | 'reactivate' | 'revoke_sessions';

export function AdministratorDirectory({load, changeAccess}: {
  load: (path: string) => Promise<DirectoryPage>;
  changeAccess: (id: number, action: AccessAction, reason: string) => Promise<unknown>;
}) {
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<DirectoryPage | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

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
            <td>{row.is_suspended ? 'Suspended' : 'Active'}</td>
            <td>{row.role !== 'Platform Owner'&&<div className="farmactions">
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
  </section>;
}
