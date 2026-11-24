import {useEffect, useState} from 'react';

interface Administrator {
  id: number;
  full_name: string;
  email: string;
  phone_number: string | null;
  created_at: string;
  role: string;
}

interface DirectoryPage {
  total: number;
  items: Administrator[];
}

const pageSize = 25;

export function AdministratorDirectory({load}: {load: (path: string) => Promise<DirectoryPage>}) {
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<DirectoryPage | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({search, offset: String(offset), limit: String(pageSize)});
    load('/admin/administrators?' + params).then(page => {
      if (active) setResult(page);
    }).catch(problem => {
      if (active) setError(String(problem));
    });
    return () => {active = false};
  }, [load, search, offset]);

  function goTo(nextOffset: number) {
    if (nextOffset === offset) return;
    setError('');
    setResult(null);
    setOffset(nextOffset);
  }

  return <section className="panel">
    <h2>Manage administrators</h2>
    <form className="farmactions" onSubmit={event => {
      event.preventDefault();
      if (query.trim() === search && offset === 0) return;
      setError('');
      setResult(null);
      setOffset(0);
      setSearch(query.trim());
    }}>
      <label className="field"><span>Name or email</span>
        <input type="search" value={query} maxLength={255} onChange={event => setQuery(event.target.value)}/>
      </label>
      <button type="submit" className="outline">Search</button>
    </form>
    {error ? <p role="alert">{error}</p> : !result ? <p role="status">Loading administrators…</p> :
      result.items.length === 0 ? <p>No matching administrators.</p> : <>
        <div className="tablewrap"><table>
          <thead><tr><th>Name</th><th>Role</th><th>Email</th><th>Phone</th><th>Created</th></tr></thead>
          <tbody>{result.items.map(row => <tr key={row.id}>
            <td>{row.full_name}</td><td>{row.role}</td><td>{row.email}</td>
            <td>{row.phone_number ?? '—'}</td><td>{new Date(row.created_at).toLocaleDateString()}</td>
          </tr>)}</tbody>
        </table></div>
        <div className="farmactions">
          <button type="button" className="outline" disabled={offset === 0} onClick={() => goTo(offset - pageSize)}>Previous</button>
          <button type="button" className="outline" disabled={offset + pageSize >= result.total} onClick={() => goTo(offset + pageSize)}>Next</button>
        </div>
      </>}
  </section>;
}
