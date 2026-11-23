import {useEffect,useState,type ReactNode} from 'react';
import {TrendingUp, Wallet, Package, Fish, CalendarDays, FileDown} from 'lucide-react';
import {ErrorNotice} from './apiErrors';
import {CashActivity} from './farmExpenses';
import {PricingAdvisor,type PricingDownload} from './pricingAdvisor';

type Row=Record<string,any>;
export const reports=[
 ['growth','Fish Growth Reports','Compare fish weights and sampling history across production units.',TrendingUp],
 ['cash','Cash Activity','Review customer payments, feed purchases, and other cash outflows.',Wallet],
 ['feed','Feed Inventory Reports','Check current feed stock, actual use, and projected requirements.',Package],
 ['pricing','Profitability & Selling Price','Compare costs, break-even prices, and selling-price scenarios.',Fish],
 ['harvest','Harvest Reports','Review planned dates, harvest forecasts, and recorded harvests.',CalendarDays],
 ['complete','Complete Farm Report','Select sections and export a report from your farm records.',FileDown],
] as const;
export type ReportView=typeof reports[number][0];
type Scope={unit_ids:number[],cycle_id:string,start:string,end:string,species:string,status:string,feed_id:string};
type Props={
 view:ReportView,farmId:number,analytics:Row|null,harvests:Row[],loading:boolean,loadError:boolean,
 load:(path:string,body?:Row)=>Promise<any>,download:(path:string,name:string)=>Promise<void>,downloadPdf:PricingDownload,
 cashChart:(title:string,data:Row[])=>ReactNode,trend:(title:string,points:Row[],dateKey:string,value:string,series:string,unit:string)=>ReactNode,
 stockChart:(data:Row[])=>ReactNode,navigate:(page:'production'|'inventory'|'expenses'|'sales',view?:'feeding'|'harvesting'|'schedule'|'water_quality'|'growth')=>void,
 refresh:()=>void,children?:ReactNode,
};
const today=()=>new Date().toISOString().slice(0,10);
const summarySections=[
 ['production','Production and mortality'],['feeding','Feeding and inventory'],['growth','Fish growth'],['water','Water quality'],
 ['harvest','Harvesting'],['sales','Sales'],['expenses','Expenses'],['cash','Cash activity'],['profitability','Profitability'],['loans','Loan obligations'],
];
const numeric=(value:unknown,unit='')=>value==null?'Unavailable':new Intl.NumberFormat('en-GH',{maximumFractionDigits:2}).format(Number(value))+unit;

export function ReportCards({open}:{open:(view:ReportView)=>void}){
 return <section className="panel"><h2>Farm Reports &amp; Analytics</h2><div className="production-grid">
  {reports.map(([key,title,description,Icon])=><button type="button" className="production-card" key={key} onClick={()=>open(key)}>
   <Icon size={22} aria-hidden="true"/><strong>{title}</strong><span>{description}</span><b>Open report</b>
  </button>)}
 </div></section>;
}

function defaultScope(view:ReportView):Scope{
 const year=today().slice(0,4);
 return {unit_ids:[],cycle_id:'',start:year+'-01-01',end:view==='harvest'?year+'-12-31':today(),species:'',status:'',feed_id:''};
}

