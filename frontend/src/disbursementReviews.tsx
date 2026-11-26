import {useEffect, useState} from 'react';

type Decision = 'approved' | 'rejected';
type Review = {
  id: number; loan_id: number; reference: string; amount_ghs: number;
  disbursed_on: string; evidence_id: number; reason: string | null;
};
type Queue = {items: Review[]; has_more: boolean};
const statuses = ['pending', 'approved', 'rejected'] as const;
const currency = new Intl.NumberFormat('en-GH', {style: 'currency', currency: 'GHS'});

export function DisbursementReviews({institutionId, required, api, refresh, video}: {
  institutionId: number;
  required: boolean;
  api: (path: string, body?: object, method?: string) => Promise<any>;
  refresh: () => Promise<unknown>;
  video: (id: number) => void;
}) {
  const root = '/finance/institutions/'+institutionId;
  const [status, setStatus] = useState<typeof statuses[number]>('pending');
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [selected, setSelected] = useState<Review | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let current = true;
    setQueue(null);
    api(root+'/disbursement-reviews?'+new URLSearchParams({status, offset:String(offset)}))
      .then(result => {if (current) setQueue(result)})
      .catch(problem => {if (current) setError(String(problem))});
    return () => {current = false};
  }, [api, root, status, offset, revision]);

  async function save(action: () => Promise<unknown>, receipt: string) {
    if (busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await action();
      setSelected(null);
      setReason('');
      setRevision(value => value + 1);
      setNotice(receipt);
      await refresh();
    } catch (problem) {setError(String(problem))}
    finally {setBusy(false)}
  }

  function decide(decision: Decision) {
    if (!selected || reason.trim().length < 3 || !window.confirm(decision === 'approved'
      ? 'Confirm that you independently verified the external payout and want to post its record?'
      : 'Reject this record and release the reserved amount?')) return;
    void save(() => api('/finance/loans/'+selected.loan_id+'/disbursement-reviews/'+selected.id+'/decision',
      {decision, reason:reason.trim()}), decision === 'approved' ? 'Verified disbursement recorded.' : 'Disbursement rejected.');
  }

  return <section className="panel">
    <h2>{selected ? 'Review disbursement' : 'Disbursement approvals'}</h2>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {selected ? <>
      <p>{selected.reference} · Loan #{selected.loan_id} · {currency.format(selected.amount_ghs)} · {selected.disbursed_on}</p>
      <button type="button" className="outline" onClick={() => video(selected.evidence_id)}>Review video evidence</button>
      <label className="field"><span>Decision reason</span>
        <textarea minLength={3} maxLength={500} value={reason} onChange={event => setReason(event.target.value)}/>
      </label>
      <div className="farmactions">
        <button type="button" className="primary" disabled={busy || reason.trim().length < 3}
          onClick={() => decide('approved')}>Approve and record verified payout</button>
        <button type="button" className="outline" disabled={busy || reason.trim().length < 3}
          onClick={() => decide('rejected')}>Reject</button>
        <button type="button" className="outline" disabled={busy} onClick={() => setSelected(null)}>Back to queue</button>
      </div>
    </> : <>
      <p>Independent approval is {required ? 'enabled' : 'disabled'}. This workflow records external payouts and does not transfer funds.</p>
      <button type="button" className="outline" disabled={busy} onClick={() => {
        if (!window.confirm((required ? 'Disable' : 'Enable')+' independent disbursement approval?')) return;
        void save(() => api(root+'/disbursement-policy', {required:!required}, 'PUT'), 'Disbursement policy saved.');
      }}>{required ? 'Disable' : 'Enable'} independent approval</button>
      <div className="farmactions">
        {statuses.map(value => <button key={value} className="outline" type="button" aria-pressed={status === value}
          disabled={busy} onClick={() => {setError('');setStatus(value);setOffset(0)}}>{value[0].toUpperCase()+value.slice(1)}</button>)}
      </div>
      {!queue && !error && <p role="status">Loading disbursement reviews</p>}
      {queue?.items.length === 0 && <p className="empty">No {status} disbursement reviews.</p>}
      {queue?.items.map(row => <div key={row.id} className="item between">
        <div><b>{row.reference}</b><p>Loan #{row.loan_id} · {currency.format(row.amount_ghs)} · {row.disbursed_on}</p>
          {row.reason && <p>{row.reason}</p>}</div>
        {status === 'pending' && <button type="button" className="outline" disabled={busy}
          onClick={() => {setSelected(row);setReason('');setError('')}}>Review</button>}
      </div>)}
      <div className="farmactions">
        <button type="button" className="outline" disabled={busy || !offset} onClick={() => setOffset(offset-25)}>Previous</button>
        <button type="button" className="outline" disabled={busy || !queue?.has_more} onClick={() => setOffset(offset+25)}>Next</button>
      </div>
    </>}
  </section>;
}
