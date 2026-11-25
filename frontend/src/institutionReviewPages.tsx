import {useEffect, useState} from 'react';

const views = [
  ['pending', 'Pending institution approvals'],
  ['verified', 'Approved financial institutions'],
  ['rejected', 'Rejected financial institutions'],
  ['suspended', 'Suspended financial institutions'],
  ['all', 'All financial institutions'],
] as const;

export interface Institution {
  id: number;
  name: string;
  status: string;
  institution_type: string;
  registration_number: string;
}

const awaitingDecision = (status: string) => ['pending', 'under_review', 'more_info_required'].includes(status);
const belongs = (status: string, view: string) => view === 'all' || (view === 'pending' ? awaitingDecision(status) : status === view);
const statusLabel = (status: string) => status === 'verified' ? 'Approved' : status.replace(/_/g, ' ');

export function InstitutionReviewPages({view, rows, owner, search, setSearch, busy, decide}: {
  view: string;
  rows: Institution[];
  owner: boolean;
  search: string;
  setSearch: (value: string) => void;
  busy: boolean;
  decide: (id: number, status: string, reason: string, queue: string) => Promise<void>;
}) {
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState('recent');
  const pageSize = 25;
  if (view === 'institutions') return <section className="panel">
    <h2>Financial institution management</h2>
    <div className="farmactions">
      <a className="primary" href="#admin/institutions/register">Register financial institution</a>
      <a className="outline" href="#admin/institutions/history">Approval history</a>
      {views.map(([key, label]) => <a key={key} className="outline" href={'#admin/institutions/'+key}>
        {label} ({rows.filter(row => belongs(row.status, key)).length})
      </a>)}
    </div>
  </section>;

  const list = views.find(([key]) => view === 'institutions/'+key);
  if (list) {
    const matches = rows.filter(row => belongs(row.status, list[0]) &&
      (row.name+' '+row.registration_number).toLowerCase().includes(search.trim().toLowerCase()));
    if (sort === 'name') matches.sort((a, b) => a.name.localeCompare(b.name));
    const currentPage = Math.min(page, Math.max(0, Math.ceil(matches.length / pageSize) - 1));
    return <section className="panel">
      <h2>{list[1]}</h2>
      <label className="field"><span>Search institutions</span>
        <input type="search" value={search} onChange={e => {setSearch(e.target.value);setPage(0)}}/>
      </label>
      <label className="field"><span>Sort institutions</span>
        <select value={sort} onChange={e => {setSort(e.target.value);setPage(0)}}>
          <option value="recent">Most recently registered</option>
          <option value="name">Institution name</option>
        </select>
      </label>
      {matches.slice(currentPage * pageSize, (currentPage + 1) * pageSize).map(row => <div className="item" key={row.id}>
        <b>{row.name}</b>
        <p>{row.institution_type} · {row.registration_number} · {statusLabel(row.status)}</p>
        <div className="row-actions">
          <a className="outline small" href={'#admin/institutions/details/'+row.id}>View details</a>
          {(awaitingDecision(row.status) || (owner && ['verified','suspended'].includes(row.status))) &&
            <a className="outline small" href={'#admin/institutions/review/'+row.id}>
              {awaitingDecision(row.status) ? 'Review' : 'Manage account'}
            </a>}
        </div>
      </div>)}
      {matches.length > pageSize && <div className="farmactions">
        <button type="button" className="outline" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button>
        <button type="button" className="outline" disabled={(currentPage + 1) * pageSize >= matches.length} onClick={() => setPage(currentPage + 1)}>Next</button>
      </div>}
      {!matches.length && <p className="empty">No institutions match this view.</p>}
    </section>;
  }

  const route = view.match(/^institutions\/(review|details)\/(\d+)$/);
  const row = rows.find(item => item.id === Number(route?.[2]));
  if (!route || !row) return <p className="empty">Institution details are unavailable.</p>;
  const actions: Record<string, string> = {};
  if (route[1] === 'review') {
    if (row.status === 'pending' || row.status === 'more_info_required') actions.under_review = 'Start review';
    if (row.status === 'pending' || row.status === 'under_review') actions.more_info_required = 'Request more information';
    if (awaitingDecision(row.status)) {
      actions.verified = 'Approve';
      actions.rejected = 'Reject';
    }
    if (owner && row.status === 'verified') actions.suspended = 'Suspend';
    if (owner && row.status === 'suspended') actions.verified = 'Reactivate';
  }
  return <section className="panel">
    <h2>{route[1] === 'review' ? 'Review institution' : 'Institution details'}</h2>
    <h3>{row.name}</h3>
    <dl>
      <dt>Institution type</dt><dd>{row.institution_type}</dd>
      <dt>Registration reference</dt><dd>{row.registration_number}</dd>
      <dt>Status</dt><dd>{statusLabel(row.status)}</dd>
    </dl>
    <a className="outline" href={'#admin/institutions/history/'+row.id}>View approval history</a>
    <div className="row-actions">{Object.entries(actions).map(([status, label]) =>
      <button key={status} type="button" className="outline" disabled={busy} onClick={() => {
        const reason = window.prompt('Enter a reason for this decision.');
        if (reason?.trim() && window.confirm(label+' '+row.name+'?')) {
          void decide(row.id, status, reason.trim(), awaitingDecision(row.status) ? 'pending' : 'all');
        }
      }}>{label}</button>)}</div>
  </section>;
}

interface ApprovalHistory {
  items: {
    id: number;
    institution: string;
    actor: string;
    created_at: string;
    previous_status: string | null;
    status: string | null;
    reason: string | null;
  }[];
  has_more: boolean;
}

export function InstitutionApprovalHistory({institutionId, load}: {
  institutionId?: number;
  load: (path: string) => Promise<ApprovalHistory>;
}) {
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<ApprovalHistory | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    setResult(null);
    setError('');
    const query = new URLSearchParams({offset: String(offset)});
    if (institutionId) query.set('institution_id', String(institutionId));
    load('/finance/admin/institutions/history?'+query).then(
      data => {if (current) setResult(data)},
      problem => {if (current) setError(String(problem))},
    );
    return () => {current = false};
  }, [institutionId, load, offset]);

  return <section className="panel">
    <h2>Financial institution approval history</h2>
    {error && <p role="alert">{error}</p>}
    {!result && !error && <p role="status">Loading approval history</p>}
    {result?.items.map(entry => <div className="item" key={entry.id}>
      <b>{entry.institution}</b>
      <p>{entry.previous_status && statusLabel(entry.previous_status)+' to '}{entry.status && statusLabel(entry.status)}</p>
      <p>{entry.actor} ? {new Date(entry.created_at).toLocaleString()}</p>
      {entry.reason && <p>{entry.reason}</p>}
    </div>)}
    {result?.items.length === 0 && <p className="empty">No approval history is available.</p>}
    <div className="farmactions">
      <button type="button" className="outline" disabled={offset === 0} onClick={() => setOffset(offset - 25)}>Previous</button>
      <button type="button" className="outline" disabled={!result?.has_more} onClick={() => setOffset(offset + 25)}>Next</button>
    </div>
  </section>;
}
