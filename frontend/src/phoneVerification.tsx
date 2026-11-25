import {useState} from 'react';

export function PhoneVerification({phone, verified, request, confirm}: {
  phone: string | null;
  verified: boolean;
  request: () => Promise<{verified: boolean; destination?: string}>;
  confirm: (code: string) => Promise<unknown>;
}) {
  const [destination, setDestination] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function send() {
    setError('');setBusy(true);
    try {
      const result = await request();
      setDestination(result.destination ?? '');
      setCode('');
    } catch (problem) {
      setError(String(problem));
    } finally {
      setBusy(false);
    }
  }

  return <section>
    <h2>Mobile number verification</h2>
    {verified ? <p>Mobile number verified.</p> : !phone ? <p>No mobile number is saved on this account.</p> : <>
      <p>{destination ? `Enter the code sent to ${destination}.` : 'Confirm that you can receive SMS at your saved mobile number.'}</p>
      {error&&<p role="alert" className="alert">{error}</p>}
      {destination&&<form onSubmit={async event=>{
        event.preventDefault();setBusy(true);setError('');
        try {await confirm(code);setCode('')}
        catch (problem) {setError(String(problem))}
        finally {setBusy(false)}
      }}>
        <label className="field"><span>SMS code</span><input value={code} required maxLength={6}
          pattern="[0-9]{6}" inputMode="numeric" autoComplete="one-time-code"
          onChange={event=>setCode(event.target.value)}/></label>
        <button type="submit" className="primary" disabled={busy}>Verify number</button>
      </form>}
      <button type="button" className="outline" onClick={()=>void send()} disabled={busy}>
        {destination ? 'Resend code' : 'Send verification code'}
      </button>
    </>}
  </section>;
}

export function PhoneReplacement({request, confirm}: {
  request: (phone: string, password: string) => Promise<{previous_destination: string; new_destination: string}>;
  confirm: (oldCode: string, newCode: string) => Promise<unknown>;
}) {
  const [destination, setDestination] = useState<{previous_destination: string; new_destination: string}|null>(null);
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [oldCode, setOldCode] = useState('');
  const [newCode, setNewCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  return <details>
    <summary>Change verified mobile number</summary>
    <p className="muted">Keep both phones nearby. You’ll need a code from each phone and will sign in again after the change.</p>
    {error&&<p role="alert" className="alert">{error}</p>}
    <form onSubmit={async event=>{
      event.preventDefault();setError('');setBusy(true);
      try {
        if(destination) await confirm(oldCode, newCode);
        else setDestination(await request(phone, password));
      } catch(problem) {setError(String(problem))}
      finally {setPassword('');setBusy(false)}
    }}>
      {destination?<>{([
        [destination.previous_destination, oldCode, setOldCode],
        [destination.new_destination, newCode, setNewCode],
      ] as const).map(([label, code, setCode], index)=><label className="field" key={index}>
        <span>{index===0?'Current phone':'New phone'} code for {label}</span>
        <input required pattern="[0-9]{6}" inputMode="numeric" maxLength={6} value={code}
          onChange={event=>setCode(event.target.value)}/>
      </label>)}</>:<>
        <label className="field"><span>New mobile number</span><input type="tel" required maxLength={64}
          autoComplete="tel" value={phone} onChange={event=>setPhone(event.target.value)}/></label>
        <label className="field"><span>Current password</span><input type="password" required maxLength={128}
          autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)}/></label>
      </>}
      <button type="submit" className="outline" disabled={busy}>{destination?'Confirm number change':'Send codes'}</button>
      {destination&&<button type="button" className="textbutton" disabled={busy} onClick={()=>{
        setDestination(null);setOldCode('');setNewCode('');setError('');
      }}>Start again</button>}
    </form>
  </details>;
}
