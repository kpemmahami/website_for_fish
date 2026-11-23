
import {useEffect,useState} from 'react';
import {ErrorNotice} from './apiErrors';

type Row=Record<string,any>;
export const historyTabs=[
 ['all','All Activities'],['feeding','Feeding History'],['water_quality','Water Quality History'],
 ['growth','Fish Sampling History'],['mortality','Mortality History'],['water_exchange','Water Exchange History'],
 ['stocking','Stocking History'],['harvest','Harvest History'],['evidence','Evidence Library'],
] as const;
export type HistoryTab=typeof historyTabs[number][0];
export type HistoryContext={tab:HistoryTab,unit?:number,cycle?:number};
type Period={start:string,end:string};
type Filters={unit_ids:number[],cycle_id:number|null,actor_id:number|null,status:string|null,activity:string|null,periods:Period[],order:string};
type Props={farmId:number,context:HistoryContext,load:(path:string,data?:Row,method?:string)=>Promise<any>,
 api:(path:string,init?:RequestInit)=>Promise<Response>,
 change:(context:HistoryContext)=>void,revision:unknown};
const title=(value:string)=>value.replaceAll('_',' ').replace(/^./,letter=>letter.toUpperCase());
const extraActivities=['feed_delivery','feed_stock_count','fish_transfer','treatment','inspection','sale_dispatch'];
const dates=['Today','Yesterday','Last 7 days','Last 14 days','Last 30 days','This month','Last month','This quarter','This year','Custom'];
const day=(value:Date)=>value.toISOString().slice(0,10);
const offset=(date:Date,days:number)=>new Date(date.getTime()+days*86400000);
const ghanaTime=(value?:string)=>value?new Intl.DateTimeFormat('en-GH',{timeZone:'Africa/Accra',dateStyle:'medium',timeStyle:'short'}).format(new Date(
 /(?:Z|[+-]\d{2}:\d{2})$/.test(value)?value:value.replace(' ','T')+'Z')):'Unavailable';
function preset(name:string):Period{
 const now=new Date(), year=now.getUTCFullYear(), month=now.getUTCMonth();
 const at=(y:number,m:number,d:number)=>new Date(Date.UTC(y,m,d));
 const today=day(now);
 if(name==='Yesterday')return {start:day(offset(now,-1)),end:day(offset(now,-1))};
 if(name.startsWith('Last ')&&name.endsWith(' days'))return {start:day(offset(now,1-Number(name.split(' ')[1]))),end:today};
 if(name==='This month')return {start:day(at(year,month,1)),end:today};
 if(name==='Last month')return {start:day(at(year,month-1,1)),end:day(at(year,month,0))};
 if(name==='This quarter')return {start:day(at(year,Math.floor(month/3)*3,1)),end:today};
 if(name==='This year')return {start:day(at(year,0,1)),end:today};
 return {start:today,end:today};
}
function saveBlob(blob:Blob,name:string){
 const url=URL.createObjectURL(blob);
 const link=document.createElement('a');link.href=url;link.download=name;link.click();
 window.setTimeout(()=>URL.revokeObjectURL(url),30_000);
}
function short(row:Row){
 const data=row.details;
 if(row.kind==='feeding')return [
  data.session_number?'Session '+data.session_number:'Unscheduled',
  data.feed, data.actual_kg+' kg',data.indicative_cost_ghs==null?'Cost unavailable':'GHS '+data.indicative_cost_ghs.toFixed(2),
 ].filter(Boolean).join(' ? ');
 if(row.kind==='evidence')return title(data.record_type)+' ? '+(data.record_id?'Record #'+data.record_id:'Unlinked')+
  ' ? '+data.media_type+' ? '+Math.round(data.size_bytes/1024)+' KB'+(data.duration_seconds?' ? '+data.duration_seconds+' s':'')+
  ' ? GPS '+(data.geofence_status??'Unavailable');
 if(row.kind==='stocking')return data.species+' ? '+data.stocked_count+' fish ? '+(data.closed_at?'Closed':'Active');
 if(row.kind==='growth')return data.sample_count+' fish sampled ? '+data.average_weight_g+' g average';
 if(row.kind==='mortality')return data.dead_count+' fish lost'+(data.cause?' ? '+data.cause:'');
 if(row.kind==='feed_delivery'||row.kind==='feed_stock_count')return data.feed+' ? '+data.quantity_change_kg+' kg';
 if(row.kind==='fish_transfer')return data.fish_count+' fish moved to cycle #'+data.target_cycle_id;
 if(row.kind==='treatment')return data.product+' ? '+data.dose+' '+data.dose_unit;
 if(row.kind==='inspection')return data.observations;
 if(row.kind==='sale_dispatch')return data.dispatched_kg+' kg dispatched';
 if(row.kind==='harvest')return data.harvested_kg+' kg'+(data.fish_count==null?'':' ? '+data.fish_count+' fish');
 return ['temperature_c','dissolved_oxygen_mg_l','ph'].map((key,index)=>data[key]==null?null:[ 'Temperature ','O? ','pH '][index]+data[key]+[' ?C',' mg/L',''][index]).filter(Boolean).join(' ? ')||'Water quality measurements';
}
function initial(context:HistoryContext):Filters{
 return {unit_ids:context.unit?[context.unit]:[],cycle_id:context.cycle??null,actor_id:null,status:null,
         activity:null,periods:[preset('Last 30 days')],order:'newest'};
}

