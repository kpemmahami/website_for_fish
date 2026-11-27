import {useEffect, useState} from 'react';

type Line = {code: string; name: string; debit_ghs: string; credit_ghs: string};
type Journal = {id: number; source_type: string; source_reference: string; effective_on: string};
type LedgerData = {
  items?: (Journal | Line)[]; lines?: Line[]; has_more?: boolean;
  as_of?: string; id?: number; effective_on?: string;
  balanced?: boolean; debit_total_ghs?: string; credit_total_ghs?: string; source_reference?: string;
};

function csvAccountText(value: string) {
  // Prevent spreadsheet apps from evaluating account codes or names as formulas.
  const literal = /^(\s*[=+@-]|[\t\r\n])/.test(value) ? "'"+value : value;
  return '"'+literal.replaceAll('"', '""')+'"';
}

function csvLine(line: Line) {
  return [csvAccountText(line.code), csvAccountText(line.name), line.debit_ghs, line.credit_ghs].join(',');
}

function downloadCsv(filename: string, rows: string[]) {
  const url = URL.createObjectURL(new Blob(['\uFEFF', rows.join('\r\n'), '\r\n'], {type: 'text/csv;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

const accountColumns = 'Account code,Account name,Debit (GHS),Credit (GHS)';

export function InstitutionLedger({institutionId, mode, routeQuery = '', load, download}: {
  institutionId: number;
  mode: 'journals' | 'trial-balance';
  routeQuery?: string;
  load: (path: string) => Promise<LedgerData>;
  download: (path: string, filename: string) => Promise<void>;
}) {
  const route = new URLSearchParams(routeQuery);
  const sameInstitution = route.get('institution') === String(institutionId);
  const routeCutoff = sameInstitution ? route.get('as_of') ?? '' : '';
  const cutoffDate = /^\d{4}-\d{2}-\d{2}$/.test(routeCutoff) ? routeCutoff : '';
  const linkedAccount = mode === 'journals' && sameInstitution ? (route.get('account_code') ?? '').slice(0, 32) : '';
  const [offset, setOffset] = useState(0);
  const [journal, setJournal] = useState<number | null>(null);
  const [asOf, setAsOf] = useState(mode === 'trial-balance' ? cutoffDate : '');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState(linkedAccount ? cutoffDate : '');
  const [reference, setReference] = useState('');
  const [accountCode, setAccountCode] = useState(linkedAccount);
  const [result, setResult] = useState<LedgerData | null>(null);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false);
  const isJournalList = mode === 'journals' && journal == null;
  const invalidDateRange = isJournalList && !!startDate && !!endDate && startDate > endDate;
  useEffect(() => {
    let current = true;
    setResult(null);
    setError('');
    if (invalidDateRange) return;
    const filters = new URLSearchParams({offset: String(offset)});
    if (startDate) filters.set('start', startDate);
    if (endDate) filters.set('end', endDate);
    if (reference) filters.set('reference', reference);
    if (accountCode) filters.set('account_code', accountCode);
    const resource = mode === 'journals'
      ? journal == null ? 'journals?'+filters.toString() : 'journals/'+journal
      : 'trial-balance'+(asOf ? '?as_of='+encodeURIComponent(asOf) : '');
    load('/finance/institutions/'+institutionId+'/accounting/'+resource).then(
      data => {if (current) setResult(data)},
      problem => {if (current) setError(String(problem))},
    );
    return () => {current = false};
  }, [accountCode, asOf, endDate, institutionId, invalidDateRange, journal, load, mode, offset, reference, startDate]);
  const lines = mode === 'trial-balance' ? result?.items as Line[] | undefined : result?.lines;
  const {as_of: cutoff, debit_total_ghs: debitTotal, credit_total_ghs: creditTotal} = result ?? {};
  const {id: journalId, effective_on: effectiveOn, source_reference: sourceReference} = result ?? {};

  function selectRecentDays(days: number) {
    // UTC and Ghana use the same calendar date year-round.
    const today = new Date();
    const firstDay = new Date(today);
    firstDay.setUTCDate(today.getUTCDate() - days + 1);
    const start = firstDay.toISOString().slice(0, 10);
    const end = today.toISOString().slice(0, 10);
    if (offset === 0 && start === startDate && end === endDate) return;
    setResult(null);
    setOffset(0);
    setStartDate(start);
    setEndDate(end);
  }

  async function downloadRange() {
    const dates = new URLSearchParams({start: startDate, end: endDate});
    if (reference) dates.set('reference', reference);
    if (accountCode) dates.set('account_code', accountCode);
    setExporting(true);
    try {
      await download('/finance/institutions/'+institutionId+'/accounting/journals/export?'+dates,
        'journals-'+startDate+'-to-'+endDate+'.csv');
    } finally {
      setExporting(false);
    }
  }

  return <section className="panel">
    <h2>{mode === 'trial-balance' ? 'Trial balance' : journal == null ? 'Posted journals' : 'Journal details'}</h2>
    {linkedAccount && <a className="outline" href={'#institution/trial-balance?'+new URLSearchParams({
      institution: String(institutionId), as_of: cutoffDate,
    })}>Back to trial balance</a>}
    {isJournalList && <div className="farmactions">
      <label className="field"><span>Source reference</span>
        <input type="search" value={reference} maxLength={200} onChange={event => {
          setResult(null);
          setOffset(0);
          setReference(event.target.value);
        }}/>
      </label>
      <label className="field"><span>Account code</span>
        <input type="search" value={accountCode} maxLength={32} onChange={event => {
          setResult(null);
          setOffset(0);
          setAccountCode(event.target.value);
        }}/>
      </label>
      <label className="field"><span>Recent days</span>
        <select value="" onChange={event => selectRecentDays(Number(event.target.value))}>
          <option value="" disabled>Choose days</option>
          {[7, 14, 30, 60, 90].map(days => <option key={days} value={days}>Last {days} days</option>)}
        </select>
      </label>
      <label className="field"><span>From effective date</span>
        <input type="date" value={startDate} onChange={event => {
          setResult(null);
          setOffset(0);
          setStartDate(event.target.value);
        }}/>
      </label>
      <label className="field"><span>Through effective date</span>
        <input type="date" value={endDate} onChange={event => {
          setResult(null);
          setOffset(0);
          setEndDate(event.target.value);
        }}/>
      </label>
      <button className="outline" type="button" disabled={!startDate || !endDate || invalidDateRange || exporting}
        onClick={downloadRange}>{exporting ? 'Downloading…' : 'Download date range CSV'}</button>
    </div>}
    {invalidDateRange && <p role="alert">From date must be on or before the through date.</p>}
    {mode === 'trial-balance' && <label className="field"><span>As of date</span>
      <input type="date" value={asOf} onChange={event => {
        setResult(null);
        setAsOf(event.target.value);
      }}/>
    </label>}
    {mode === 'trial-balance' && lines && cutoff && debitTotal != null && creditTotal != null &&
      <button className="outline" type="button" onClick={() =>
        downloadCsv('trial-balance-'+cutoff+'.csv', [
          'As of date,'+accountColumns,
          ...lines.map(line => cutoff+','+csvLine(line)),
          [cutoff, '', 'Total', debitTotal, creditTotal].join(','),
        ])
      }>Download CSV</button>}
    {mode === 'journals' && journal != null && journalId === journal && effectiveOn && sourceReference != null && lines &&
      <button className="outline" type="button" onClick={() =>
        downloadCsv('journal-'+journalId+'.csv', [
          'Journal ID,Effective date,Source reference,'+accountColumns,
          ...lines.map(line => [journalId, effectiveOn, csvAccountText(sourceReference), csvLine(line)].join(',')),
        ])
      }>Download CSV</button>}
    {journal != null && <button className="outline" type="button" onClick={() => setJournal(null)}>Back to journals</button>}
    {error && <p role="alert">{error}</p>}
    {!result && !error && !invalidDateRange && <p role="status">Loading accounting records</p>}
    {result?.source_reference && <p>Source reference {result.source_reference}</p>}
    {isJournalList && !invalidDateRange && result && <>
      {((result.items ?? []) as Journal[]).map(item => <div className="item between" key={item.id}>
        <div><b>{item.source_reference}</b><p>{item.source_type} · {item.effective_on}</p></div>
        <button type="button" className="outline" onClick={() => {
          setResult(null);
          setJournal(item.id);
        }}>View journal</button>
      </div>)}
      {result.items?.length === 0 && <p className="empty">
        {startDate || endDate || reference.trim() || accountCode.trim()
          ? 'No posted journals match these filters.' : 'No journals have been posted.'}
      </p>}
      <div className="farmactions">
        <button type="button" className="outline" disabled={!offset} onClick={() => setOffset(offset-25)}>Previous</button>
        <button type="button" className="outline" disabled={!result.has_more} onClick={() => setOffset(offset+25)}>Next</button>
      </div>
    </>}
    {lines && <div className="tablewrap"><table>
      <thead><tr><th>Account</th><th>Debit (GHS)</th><th>Credit (GHS)</th></tr></thead>
      <tbody>{lines.map((line, index) => <tr key={line.code+'-'+index}>
        <td>{mode === 'trial-balance' && cutoff
          ? <a href={'#institution/journals?'+new URLSearchParams({
            institution: String(institutionId), account_code: line.code, as_of: cutoff,
          })}>{line.code} · {line.name}</a>
          : <>{line.code} · {line.name}</>}</td><td>{line.debit_ghs}</td><td>{line.credit_ghs}</td>
      </tr>)}</tbody>
      {mode === 'trial-balance' && <tfoot><tr><th>Total</th><td>{result?.debit_total_ghs}</td><td>{result?.credit_total_ghs}</td></tr></tfoot>}
    </table></div>}
    {lines?.length === 0 && <p className="empty">No posted lines for this view.</p>}
    {result?.balanced === false && <p role="alert">Debit and credit totals differ.</p>}
  </section>;
}
