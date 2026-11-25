import {useState} from 'react';

export function AdministratorAuthenticator({phone, enrolled, send}: {
  phone: string | null;
  enrolled: boolean;
  send: (password: string) => Promise<{message: string}>;
}) {
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  if (enrolled) return <p>Authenticator enabled.</p>;
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
