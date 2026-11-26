import {useState} from 'react';
import {ArrowLeft, Building2, Fish, ShieldCheck, Waves} from 'lucide-react';

const currency = new Intl.NumberFormat('en-GH', {style: 'currency', currency: 'GHS'});
const money = (pesewas: number) => currency.format(pesewas / 100);
const roles = [
  {id: 'farmer', label: 'Farmer', icon: Fish},
  {id: 'institution', label: 'Financial institution', icon: Building2},
  {id: 'admin', label: 'Platform administrator', icon: ShieldCheck},
] as const;

export function splitDemoPayment(received: number, outstanding: number, depositOnly: boolean) {
  const loan = depositOnly ? 0 : Math.min(received, outstanding);
  return {loan, deposit: received - loan};
}

export function AquaFarmDemo() {
  const [role, setRole] = useState<typeof roles[number]['id']>('farmer');
  const [feed, setFeed] = useState(0);
  const [amount, setAmount] = useState('');
  const [payments, setPayments] = useState<{id: number; loan: number; deposit: number}[]>([]);
  const [approved, setApproved] = useState(false);
  const [payout, setPayout] = useState<'ready' | 'pending' | 'approved' | 'rejected'>('ready');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const recovered = payments.reduce((total, payment) => total + payment.loan, 0);
  const deposited = payments.reduce((total, payment) => total + payment.deposit, 0);
  const outstanding = 10100 - recovered;

  function reset() {
    setFeed(0);setAmount('');setPayments([]);setApproved(false);setPayout('ready');
    setError('');setNotice('Sample records reset.');
  }

  function recordPayment(depositOnly: boolean) {
    const value = amount.trim();
    if (!/^\d{1,7}(\.\d{1,2})?$/.test(value) || Number(value) <= 0) {
      setError('Enter a positive amount with up to two decimal places.');
      return;
    }
    const received = Math.round(Number(value)*100);
    setPayments(current => {
      const remaining = 10100 - current.reduce((total, payment) => total + payment.loan, 0);
      return [...current, {id: current.length + 1, ...splitDemoPayment(received, remaining, depositOnly)}];
    });
    setAmount('');setError('');
    setNotice('Sample transaction recorded.');
  }

  return <main className="demo-workspace">
    <div className="demo-top">
      <div className="brand"><Waves size={28}/><span>AquaFarm <b>Manager Ghana</b></span></div>
      <a className="outline" href="#"><ArrowLeft size={16}/> Back to sign in</a>
    </div>
    <header className="demo-header">
      <h1>Try AquaFarm</h1>
      <p>Explore with fictional records. Changes stay on this page and reset when you leave.</p>
    </header>
    <nav className="demo-actions" aria-label="Choose a demo workspace">
      {roles.map(({id, label, icon: Icon}) => <button key={id} type="button" className={role === id ? 'primary' : 'outline'}
        aria-pressed={role === id} onClick={() => {setRole(id);setNotice('');setError('')}}><Icon size={17}/>{label}</button>)}
      <button type="button" className="outline" onClick={reset}>Reset sample data</button>
    </nav>
    {notice && <p className="success" role="status">{notice}</p>}
    {error && <p className="alert" role="alert">{error}</p>}

    {role === 'farmer' && <div className="demo-grid">
      <section className="panel">
        <h2>Sample Tilapia Farm</h2>
        <dl className="demo-metrics">
          <dt>Production unit</dt><dd>Pond A</dd>
          <dt>Fish stocked</dt><dd>800 tilapia</dd>
          <dt>Feed recorded today</dt><dd>{feed} kg</dd>
        </dl>
        <button type="button" className="primary" disabled={feed > 0}
          onClick={() => {setFeed(5);setNotice('Sample feeding of 5 kg recorded.')}}>Record 5 kg feeding</button>
      </section>
      <section className="panel">
        <h2>My loan and deposits</h2>
        <dl className="demo-metrics">
          <dt>Loan outstanding</dt><dd>{money(outstanding)}</dd>
          <dt>Recorded deposits</dt><dd>{money(deposited)}</dd>
        </dl>
      </section>
    </div>}

    {role === 'institution' && <div className="demo-grid">
      <section className="panel">
        <h2>Sample collections</h2>
        <p>Demo borrower · AQUA-DEMO-0001</p>
        <dl className="demo-metrics">
          <dt>Loan outstanding</dt><dd>{money(outstanding)}</dd>
          <dt>Recorded deposits</dt><dd>{money(deposited)}</dd>
        </dl>
        <form onSubmit={event => {event.preventDefault();recordPayment(false)}}>
          <label className="field"><span>Amount received (GHS)</span>
            <input required inputMode="decimal" value={amount} onChange={event => setAmount(event.target.value)}/>
          </label>
          <div className="demo-actions">
            <button type="submit" className="primary">Record loan collection</button>
            <button type="button" className="outline" onClick={() => recordPayment(true)}>Record deposit</button>
          </div>
        </form>
        <p className="muted">Amounts above the loan balance are recorded as a deposit in this demo.</p>
        {payments.length > 0 && <ul>{payments.map(payment => <li key={payment.id}>
          Receipt {payment.id} · Loan {money(payment.loan)} · Deposit {money(payment.deposit)}
        </li>)}</ul>}
      </section>
      <section className="panel">
        <h2>Disbursement approval</h2>
        <p>Sample payout · {money(75000)}</p>
        <p>Status: <b>{payout === 'ready' ? 'Ready to prepare' : payout === 'pending' ? 'Awaiting owner review' : payout}</b></p>
        {payout === 'ready' && <button type="button" className="primary" onClick={() => setPayout('pending')}>Prepare sample payout</button>}
        {payout === 'pending' && <div className="demo-actions">
          <button type="button" className="primary" onClick={() => setPayout('approved')}>Approve as demo owner</button>
          <button type="button" className="outline" onClick={() => setPayout('rejected')}>Reject as demo owner</button>
        </div>}
      </section>
    </div>}

    {role === 'admin' && <section className="panel">
      <h2>Farmer approvals</h2>
      <p>Demo farmer account · <b>{approved ? 'Approved' : 'Pending approval'}</b></p>
      <button type="button" className="primary" disabled={approved}
        onClick={() => {setApproved(true);setNotice('Sample farmer approved.')}}>Approve sample farmer</button>
    </section>}
  </main>;
}
