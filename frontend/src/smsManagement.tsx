import {useEffect, useState, type FormEvent} from 'react';

const pages = {
  dashboard: 'SMS dashboard', gateway: 'Gateway status', balance: 'SMS balance',
  test: 'Send test SMS', history: 'SMS history', delivered: 'Delivered messages',
  failed: 'Failed messages', usage: 'SMS usage reports', audit: 'SMS audit history',
  templates: 'Notification templates', scheduled: 'Scheduled notifications', settings: 'Notification settings',
} as const;

type Page = keyof typeof pages;
type Delivery = {id: number; category: string; state: string; message_id: string | null; created_at: string;
  updated_at: string; message_count: number | null; operator_id: number | null};
type Data = {items?: Delivery[]; has_more?: boolean; ready?: boolean; reason?: string; provider?: string; sandbox?: boolean;
  sms_balance?: string; main_balance?: string; low_balance?: boolean; requests_today?: number; requests_this_month?: number;
  states_this_month?: Record<string, number>; categories_this_month?: Record<string, number>; delivery_success_pct?: number | null;
  requests?: number; states?: Record<string, number>; categories?: Record<string, number>;
  message_id?: string; templates?: {event: string; text: string}[]; outbox_states?: Record<string, number>;
  financial_notifications?: boolean; daily_reminders?: boolean; loan_reminders?: boolean};
type Api = (path: string, body?: Record<string, unknown>) => Promise<Data>;