export function ReportDetail({view,farmId,analytics,harvests,loading,loadError,load,download,downloadPdf,cashChart,trend,stockChart,navigate,refresh,children}:Props){
 const storage='aquafarm-report-filters:'+farmId+':'+view;
 const [scope,setScope]=useState<Scope>(()=>{
  try{return {...defaultScope(view),...JSON.parse(sessionStorage.getItem(storage)??'{}')}}
  catch{return defaultScope(view)}
 });
 const [draft,setDraft]=useState(scope);
 const [feed,setFeed]=useState<Row|null>(null);
 const [lots,setLots]=useState<Row[]|null>(null);
 const [complete,setComplete]=useState<Row|null>(null);
 const [sections,setSections]=useState(summarySections.map(([key])=>key));
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const units:Row[]=analytics?.production?.unit_comparisons??[];
 const cycles:Row[]=analytics?.production?.cycles??[];
 const inventory:Row[]=analytics?.feed?.inventory??[];
 const byId=new Map(cycles.map(row=>[row.cycle_id,row]));
 const matches=(row:Row)=>(!scope.unit_ids.length||scope.unit_ids.includes(row.unit_id))&&(!scope.cycle_id||Number(scope.cycle_id)===row.cycle_id)&&(!scope.species||row.species===scope.species);
 const within=(date?:string)=>Boolean(date&&date.slice(0,10)>=scope.start&&date.slice(0,10)<=scope.end);
 const body={start:scope.start,end:scope.end,unit_ids:scope.unit_ids,cycle_id:scope.cycle_id?Number(scope.cycle_id):null};
 const reportPath='/farms/'+farmId+'/reports/complete';
 useEffect(()=>{
   let current=true;
   if(view==='feed'){
     setFeed(null);setError('');
     load('/farms/'+farmId+'/reports/feed-activity',{start:scope.start,end:scope.end,
       unit_ids:scope.unit_ids,cycle_id:scope.cycle_id?Number(scope.cycle_id):null,feed_id:scope.feed_id?Number(scope.feed_id):null})
      .then(data=>{if(current)setFeed(data)}).catch(problem=>{if(current)setError(String(problem))});
   }
   if(view==='harvest'){
     setLots(null);setError('');
     load('/farms/'+farmId+'/sales/harvests').then(data=>{if(current)setLots(data)})
       .catch(problem=>{if(current)setError(String(problem))});
   }
   return ()=>{current=false};
 },[view,farmId,scope,load,analytics]);

 function apply(value:Scope){
   setScope(value);setDraft(value);setComplete(null);setError('');
   sessionStorage.setItem(storage,JSON.stringify(value));
 }
 async function generate(pdf=false){
   setBusy(true);setError('');
   const params={...body,sections};
   try{
     if(pdf)await downloadPdf(reportPath+'.pdf',params,'complete-farm-report.pdf');
     else setComplete(await load(reportPath,params));
   }catch(problem){setError(String(problem))}
   finally{setBusy(false)}
 }
 if(view==='cash')return <>
  <CashActivity persistKey={'aquafarm-cash-filters:'+farmId} key={farmId} farmId={farmId} load={load} refreshKey={analytics} chart={cashChart} download={download}/>
  <div className="farmactions"><button className="outline" onClick={()=>navigate('expenses')}>Open expense history</button><button className="outline" onClick={()=>navigate('sales')}>View sales and payments</button></div>
 </>;
 const filters=<details className="report-filters" open>
  <summary>Report filters</summary>
  <form className="farmform" onSubmit={event=>{event.preventDefault();apply(draft)}}>
   <fieldset><legend>Production units</legend>
    <p className="muted">Leave all unchecked to include all units.</p>
    <div className="farmactions">{units.map(unit=><label className="consent" key={unit.unit_id}><input type="checkbox" checked={draft.unit_ids.includes(unit.unit_id)}
      onChange={event=>setDraft({...draft,cycle_id:'',unit_ids:event.target.checked?[...draft.unit_ids,unit.unit_id]:draft.unit_ids.filter(id=>id!==unit.unit_id)})}/>{unit.unit_name}</label>)}</div>
   </fieldset>
   <label className="field"><span>Stocking cycle</span><select value={draft.cycle_id} onChange={event=>setDraft({...draft,cycle_id:event.target.value})}>
    <option value="">All cycles</option>{cycles.filter(row=>!draft.unit_ids.length||draft.unit_ids.includes(row.unit_id)).map(row=><option key={row.cycle_id} value={row.cycle_id}>{row.unit_name} | {row.species} | #{row.cycle_id}</option>)}
   </select></label>
   {(view==='growth'||view==='harvest'||view==='pricing')&&<label className="field"><span>Fish species</span><select value={draft.species} onChange={event=>setDraft({...draft,species:event.target.value})}>
    <option value="">All species</option>{[...new Set(cycles.map(row=>row.species))].map(species=><option key={species}>{species}</option>)}
   </select></label>}
   {view!=='pricing'&&<>
    <label className="field"><span>From</span><input type="date" required max={draft.end} value={draft.start} onChange={event=>setDraft({...draft,start:event.target.value})}/></label>
    <label className="field"><span>To</span><input type="date" required min={draft.start} value={draft.end} onChange={event=>setDraft({...draft,end:event.target.value})}/></label>
   </>}
   {view==='feed'&&<label className="field"><span>Feed product</span><select value={draft.feed_id} onChange={event=>setDraft({...draft,feed_id:event.target.value})}><option value="">All products</option>{inventory.map(row=><option value={row.feed_id} key={row.feed_id}>{row.feed_name}</option>)}</select></label>}
   {view==='harvest'&&<label className="field"><span>Harvest status</span><select value={draft.status} onChange={event=>setDraft({...draft,status:event.target.value})}>
    <option value="">All statuses</option>{[...new Set(harvests.map(row=>row.status))].map(status=><option key={status}>{status}</option>)}
   </select></label>}
   <div className="farmactions"><button className="primary">Apply Filters</button><button className="outline" type="button" onClick={()=>apply(defaultScope(view))}>Reset Filters</button></div>
  </form>
 </details>;
 if(loadError&&!analytics)return <ErrorNotice message="Unable to load farm report data." retry={refresh}/>;
 if(!analytics)return <p role="status">{loading?'Loading farm report data…':'Farm report data is unavailable.'}</p>;
 const growth=(analytics.production?.growth_trends??[]).filter((row:Row)=>matches(row)&&within(row.sampled_on))
  .map((row:Row)=>({...row,series:row.unit_name+' | Cycle #'+row.cycle_id}));
 const chosenHarvests=harvests.filter(row=>matches(row)&&(!scope.status||row.status===scope.status)&&
   (within(row.expected_harvest_on)||within(row.last_harvest_on)||(!row.expected_harvest_on&&!row.last_harvest_on)));
 const forecasts:Row[]=(analytics.production?.harvest_forecasts??[]).filter((row:Row)=>matches(byId.get(row.cycle_id)??row)&&within(row.expected_harvest_on));
 const harvestLots=lots?.filter(lot=>{
   const cycle=byId.get(lot.cycle_id);
   return cycle&&matches(cycle)&&within(lot.harvested_on)&&(!scope.status||harvests.some(row=>row.cycle_id===lot.cycle_id&&row.status===scope.status));
 });
 return <>
  {filters}
  {error&&<ErrorNotice message={error} retry={()=>apply({...scope})}/>}
  {view==='growth'&&<>
   {trend('Fish Growth History · Average Sample Weight',growth,'sampled_on','average_weight_g','series',' g')}
   {trend('Estimated biomass at sampling dates',growth,'sampled_on','estimated_biomass_kg','series',' kg')}
   <section className="panel"><h3>Sampling history</h3>{growth.length?<div className="tablewrap"><table><thead><tr><th>Unit and cycle</th><th>Date</th><th>Fish sampled</th><th>Average weight</th></tr></thead><tbody>{growth.map((row:Row,i:number)=><tr key={i}><td>{row.series}</td><td>{row.sampled_on}</td><td>{row.sample_count}</td><td>{numeric(row.average_weight_g,' g')}</td></tr>)}</tbody></table></div>:<p className="empty">No fish samples match this period.</p>}</section>
   <section className="panel"><h3>Current biomass estimates</h3>{cycles.filter(row=>matches(row)&&row.status==='active').map(row=><p className="item" key={row.cycle_id}>{row.unit_name} | {numeric(row.estimated_biomass_kg,' kg')} | Sample {row.latest_sampled_on??'Initial stocking weight used'}</p>)}
    <p className="muted">Biomass estimates use recorded sample weights and fish movements through each sample date.</p>
    <button className="outline" onClick={()=>navigate('production','growth')}>Record a growth sample</button>
    <button className="outline" onClick={()=>navigate('production','water_quality')}>Open water quality records</button>
   </section>
   {trend('Dissolved oxygen history',(analytics.water_quality?.history??[]).filter((row:Row)=>
    (!scope.unit_ids.length||scope.unit_ids.includes(row.unit_id))&&(!scope.cycle_id||row.unit_id===byId.get(Number(scope.cycle_id))?.unit_id)&&within(row.observed_at)),
    'observed_at','dissolved_oxygen_mg_l','unit_name',' mg/L')}
  </>}
  {view==='feed'&&<>
   {stockChart(inventory.filter(row=>!scope.feed_id||Number(scope.feed_id)===row.feed_id))}
   <p className="muted">Current inventory and projected shortages are farm-wide. Unit and cycle filters apply to actual consumption.</p>
   {!feed&&!error&&<p role="status">Loading feed activity…</p>}
   {feed&&<><p>Feed purchased in period: {numeric(feed.purchased_kg,' kg')} | Actual consumption: {numeric(feed.consumed_kg,' kg')}</p>
    {trend('Actual feed consumption',feed.trends,'date','kg','feed',' kg')}
    <section className="panel"><h3>Feed consumed by unit and cycle</h3>{feed.consumption.length?feed.consumption.map((row:Row,i:number)=><p className="item" key={i}>{row.unit} | Cycle {row.cycle_id??'Unavailable'} | {row.feed} | {numeric(row.kg,' kg')}</p>):<p className="empty">No feed consumption recorded for this period.</p>}</section>
   </>}
   <section className="panel"><h3>Projected feed required over 30 days</h3>
    {(analytics.feed?.forecast?.feeds??[]).filter((row:Row)=>!scope.feed_id||Number(scope.feed_id)===row.feed_id).map((row:Row)=><p key={row.feed_id}>{row.feed_name} | {row.approved_daily_demand_kg>0?numeric(row.expected_usage_kg,' kg'):'No approved demand'}{row.shortage_expected?' | Stock shortage expected':''}</p>)}
    {analytics.feed?.forecast?.cycles_without_approved_recommendation?.length>0&&<p className="muted">Some active cycles have no approved feeding recommendation.</p>}
    <div className="farmactions"><button className="outline" onClick={()=>navigate('inventory')}>Record Feed Purchase / View Inventory</button><button className="outline" onClick={()=>navigate('production','feeding')}>Record Feeding Session</button></div>
   </section>
  </>}
  {view==='pricing'&&<>
   {cycles.filter(matches).map(row=><PricingAdvisor key={row.cycle_id} farmId={farmId} cycleId={row.cycle_id} load={load} download={downloadPdf} revision={analytics} compact/>)}
   {!cycles.some(matches)&&<p className="empty">No cycles match the filters.</p>}
   {children}
  </>}
  {view==='harvest'&&<section className="panel">
   <div className="farmactions"><button className="outline" onClick={()=>navigate('production','harvesting')}>Open Harvesting</button><button className="outline" onClick={()=>navigate('production','schedule')}>Open Harvest Planning</button></div>
   <h3>Harvest schedule</h3>
   {chosenHarvests.length?chosenHarvests.map(row=><p className="item" key={row.cycle_id}>{row.unit_name} | {row.species} | Cycle #{row.cycle_id} | {row.status} | Planned {row.expected_harvest_on??'Not scheduled'} | Target {numeric(row.target_harvest_weight_g,' g')} | Forecast {numeric(row.estimated_harvest_kg,' kg')}</p>):<p className="empty">No planned harvests match these filters.</p>}
   {forecasts.filter(row=>row.date_basis!=='farmer_schedule').map(row=><p className="muted" key={row.cycle_id}>{row.unit_name} | Model forecast {row.expected_harvest_on} | {numeric(row.expected_harvest_kg,' kg')}</p>)}
   <h3>Recorded harvests</h3>
   {!lots&&!error?<p role="status">Loading harvest records…</p>:harvestLots?.length?harvestLots.map(row=><p className="item" key={row.id}>{byId.get(row.cycle_id)?.unit_name??'Unit unavailable'} | {row.harvested_on} | {numeric(row.quantity_kg,' kg')} | {numeric(row.fish_count,' fish')} | Stock remaining {numeric(row.available_kg,' kg')}</p>):!error&&<p className="empty">No recorded harvests match these filters.</p>}
  </section>}
  {view==='complete'&&<section className="panel complete-farm-print">
   <h2>Complete Farm Report</h2>
   <fieldset><legend>Include report sections</legend><div className="farmactions">{summarySections.map(([key,label])=><label key={key} className="consent"><input type="checkbox" checked={sections.includes(key)} onChange={event=>{setComplete(null);setSections(event.target.checked?[...sections,key]:sections.filter(item=>item!==key))}}/>{label}</label>)}</div></fieldset>
   <div className="farmactions"><button className="primary" disabled={busy||!sections.length} onClick={()=>void generate()}>View Report</button><button className="outline" disabled={busy||!sections.length} onClick={()=>void generate(true)}>Download PDF</button>
    <button className="outline" disabled={!complete} onClick={()=>{document.body.classList.add('printing-complete-farm');try{window.print()}finally{document.body.classList.remove('printing-complete-farm')}}}>Print</button></div>
   {complete&&<article className="complete-farm-output"><h3>{complete.farm_name} | {complete.start} to {complete.end}</h3><p>{complete.note}</p>
    {complete.rows.length?<div className="tablewrap"><table><thead><tr><th>Section</th><th>Record</th><th>Detail</th></tr></thead><tbody>{complete.rows.map((row:Row,i:number)=><tr key={i}><td>{row.section}</td><td>{row.record}</td><td>{row.detail}</td></tr>)}</tbody></table></div>:<p className="empty">No records for this report selection.</p>}
   </article>}
   {children}
  </section>}
 </>;
}
