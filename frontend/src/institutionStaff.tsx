import {useCallback, useEffect, useState} from 'react';

type Data = Record<string, any>;
type Api = (path:string, body?:Data, method?:string) => Promise<any>;
const roles: Record<string,string> = {
  owner:'Institution Administrator', loan_officer:'Loan Officer', credit_manager:'Credit Manager',
  disbursement:'Disbursement Officer', collections:'Collections Officer', viewer:'Institution Viewer',
  officer:'Officer (legacy)', reviewer:'Reviewer (legacy)',
};
const roleLabel = (value:string) => roles[value] ?? value;
const roleOptions = Object.entries(roles).filter(([key])=>key!=='owner');
const emptyForm = {full_name:'',email:'',phone_number:'',department:'',job_title:'',role:'loan_officer',password:''};

export function InstitutionStaff({id, name, api}:{id:number,name:string,api:Api}) {
  const root='/finance/institutions/'+id+'/staff';
  const [view,setView]=useState('Staff Management');
  const [data,setData]=useState<Data|null>(null);
  const [form,setForm]=useState(emptyForm);
  const [showForm,setShowForm]=useState(false);
  const [search,setSearch]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [status,setStatus]=useState('');
  const load=useCallback(()=>api(root),[api,root]);
  useEffect(()=>{
    let current=true;
    load().then(result=>{if(current)setData(result)}).catch(problem=>{if(current)setError(String(problem))});
    return ()=>{current=false};
  },[load]);
  async function save(path:string, body:Data, method='POST'){
    setBusy(true);setError('');setStatus('');
    try{
      await api(root+path,body,method);
      setStatus(method==='POST'?'Staff account created. The employee can now sign in.':'Staff access updated.');
      try{setData(await load())}catch(problem){setError(String(problem))}
      return true;
    }catch(problem){setError(String(problem));return false}
    finally{setBusy(false)}
  }
  return <section className="panel">
    <h2>Institution Management</h2>
    <div className="farmactions workspace-tabs" aria-label="Institution management">
      {['Institution Profile','Staff Management','Roles & Permissions','Staff Activity Logs'].map(label=>
        <button type="button" key={label} className="outline" aria-pressed={view===label} onClick={()=>setView(label)}>{label}</button>)}
    </div>
    {error&&<p role="alert" className="alert">{error}</p>}
    {status&&<p role="status" className="success">{status}</p>}
    {view==='Institution Profile'&&<p>{name}</p>}
    {view==='Roles & Permissions'&&<dl>
      <dt>Institution Administrator</dt><dd>Manage staff and institution lending.</dd>
      <dt>Loan Officer</dt><dd>Review applications and request more information.</dd>
      <dt>Credit Manager</dt><dd>Make lending decisions and prepare offers.</dd>
      <dt>Disbursement Officer</dt><dd>Record disbursements.</dd>
      <dt>Collections Officer</dt><dd>Record repayments.</dd>
      <dt>Institution Viewer</dt><dd>View institution lending records.</dd>
    </dl>}
    {view==='Staff Management'&&<>
      <button className="primary" onClick={()=>setShowForm(!showForm)}>{showForm?'Close form':'Add Staff'}</button>
      {showForm&&<form className="farmform" onSubmit={async event=>{
        event.preventDefault();
        if(await save('',{...form,department:form.department||null,job_title:form.job_title||null})){
          setForm(emptyForm);setShowForm(false);
        }
      }}>
        <p className="muted">Create a sign-in account for a new employee at {name}. Share their initial sign-in details privately.</p>
        {([['full_name','Full Name','text'],['email','Email Address','email'],['phone_number','Phone (international format)','tel'],['department','Department','text'],['job_title','Job title','text']] as const).map(([key,label,type])=>
          <label className="field" key={key}><span>{label}</span><input type={type} required={key==='full_name'||key==='email'||key==='phone_number'} maxLength={key==='email'?255:120} value={form[key]} onChange={event=>setForm({...form,[key]:event.target.value})}/></label>)}
        <label className="field"><span>Staff role</span><select value={form.role} onChange={event=>setForm({...form,role:event.target.value})}>{roleOptions.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label className="field"><span>Initial password</span><input type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={form.password} onChange={event=>setForm({...form,password:event.target.value})}/></label>
        <button className="primary" disabled={busy}>Create staff account</button>
      </form>}
      <label className="field"><span>Search staff</span><input type="search" value={search} onChange={event=>setSearch(event.target.value)}/></label>
      {data?.staff.filter((row:Data)=>(row.full_name+' '+row.email+' '+row.status).toLowerCase().includes(search.trim().toLowerCase())).map((row:Data)=><div className="item" key={row.user_id}>
        <b>{row.full_name} · {roleLabel(row.role)}</b><small>{row.email} · {row.status} · Added {row.created_at.slice(0,10)}</small>
        {(row.phone_number||row.department||row.job_title)&&<small>{[row.phone_number,row.department,row.job_title].filter(Boolean).join(' · ')}</small>}
        {row.role!=='owner'&&<div className="farmactions">
          <label className="field"><span>Edit role for {row.full_name}</span><select value={row.role} disabled={busy} onChange={event=>void save('/'+row.user_id,{role:event.target.value},'PATCH')}>{roleOptions.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
          {row.status==='active'&&<button className="outline small" disabled={busy} onClick={()=>void save('/'+row.user_id,{status:'suspended'},'PATCH')}>Suspend</button>}
          {row.status==='suspended'&&<button className="outline small" disabled={busy} onClick={()=>void save('/'+row.user_id,{status:'active'},'PATCH')}>Reactivate</button>}
          {row.status!=='removed'&&<button className="outline small" disabled={busy} onClick={()=>{if(window.confirm('Remove access for '+row.full_name+'?'))void save('/'+row.user_id,{status:'removed'},'PATCH')}}>Remove access</button>}
        </div>}
      </div>)}
    </>}
    {view==='Staff Activity Logs'&&(data?.activity.length?data.activity.map((row:Data,index:number)=><div className="item" key={index}><b>{row.action.replace(/_/g,' ')}</b><small>{row.created_at} · User #{row.actor_id}</small><small>{row.details}</small></div>):data&&<p className="empty">No staff activity recorded.</p>)}
    {!data&&!error&&<p role="status">Loading staff information…</p>}
  </section>;
}
