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

export function FarmerApprovals({load, approve}: {
  load: (path: string) => Promise<ApprovalQueue>;
  approve: (id: number) => Promise<unknown>;
}) {
  const [queue, setQueue] = useState<ApprovalQueue | null>(null);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    try {setQueue(await load(`/admin/farmers/pending?offset=${offset}`))}
    catch (problem) {setError(String(problem))}
  }, [load, offset]);
  useEffect(() => {void refresh()}, [refresh]);

  return <section className="panel">
    <h2>Farmer and processor approvals</h2>
    {error&&<p role="alert">{error}</p>}
    {!queue&&!error&&<p role="status">Loading pending accounts…</p>}
    {queue?.items.length===0&&<p>No pending accounts on this page.</p>}
    {queue?.items.map(row => <div className="item between" key={row.id}>
      <div><b>{row.full_name}</b><small>{row.email}{row.phone_number&&` · ${row.phone_number}`}</small></div>
      <button type="button" className="outline" disabled={busy} onClick={async () => {
        if (!window.confirm(`Approve ${row.full_name}’s account?`)) return;
        setBusy(true);setError('');
        try {await approve(row.id);await refresh()}
        catch (problem) {setError(String(problem))}
        finally {setBusy(false)}
      }}>Approve</button>
    </div>)}
    <div className="farmactions">
      <button type="button" className="outline" disabled={busy||offset===0} onClick={()=>setOffset(offset-50)}>Previous</button>
      <button type="button" className="outline" disabled={busy||!queue?.has_more} onClick={()=>setOffset(offset+50)}>Next</button>
    </div>
  </section>;
}
