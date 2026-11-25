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

interface ActivityPage {
  items: {id: number; action: string; created_at: string; unit_id: number; user_id: number; actor_name: string}[];
  has_more: boolean;
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
  const [activity, setActivity] = useState<ActivityPage|null>(null);
  const [activityOffset, setActivityOffset] = useState(0);
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

  async function loadActivity(offset: number) {
    try {
      const page: ActivityPage = await load(`/farms/${farmId}/staff-unit-access/activity?offset=${offset}`);
      setActivity(page);
      setActivityOffset(offset);
    } catch (problem) {
      setError(String(problem));
    }
  }

  async function save(action: () => Promise<unknown>) {
    setBusy(true);setError('');
    try {
      await action();
      await refresh();
      if(activity)await loadActivity(0);
    }
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
      <details onToggle={event=>{
        if(event.currentTarget.open)void loadActivity(0);
      }}>
        <summary>Unit access history</summary>
        {activity?.items.length===0&&<p>No access changes recorded.</p>}
        {activity?.items.map(event=>{
          const assignment=granted.find(row=>row.unit_id===event.unit_id&&row.user_id===event.user_id);
          return <div className="item" key={event.id}>
            <b>{event.action==='grant_unit_view'?'Granted access':'Revoked access'}</b>
            <small>{assignment?.full_name??`Account ${event.user_id}`} · {assignment?.unit_name??`Unit ${event.unit_id}`}</small>
            <small>{event.actor_name} · {new Date(event.created_at).toLocaleString()}</small>
          </div>;
        })}
        <div className="farmactions">
          <button type="button" className="outline" disabled={activityOffset===0}
            onClick={()=>void loadActivity(activityOffset-25)}>Previous</button>
          <button type="button" className="outline" disabled={!activity?.has_more}
            onClick={()=>void loadActivity(activityOffset+25)}>Next</button>
        </div>
      </details>
    </>}
  </section>;
}