export function SmsManagement({view, api}: {view: string; api: Api}) {
  const page = (Object.hasOwn(pages, view) ? view : 'dashboard') as Page;
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const isHistory = ['history', 'delivered', 'failed', 'audit'].includes(page);
  const invalidRange = Boolean(start && end && start > end);

  useEffect(() => {
    if (page === 'test' || invalidRange) return;
    let current = true;
    const filters = new URLSearchParams({offset: String(offset)});
    if (start) filters.set('start', start);
    if (end) filters.set('end', end);
    if (page === 'delivered' || page === 'failed') filters.set('state', page);
    const path = isHistory ? 'history?'+filters : page === 'usage' ? 'usage?'+filters : page === 'dashboard' ? 'summary' : page;
    setData(null);
    setError('');
    api('/admin/sms/'+path).then(result => {
      if (current) setData(result);
    }, problem => {if (current) setError(String(problem))});
    return () => {current = false};
  }, [api, end, invalidRange, isHistory, offset, page, revision, start]);

  async function send(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setData(null);
    try {
      setData(await api('/admin/sms/sandbox-test', {phone_number: phone.trim()}));
      setPhone('');
    } catch (problem) {
      setError(String(problem));
    } finally {
      setBusy(false);
    }
  }

  async function refreshReports() {
    const ids = (data?.items ?? []).flatMap(row =>
      row.message_id && ['accepted', 'unknown'].includes(row.state) ? [row.message_id] : []);
    if (!ids.length) return;
    setBusy(true);
    setError('');
    try {
      await api('/admin/sms/delivery-reports', {message_ids: ids});
      setRevision(value => value + 1);
    } catch (problem) {
      setError(String(problem));
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel">
    <h2>{pages[page]}</h2>
    {page === 'dashboard' ? <nav className="farmactions" aria-label="SMS management">
      {Object.entries(pages).filter(([key]) => key !== 'dashboard').map(([key, label]) =>
        <a className="outline" key={key} href={'#admin/sms/'+key}>{label}</a>)}
    </nav> : <a className="outline" href="#admin/sms">Back to SMS dashboard</a>}
    {error && <p role="alert" className="alert">{error}</p>}
    {page !== 'test' && !data && !error && !invalidRange && <p role="status">Loading SMS information…</p>}
    {page === 'gateway' && data && <p>{data.ready
      ? ('Configured provider: '+data.provider+(data.sandbox ? ' · Sandbox' : ' · Live'))
      : data.reason}</p>}
    {page === 'balance' && data && <>
      <p>SMS credits <strong>{data.sms_balance}</strong></p>
      <p>Main account balance <strong>{data.main_balance}</strong></p>
      {data.low_balance && <p role="status" className="alert">SMS credits are at or below the configured threshold.</p>}
    </>}
    {page === 'templates' && data && <dl>{data.templates?.map(template =>
      <div key={template.event}><dt>{template.event.replaceAll('-', ' ')}</dt><dd>{template.text}</dd></div>)}</dl>}
    {page === 'scheduled' && data && <dl>
      {['pending', 'processing', 'accepted', 'delivered', 'failed', 'unknown', 'cancelled'].map(state =>
        <div key={state}><dt>{state}</dt><dd>{data.outbox_states?.[state] ?? 0}</dd></div>)}
    </dl>}
    {page === 'settings' && data && <dl>
      <dt>Financial confirmations</dt><dd>{data.financial_notifications ? 'Enabled' : 'Disabled'}</dd>
      <dt>Daily feeding reminders</dt><dd>{data.daily_reminders ? 'Enabled' : 'Disabled'}</dd>
      <dt>Loan repayment reminders</dt><dd>{data.loan_reminders ? 'Enabled' : 'Disabled'}</dd>
    </dl>}
    {page === 'dashboard' && data && <dl>
      <dt>Requests today</dt><dd>{data.requests_today}</dd>
      <dt>Requests this month</dt><dd>{data.requests_this_month}</dd>
      {['accepted', 'delivered', 'failed', 'sandbox', 'unknown'].map(state =>
        <div key={state}><dt>{state} this month</dt><dd>{data.states_this_month?.[state] ?? 0}</dd></div>)}
      {['otp', 'financial', 'farm', 'test'].map(category =>
        <div key={category}><dt>{category.toUpperCase()} requests this month</dt><dd>{data.categories_this_month?.[category] ?? 0}</dd></div>)}
      <dt>Delivery success rate</dt><dd>{data.delivery_success_pct == null ? 'Unavailable' : data.delivery_success_pct+'%'}</dd>
    </dl>}
    {page === 'test' && <form onSubmit={event => void send(event)}>
      <p>Sandbox requests check Arkesel connectivity without delivering a text to the phone.</p>
      <label className="field"><span>Test recipient phone number</span>
        <input type="tel" required maxLength={64} value={phone} onChange={event => setPhone(event.target.value)}/>
      </label>
      <button type="submit" className="primary" disabled={busy}>{busy ? 'Testing…' : 'Send sandbox test'}</button>
      {data?.message_id && <p role="status">Sandbox request accepted. Provider reference {data.message_id}.</p>}
    </form>}
    {(isHistory || page === 'usage') && <>
      <div className="farmactions">
        <label className="field"><span>From date</span><input type="date" value={start} onChange={event => {setOffset(0); setStart(event.target.value)}}/></label>
        <label className="field"><span>Through date</span><input type="date" value={end} onChange={event => {setOffset(0); setEnd(event.target.value)}}/></label>
        {page === 'history' && <button type="button" className="outline"
          disabled={busy || invalidRange || !data?.items?.some(row => row.message_id && ['accepted', 'unknown'].includes(row.state))}
          onClick={() => void refreshReports()}>{busy ? 'Checking…' : 'Check delivery reports'}</button>}
      </div>
      {invalidRange && <p role="alert">From date must be on or before through date.</p>}
    </>}
    {page === 'usage' && !invalidRange && data && <dl>
      <dt>Requests in selected dates</dt><dd>{data.requests}</dd>
      {['accepted', 'delivered', 'failed', 'sandbox', 'unknown'].map(state =>
        <div key={state}><dt>{state}</dt><dd>{data.states?.[state] ?? 0}</dd></div>)}
      {Object.entries(data.categories ?? {}).map(([category, count]) =>
        <div key={category}><dt>{category.toUpperCase()} requests</dt><dd>{count}</dd></div>)}
      <dt>Delivery success rate</dt><dd>{data.delivery_success_pct == null ? 'Unavailable' : data.delivery_success_pct+'%'}</dd>
    </dl>}
    {isHistory && <>
      {!invalidRange && data?.items?.length === 0 && <p>No SMS requests match these filters.</p>}
      {!invalidRange && Boolean(data?.items?.length) && <div className="tablewrap"><table>
        <thead><tr><th>Requested</th><th>Category</th><th>Status</th><th>Provider reference</th><th>Message count</th>{page === 'audit' && <th>Operator ID</th>}</tr></thead>
        <tbody>{data?.items?.map(row => <tr key={row.id}>
          <td>{new Date(row.created_at.endsWith('Z') || /[+-]\d\d:\d\d$/.test(row.created_at) ? row.created_at : row.created_at+'Z')
            .toLocaleString('en-GH', {timeZone: 'Africa/Accra'})}</td>
          <td>{row.category}</td><td>{row.state}</td><td>{row.message_id ?? '—'}</td><td>{row.message_count ?? '—'}</td>
          {page === 'audit' && <td>{row.operator_id ?? 'System'}</td>}
        </tr>)}</tbody>
      </table></div>}
      <div className="farmactions">
        <button className="outline" disabled={!offset || busy} onClick={() => setOffset(offset - 50)}>Previous</button>
        <button className="outline" disabled={!data?.has_more || busy || invalidRange} onClick={() => setOffset(offset + 50)}>Next</button>
      </div>
    </>}
  </section>;
}
