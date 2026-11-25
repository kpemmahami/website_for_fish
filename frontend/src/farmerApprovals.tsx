import {useCallback, useEffect, useState} from 'react';

interface PendingFarmer {
  id: number;
  full_name: string;
  email: string;
  phone_number: string | null;
}

interface ApprovalQueue {
  items: PendingFarmer[];
  has_more: boolean;
}

export function FarmerApprovals({load, approve, revision}: {
  load: (path: string) => Promise<ApprovalQueue>;
  revision?: number;
  approve?: (id: number) => Promise<unknown>;
}) {
  const [queue, setQueue] = useState<ApprovalQueue | null>(null);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const status = approve ? 'pending' : 'approved';
  const refresh = useCallback(async () => {
    setError('');
    try {
      const params = new URLSearchParams({offset: String(offset)});
      if (status === 'pending' && query) params.set('search', query);
      setQueue(await load('/admin/farmers/'+status+'?'+params));
    }
    catch (problem) {setError(String(problem))}
  }, [load, offset, query, status]);
  useEffect(() => {void refresh()}, [refresh, revision]);

  return <section className="panel">
    <h2>{approve ? 'Pending farmer and processor approvals' : 'Approved farmers and processors'}</h2>
    {approve&&<form className="farmactions" onSubmit={e=>{e.preventDefault();setQueue(null);setOffset(0);setQuery(search.trim());if(offset===0&&query===search.trim())void refresh()}}>
      <label className="field"><span>Search by name, email or phone</span><input type="search" value={search} maxLength={255} onChange={e=>setSearch(e.target.value)}/></label>
      <button type="submit" className="outline" disabled={busy}>Search</button>
    </form>}
    {error&&<p role="alert">{error}</p>}
    {!queue&&!error&&<p role="status">Loading accounts…</p>}
    {queue?.items.length===0&&<p>No {status} accounts on this page.</p>}
    {queue?.items.map(row => <div className="item between" key={row.id}>
      <div><b>{row.full_name}</b><small>{row.email}{row.phone_number&&` · ${row.phone_number}`}</small></div>
      {approve && <button type="button" className="outline" disabled={busy} onClick={async () => {
        if (!window.confirm(`Approve ${row.full_name}’s account?`)) return;
        setBusy(true);setError('');
        try {await approve(row.id);if(queue?.items.length===1&&offset>0)setOffset(offset-50);else await refresh()}
        catch (problem) {setError(String(problem))}
        finally {setBusy(false)}
      }}>Approve</button>}
    </div>)}
    <div className="farmactions">
      <button type="button" className="outline" disabled={busy||offset===0} onClick={()=>setOffset(offset-50)}>Previous</button>
      <button type="button" className="outline" disabled={busy||!queue?.has_more} onClick={()=>setOffset(offset+50)}>Next</button>
    </div>
  </section>;
}
