import {useEffect, useState} from 'react';

type Period = {starts_on: string; closed: boolean; changed_at: string};

export function InstitutionPeriods({institutionId, api}: {
  institutionId: number;
  api: (path: string, body?: object, method?: string) => Promise<any>;
}) {
  const root = '/finance/institutions/'+institutionId+'/accounting/periods';
  const [rows, setRows] = useState<Period[] | null>(null);
  const [month, setMonth] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    let current = true;
    api(root).then(result => {if (current) setRows(result)})
      .catch(problem => {if (current) setError(String(problem))});
    return () => {current = false};
  }, [api, root]);
  const closed = rows?.some(row => row.starts_on === month+'-01' && row.closed) ?? false;

  return <section className="panel">
    <h2>Accounting periods</h2>
    <p>Closing a month prevents new journal entries with effective dates in that month.</p>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <form className="farmform" onSubmit={async event => {
      event.preventDefault();
      if (!rows || busy || !month || !window.confirm((closed ? 'Reopen ' : 'Close ')+month+'?')) return;
      setBusy(true);
      setError('');
      setNotice('');
      try {
        const period: Period = await api(root, {starts_on: month+'-01', closed: !closed, reason}, 'PUT');
        setRows(previous => [period, ...(previous ?? []).filter(row => row.starts_on !== period.starts_on)]
          .sort((a, b) => b.starts_on.localeCompare(a.starts_on)));
        setReason('');
        setNotice(period.closed ? 'Accounting period closed.' : 'Accounting period reopened.');
      } catch (problem) {setError(String(problem))}
      finally {setBusy(false)}
    }}>
      <label className="field"><span>Accounting month</span><input type="month" required value={month}
        onChange={event => setMonth(event.target.value)}/></label>
      <label className="field"><span>Reason</span><textarea required minLength={3} maxLength={500}
        value={reason} onChange={event => setReason(event.target.value)}/></label>
      <button className="primary" disabled={!rows || busy || !month}>{closed ? 'Reopen month' : 'Close month'}</button>
    </form>
    {rows?.length === 0 && <p className="empty">No accounting periods have been closed.</p>}
    {rows?.map(row => <div key={row.starts_on} className="item">
      <b>{row.starts_on.slice(0, 7)}</b><p>{row.closed ? 'Closed' : 'Reopened'}</p>
    </div>)}
  </section>;
}