function ComplianceHistory({path,load,end}:{path:string,load:Props['load'],end:string}){
 const [days,setDays]=useState(7);
 const [summary,setSummary]=useState<Row|null>(null);
 const [error,setError]=useState('');
 async function fetchCompliance(){
  setSummary(null);setError('');
  try{setSummary(await load(path+'/history?'+new URLSearchParams({end,days:String(days)})))}
  catch{setError('Unable to load feeding compliance for the selected period.')}
 }
 return <details className="activity-controls">
  <summary>Feeding compliance history</summary>
  <label className="field"><span>Period ending {end}</span><select value={days} onChange={event=>{setDays(Number(event.target.value));setSummary(null)}}>
   <option value={1}>Selected day</option><option value={7}>Last 7 days</option><option value={31}>Last 31 days</option>
  </select></label>
  <button type="button" className="outline small" onClick={()=>void fetchCompliance()}>Load compliance</button>
  {error&&<p role="alert">{error}</p>}
  {summary&&<>
   <p>{summary.recorded_count} of {summary.scheduled_count} completed ? {summary.missed_count} overdue ? {summary.skipped_count} skipped</p>
   {summary.days.map((row:Row)=><details key={row.date}><summary>{row.date} ? {row.actual_kg} kg actual{row.daily_ration_kg!=null?' ? '+row.daily_ration_kg+' kg recommended':''}</summary>
    {row.sessions.map((session:Row)=><p key={session.number}>Session {session.number}{session.name?' ? '+session.name:''} ? {session.status==='recorded'?'Completed':session.status==='missed'?'Overdue':title(session.status)}
     {session.scheduled_time?' ? '+session.scheduled_time+(session.scheduled_end?'?'+session.scheduled_end:''):''} ? {session.actual_kg} kg</p>)}
    {!!row.unassigned_entries.length&&<p>Unscheduled events: {row.unassigned_entries.length}</p>}
   </details>)}
  </>}
 </details>;
}

