import {useEffect, useState} from 'react';

interface CollectionRow {
  id?: number;
  loan_id: number;
  account_number: string;
  customer_name: string;
  farm_name?: string;
  amount_ghs?: number;
  evidence_id?: number | null;
  evidence_media_type?: string | null;
}
interface CollectionPage {
  items: CollectionRow[];
  has_more: boolean;
  total_ghs?: number;
  count?: number;
}
const currency = new Intl.NumberFormat('en-GH', {style: 'currency', currency: 'GHS'});

export function LoanCollections({institutionId, load, collect, video, refresh}: {
  institutionId: number;
  load: (path: string) => Promise<CollectionPage>;
  collect: (loanId: number) => void;
  video: (id: number, mediaType?: string | null) => void;
  refresh: unknown;
}) {
  const [view, setView] = useState<'daily' | 'customers'>('daily');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [day, setDay] = useState(() => new Date().toISOString().slice(0, 10));
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<CollectionPage | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    setResult(null);
    setError('');
    const params = new URLSearchParams({offset: String(offset)});
    params.set(view === 'daily' ? 'day' : 'search', view === 'daily' ? day : query);
    const resource = view === 'daily' ? 'collections' : 'collection-customers';
    load('/finance/institutions/'+institutionId+'/'+resource+'?'+params).then(
      data => {if (current) setResult(data)},
      failure => {if (current) setError(String(failure))},
    );
    return () => {current = false};
  }, [day, institutionId, load, offset, query, refresh, view]);

  return <section className="panel">
    <div className="farmactions">
      <button type="button" className="outline" aria-pressed={view === 'daily'} onClick={() => {setOffset(0);setView('daily')}}>Daily collections</button>
      <button type="button" className="outline" aria-pressed={view === 'customers'} onClick={() => {setOffset(0);setView('customers')}}>Find a customer</button>
    </div>
    <h2>{view === 'daily' ? 'Daily collections' : 'Find a customer'}</h2>
    {view === 'daily' ? <label className="field"><span>Collection date</span>
      <input type="date" required value={day} onChange={e => {if (e.target.value) {setDay(e.target.value);setOffset(0)}}}/>
    </label> : <form onSubmit={e => {e.preventDefault();setOffset(0);setQuery(search)}}>
      <label className="field"><span>Customer name or loan account number</span>
        <input type="search" value={search} maxLength={120} onChange={e => setSearch(e.target.value)}/>
      </label>
      <button className="primary">Search</button>
    </form>}
    {error && <p role="alert">{error}</p>}
    {!result && !error && <p role="status">Loading…</p>}
    {result && view === 'daily' && <p>{result.count} posted repayments · {currency.format(result.total_ghs ?? 0)}</p>}
    {result?.items.map(row => <div className="item" key={row.id ?? row.loan_id}>
      <b>{row.customer_name}</b>
      <p>{row.account_number}{row.farm_name && ' · '+row.farm_name}</p>
      {view === 'customers' ?
        <button type="button" className="outline" onClick={() => collect(row.loan_id)}>Collect loan repayment</button> :
        <><p>{currency.format(row.amount_ghs ?? 0)}</p>
        {row.evidence_id != null && <button type="button" className="outline" onClick={() => video(row.evidence_id!, row.evidence_media_type)}>Review video</button>}</>}
    </div>)}
    {result?.items.length === 0 && <p className="empty">{view === 'daily' ? 'No repayments posted for this date.' : 'No active loan accounts match this search.'}</p>}
    <div className="farmactions">
      <button type="button" className="outline" disabled={!offset} onClick={() => setOffset(offset - 25)}>Previous</button>
      <button type="button" className="outline" disabled={!result?.has_more} onClick={() => setOffset(offset + 25)}>Next</button>
    </div>
  </section>;
}
