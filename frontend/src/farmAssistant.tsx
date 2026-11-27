import {useEffect, useState, type FormEvent} from 'react';

type Cycle = {id: number; unit_name: string; species: string; stocked_on: string; closed: boolean};
type Config = {ai_enabled: boolean; cycles: Cycle[]};
type Answer = {answer: string; source: string; source_url?: string};
type Exchange = Answer & {question: string};
type Request = {question: string; cycle_id: number | null; margin_pct: number;
  history: {role: 'user' | 'assistant'; content: string}[]};

export function FarmAssistant({farmId, farmName, load, ask}: {
  farmId: number;
  farmName: string;
  load: (path: string) => Promise<Config>;
  ask: (path: string, body: Request) => Promise<Answer>;
}) {
  const path = '/farms/'+farmId+'/assistant';
  const [config, setConfig] = useState<Config | null>(null);
  const [cycle, setCycle] = useState('');
  const [margin, setMargin] = useState('25');
  const [question, setQuestion] = useState('');
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let current = true;
    load(path).then(data => {
      if (!current) return;
      setConfig(data);
      if (data.cycles.length === 1) setCycle(String(data.cycles[0].id));
    }, problem => {if (current) setError(String(problem))});
    return () => {current = false};
  }, [load, path]);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy || !config) return;
    const history = exchanges.slice(-3).flatMap(({question: previous, answer, source}) => [
      {role: 'user' as const, content: previous},
      ...(source === 'Pricing advisor' ? [] : [{role: 'assistant' as const, content: answer.slice(0, 4000)}]),
    ]);
    setBusy(true);
    setError('');
    try {
      const reply = await ask(path, {question: text, cycle_id: cycle ? Number(cycle) : null, margin_pct: Number(margin), history});
      setExchanges(current => [...current, {...reply, question: text}]);
      setQuestion('');
    } catch (problem) {
      setError(String(problem));
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel">
    <div className="between">
      <h2>{farmName}</h2>
      {exchanges.length > 0 && <button className="outline" type="button" disabled={busy} onClick={() => {
        setExchanges([]);
        setQuestion('');
        setError('');
      }}>New chat</button>}
    </div>
    {config && <p className="muted">{config.ai_enabled
      ? 'For general AI answers, your questions and farm summary figures are sent to OpenAI. Avoid entering personal or payment details.'
      : 'Built-in farm reports, pricing estimates and fish care guidance are available. Open-ended AI answers require provider setup.'}</p>}
    {!config && !error && <p role="status">Loading farm assistant…</p>}
    {error && <p className="alert" role="alert">{error}</p>}
    <div role="log" aria-label="Farm conversation" aria-live="polite">
      {exchanges.map((exchange, index) => <div className="item" key={index}>
        <p style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}><strong>You</strong>{'\n'}{exchange.question}</p>
        <p style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}><strong>Farm assistant</strong>{'\n'}{exchange.answer}</p>
        <small>{exchange.source_url ? <a href={exchange.source_url} target="_blank" rel="noreferrer">{exchange.source}</a> : exchange.source}</small>
      </div>)}
    </div>
    {config && <form onSubmit={event => void send(event)}>
      <div className="farmactions">
        {['Summarize my farm records', 'What price should I sell my fish for?', 'Cash flow for the last 30 days',
          'What should I record when feeding fish?'].map(prompt =>
          <button className="outline" type="button" key={prompt} disabled={busy} onClick={() => setQuestion(prompt)}>{prompt}</button>
        )}
      </div>
      <div className="farmactions">
        <label className="field"><span>Cycle for pricing</span>
          <select value={cycle} disabled={busy} onChange={event => setCycle(event.target.value)}>
            <option value="">{config.cycles.length ? 'Choose a stocking cycle' : 'No stocking cycles recorded'}</option>
            {config.cycles.map(row => <option key={row.id} value={row.id}>
              {row.unit_name} · {row.species} · {row.stocked_on}{row.closed ? ' · Closed' : ''}
            </option>)}
          </select>
        </label>
        <label className="field"><span>Target profit margin (%)</span>
          <input type="number" required min="0" max="99.99" step="0.01" value={margin} disabled={busy}
            onChange={event => setMargin(event.target.value)}/>
        </label>
      </div>
      <label className="field"><span>Your question</span>
        <textarea rows={3} value={question} maxLength={1500} required disabled={busy}
          onChange={event => setQuestion(event.target.value)}/>
      </label>
      <button className="primary" disabled={busy || !question.trim()}>{busy ? 'Getting answer…' : 'Send question'}</button>
    </form>}
  </section>;
}
