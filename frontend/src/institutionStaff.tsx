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
const emptyForm = {full_name:'',email:'',phone_number:'',department:'',job_title:'',role:'loan_officer'};

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
  const [activationLink,setActivationLink]=useState('');
  const load=useCallback(()=>api(root),[api,root]);
  useEffect(()=>{
    let current=true;
    load().then(result=>{if(current)setData(result)}).catch(problem=>{if(current)setError(String(problem))});
    return ()=>{current=false};
  },[load]);
  async function save(path:string, body:Data, method='POST'){
    setBusy(true);setError('');setStatus('');setActivationLink('');
    try{
      const result=await api(root+path,body,method);
      if(result.invitation_token)setActivationLink(window.location.origin+'/#staff-invitation='+result.invitation_token);
      setStatus(result.delivery==='failed'?'Invitation saved. Email delivery failed. Use Resend after checking SMTP.':
        result.delivery==='not_configured'?'Invitation saved. Email delivery is unavailable. Existing users can respond after signing in.':
        result.delivery?'Invitation is awaiting acceptance.':'Staff access updated.');
      setData(await load());
      return true;
    }catch(problem){setError(String(problem));return false}
    finally{setBusy(false)}
  }
  return <section className="panel">
    <h2>Institution Management</h2>
    <div className="farmactions workspace-tabs" aria-label="Institution management">
      {['Institution Profile','Staff Management','Roles & Permissions','Pending Invitations','Staff Activity Logs'].map(label=>
        <button type="button" key={label} className="outline" aria-pressed={view===label} onClick={()=>setView(label)}>{label}</button>)}
    </div>
    {error&&<p role="alert" className="alert">{error}</p>}
    {status&&<p role="status" className="success">{status}</p>}
    {activationLink&&<p><a href={activationLink} target="_blank" rel="noreferrer">Open local activation link</a> <button className="outline small" onClick={()=>void navigator.clipboard.writeText(activationLink).catch(problem=>setError(String(problem)))}>Copy link</button></p>}
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
        if(await save('/invitations',{...form,phone_number:form.phone_number||null,department:form.department||null,job_title:form.job_title||null})){
          setForm(emptyForm);setShowForm(false);setView('Pending Invitations');
        }
      }}>
        <p className="muted">Invite a new employee or an existing AquaFarm user to {name}.</p>
        {([['full_name','Full Name','text'],['email','Email Address','email'],['phone_number','Phone (international format)','tel'],['department','Department','text'],['job_title','Job title','text']] as const).map(([key,label,type])=>
          <label className="field" key={key}><span>{label}</span><input type={type} required={key==='full_name'||key==='email'} maxLength={key==='email'?255:120} value={form[key]} onChange={event=>setForm({...form,[key]:event.target.value})}/></label>)}
        <label className="field"><span>Staff role</span><select value={form.role} onChange={event=>setForm({...form,role:event.target.value})}>{roleOptions.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <button className="primary" disabled={busy}>Create invitation</button>
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
    {view==='Pending Invitations'&&(data?.invitations.length?data.invitations.map((row:Data)=><div className="item" key={row.id}>
      <b>{row.full_name} · {roleLabel(row.role)}</b><small>{row.email} · {row.status} · Expires {new Date(row.expires_at).toLocaleString()}</small>
      {['pending','expired'].includes(row.status)&&<div className="farmactions">
        <button className="outline small" disabled={busy} onClick={()=>void save('/invitations/'+row.id+'/resend',{})}>Resend invitation</button>
        <button className="outline small" disabled={busy} onClick={()=>void save('/invitations/'+row.id+'/cancel',{})}>Cancel invitation</button>
      </div>}
    </div>):data&&<p className="empty">No invitations.</p>)}
    {view==='Staff Activity Logs'&&(data?.activity.length?data.activity.map((row:Data,index:number)=><div className="item" key={index}><b>{row.action.replace(/_/g,' ')}</b><small>{row.created_at} · User #{row.actor_id}</small><small>{row.details}</small></div>):data&&<p className="empty">No staff activity recorded.</p>)}
    {!data&&!error&&<p role="status">Loading staff information…</p>}
  </section>;
}

export function StaffActivation({api,onSignIn}:{api:Api,onSignIn:(email:string)=>void}){
  const [token,setToken]=useState(()=>new URLSearchParams(window.location.hash.slice(1)).get('staff-invitation')??'');
  const [invite,setInvite]=useState<Data|null>(null);
  const [name,setName]=useState('');
  const [password,setPassword]=useState('');
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  useEffect(()=>{if(token&&window.location.hash.startsWith('#staff-invitation='))window.history.replaceState(null,'',window.location.pathname+window.location.search)},[token]);
  return <section>
    <h2>Accept a staff invitation</h2>
    {error&&<p role="alert" className="alert">{error}</p>}
    <form onSubmit={async event=>{
      event.preventDefault();setBusy(true);setError('');
      try{
        if(!invite){
          const result=await api('/auth/institution/staff-invitations/preview',{token});
          setInvite(result);setName(result.full_name);
        }else{
          await api('/auth/institution/staff-invitations/activate',{token,full_name:name,password});
          onSignIn(invite.email);
        }
      }catch(problem){setError(String(problem))}
      finally{setBusy(false)}
    }}>
      {!invite&&<><label className="field"><span>Invitation token</span><input required minLength={43} maxLength={43} value={token} onChange={event=>setToken(event.target.value)}/></label><button className="outline" disabled={busy}>Review invitation</button></>}
      {invite&&<><p>{invite.institution_name} · {roleLabel(invite.role)} · {invite.email}</p>
        {invite.requires_sign_in?<p>Sign in with the invited email using your existing portal, then open your staff invitations.</p>:<>
          <label className="field"><span>Full Name</span><input required maxLength={120} value={name} onChange={event=>setName(event.target.value)}/></label>
          <label className="field"><span>New password</span><input type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={password} onChange={event=>setPassword(event.target.value)}/></label>
          <button className="primary" disabled={busy}>Activate account and accept</button>
        </>}
      </>}
    </form>
  </section>;
}

export function StaffInvitationInbox({api,refresh}:{api:Api,refresh:()=>Promise<unknown>}){
  const [rows,setRows]=useState<Data[]>([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{
    let current=true;
    api('/auth/institution/staff-invitations').then(items=>{if(current)setRows(items)}).catch(problem=>{if(current)setError(String(problem))});
    return ()=>{current=false};
  },[api]);
  async function respond(id:number,decision:string){
    setBusy(true);setError('');
    try{
      await api('/auth/institution/staff-invitations/'+id+'/respond',{decision});
      setRows(previous=>previous.filter(row=>row.id!==id));await refresh();
    }catch(problem){setError(String(problem))}
    finally{setBusy(false)}
  }
  if(!rows.length&&!error)return null;
  return <section className="panel"><h2>Staff invitations</h2>
    {error&&<p role="alert">{error}</p>}
    {rows.map(row=><div className="item" key={row.id}><b>{row.institution_name} · {roleLabel(row.role)}</b><div className="farmactions">
      <button className="outline" disabled={busy} onClick={()=>void respond(row.id,'accept')}>Accept</button>
      <button className="outline" disabled={busy} onClick={()=>void respond(row.id,'decline')}>Decline</button>
    </div></div>)}
  </section>;
}
