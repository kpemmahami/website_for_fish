import {useCallback, useEffect, useState} from 'react';

interface Assignment {
  user_id: number;
  full_name: string;
  email: string;
  unit_id: number;
  unit_name: string;
  is_active: boolean;
}

interface AssignedUnit {
  farm_id: number;
  farm_name: string;
  unit_id: number;
  unit_name: string;
  unit_type: string;
}

export function FarmStaffAccess({farmId, units, load, grant, revoke}: {
  farmId: number | null;
  units: {id: number; name: string}[];
  load: (path: string) => Promise<any>;
  grant: (path: string, email: string) => Promise<unknown>;
  revoke: (path: string) => Promise<unknown>;
}) {
  const [assigned, setAssigned] = useState<AssignedUnit[]>([]);
  const [granted, setGranted] = useState<Assignment[]>([]);
  const [unit, setUnit] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    const [mine, access] = await Promise.all([
      load('/staff/assigned-units'),
      farmId ? load(`/farms/${farmId}/staff-unit-access`) : [],
    ]);
    setAssigned(mine);
    setGranted(access);
  }, [load, farmId]);

  useEffect(() => {
    void refresh().catch(problem => setError(String(problem)));
  }, [refresh]);

  async function save(action: () => Promise<unknown>) {
    setBusy(true);setError('');
    try {await action();await refresh()}
    catch (problem) {setError(String(problem))}
    finally {setBusy(false)}
  }

  return <section className="panel">
    <h2>Production unit access</h2>
    {error&&<p role="alert" className="alert">{error}</p>}
    <h3>Units assigned to me</h3>
    {assigned.length===0?<p>No production units assigned.</p>:assigned.map(row=><div className="item" key={row.unit_id}>
      <b>{row.unit_name}</b><small>{row.farm_name} · {row.unit_type} · Read-only</small>
    </div>)}
    {farmId&&<>
      <h3>Manage unit access</h3>
      <form className="farmform" onSubmit={event=>{
        event.preventDefault();
        void save(async()=>{
          await grant(`/farms/${farmId}/units/${unit}/staff-access`,email);
          setEmail('');
        });
      }}>
        <label className="field"><span>Existing farmer account email</span>
          <input type="email" required value={email} onChange={event=>setEmail(event.target.value)}/>
        </label>
        <label className="field"><span>Production unit</span>
          <select required value={unit} onChange={event=>setUnit(event.target.value)}>
            <option value="">Select a unit</option>
            {units.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}
          </select>
        </label>
        <button type="submit" className="primary" disabled={busy||units.length===0}>Grant read access</button>
      </form>
      {granted.filter(row=>row.is_active).map(row=><div className="item" key={`${row.unit_id}:${row.user_id}`}>
        <b>{row.full_name} · {row.unit_name}</b><small>{row.email}</small>
        <button type="button" className="outline small" disabled={busy} onClick={()=>{
          if(window.confirm(`Revoke ${row.full_name}’s access to ${row.unit_name}?`)){
            void save(()=>revoke(`/farms/${farmId}/units/${row.unit_id}/staff-access/${row.user_id}`));
          }
        }}>Revoke access</button>
      </div>)}
    </>}
  </section>;
}
