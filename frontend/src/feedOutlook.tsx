
import {useEffect,useState} from 'react';
import {ErrorNotice} from './apiErrors';

type Row=Record<string,any>;
type Action='feeding'|'growth'|'water_quality'|'schedule'|'inventory';
type Props={farmId:number,load:(path:string,body?:Row,method?:string)=>Promise<any>,
 api:(path:string,init?:RequestInit)=>Promise<Response>,revision:unknown,compact?:boolean,
 navigate:(action:Action,row?:Row)=>void,changed:()=>void};
const number=(value:unknown)=>value==null?'Unavailable':new Intl.NumberFormat('en-GH',{maximumFractionDigits:4}).format(Number(value));
const statusLabels:Record<string,string>={draft:'Needs recommendation',provisional:'Provisional',pending_approval:'Awaiting approval',
 approved:'Approved',suspended:'Suspended',expired:'Expired ? review required'};
const sum=(rows:Row[],key:string)=>rows.reduce((total,row)=>total+(Number(row[key])||0),0);

export function FeedOutlook({farmId,load,api,revision,compact,navigate,changed}:Props){
 const root='/farms/'+farmId;
 const [report,setReport]=useState<Row|null>(null);
 const [error,setError]=useState('');
 const [reload,setReload]=useState(0);
 const [units,setUnits]=useState<number[]>([]);
 const [cycle,setCycle]=useState('');
 const [product,setProduct]=useState('');
 const [review,setReview]=useState<number|null>(null);
 const [feed,setFeed]=useState('');
 const [rate,setRate]=useState('');
 const [evidence,setEvidence]=useState<Row[]|null>(null);
 const [video,setVideo]=useState<{id:number,url:string}|null>(null);
 const [reviewNotes,setReviewNotes]=useState('');
 const [actionError,setActionError]=useState('');
 const [busy,setBusy]=useState(false);
 const refresh=()=>setReload(value=>value+1);
 useEffect(()=>{
  let active=true;
  async function fetchReport(){
   try{
    const result=await load(root+'/feed-outlook');
    if(active){setReport(result);setError('')}
   }catch{if(active)setError('Unable to load feeding forecast.')}
  }
  void fetchReport();
  const timer=window.setInterval(()=>void fetchReport(),60_000);
  return ()=>{active=false;window.clearInterval(timer)};
 },[root,load,reload,revision]);
 useEffect(()=>()=>{if(video)URL.revokeObjectURL(video.url)},[video]);
 if(error)return <section id={compact?undefined:'seven-day-feed-outlook'}><ErrorNotice message={error} retry={refresh}/></section>;
 if(!report)return <section id={compact?undefined:'seven-day-feed-outlook'} className="panel" aria-busy="true"><p>Loading seven-day feed outlook?</p></section>;

 const allCycles:Row[]=report.cycles;
 const allInventory:Row[]=report.inventory;
 const filtered=allCycles.filter(row=>(!units.length||units.includes(row.unit_id))&&(!cycle||row.cycle_id===Number(cycle))
   &&(!product||!row.feed_id||row.feed_id===Number(product)));
 const approved=filtered.filter(row=>row.status==='approved'&&row.forecast.length);
 const attention=filtered.filter(row=>!approved.includes(row));
 const selected=allCycles.find(row=>row.cycle_id===review);
 const selectedInventory=allInventory.filter(row=>!product||row.feed_id===Number(product));
 const shortage=selectedInventory.some(row=>row.shortage_kg>0);
 const projection=approved.length?number(sum(approved,'forecast_kg'))+' kg':'Unavailable';
 const summary=<div className="statgrid">
  <div className="stat"><small>Seven-day forecast</small><strong>{projection}</strong></div>
  <div className="stat"><small>Current feed stock</small><strong>{allInventory.length?number(sum(selectedInventory,'available_kg'))+' kg':'Unavailable'}</strong></div>
  {compact?<div className="stat"><small>Projected stock shortage</small><strong>{shortage?'Possible':approved.length?'None projected':'Unavailable'}</strong></div>:<>
   <div className="stat"><small>Active cycles in view</small><strong>{filtered.length}</strong></div>
   <div className="stat"><small>Approved forecasts</small><strong>{approved.length}</strong></div>
  </>}
  <div className="stat"><small>Cycles needing review</small><strong>{attention.length}</strong></div>
 </div>;
 if(compact)return <section className="panel"><h2>Seven-day feed outlook</h2>{summary}
  <button className="outline" type="button" onClick={()=>navigate('feeding')}>View Seven-Day Feed Outlook</button>
 </section>;

 async function run(action:()=>Promise<unknown>,notify=true){
  setActionError('');setBusy(true);
  try{await action();if(notify){refresh();changed()}}
  catch(problem){setActionError(String(problem))}
  finally{setBusy(false)}
 }
 const cycleUnits=[...new Map(allCycles.map(row=>[row.unit_id,row.unit_name])).entries()];
 return <section id="seven-day-feed-outlook" className="panel">
  <h2>Seven-day feed outlook</h2>
  <p className="muted">{report.farm_name} | {report.dates[0]} to {report.dates[6]} | Ghana time. Forecasts hold today's reviewed conditions and biomass constant across the projection.</p>
  <details className="report-filters"><summary>Forecast filters</summary>
   <fieldset className="feeding-window"><legend>Production units</legend>
    {cycleUnits.map(([id,name])=><label key={id}><input type="checkbox" checked={units.includes(id)} onChange={event=>{
     setUnits(previous=>event.target.checked?[...previous,id]:previous.filter(value=>value!==id));setCycle('');
    }}/>{name}</label>)}
    <button type="button" className="outline small" onClick={()=>{setUnits([]);setCycle('')}}>All production units</button>
   </fieldset>
   <div className="farmactions">
    <label className="field"><span>Stocking cycle</span><select value={cycle} onChange={event=>setCycle(event.target.value)}>
     <option value="">All cycles</option>{allCycles.filter(row=>!units.length||units.includes(row.unit_id)).map(row=><option key={row.cycle_id} value={row.cycle_id}>{row.unit_name} ? #{row.cycle_id}</option>)}
    </select></label>
    <label className="field"><span>Feed product</span><select value={product} onChange={event=>setProduct(event.target.value)}>
     <option value="">All feeds</option>{allInventory.map(row=><option key={row.feed_id} value={row.feed_id}>{row.name}</option>)}
    </select></label>
   </div>
  </details>
  {summary}
  {shortage&&<p className="alert">Feed stock may be insufficient for the next seven days.</p>}
  <details><summary>Feed inventory and coverage</summary>
   <p className="muted">Inventory and projected shortages include all approved cycles using each product on this farm.</p>
   {selectedInventory.length?<div className="tablewrap"><table><thead><tr><th>Product</th><th>Available kg</th><th>Required kg</th><th>Remaining kg</th><th>Shortage kg</th><th>Coverage days</th></tr></thead>
    <tbody>{selectedInventory.map(row=><tr key={row.feed_id}><td>{row.name}</td><td>{number(row.available_kg)}</td><td>{number(row.required_kg)}</td><td>{number(row.remaining_kg)}</td><td>{number(row.shortage_kg)}</td><td>{number(row.coverage_days)}</td></tr>)}</tbody></table></div>:<p>Feed inventory unavailable.</p>}
  </details>
  <button type="button" className="outline small" onClick={()=>navigate('inventory')}>View Feed Inventory</button>
  {!filtered.length&&<p>No active stocking cycles match these filters.</p>}
  {approved.length>0&&<div className="tablewrap"><table><thead><tr><th>Date</th><th>Unit and cycle</th><th>Biomass kg</th><th>Rate %</th><th>Daily feed kg</th><th>Session allocations kg</th></tr></thead>
   <tbody>{approved.flatMap(row=>row.forecast.map((day:Row)=><tr key={row.cycle_id+'-'+day.date}>
    <td>{day.date}</td><td>{row.unit_name} ? #{row.cycle_id} ? {row.feed_name}</td><td>{number(row.biomass_kg)}</td>
    <td>{number(row.feeding_rate_pct)}</td><td>{number(day.daily_kg)}</td><td>
     <details><summary>{day.sessions.length} sessions</summary>
      {day.sessions.map((session:Row)=><div key={session.number}>{session.name??'Session '+session.number}{session.start?' ('+session.start+'?'+session.end+')':''} ? {number(session.quantity_kg)}</div>)}
     </details>
    </td></tr>))}</tbody></table></div>}
  {attention.length>0&&<h3>Recommendations needing attention</h3>}
  {[...attention,...approved].map(row=><article className="item" key={row.cycle_id}>
   <b>{row.unit_name} ? {row.species} ? Cycle #{row.cycle_id} ? {statusLabels[row.status]??row.status}</b>
   {row.reasons.length>0&&<ul>{row.reasons.map((reason:string)=><li key={reason}>{reason}</li>)}</ul>}
   <div className="farmactions">
    <button type="button" className="outline small" onClick={()=>{
     setReview(row.cycle_id);setFeed(String(row.feed_id??''));setRate(String(row.feeding_rate_pct??''));setEvidence(null);setVideo(null);setReviewNotes('');setActionError('');
     requestAnimationFrame(()=>document.getElementById('feeding-recommendation-review')?.scrollIntoView({block:'start'}));
    }}>Review Feeding Recommendation</button>
    {row.status!=='approved'&&<><button type="button" className="outline small" onClick={()=>navigate('growth',row)}>Record Fish Sample</button>
     <button type="button" className="outline small" onClick={()=>navigate('water_quality',row)}>Record Water Quality</button></>}
    <button type="button" className="outline small" onClick={()=>navigate('schedule',row)}>Manage Feeding Schedule</button>
    <button type="button" className="outline small" onClick={()=>navigate('feeding',row)}>Record Feeding</button>
   </div>
  </article>)}
  {selected&&<section id="feeding-recommendation-review" className="item">
   <h3>Review Feeding Recommendation</h3>
   <p>{report.farm_name} ? {selected.unit_name} ({selected.unit_type}) ? {selected.species} ? Cycle #{selected.cycle_id}</p>
   <p>{statusLabels[selected.status]} ? {number(selected.estimated_live_count)} live fish ? {number(selected.average_weight_g)} g average ? {number(selected.biomass_kg)} kg biomass</p>
   <p>Verified sample {selected.sampled_on??'required'} ? Verified water reading {selected.water_observed_at?.replace('T',' ').slice(0,16)??'required'} (Ghana time)</p>
   {selected.recommendation&&<p>Saved calculation: {number(selected.feeding_rate_pct)}% ? {number(selected.recommendation.daily_ration_kg)} kg/day ? {selected.recommendation.session_count} advisory sessions ? {selected.feed_name}</p>}
   {selected.recommendation?.warnings?.length>0&&<ul>{selected.recommendation.warnings.map((warning:string)=><li key={warning}>{warning}</li>)}</ul>}
   {actionError&&<p className="alert" role="alert">{actionError}</p>}
   {!selected.profile_confirmed&&selected.profile_species&&<button type="button" className="outline small" disabled={busy}
    onClick={()=>void run(()=>load(root+'/feeding-profiles/'+selected.profile_species+'/approve',{}))}>Confirm advisory species profile</button>}
   <form className="farmform" onSubmit={event=>{
    event.preventDefault();
    void run(()=>load(root+'/units/'+selected.unit_id+'/cycles/'+selected.cycle_id+'/feeding-estimate',
     {feed_id:Number(feed),...(rate?{daily_feeding_rate_pct:Number(rate)}:{})}));
   }}>
    <label className="field"><span>Feed product</span><select required value={feed} onChange={event=>setFeed(event.target.value)}>
     <option value="">Select feed</option>{allInventory.map(row=><option key={row.feed_id} value={row.feed_id}>{row.name}</option>)}
    </select></label>
    <label className="field"><span>Feeding rate % (optional profile override)</span><input type="number" min="0.01" max="20" step="any" value={rate} onChange={event=>setRate(event.target.value)}/></label>
    <button className="outline" disabled={busy||!selected.profile_confirmed}>Calculate recommendation</button>
   </form>
   {selected.status==='pending_approval'&&<button className="primary" type="button" disabled={busy}
    onClick={()=>void run(()=>load(root+'/feeding-recommendations/'+selected.recommendation.id+'/approve',{}))}>Approve reviewed recommendation</button>}
   <button type="button" className="outline small" disabled={busy} onClick={()=>void run(async()=>{
    const rows:Row[]=await load(root+'/evidence-review?verification_status=pending');
    setEvidence(rows.filter(row=>row.cycle_id===selected.cycle_id&&row.record_id&&['growth','water_quality'].includes(row.record_type)));
   },false)}>Find fish sample and water evidence to review</button>
   {evidence&&(!evidence.length?<p>No linked evidence awaiting review for this cycle.</p>:evidence.map(row=><div className="item" key={row.id}>
    <b>{row.record_type==='growth'?'Fish sample':'Water quality'} ? {row.captured_at??row.created_at}</b>
    <button className="outline small" type="button" disabled={busy} onClick={()=>void run(async()=>{
     const response=await api(root+'/evidence/'+row.id+'/video');
     setReviewNotes('');setVideo({id:row.id,url:URL.createObjectURL(await response.blob())});
    },false)}>Inspect evidence video</button>
    {video?.id===row.id&&<><video controls src={video?.url} style={{maxWidth:'100%'}}/>
     <form className="farmform" onSubmit={event=>{
      event.preventDefault();
      const decision=new FormData(event.currentTarget).get('decision');
      void run(async()=>{
       await load(root+'/evidence/'+row.id+'/verification',{verification_status:decision,notes:reviewNotes});
       setEvidence(previous=>previous?.filter(item=>item.id!==row.id)??null);setVideo(null);
      });
     }}>
      <label className="field"><span>Review decision</span><select name="decision" required defaultValue=""><option value="">Select decision</option><option value="verified">Verify evidence</option><option value="flagged">Flag evidence</option></select></label>
      <label className="field"><span>Review notes</span><input required minLength={5} maxLength={2000} value={reviewNotes} onChange={event=>setReviewNotes(event.target.value)}/></label>
      <button className="outline" disabled={busy}>Save evidence review</button>
     </form></>}
   </div>))}
  </section>}
 </section>;
}
