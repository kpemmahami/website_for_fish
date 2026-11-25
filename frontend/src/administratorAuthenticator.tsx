import {useState} from 'react';

export function AdministratorAuthenticator({phone, enrolled, send, generateCodes}: {
  phone: string | null;
  enrolled: boolean;
  send: (password: string) => Promise<{message: string}>;
  generateCodes: (password: string, authenticator_code: string) => Promise<{codes: string[]}>;
}) {
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [authenticatorCode, setAuthenticatorCode] = useState('');
  const [codes, setCodes] = useState<string[]>([]);

  if (enrolled) return <details onToggle={event=>{if(!event.currentTarget.open)setCodes([])}}>
    <summary>Administrator recovery codes</summary>
    <p>Save these codes privately. Each code can be used once with your password. Generating a set replaces any previous codes.</p>
    {error&&<p className="alert" role="alert">{error}</p>}
    {codes.length>0?<pre>{codes.join('\n')}</pre>:<form onSubmit={async event=>{
      event.preventDefault();setError('');setBusy(true);
      try {setCodes((await generateCodes(password, authenticatorCode)).codes)}
      catch (problem) {setError(String(problem))}
      finally {setPassword('');setAuthenticatorCode('');setBusy(false)}
    }}>
      <label className="field"><span>Current password</span>
        <input type="password" required autoComplete="current-password" maxLength={128}
          value={password} onChange={event=>setPassword(event.target.value)}/>
      </label>
      <label className="field"><span>Authenticator code</span>
        <input required pattern="[0-9]{6}" maxLength={6} inputMode="numeric" autoComplete="one-time-code"
          value={authenticatorCode} onChange={event=>setAuthenticatorCode(event.target.value)}/>
      </label>
      <button type="submit" className="outline" disabled={busy}>Generate recovery codes</button>
    </form>}
  </details>;
  if (!phone) return <p>A saved mobile number is required for authenticator setup.</p>;
  return <details>
    <summary>Set up administrator authenticator</summary>
    <p>We’ll send a link to your account email and a code to your saved mobile number.</p>
    {error&&<p className="alert" role="alert">{error}</p>}
    {notice&&<p className="success" role="status">{notice}</p>}
    <form onSubmit={async event=>{
      event.preventDefault();setError('');setNotice('');setBusy(true);
      try {setNotice((await send(password)).message)}
      catch (problem) {setError(String(problem))}
      finally {setPassword('');setBusy(false)}
    }}>
      <label className="field"><span>Current password</span>
        <input type="password" required autoComplete="current-password" maxLength={128}
          value={password} onChange={event=>setPassword(event.target.value)}/>
      </label>
      <button type="submit" className="outline" disabled={busy}>Send setup instructions</button>
    </form>
  </details>;
}
