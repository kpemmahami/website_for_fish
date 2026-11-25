import {useEffect, useState} from 'react';

interface RecoveryTotals {
  disbursed_ghs: number;
  recovered_ghs: number;
  principal_recovered_ghs: number;
  principal_recovery_percent: number | null;
}
interface DisbursementPage {
  totals: RecoveryTotals;
  has_more: boolean;
  items: (RecoveryTotals & {loan_id: number; account_number: string; customer_name: string; status: string})[];
}
const currency = new Intl.NumberFormat('en-GH', {style: 'currency', currency: 'GHS'});
export const recoveryRate = (rate?: number | null) => rate == null ? 'Unavailable' : rate.toFixed(2)+'%';

export function LoanDisbursements({institutionId, load, open, pending, revision}: {
  institutionId: number;
  load: (path: string) => Promise<DisbursementPage>;
  open: (id: number) => void;
  pending: {id: number; undisbursed_ghs: number}[];
  revision: unknown;
}) {
  const [offset, setOffset] = useState(0);
  const [recording, setRecording] = useState(false);
  const [data, setData] = useState<DisbursementPage | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (recording) return;
    let current = true;
    setData(null);
    setError('');
    load('/finance/institutions/'+institutionId+'/disbursements?offset='+offset).then(
      result => {if (current) setData(result)},
      problem => {if (current) setError(String(problem))},
    );
    return () => {current = false};
  }, [institutionId, load, offset, recording, revision]);

  return <section className="panel">
    {recording ? <>
      <button type="button" className="outline" onClick={() => setRecording(false)}>Back to disbursed loans</button>
      <h2>Record a disbursement</h2>
      {pending.map(loan => <div className="item" key={loan.id}>
        <p>AQUA-LOAN-{String(loan.id).padStart(6, '0')} · Available to disburse {currency.format(loan.undisbursed_ghs)}</p>
        <button type="button" className="outline" onClick={() => open(loan.id)}>Record disbursement</button>
      </div>)}
      {!pending.length && <p className="empty">No loans awaiting disbursement.</p>}
    </> : <>
      <h2>Disbursed loans</h2>
      {pending.length > 0 && <button type="button" className="primary" onClick={() => setRecording(true)}>Record a disbursement</button>}
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading disbursements</p>}
      {data && <>
        <dl>
          <dt>Total disbursed</dt><dd>{currency.format(data.totals.disbursed_ghs)}</dd>
          <dt>Total recovered</dt><dd>{currency.format(data.totals.recovered_ghs)}</dd>
          <dt>Principal recovery</dt><dd>{recoveryRate(data.totals.principal_recovery_percent)}</dd>
        </dl>
        <p className="muted">Total recovered includes principal, interest and fees. Principal recovery is principal repaid divided by principal disbursed.</p>
        {data.items.map(row => <div className="item" key={row.loan_id}>
          <b>{row.customer_name}</b>
          <p>{row.account_number} · {row.status.replace(/_/g, ' ')}</p>
          <p>Disbursed {currency.format(row.disbursed_ghs)} · Recovered {currency.format(row.recovered_ghs)} · Principal recovery {recoveryRate(row.principal_recovery_percent)}</p>
          <button type="button" className="outline" onClick={() => open(row.loan_id)}>View loan</button>
        </div>)}
        {!data.items.length && <p className="empty">No loans have been disbursed.</p>}
        <div className="farmactions">
          <button type="button" className="outline" disabled={!offset} onClick={() => setOffset(offset - 25)}>Previous</button>
          <button type="button" className="outline" disabled={!data.has_more} onClick={() => setOffset(offset + 25)}>Next</button>
        </div>
      </>}
    </>}
  </section>;
}
