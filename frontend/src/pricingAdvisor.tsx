import {useEffect,useState} from 'react';

type Row=Record<string,any>;
export type PricingApi=(path:string,body:Row)=>Promise<Row>;
export type PricingDownload=(path:string,body:Row,filename:string)=>Promise<void>;
const currency=new Intl.NumberFormat('en-GH',{style:'currency',currency:'GHS'});
const money=(value:number|null|undefined)=>value==null?'Unavailable':currency.format(value);
const kg=(value:number|null|undefined)=>value==null?'Unavailable':value.toLocaleString('en-GH',{maximumFractionDigits:2})+' kg';

export function PricingAdvisor({farmId,cycleId,load,download,revision,compact=false,price,quantity,onUsePrice}:{
 farmId:number,cycleId:number,load:PricingApi,download:PricingDownload,revision:unknown,compact?:boolean,
 price?:string,quantity?:string,onUsePrice?:(value:string)=>void
}){
 const root='/farms/'+farmId+'/cycles/'+cycleId+'/pricing-advisor';
 const [margin,setMargin]=useState('25');
 const [yieldPct,setYield]=useState('100');
 const [sellingCost,setSellingCost]=useState('0');
 const [proposed,setProposed]=useState('');
 const [expanded,setExpanded]=useState(!compact);
 const [result,setResult]=useState<Row|null>(null);
 const [error,setError]=useState('');
 const [downloading,setDownloading]=useState(false);
 const effectivePrice=price??proposed;
 const valid=margin!==''&&Number(margin)>=0&&Number(margin)<100&&yieldPct!==''&&Number(yieldPct)>0&&Number(yieldPct)<=100&&Number(sellingCost)>=0&&Number(effectivePrice)>=0;
 const input={margin_pct:margin,saleable_yield_pct:yieldPct,selling_cost_per_kg:sellingCost||'0',
  proposed_price:effectivePrice||null,sale_quantity_kg:Number(quantity)>0?quantity:null};
 useEffect(()=>{
   let current=true;
   setResult(null);setError('');
   if(!valid)return;
   const timer=window.setTimeout(()=>{
     load(root,{margin_pct:margin,saleable_yield_pct:yieldPct,selling_cost_per_kg:sellingCost||'0',
       proposed_price:effectivePrice||null,sale_quantity_kg:Number(quantity)>0?quantity:null}).then(data=>{if(current)setResult(data)})
       .catch(problem=>{if(current)setError(String(problem))});
   },250);
   return ()=>{current=false;window.clearTimeout(timer)};
 },[root,load,revision,margin,yieldPct,sellingCost,effectivePrice,quantity,valid]);
 const pricePerKg=(value:number|null|undefined)=>value==null?'Unavailable':money(value)+'/kg';
 return <section className="panel">
  <h3>{compact?'Fish Selling Price & Profitability':'Cost & Selling Price'}</h3>
  {expanded&&<div className="farmform">
     <label className="field"><span>Target profit margin (%)</span><input type="number" min="0" max="99.99" step=".01" list={'pricing-margin-'+cycleId} value={margin} onChange={event=>setMargin(event.target.value)}/><datalist id={'pricing-margin-'+cycleId}>{[10,15,20,25,30].map(value=><option key={value} value={value}/>)}</datalist></label>
     <label className="field"><span>Expected saleable yield (%)</span><input type="number" min=".01" max="100" step=".01" value={yieldPct} onChange={event=>setYield(event.target.value)}/></label>
     <label className="field"><span>Additional selling cost per kg (GH₵)</span><input type="number" min="0" step=".01" value={sellingCost} onChange={event=>setSellingCost(event.target.value)}/></label>
     {price===undefined&&<label className="field"><span>Proposed Selling Price (GH₵/kg)</span><input type="number" min="0" step=".01" value={proposed} onChange={event=>setProposed(event.target.value)}/></label>}
    </div>}
  {!valid?<p className="alert" role="alert">Use a margin below 100%, a saleable yield above zero, and non-negative prices.</p>:error?<p className="alert" role="alert">{error}</p>:!result?<p role="status">Calculating price analysis…</p>:<>
   <p className="muted">{result.unit_name} | {result.species} | Cycle #{result.cycle_id} | {result.confidence.replaceAll('_',' ')}</p>
   <dl className="pricing-summary">
    <div><dt>Expected saleable weight</dt><dd>{kg(result.saleable_weight_kg)}</dd></div>
    <div><dt>Estimated production and selling costs</dt><dd>{money(result.total_cost_ghs)}</dd></div>
    <div><dt>Full-cycle break-even</dt><dd>{pricePerKg(result.break_even_ghs_per_kg)}</dd></div>
    <div><dt>Suggested price on remaining fish</dt><dd>{pricePerKg(result.target_ghs_per_kg)}</dd></div>
    <div><dt>Expected cycle profit at target</dt><dd>{money(result.at_target?.profit_ghs)}</dd></div>
    <div><dt>Planned harvest date</dt><dd>{result.planned_harvest_on??'Not scheduled'}</dd></div>
   </dl>
   {result.warnings.length>0&&<ul className="muted">{(expanded?result.warnings:result.warnings.slice(0,1)).map((warning:string)=><li key={warning}>{warning}</li>)}</ul>}
   {onUsePrice&&result.target_ghs_per_kg!=null&&<button className="outline" type="button" onClick={()=>onUsePrice(result.target_ghs_per_kg.toFixed(2))}>Use suggested price</button>}
   {compact&&<button type="button" className="outline" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'Hide price analysis':'View Price Analysis'}</button>}
   {expanded&&<>
    <p>Incurred {money(result.incurred_ghs)} | Expected remaining {money(result.remaining_cost_ghs)} | Additional selling {money(result.expected_selling_cost_ghs)}</p>
    <p>Consumed feed {money(result.consumed_feed_cost_ghs)} | Unallocated expenses excluded {money(result.unallocated_ghs)}</p>
    {Object.entries(result.allocated_expenses_ghs).map(([name,value])=><p key={name}>{name} | {money(Number(value))}</p>)}
    <p>Forecast remaining harvest {kg(result.forecast_harvest_kg)} | Actual harvested {kg(result.harvested_kg)} | Sold {kg(result.sold_kg)} | Recorded stock available {kg(result.unsold_harvest_kg)}</p>
    <p>Invoiced revenue to date {money(result.realized_revenue_ghs)} | Estimated production cost allocated to harvested fish {money(result.cost_allocated_to_harvest_ghs)}</p>
    <p>Biomass {kg(result.current_biomass_kg)} | Latest sample {result.sampled_on??'Not recorded'} | Market reference {pricePerKg(result.market_reference_ghs_per_kg)}</p>
    <p>Remaining fish break-even {pricePerKg(result.remaining_break_even_ghs_per_kg)}. Cycle estimates include invoiced sales already recorded. Harvested fish share production costs in proportion to estimated full-cycle saleable weight.</p>
    {([['Whole cycle at proposed price',result.proposal],['This proposed sale only',result.batch]] as const).map(([label,row])=>row&&<div className={row.status==='below_break_even'?'alert':'infobox'} key={label}>
     <b>{label}{row.status==='below_break_even'?' | Expected loss':row.status==='meets_target'?' | Meets target':' | Below target margin'}</b>
     <p>Revenue {money(row.revenue_ghs)} | Cost {money(row.cost_ghs)} | Profit or loss {money(row.profit_ghs)} | Margin {row.margin_pct==null?'Unavailable':row.margin_pct+'%'}</p>
     <p>Profit per kg {pricePerKg(row.profit_per_kg_ghs)} | Return on cost {row.return_on_cost_pct==null?'Unavailable':row.return_on_cost_pct+'%'}</p>
     {row.difference_from_break_even!=null&&<p>Difference from break-even {pricePerKg(row.difference_from_break_even)} | Difference from target {pricePerKg(row.difference_from_target)}</p>}
    </div>)}
    <button className="outline" type="button" disabled={downloading} onClick={async()=>{
      setDownloading(true);
      try{await download(root+'.pdf',input,'production-pricing-'+cycleId+'.pdf')}
      catch(problem){setError(String(problem))}
      finally{setDownloading(false)}
    }}>{downloading?'Preparing report…':'Download pricing PDF'}</button>
   </>}
  </>}
 </section>;
}