export function FarmActivityHistory({farmId,context,load,api,change,revision}:Props){
 const root='/farms/'+farmId+'/activity-history';
 const [options,setOptions]=useState<Row|null>(null);
 const [draft,setDraft]=useState(()=>initial(context));
 const [filters,setFilters]=useState(draft);
 const [periodMode,setPeriodMode]=useState('Last 30 days');
 const [periodKind,setPeriodKind]=useState('week');
 const [periodText,setPeriodText]=useState('');
 const [page,setPage]=useState(1);
 const [result,setResult]=useState<Row|null>(null);
 const [record,setRecord]=useState<Row|null>(null);
 const [media,setMedia]=useState<{url:string,type:string}|null>(null);
 const [error,setError]=useState('');
 const [actionError,setActionError]=useState('');
 const [reload,setReload]=useState(0);
 const [busy,setBusy]=useState(false);
 const [printing,setPrinting]=useState(false);
 useEffect(()=>()=>{if(media)URL.revokeObjectURL(media.url)},[media]);
 useEffect(()=>{
  let current=true;
  void load(root+'/options').then(data=>{if(current)setOptions(data)}).catch(()=>{if(current)setError('Unable to load activity history filters.')});
  return ()=>{current=false};
 },[root,load,revision,reload]);
 useEffect(()=>{
  let current=true;setResult(null);setError('');
  void load(root,{...filters,kind:context.tab,page}).then(data=>{if(current)setResult(data)})
   .catch(()=>{if(current)setError(context.tab==='feeding'?'Unable to load feeding history.':'Unable to load farm activity history.')});
  return ()=>{current=false};
 },[root,filters,context.tab,page,revision,load,reload]);
 const apply=(values:Filters)=>{setFilters(values);setPage(1);setRecord(null);setActionError('')};
 const label=historyTabs.find(([key])=>key===context.tab)?.[1];
 const complianceCycle=options?.cycles?.find((row:Row)=>row.id===filters.cycle_id);
 const complianceEnd=filters.periods.reduce((latest,period)=>period.end>latest?period.end:latest,'')||day(new Date());

 const selectTab=(tab:HistoryTab)=>{
  setRecord(null);setMedia(null);setPage(1);setActionError('');
  const values={...draft,status:null,activity:null};
  setDraft(values);setFilters({...filters,status:null,activity:null});change({...context,tab});
 };
 async function run(task:()=>Promise<void>,fallback:string){
  setBusy(true);setActionError('');
  try{await task()}catch(problem){setActionError(fallback||String(problem))}
  finally{setBusy(false)}
 }
 function open(row:Row){
  setMedia(null);
  void run(async()=>setRecord(await load(root+'/record/'+row.kind+'/'+row.id)),'Unable to load this activity record.');
 }
 function mediaPath(id:number){return '/farms/'+farmId+'/evidence/'+id+'/video'}
 function evidenceActions(item:Row){
  const ext=({'video/webm':'webm','video/mp4':'mp4','image/png':'png','image/jpeg':'jpg','image/webp':'webp'} as Record<string,string>)[item.media_type]??'bin';
  return <div className="farmactions">
   {!!item.record_id&&<span className="pill">Record locked</span>}
   {item.archived_at?<small>Archived</small>:<>
    <button type="button" className="outline small" disabled={busy} onClick={()=>void run(async()=>{
     const response=await api(mediaPath(item.id));
     setMedia({url:URL.createObjectURL(await response.blob()),type:item.media_type});
    },'Evidence unavailable.')}>Preview</button>
    <button type="button" className="outline small" disabled={busy} onClick={()=>void run(async()=>{
     const response=await api(mediaPath(item.id));
     saveBlob(await response.blob(),'aquafarm-evidence-'+item.id+'.'+ext);
    },'Unable to download evidence.')}>Download</button>
    {!item.record_id&&<button className="outline danger small" disabled={busy} onClick={()=>{
     if(!window.confirm('Archive this unlinked evidence?'))return;
     void run(async()=>{await api('/farms/'+farmId+'/evidence/'+item.id,{method:'DELETE'});setRecord(null);setMedia(null);setReload(value=>value+1)},'Unable to archive evidence.');
    }}>Archive unlinked evidence</button>}
   </>}
   {record?.kind==='evidence'&&!!item.record_id&&(historyTabs.some(([key])=>key===item.record_type)||extraActivities.includes(item.record_type))&&
    <button type="button" className="outline small" disabled={busy} onClick={()=>open({kind:item.record_type,id:item.record_id})}>Open related record</button>}
  </div>;
 }
 function addPeriod(){
  if(!periodText||draft.periods.length>=24)return;
  const date=new Date(periodText+(periodKind==='month'?'-01T00:00:00Z':periodKind==='year'?'-01-01T00:00:00Z':'T00:00:00Z'));
  if(!Number.isFinite(date.getTime()))return;
  const start=periodKind==='week'?offset(date,-((date.getUTCDay()+6)%7)):date;
  const end=periodKind==='week'?offset(start,6):periodKind==='month'?new Date(Date.UTC(start.getUTCFullYear(),start.getUTCMonth()+1,0)):new Date(Date.UTC(start.getUTCFullYear(),11,31));
  const next={start:day(start),end:day(end)};
  setDraft({...draft,periods:periodMode==='Multiple periods'?[...draft.periods,next]:[next]});setPeriodMode('Multiple periods');setPeriodText('');
 }
 function exportFile(format:'csv'|'pdf'){
  void run(async()=>{
   const response=await api(root+'/export/'+format,{method:'POST',body:JSON.stringify({...filters,kind:context.tab})});
   saveBlob(await response.blob(),'farm-activity.'+format);
  },'');
 }
 function print(){
  setPrinting(true);
  window.requestAnimationFrame(()=>{try{window.print()}finally{setPrinting(false)}});
 }
 return <section className={'panel farm-activity-history'+(printing?' activity-print':'')}>
  <div className="activity-controls">
   <p>{options?.farm_name??'Selected farm'} ? Africa/Accra</p>
   <div className="farmactions" aria-label="Activity history views">{historyTabs.map(([key,name])=><button type="button" key={key}
    className={context.tab===key?'primary small':'outline small'} aria-pressed={context.tab===key} onClick={()=>selectTab(key)}>{name}</button>)}</div>
   {!record&&<details open className="report-filters"><summary>History filters</summary>
    <form className="farmform" onSubmit={event=>{event.preventDefault();apply(draft)}}>
     <fieldset className="feeding-window"><legend>Production units</legend>
      <p className="muted">Leave all unchecked to include every unit.</p>
      {(options?.units??[]).map((row:Row)=><label className="consent" key={row.id}><input type="checkbox" checked={draft.unit_ids.includes(row.id)}
       onChange={event=>setDraft({...draft,cycle_id:null,unit_ids:event.target.checked?[...draft.unit_ids,row.id]:draft.unit_ids.filter(id=>id!==row.id)})}/>{row.name}</label>)}
     </fieldset>
     <label className="field"><span>Stocking cycle</span><select value={draft.cycle_id??''} onChange={event=>setDraft({...draft,cycle_id:Number(event.target.value)||null})}>
      <option value="">All cycles</option>{(options?.cycles??[]).filter((row:Row)=>!draft.unit_ids.length||draft.unit_ids.includes(row.unit_id)).map((row:Row)=>
       <option key={row.id} value={row.id}>#{row.id} ? {row.species} ? {row.stocked_on}</option>)}
     </select></label>
     {(context.tab==='all'||context.tab==='evidence')&&<label className="field"><span>Activity type</span><select value={draft.activity??''} onChange={event=>setDraft({...draft,activity:event.target.value||null})}>
      <option value="">All types</option>{historyTabs.slice(1,-1).filter(([key])=>key!=='water_exchange').map(([key])=><option key={key} value={key}>{title(key)}</option>)}
      {extraActivities.map(key=><option key={key} value={key}>{title(key)}</option>)}
     </select></label>}
     <label className="field"><span>Record status</span><select value={draft.status??''} onChange={event=>setDraft({...draft,status:event.target.value||null})}>
      <option value="">All statuses</option>{(context.tab==='evidence'?['verified','pending','flagged','archived','locked','unlinked']:
       ['recorded','verified','pending','flagged','missing','archived',...(context.tab==='feeding'||context.tab==='all'?['scheduled','unscheduled']:[]),
        ...(context.tab==='stocking'||context.tab==='all'?['active','closed']:[])]).map(key=><option key={key} value={key}>{title(key)}</option>)}
     </select></label>
     <label className="field"><span>Staff member</span><select value={draft.actor_id??''} onChange={event=>setDraft({...draft,actor_id:Number(event.target.value)||null})}>
      <option value="">All staff</option>{(options?.staff??[]).map((row:Row)=><option key={row.id} value={row.id}>{row.full_name}</option>)}
     </select></label>
     <label className="field"><span>Date range</span><select value={periodMode} onChange={event=>{
      const mode=event.target.value;setPeriodMode(mode);
      setDraft({...draft,periods:mode==='All dates'||mode==='Multiple periods'?[]:[preset(mode)]});
     }}>{[...dates,'Multiple periods','All dates'].map(value=><option key={value}>{value}</option>)}</select></label>
     {periodMode==='Custom'&&(['start','end'] as const).map(key=><label key={key} className="field"><span>{title(key)} date</span><input required type="date"
      value={draft.periods[0]?.[key]??''} onChange={event=>setDraft({...draft,periods:[{...draft.periods[0],[key]:event.target.value}]})}/></label>)}
     {periodMode==='Multiple periods'&&<>
      <label className="field"><span>Period type</span><select value={periodKind} onChange={event=>{setPeriodKind(event.target.value);setPeriodText('')}}>
       <option value="week">Week containing date</option><option value="month">Month</option><option value="year">Year</option>
      </select></label>
      <label className="field"><span>Choose period</span><input type={periodKind==='year'?'number':periodKind==='month'?'month':'date'}
       min={periodKind==='year'?1900:undefined} max={periodKind==='year'?2200:undefined} value={periodText} onChange={event=>setPeriodText(event.target.value)}/></label>
      <button type="button" className="outline" onClick={addPeriod}>Add period</button>
      <div className="farmactions">{draft.periods.map((period,index)=><button type="button" className="outline small" key={index}
       onClick={()=>setDraft({...draft,periods:draft.periods.filter((_,i)=>i!==index)})}>{period.start} to {period.end} ? Remove</button>)}</div>
     </>}
     <label className="field"><span>Sort</span><select value={draft.order} onChange={event=>setDraft({...draft,order:event.target.value})}>
      <option value="newest">Newest first</option><option value="oldest">Oldest first</option>
     </select></label>
     <div className="farmactions"><button className="primary">Apply filters</button><button type="button" className="outline" onClick={()=>{
      const defaults=initial(context);setDraft(defaults);setPeriodMode('Last 30 days');apply(defaults);
     }}>Reset filters</button></div>
    </form>
   </details>}
  </div>
  {error&&<ErrorNotice message={error} retry={()=>setReload(value=>value+1)}/>}
  {actionError&&<p className="alert" role="alert">{actionError}</p>}
  {record?<article>
   <button className="outline activity-controls" onClick={()=>{setRecord(null);setMedia(null);setActionError('')}}>Back to History</button>
   <h2>{title(record.kind)} #{record.id} ? {record.unit_name}</h2>
   <p>{record.day}{record.cycle_id?' ? Cycle #'+record.cycle_id:''} ? {record.actor_name??'Recorder unavailable'}</p>
   <dl className="activity-detail-grid">{Object.entries(record.details).filter(([key,value])=>value!=null&&key!=='id').map(([key,value])=>
    <div key={key}><dt>{title(key)}</dt><dd>{key.endsWith('_at')?ghanaTime(String(value)):String(value)}</dd></div>)}</dl>
   {record.kind==='evidence'?evidenceActions(record.details):<>
    <h3>Related evidence</h3>
    {record.evidence.length?record.evidence.map((item:Row)=><div className="item" key={item.id}><b>Evidence #{item.id} ? {title(item.verification_status)}</b>
     {item.verification_notes&&<p>{item.verification_notes}</p>}{evidenceActions(item)}</div>):<p>No linked evidence.</p>}
   </>}
   {media&&<div className="item">
    {media.type.startsWith('image/')?<img className="activity-media" src={media.url} alt="Farm activity evidence"/>:<video className="activity-media" controls src={media.url}/>}
    <button className="outline small" onClick={()=>setMedia(null)}>Close preview</button>
   </div>}
   {!!record.audit.length&&<details><summary>Audit history</summary>{record.audit.map((entry:Row,index:number)=><p key={index}>{ghanaTime(entry.created_at)} ? {title(entry.action)} ? {entry.full_name}</p>)}</details>}
  </article>:<>
   <h2>{label}</h2>
   <p>{options?.farm_name} ? {filters.periods.length?filters.periods.map(period=>period.start+' to '+period.end).join(', '):'All dates'}
   {filters.unit_ids.length?' ? '+options?.units?.filter((row:Row)=>filters.unit_ids.includes(row.id)).map((row:Row)=>row.name).join(', '):' ? All units'}
   {filters.cycle_id?' ? Cycle #'+filters.cycle_id:''}{filters.status?' ? '+title(filters.status):''}
   {filters.activity?' ? '+title(filters.activity):''}{filters.actor_id?' ? '+options?.staff?.find((row:Row)=>row.id===filters.actor_id)?.full_name:''}</p>
   {context.tab==='feeding'&&<>
    <p className="muted">Indicative cost uses the quantity in each event and the feed?s purchase-weighted average cost.</p>
    {complianceCycle?<ComplianceHistory key={complianceCycle.id+'-'+complianceEnd}
     path={'/farms/'+farmId+'/units/'+complianceCycle.unit_id+'/cycles/'+complianceCycle.id+'/feeding-sessions'} load={load} end={complianceEnd}/>:
     <p className="muted">Select a stocking cycle to view scheduled feeding compliance.</p>}
   </>}
   {!result&&!error&&<p role="status">Loading history?</p>}
   {result&&<>
    <div className="farmactions activity-controls">
     <button className="outline small" disabled={busy} onClick={()=>exportFile('csv')}>Export CSV</button>
     <button className="outline small" disabled={busy} onClick={()=>exportFile('pdf')}>Download PDF</button>
     <button className="outline small" onClick={print}>Print page</button>
    </div>
    {!result.items.length?<p>{context.tab==='feeding'?'No feeding records found for this period.':context.tab==='water_exchange'?'No water exchange records are available.':'No matching records.'}</p>:
    <div className="tablewrap"><table><thead><tr><th>Date and time</th><th>Activity</th><th>Unit / cycle</th><th>Record summary</th><th>Recorded by</th><th>Evidence</th><th className="activity-controls">Open</th></tr></thead><tbody>
     {result.items.map((row:Row)=><tr key={row.kind+row.id}>
      <td>{row.kind==='evidence'||row.kind==='water_quality'||row.details.actual_fed_at?ghanaTime(row.stamp):row.day}</td>
      <td>{row.kind==='evidence'?title(row.details.record_type):title(row.kind)} #{row.id}</td>
      <td>{row.unit_name}{row.cycle_id?' / #'+row.cycle_id:''}</td><td>{short(row)}</td><td>{row.actor_name??'Unavailable'}</td>
      <td>{row.kind==='evidence'?title(row.details.verification_status)+(row.details.record_id?' ? Locked':''):title(row.evidence_status??'missing')}</td>
      <td className="activity-controls"><button className="outline small" disabled={busy} onClick={()=>open(row)}>View record</button></td>
     </tr>)}
    </tbody></table></div>}
    {!!result.daily_totals.length&&<details><summary>Daily totals for dates on this page</summary>{result.daily_totals.map((row:Row)=>
     <p key={row.day}>{row.day} ? {Number(row.actual_kg.toFixed(6))} kg</p>)}</details>}
    <div className="farmactions activity-controls"><button className="outline small" disabled={page<=1} onClick={()=>setPage(page-1)}>Previous</button>
     <span>{result.total} matching records ? Page {page} of {Math.max(1,Math.ceil(result.total/result.size))}</span>
     <button className="outline small" disabled={page*result.size>=result.total} onClick={()=>setPage(page+1)}>Next</button></div>
   </>}
  </>}
 </section>;
}
