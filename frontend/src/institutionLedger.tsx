import {useEffect, useState} from 'react';

type Line = {code: string; name: string; debit_ghs: string; credit_ghs: string};
type Journal = {id: number; source_type: string; source_reference: string; effective_on: string};
type LedgerData = {
  items?: (Journal | Line)[]; lines?: Line[]; has_more?: boolean;
  balanced?: boolean; debit_total_ghs?: string; credit_total_ghs?: string; source_reference?: string;
};

export function InstitutionLedger({institutionId, mode, load}: {
  institutionId: number;
  mode: 'journals' | 'trial-balance';
  load: (path: string) => Promise<LedgerData>;
}) {
  const [offset, setOffset] = useState(0);
  const [journal, setJournal] = useState<number | null>(null);
  const [asOf, setAsOf] = useState('');
  const [result, setResult] = useState<LedgerData | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    setResult(null);
    setError('');
    const resource = mode === 'journals'
      ? journal == null ? 'journals?offset='+offset : 'journals/'+journal
      : 'trial-balance'+(asOf ? '?as_of='+encodeURIComponent(asOf) : '');
    load('/finance/institutions/'+institutionId+'/accounting/'+resource).then(
      data => {if (current) setResult(data)},
      problem => {if (current) setError(String(problem))},
    );
    return () => {current = false};
  }, [asOf, institutionId, journal, load, mode, offset]);
  const lines = mode === 'trial-balance' ? result?.items as Line[] | undefined : result?.lines;

  return <section className="panel">
    <h2>{mode === 'trial-balance' ? 'Trial balance' : journal == null ? 'Posted journals' : 'Journal details'}</h2>
    {mode === 'trial-balance' && <label className="field"><span>As of date</span>
      <input type="date" value={asOf} onChange={event => setAsOf(event.target.value)}/>
    </label>}
    {journal != null && <button className="outline" type="button" onClick={() => setJournal(null)}>Back to journals</button>}
    {error && <p role="alert">{error}</p>}
    {!result && !error && <p role="status">Loading accounting records</p>}
    {result?.source_reference && <p>Source reference {result.source_reference}</p>}
    {mode === 'journals' && journal == null && result && <>
      {((result.items ?? []) as Journal[]).map(item => <div className="item between" key={item.id}>
        <div><b>{item.source_reference}</b><p>{item.source_type} · {item.effective_on}</p></div>
        <button type="button" className="outline" onClick={() => setJournal(item.id)}>View journal</button>
      </div>)}
      {result.items?.length === 0 && <p className="empty">No journals have been posted.</p>}
      <div className="farmactions">
        <button type="button" className="outline" disabled={!offset} onClick={() => setOffset(offset-25)}>Previous</button>
        <button type="button" className="outline" disabled={!result.has_more} onClick={() => setOffset(offset+25)}>Next</button>
      </div>
    </>}
    {lines && <div className="tablewrap"><table>
      <thead><tr><th>Account</th><th>Debit (GHS)</th><th>Credit (GHS)</th></tr></thead>
      <tbody>{lines.map((line, index) => <tr key={line.code+'-'+index}>
        <td>{line.code} · {line.name}</td><td>{line.debit_ghs}</td><td>{line.credit_ghs}</td>
      </tr>)}</tbody>
      {mode === 'trial-balance' && <tfoot><tr><th>Total</th><td>{result?.debit_total_ghs}</td><td>{result?.credit_total_ghs}</td></tr></tfoot>}
    </table></div>}
    {lines?.length === 0 && <p className="empty">No posted lines for this view.</p>}
    {result?.balanced === false && <p role="alert">Debit and credit totals differ.</p>}
  </section>;
}
