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
