import {PricingAdvisor, type PricingDownload} from './pricingAdvisor';
import {useEffect,useState} from 'react';

type Row=Record<string,any>;
type Scope={units:number[]|null,type:string,species:string,cycle:string,history:boolean};
type Props={
 farmId:number, analytics:Row, harvests:Row[], pricingDownload:PricingDownload, load:(path:string,body:Row)=>Promise<Row>,
 open:(section:'feeding'|'growth'|'water_quality'|'schedule'|'harvesting'|'inventory',row:Row,session?:Row)=>void,
};
const initial:Scope={units:null,type:'',species:'',cycle:'',history:false};
const number=new Intl.NumberFormat('en-GH',{maximumFractionDigits:2});
const fmt=(value:number|null|undefined,unit='')=>value==null?'Unavailable':number.format(value)+unit;
const dateOffset=(offset=0)=>new Date(Date.now()+offset*86400000).toISOString().slice(0,10);

export function ProductionIntelligence({farmId,analytics,harvests,load,open,pricingDownload}:Props){
 const units:Row[]=analytics.production?.unit_comparisons??[];
 const rows:Row[]=analytics.production?.cycles??[];
 const storageKey='aquafarm-production-filter:'+farmId;
 const [scope,setScope]=useState<Scope>(()=>{
   try{return JSON.parse(sessionStorage.getItem(storageKey)??'null')??initial}
   catch{return initial}
 });
 const [draft,setDraft]=useState<Scope>(scope);
 function applyScope(value:Scope){
   setScope(value);
   sessionStorage.setItem(storageKey,JSON.stringify(value));
 }
 const [period,setPeriod]=useState('today');
 const [from,setFrom]=useState(dateOffset());
 const [to,setTo]=useState(dateOffset());
 const [forecast,setForecast]=useState('7');
 const [sort,setSort]=useState('name');
 const [detail,setDetail]=useState<number|null>(null);
 const [feed,setFeed]=useState<Row|null>(null);
 const [error,setError]=useState('');
 const [retry,setRetry]=useState(0);
 const selected=units.filter(unit=>(scope.units===null||scope.units.includes(unit.unit_id))&&(!scope.type||scope.type===unit.unit_type)&&
   ((!scope.species&&!scope.cycle)||rows.some(row=>row.unit_id===unit.unit_id&&(scope.history||row.status==='active')&&(!scope.species||row.species===scope.species)&&(!scope.cycle||String(row.cycle_id)===scope.cycle))));
 const cycles=rows.filter(row=>selected.some(unit=>unit.unit_id===row.unit_id)&&(scope.history||row.status==='active')&&
   (!scope.species||row.species===scope.species)&&(!scope.cycle||String(row.cycle_id)===scope.cycle));
 const active=cycles.filter(row=>row.status==='active');
 const ids=cycles.map(row=>row.cycle_id).sort((a,b)=>a-b).join(',');
 const start=period==='custom'?from:dateOffset(period==='yesterday'?-1:period==='7'?-6:period==='30'?-29:0);
 const end=period==='custom'?to:dateOffset(period==='yesterday'?-1:0);
 const requestKey=[ids,start,end,forecast,retry].join('|');
 const currentFeed=feed?.key===requestKey?feed:null;
 useEffect(()=>{
   let current=true;
   setError('');
   if(!ids){setFeed({key:requestKey,cycles:[],balances:[]});return}
   setFeed(null);
   load('/farms/'+farmId+'/dashboard/production-feeding',{
     cycle_ids:ids.split(',').map(Number),start,end,forecast_days:forecast==='harvest'?7:Number(forecast),until_harvest:forecast==='harvest',
   }).then(response=>{if(current)setFeed({...response,key:requestKey})})
     .catch(problem=>{if(current)setError(String(problem))});
   return ()=>{current=false};
 },[farmId,ids,start,end,forecast,requestKey,load,analytics]);
 const planned=harvests.filter(row=>active.some(cycle=>cycle.cycle_id===row.cycle_id));
 const projected:Row[]=(analytics.production?.harvest_forecasts??[]).filter((row:Row)=>active.some(cycle=>cycle.cycle_id===row.cycle_id));
 const projectedAmounts=projected.filter(row=>row.expected_harvest_kg!=null);
 const feedRows:Row[]=currentFeed?.cycles??[];
 const feeding=(row:Row)=>feedRows.find(item=>item.cycle_id===row.cycle_id);
 const sum=(values:number[])=>values.reduce((total,value)=>total+value,0);
 const totalRecommended=feedRows.filter(row=>row.period.recommended_kg!=null);
 const todayRations=feedRows.filter(row=>row.today?.daily_ration_kg!=null&&row.recommendation?.status!=='suspended');
 const plannedFor=(row:Row)=>planned.find(item=>item.cycle_id===row.cycle_id)??harvests.find(item=>item.cycle_id===row.cycle_id);
 const estimateFor=(row:Row)=>projected.find(item=>item.cycle_id===row.cycle_id);
 const metrics=[
   ['Active production cycles',active.length],['Estimated live fish',sum(active.map(row=>row.estimated_live_count))],
   ['Estimated biomass',fmt(sum(active.map(row=>row.estimated_biomass_kg)),' kg')],
   ['Upcoming planned harvests',planned.filter(row=>row.days_remaining!=null&&row.days_remaining>=0).length],
   ['Actual feed in period',fmt(currentFeed?sum(feedRows.map(row=>row.period.actual_kg)):null,' kg')],
   ['Approved daily feed (eligible cycles)',fmt(todayRations.length?sum(todayRations.map(row=>row.today.daily_ration_kg)):null,' kg')],
   ['Recommended feed for scheduled days',fmt(totalRecommended.length?sum(totalRecommended.map(row=>row.period.recommended_kg)):null,' kg')],
   ['Projected harvest biomass',fmt(projectedAmounts.length?sum(projectedAmounts.map(row=>row.expected_harvest_kg)):null,' kg')],
 ];
 const sorted=[...cycles].sort((a,b)=>{
   if(sort==='species')return String(a.species).localeCompare(String(b.species));
   if(sort==='biomass')return b.estimated_biomass_kg-a.estimated_biomass_kg;
   if(sort==='completion')return (feeding(b)?.period.completion_pct??-1)-(feeding(a)?.period.completion_pct??-1);
   if(sort==='harvest')return String(a.expected_harvest_on??'9999').localeCompare(String(b.expected_harvest_on??'9999'));
   return String(a.unit_name).localeCompare(String(b.unit_name));
 });
 return <section className="panel">
  <h2>Production Unit Intelligence</h2>
  <details><summary>Filter Production Units</summary>
   <form className="farmform" onSubmit={event=>{event.preventDefault();applyScope(draft);setDetail(null)}}>
    <div className="farmactions"><button type="button" className="outline" onClick={()=>setDraft({...draft,units:null})}>Select All</button>
     <button type="button" className="outline" onClick={()=>setDraft({...draft,units:[]})}>Clear Selection</button></div>
    <fieldset><legend>Units on this farm</legend>{units.map(unit=><label className="consent" key={unit.unit_id}>
     <input type="checkbox" checked={draft.units===null||draft.units.includes(unit.unit_id)} onChange={event=>{
       const chosen=draft.units??units.map(item=>item.unit_id);
       setDraft({...draft,units:event.target.checked?[...chosen,unit.unit_id]:chosen.filter(id=>id!==unit.unit_id)});
     }}/>{unit.unit_name}</label>)}</fieldset>
    <label className="field"><span>Unit type</span><select value={draft.type} onChange={event=>setDraft({...draft,type:event.target.value})}><option value="">All types</option>{[...new Set(units.map(unit=>unit.unit_type))].sort().map(type=><option key={type}>{type}</option>)}</select></label>
    <label className="field"><span>Fish species</span><select value={draft.species} onChange={event=>setDraft({...draft,species:event.target.value,cycle:''})}><option value="">All species</option>{[...new Set(rows.map(row=>row.species))].sort().map(species=><option key={species}>{species}</option>)}</select></label>
    <label className="field"><span>Stocking cycle</span><select value={draft.cycle} onChange={event=>setDraft({...draft,cycle:event.target.value})}><option value="">All matching cycles</option>{rows.filter(row=>(draft.history||row.status==='active')&&(!draft.species||row.species===draft.species)).map(row=><option key={row.cycle_id} value={row.cycle_id}>{row.unit_name} | {row.species} | #{row.cycle_id}</option>)}</select></label>
    <label className="consent"><input type="checkbox" checked={draft.history} onChange={event=>setDraft({...draft,history:event.target.checked,cycle:''})}/> Include historical cycles</label>
    <div className="farmactions"><button className="primary">Apply Filters</button><button type="button" className="outline" onClick={()=>{setDraft(initial);applyScope(initial);setPeriod('today');setForecast('7');setDetail(null)}}>Reset Filters</button></div>
   </form>
  </details>
  <div className="farmactions">
   <label className="field"><span>Feeding period</span><select value={period} onChange={event=>setPeriod(event.target.value)}><option value="today">Today</option><option value="yesterday">Yesterday</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="custom">Custom dates</option></select></label>
   {period==='custom'&&<>
     <label className="field"><span>Start date</span><input type="date" value={from} max={to} onChange={event=>setFrom(event.target.value)}/></label>
     <label className="field"><span>End date</span><input type="date" value={to} min={from} max={dateOffset()} onChange={event=>setTo(event.target.value)}/></label>
   </>}
   <label className="field"><span>Feed forecast</span><select value={forecast} onChange={event=>setForecast(event.target.value)}><option value="7">Next 7 days</option><option value="14">Next 14 days</option><option value="30">Next 30 days</option><option value="harvest">Until planned harvest</option></select></label>
  </div>
  <p className="muted">Showing {selected.length} of {units.length} production units. Current fish and biomass totals use active cycles.</p>
  {error&&<div className="alert" role="alert">{error}<button type="button" onClick={()=>setRetry(value=>value+1)}>Retry</button></div>}
  {!currentFeed&&!error&&ids&&<p role="status">Loading feeding summaries…</p>}
  {selected.length===0?<p className="empty">No production units match the selected filters.</p>:<>
   <div className="statgrid">{metrics.map(([label,value])=><div className="stat" key={label}><small>{label}</small><strong>{value}</strong></div>)}</div>
   <details><summary>Selected feed requirements and stock</summary><p className="muted">Forecast uses the approved daily ration at a constant rate. Feed stock is shared across the farm, including units outside this selection.</p>
    {currentFeed?.balances?.length?currentFeed.balances.map((row:Row)=><p key={row.feed_id}>{row.feed_name} | Need {fmt(row.required_kg,' kg')} | Stock {fmt(row.stock_kg,' kg')} | {row.balance_kg<0?'Shortage':'Surplus'} {fmt(Math.abs(row.balance_kg),' kg')} | Last stock record {row.last_stock_record_on??'Unavailable'}</p>):<p>Feed forecast unavailable for this selection.</p>}
    <button className="outline" onClick={()=>open('inventory',{})}>View feed inventory</button>
   </details>
   {active.length>0&&<details><summary>Fish Selling Price &amp; Profitability</summary>
    {active.map(row=><PricingAdvisor key={row.cycle_id} farmId={farmId} cycleId={row.cycle_id} load={load} revision={analytics} download={pricingDownload} compact/>)}
   </details>}
   <div className="production-grid">
    {selected.map(unit=><section className="panel" key={unit.unit_id}><h3>{unit.unit_name}</h3><p className="muted">{unit.unit_type}</p>
     {cycles.filter(row=>row.unit_id===unit.unit_id).length?cycles.filter(row=>row.unit_id===unit.unit_id).map(row=>{
       const data=feeding(row), plan=plannedFor(row), estimate=estimateFor(row);
       return <div className="item" key={row.cycle_id}><b>{row.species} | Cycle #{row.cycle_id} | {row.status}</b>
        <p>Stocked {row.stocked_on} | {fmt(row.estimated_live_count)} fish | {fmt(row.estimated_biomass_kg,' kg')} biomass</p>
        <p>Current weight {fmt(row.latest_average_weight_g,' g')} | Sample {row.latest_sampled_on??'Not recorded'}</p>
        <p>Approved daily ration {fmt(data?.recommendation?.status==='suspended'?null:data?.today?.daily_ration_kg,' kg')} | Today {fmt(data?.today?.actual_kg,' kg')} | Period {fmt(data?.period.actual_kg,' kg')}</p>
        <p>Sessions today {data?.today?.scheduled_count?data.today.recorded_count+' / '+data.today.scheduled_count:'Unavailable'} | Period completion {fmt(data?.period.completion_pct,'%')}</p>
        <p>{plan?.expected_harvest_on?'Planned harvest '+plan.expected_harvest_on+' | '+plan.status:'Harvest date not scheduled.'}</p>
        <p>Target {fmt(plan?.target_harvest_weight_g??estimate?.target_weight_g,' g')} | Projected harvest {fmt(estimate?.expected_harvest_kg??plan?.estimated_harvest_kg,' kg')}</p>
        <button type="button" className="outline small" onClick={()=>setDetail(detail===row.cycle_id?null:row.cycle_id)} aria-expanded={detail===row.cycle_id}>View Details</button>
       </div>;
     }):<p className="empty">No matching stocking cycle.</p>}
    </section>)}
   </div>
   {cycles.filter(row=>row.cycle_id===detail).map(row=>{
     const data=feeding(row), plan=plannedFor(row), estimate=estimateFor(row), recommendation=data?.recommendation;
     const water=analytics.water_quality?.latest_by_unit?.find((item:Row)=>item.unit_id===row.unit_id);
     const observed=water?.observed_at?Date.parse(/Z|[+-][0-9]{2}:[0-9]{2}$/.test(water.observed_at)?water.observed_at:water.observed_at+'Z'):NaN;
     const samples=(analytics.production?.growth_trends??[]).filter((item:Row)=>item.cycle_id===row.cycle_id);
     return <section className="panel" key={row.cycle_id}>
      <h3>{row.unit_name} | {row.species} | Cycle #{row.cycle_id}</h3>
      <p>Mortality {fmt(row.mortality_count)} | Already harvested {fmt(row.harvested_count)} fish | Survival {fmt(row.estimated_survival_pct,'%')}</p>
      {row.population_warning&&<p className="alert">{row.population_warning}</p>}
      <details><summary>Cost &amp; Selling Price</summary>
       <PricingAdvisor key={row.cycle_id} farmId={farmId} cycleId={row.cycle_id} load={load} revision={analytics} download={pricingDownload}/>
      </details>
      <details open><summary>Feeding and activity</summary>
       <p>{recommendation?'Latest advisory: '+String(recommendation.status).replaceAll('_',' ')+' | '+String(recommendation.date).slice(0,10):'No recommendation available'}</p>
       {recommendation&&<><p>{fmt(recommendation.daily_kg,' kg/day')} | {recommendation.sessions} sessions | {fmt(recommendation.session_kg,' kg/session')} | {recommendation.feed_name??'Feed unavailable'} | Basis {fmt(recommendation.biomass_kg,' kg biomass')}</p>
        {recommendation.warnings.map((warning:string)=><p className="muted" key={warning}>{warning}</p>)}</>}
       <p>Period: {start} to {end} | Scheduled {data?.period.scheduled_count??'Unavailable'} | Recorded {data?.period.recorded_count??'Unavailable'} | Skipped {data?.period.skipped_count??'Unavailable'} | Missed {data?.period.missed_count??'Unavailable'}</p>
       <p>Actual minus recommended on covered days: {fmt(data?.period.difference_kg,' kg')} | Schedule coverage {data?data.period.covered_days+' / '+data.period.cycle_days+' days':'Unavailable'}</p>
       <p>Projected feed: {fmt(data?.forecast.quantity_kg,' kg')}{data?.forecast.quantity_kg!=null?' | '+data.forecast.start+' to '+data.forecast.end:''}</p>
       {data?.today?.sessions.map((session:Row)=><div className="item" key={session.number}><b>Session {session.number} | {session.scheduled_time??'Time not set'} | {session.status}</b>
        <p>Recommended {fmt(session.recommended_kg,' kg')} | Actual {fmt(session.actual_kg,' kg')}</p>
        {session.entries.map((entry:Row)=><small key={entry.id}>{entry.feed_name} | {entry.recorder??'Recorder unavailable'} | Evidence {entry.evidence_status}</small>)}
        {session.status!=='skipped'&&<button type="button" className="outline small" onClick={()=>open('feeding',row,session)}>Record Feeding Session</button>}
       </div>)}
       {row.status==='active'&&<button className="outline" onClick={()=>open('feeding',row)}>View Feeding Records</button>}
      </details>
      <details><summary>Growth and water quality</summary>
       <p>Initial weight {fmt(row.initial_average_weight_g,' g')} | {row.latest_sampled_on?'Latest sampled weight '+fmt(row.latest_average_weight_g,' g')+' on '+row.latest_sampled_on:'No sample recorded. Current biomass uses stocking weight.'}</p>
       {samples.map((item:Row,index:number)=><p className="muted" key={index}>{item.sampled_on} | {fmt(item.average_weight_g,' g')} | {item.sample_count} fish sampled</p>)}
       <p>{estimate?.date_basis==='linear_projection_from_last_two_samples'?'Growth model predicts target weight on '+estimate.expected_harvest_on:'Insufficient growth data for an independent forecast.'}</p>
       <p>{water?'Last reading '+water.observed_at+' | '+fmt(water.temperature_c,' °C')+' | pH '+fmt(water.ph)+' | Dissolved oxygen '+fmt(water.dissolved_oxygen_mg_l,' mg/L'):'No recent water quality reading available.'}</p>
       {Number.isFinite(observed)&&Date.now()-observed>86400000&&<p className="muted">The latest water reading is more than 24 hours old.</p>}
       {row.status==='active'&&<div className="farmactions"><button className="outline" onClick={()=>open('growth',row)}>Record Fish Sample</button><button className="outline" onClick={()=>open('water_quality',row)}>Record Water Quality</button></div>}
      </details>
      <details><summary>Harvest</summary>
       <p>{plan?.expected_harvest_on?'Planned '+plan.expected_harvest_on+' | '+plan.days_remaining+' days remaining':'Harvest date not scheduled.'} | Survival assumption {fmt(plan?.expected_survival_pct,'%')}</p>
       {estimate?.expected_harvest_on&&estimate.date_basis!=='farmer_schedule'&&<p>Model forecast {estimate.expected_harvest_on}</p>}
       <p>Latest recorded harvest {plan?.last_harvest_on??'Unavailable'} | Recorded biomass {fmt(plan?.actual_harvest_kg,' kg')}</p>
       <div className="farmactions"><button className="outline" onClick={()=>open('schedule',row)}>View or update harvest plan</button><button className="outline" onClick={()=>open('harvesting',row)}>View harvest records</button></div>
      </details>
     </section>;
   })}
   {selected.length>1&&<details><summary>Compare production units</summary>
    <label className="field"><span>Sort by</span><select value={sort} onChange={event=>setSort(event.target.value)}><option value="name">Unit name</option><option value="species">Species</option><option value="biomass">Biomass</option><option value="completion">Feeding completion</option><option value="harvest">Planned harvest date</option></select></label>
    <div className="tablewrap"><table><thead><tr>{['Unit','Species','Cycle','Live fish','Biomass','Daily ration','Period feed','Completion','Latest weight','Planned harvest','Target weight','Harvest status'].map(label=><th key={label}>{label}</th>)}</tr></thead>
    <tbody>{sorted.map(row=><tr key={row.cycle_id}><td>{row.unit_name}</td><td>{row.species}</td><td>#{row.cycle_id} {row.status}</td><td>{fmt(row.estimated_live_count)}</td><td>{fmt(row.estimated_biomass_kg,' kg')}</td><td>{fmt(feeding(row)?.recommendation?.status==='suspended'?null:feeding(row)?.today?.daily_ration_kg,' kg')}</td><td>{fmt(feeding(row)?.period.actual_kg,' kg')}</td><td>{fmt(feeding(row)?.period.completion_pct,'%')}</td><td>{fmt(row.latest_average_weight_g,' g')}</td><td>{row.expected_harvest_on??'Not scheduled'}</td><td>{fmt(plannedFor(row)?.target_harvest_weight_g,' g')}</td><td>{plannedFor(row)?.status??'Unavailable'}</td></tr>)}</tbody></table></div>
   </details>}
  </>}
 </section>;
}
