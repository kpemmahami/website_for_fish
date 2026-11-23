import {ProcessingEvidenceLibrary} from './processingEvidence';

import {useCallback,useEffect,useRef,useState,type FormEvent,type ReactNode} from 'react';
import {ErrorNotice} from './apiErrors';

type Row=Record<string,any>;
type Props={api:(path:string,init?:RequestInit)=>Promise<Response>,load:(path:string,body?:Row,method?:string)=>Promise<any>,
 download:(path:string,name:string)=>Promise<void>,farmId:number|null,initial?:View,onBusinessChange:()=>void};
const sections=[
 ['batches','Start Processing Batch','Allocate fish, record methods and complete the batch.'],
 ['raw','Raw Fish Purchases','Manage suppliers, raw lots and supplier balances.'],
 ['methods','Processing Methods','Configure methods for sequential and combined processing.'],
 ['expenses','Processing Expenses','Record costs in the shared expense ledger.'],
 ['packaging','Packaging','Receive packaging materials and record completed runs.'],
 ['inventory','Finished Product Inventory','Review stock, quality decisions and lot labels.'],
 ['pricing','Processing Costing & Pricing','Review costs and model per-package prices.'],
 ['sales','Processed Sales & Invoices','Record sales, invoices and customer payments.'],
 ['reports','Processing History & Reports','Review yields, traceability and profitability.'],
 ['staff','Processing Staff','Assign permissions to staff with existing accounts.'],
] as const;
type View='overview'|typeof sections[number][0];
const root='/processing';
const today=()=>new Date().toISOString().slice(0,10);
const money=(value:unknown)=>value==null?'Unavailable':new Intl.NumberFormat('en-GH',{style:'currency',currency:'GHS'}).format(Number(value));
const num=(value:unknown)=>value==null?'—':new Intl.NumberFormat('en-GH',{maximumFractionDigits:4}).format(Number(value));
const date=(name:string,label:string)=><Field name={name} label={label} type="date" defaultValue={today()}/>;
const permissions=['processing.view','processing.create','processing.complete','processing.quality_review','packaging.create','inventory.adjust','pricing.view','finance.manage','sales.manage','processing_reports.view'];
const methods=['cash','mobile_money','bank_transfer','cheque','other'];
const label=(text:string)=>text.replaceAll('_',' ');
type FieldProps={name:string,label:string,type?:string,defaultValue?:string|number,optional?:boolean,step?:string};
function Field({name,label,type='text',defaultValue,optional,step}:FieldProps){
 return <label className="field"><span>{label}</span><input required={!optional} name={name} type={type} defaultValue={defaultValue} step={step??(type==='number'?'any':undefined)}/></label>;
}
function Choice({name,label,items,optional}:{name:string,label:string,items:[string|number,string][],optional?:boolean}){
 return <label className="field"><span>{label}</span><select name={name} required={!optional} defaultValue="">
  <option value="">{optional?'None / all':'Choose…'}</option>{items.map(([id,text])=><option key={id} value={id}>{text}</option>)}
 </select></label>;
}
const values=(items:string[]):[string,string][]=>items.map(item=>[item,label(item)]);
function Receipts(){
 return <><label className="field"><span>Receipt images or PDFs</span><input name="receipts" type="file" accept="image/jpeg,image/png,image/webp,application/pdf" multiple/></label>
  <Field name="exception_reason" label="Reason if receipt is unavailable" optional/></>;
}
async function receipts(form:FormData){
 const files=form.getAll('receipts').filter((value):value is File=>value instanceof File&&value.size>0);
 if(files.length>3||files.some(file=>file.size>5*1024*1024))throw new Error('Choose up to three receipts, each no larger than 5 MB.');
 return Promise.all(files.map(file=>new Promise<string>((resolve,reject)=>{
  const reader=new FileReader();reader.onerror=()=>reject(new Error('Unable to read receipt.'));
  reader.onload=()=>resolve(String(reader.result).split(',',2)[1]);reader.readAsDataURL(file);
 })));
}
const opt=(data:FormData,key:string)=>String(data.get(key)??'').trim()||undefined;
const str=(data:FormData,key:string)=>String(data.get(key)??'').trim();
const digits=(data:FormData,key:string)=>Number(data.get(key)||0);
const optionalNumber=(data:FormData,key:string)=>opt(data,key)?digits(data,key):undefined;
function paid(data:FormData,day:string){
 return digits(data,'paid')>0?{paid_on:day,amount_ghs:str(data,'paid'),method:str(data,'payment_method')||'cash'}:undefined;
}
function Paid(){
 return <><Field name="paid" label="Amount paid now (GHS)" type="number" optional/>
  <Choice name="payment_method" label="Payment method" items={values(methods)} optional/></>;
}
function PaymentFields(){
 return <>{date('paid_on','Payment date')}<Field name="amount_ghs" label="Amount (GHS)" type="number"/>
  <Choice name="method" label="Payment method" items={values(methods)}/><Field name="reference" label="Payment reference" optional/></>;
}
const payment=(d:FormData)=>({paid_on:str(d,'paid_on'),amount_ghs:str(d,'amount_ghs'),method:str(d,'method'),reference:opt(d,'reference')});

export function ProcessingWorkspace({load,api,download,farmId,initial,onBusinessChange}:Props){
 const [page,setPage]=useState<View>(initial??'overview');
 const [business,setBusiness]=useState<Row|null>(null);
 const [data,setData]=useState<Row|null>(null);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [busy,setBusy]=useState(false);
 const [batchId,setBatchId]=useState('');
 const [qualityBatch,setQualityBatch]=useState('');
 const [staff,setStaff]=useState<Row[]>([]);
 const [report,setReport]=useState<Row|null>(null);
 const [reportQuery,setReportQuery]=useState('');
 const [quote,setQuote]=useState<Row|null>(null);
 const [outputCount,setOutputCount]=useState(1);
 const pendingRequests=useRef(new Map<string,{fingerprint:string,key:string}>());
 const [saleRequest,setSaleRequest]=useState(()=>crypto.randomUUID());
 const refresh=useCallback(async()=>{
  const current=await load(root+'/business');
  setBusiness(current);
  setData(current.business_type!=='farmer'?await load(root+'/workspace'):null);
 },[load]);
 useEffect(()=>{void refresh().catch(()=>setError('Unable to load the processing workspace.'))},[refresh]);
 useEffect(()=>{if(initial)setPage(initial)},[initial]);
 useEffect(()=>{
  if(page==='staff'&&business?.is_owner)void load(root+'/staff').then(setStaff).catch(()=>setError('Unable to load processing staff.'));
 },[page,business?.is_owner,load]);
 function act(title:string,task:(d:FormData)=>Promise<void>,reset=true){
  return async(event:FormEvent<HTMLFormElement>)=>{
   event.preventDefault();
   const form=event.currentTarget;
   const values=new FormData(form);
   setBusy(true);setError('');setNotice('');
   try{await task(values);if(reset)form.reset();setNotice(title)}
   catch(problem){setError(problem instanceof Error?problem.message:String(problem))}
   finally{setBusy(false)}
  };
 }
 function submit(path:string,title:string,body:(d:FormData)=>Row|Promise<Row>,method='POST'){
  return act(title,async form=>{
   const payload=await body(form);
   const fingerprint=JSON.stringify(payload);
   const previous=pendingRequests.current.get(path);
   const key=previous?.fingerprint===fingerprint?previous.key:crypto.randomUUID();
   pendingRequests.current.set(path,{fingerprint,key});
   await load(root+path,{...payload,request_key:key},method);
   pendingRequests.current.delete(path);
   await refresh();
  });
 }
 const may=(permission:string)=>business?.is_owner!==false||(business.permissions??[]).includes(permission);
 const pagePermission:Partial<Record<View,string>>={expenses:'finance.manage',pricing:'pricing.view',sales:'sales.manage',reports:'processing_reports.view'};
 const formPermission:Record<string,string>={
  'Add a method':'processing.create','Create batch':'processing.create','Allocate raw fish':'processing.create',
  'Record processing step':'processing.create','Complete and reconcile batch':'processing.complete','Add supplier':'processing.create',
  'Receive purchased fish':'finance.manage','Register packaging material':'packaging.create','Receive packaging materials':'finance.manage',
  'Record a completed packaging run':'packaging.create','Record quality decision':'processing.quality_review',
  'Adjust stock or record a physical return':'inventory.adjust',
 };
 const form=(title:string,action:(event:FormEvent<HTMLFormElement>)=>void,content:ReactNode,button='Save')=>(!formPermission[title]||may(formPermission[title]))&&<section className="panel">
  <h3>{title}</h3><form className="farmform" onSubmit={action}>{content}<div className="farmactions"><button className="primary" disabled={busy}>{button}</button></div></form>
 </section>;
 const go=(view:View)=>{setPage(view);setNotice('');setError('');setQuote(null);window.scrollTo(0,0)};
 const settings=business?.is_owner!==false&&business&&form('Business type',act('Business settings saved',async d=>{
  await load(root+'/business',{name:str(d,'name'),business_type:str(d,'business_type')},'PUT');
  await refresh();onBusinessChange();
 },false),<>
  <Field name="name" label="Business name" defaultValue={business.name}/>
  <label className="field"><span>Business type</span><select name="business_type" defaultValue={business.business_type}>
   {business.business_type==='farmer'&&<option value="farmer">Fish Farmer</option>}
   <option value="processor">Fish Processor</option><option value="integrated">Integrated Fish Farmer and Processor</option>
  </select></label>
 </>,'Save business settings');
 if(!business)return error?<ErrorNotice message={error} retry={()=>void refresh().catch(()=>setError('Unable to load the processing workspace.'))}/>:<p role="status">Loading processing workspace…</p>;
 if(!data)return <>{error&&<ErrorNotice message={error}/>}<p>Enable fish processing for your business. Processor-only businesses can purchase fish and sell finished products without a farm or stocking cycle.</p>{settings}</>;
 const batches:Row[]=data.batches, lots:Row[]=data.lots, purchases:Row[]=data.raw_lots, expenses:Row[]=data.expenses, sales:Row[]=data.sales;
 const batchChoices:[number,string][]=batches.map(row=>[row.id,row.reference+' · '+row.method]);
 const lotChoices:[number,string][]=lots.map(row=>[row.id,row.reference+' · '+row.product]);
 const selected=batches.find(row=>row.id===Number(batchId));
 const methodChoices=values(data.methods);
 const expenseLines=(items:Row[])=>items.length?<div className="tablewrap"><table><thead><tr><th>Date / reference</th><th>Activity / category</th><th>Description / payee</th><th>Batch</th><th>Quantity / unit price</th><th>Total / paid / outstanding</th><th>Recorded by / evidence</th></tr></thead><tbody>
  {items.map(row=><tr key={row.id}><td>{row.occurred_on}<br/>{row.reference}</td><td>{label(row.activity)} / {row.category}</td><td>{row.description}<br/>{row.supplier}</td><td>{row.batch_id??'—'}</td>
   <td>{row.quantity??'—'} {row.unit_label} {row.unit_price==null?'':'at '+money(row.unit_price)}</td>
   <td>{money(row.amount_ghs)} / {money(row.paid_ghs)} / {money(row.outstanding_ghs)}<br/>{row.payment_status}{row.payments?.map((p:Row)=><div key={p.id}>{p.paid_on} · {label(p.method)} · {money(p.amount_ghs)}</div>)}</td>
   <td>{row.recorded_by_name}{row.attachments.map((item:Row)=><button className="outline small" key={item.id} onClick={()=>void download(root+'/expenses/'+row.id+'/attachments/'+item.id,'receipt-'+item.id+(item.media_type==='application/pdf'?'.pdf':'.'+item.media_type.split('/')[1]))}>Receipt</button>)}{row.exception_reason&&<div>{row.exception_reason}</div>}</td></tr>)}
 </tbody></table></div>:<p className="empty">No matching expenses.</p>;
 const expenseBody=async(d:FormData)=>({category:str(d,'category'),description:str(d,'description'),supplier:opt(d,'supplier'),occurred_on:str(d,'occurred_on'),
  amount_ghs:str(d,'amount_ghs'),attachments:await receipts(d),exception_reason:opt(d,'exception_reason'),initial_payment:paid(d,str(d,'occurred_on'))});
 return <>
  <div className="farmactions"><button className="outline" onClick={()=>go('overview')}>Processing Overview</button>
   {page!=='overview'&&<h2>{sections.find(([key])=>key===page)?.[1]}</h2>}</div>
  {error&&<ErrorNotice message={error}/>}
  {notice&&<p className="success" role="status">{notice}</p>}
  {page==='overview'&&<>
   <div className="statgrid">{([
    ['Active batches',batches.filter(row=>['draft','allocated','in_progress'].includes(row.status)).length],
    ['Raw fish available',num(purchases.reduce((sum,row)=>sum+Number(row.available_kg),0))+' kg'],
    ['Awaiting release',batches.filter(row=>['quality_review','packaged','held'].includes(row.status)).length],
    ['Released packages',lots.filter(row=>row.status==='released').reduce((sum,row)=>sum+row.available_units,0)],
    ['Processed sales',money(sales.reduce((sum,row)=>sum+row.total_ghs,0))],
    ['Recorded batch costs',money(batches.reduce((sum,row)=>sum+row.cost.total_cost_ghs,0))],
    ['Recorded waste and spoilage',num(batches.reduce((sum,row)=>sum+Number(row.mass_balance.waste_kg||0)+Number(row.mass_balance.spoilage_kg||0),0))+' kg'],
    ['Finished inventory value',lots.some(row=>row.inventory_value_ghs==null)?'Incomplete':money(lots.reduce((sum,row)=>sum+Number(row.inventory_value_ghs),0))],
   ] as const).map(([name,value])=><div className="stat" key={name}><small>{name}</small><strong>{value}</strong></div>)}</div>
   <div className="production-grid">{sections.filter(([key])=>key==='staff'?business.is_owner:!pagePermission[key]||may(pagePermission[key]!)).map(([key,title,description])=><button type="button" className="production-card" key={key} onClick={()=>go(key)}>
    <strong>{title}</strong><span>{description}</span></button>)}</div>
   {settings&&<details><summary>Business settings</summary>{settings}</details>}
  </>}
  {page==='staff'&&business.is_owner&&<>
   {form('Assign or update staff access',act('Processing staff access saved',async d=>{
    await load(root+'/staff',{email:str(d,'email'),permissions:d.getAll('permission').map(String)},'PUT');
    setStaff(await load(root+'/staff'));
   }),<>
    <Field name="email" label="Existing staff account email" type="email"/>
    <fieldset className="feeding-window"><legend>Processing permissions</legend>
     {permissions.map(permission=><label className="consent" key={permission}><input type="checkbox" name="permission" value={permission}/>{label(permission.replace('.',' ? '))}</label>)}
    </fieldset>
    <p className="muted">Choose no permissions to remove this account?s access.</p>
   </>)}
   <section className="panel"><h3>Assigned staff</h3>{staff.map(row=><p key={row.email}>{row.name} ? {row.email}<br/>{row.permissions.join(', ')}</p>)}</section>
  </>}
  {page==='methods'&&<>
   <section className="panel"><h3>Available processing methods</h3>{data.methods.map((method:string)=><p key={method}>{method}</p>)}</section>
   {form('Add a method',submit('/methods','Processing method added',d=>({name:str(d,'name')})),<Field name="name" label="Method name"/>)}
   {business.is_owner&&form('Configure required quality checks',submit('/quality-rules','Quality checklist saved',d=>({
    method:str(d,'method'),product:opt(d,'product')??'',checks:str(d,'checks').split('\n').map(value=>value.trim()).filter(Boolean),
   }),'PUT'),<>
    <Choice name="method" label="Processing method" items={methodChoices}/>
    <Field name="product" label="Specific product name (blank for every output)" optional/>
    <label className="field"><span>Required checks, one per line</span><textarea name="checks" rows={5}/></label>
   </>)}
   {data.quality_rules?.map((rule:Row)=><p key={rule.id}>{rule.method} ? {rule.product||'All products'} ? {rule.checks.join(', ')}</p>)}

  </>}
  {page==='raw'&&<>
   {form('Add supplier',submit('/suppliers','Supplier added',d=>({name:str(d,'name'),contact:opt(d,'contact')})),
    <><Field name="name" label="Supplier name"/><Field name="contact" label="Supplier contact" optional/></>)}
   {form('Receive purchased fish',submit('/purchases','Raw fish and purchase expense recorded',async d=>({
    supplier_id:digits(d,'supplier_id'),species:str(d,'species'),received_on:str(d,'received_on'),quantity_kg:str(d,'quantity_kg'),
    unit_price:str(d,'unit_price'),acquisition_cost:opt(d,'acquisition_cost')??'0',storage:str(d,'storage'),observations:opt(d,'observations'),
    attachments:await receipts(d),exception_reason:opt(d,'exception_reason'),initial_payment:paid(d,str(d,'received_on')),
   })),<>
    <Choice name="supplier_id" label="Supplier" items={data.suppliers.map((row:Row)=>[row.id,row.name])}/>
    <Field name="species" label="Fish species"/>{date('received_on','Purchase date')}
    <Field name="quantity_kg" label="Received weight (kg)" type="number"/><Field name="unit_price" label="Unit price (GHS/kg)" type="number"/>
    <Field name="acquisition_cost" label="Additional acquisition costs (GHS)" type="number" optional/>
    <Field name="storage" label="Storage location"/><Field name="observations" label="Receiving and quality observations" optional/><Paid/><Receipts/>
   </>)}
   <section className="panel"><h3>Raw material inventory</h3>{purchases.map(row=><p key={row.id}>{row.reference} · {row.species} · {row.storage} · {num(row.available_kg)} of {num(row.quantity_kg)} kg available</p>)}
    {expenseLines(expenses.filter(row=>row.usage==='raw_inventory'))}</section>
  </>}
  {page==='batches'&&<>
   {form('Create batch',act('Processing batch created',async d=>{
    const result=await load(root+'/batches',{facility:str(d,'facility'),method:str(d,'method'),started_on:str(d,'started_on'),notes:opt(d,'notes')});
    setBatchId(String(result.id));await refresh();
   }),<><Field name="facility" label="Facility"/><Choice name="method" label="Processing method" items={methodChoices}/>
    {date('started_on','Start date')}<Field name="notes" label="Batch notes" optional/></>)}
   <label className="field"><span>Select a batch</span><select value={batchId} onChange={event=>setBatchId(event.target.value)}>
    <option value="">Choose…</option>{batchChoices.map(([id,name])=><option key={id} value={id}>{name}</option>)}
   </select></label>
   {selected&&<>
    <p>{selected.reference} · {selected.facility} · {label(selected.status)} · {num(selected.cost.input_kg)} kg allocated</p>
    {selected.sources.map((row:Row)=><p key={row.id}>{row.species} · {num(row.quantity_kg)} kg · {row.harvest_id?'Harvest #'+row.harvest_id+' · '+row.unit_name+' · Cycle #'+row.cycle_id:'Purchased lot #'+row.raw_lot_id}</p>)}
    {['draft','allocated','in_progress'].includes(selected.status)&&form('Allocate raw fish',submit('/batches/'+selected.id+'/inputs','Raw fish allocated',d=>{
     const [source,id]=str(d,'source').split(':');return {source,source_id:Number(id),quantity_kg:str(d,'quantity_kg')};
    }),<><Choice name="source" label="Raw material source" items={[
     ...purchases.filter(row=>Number(row.available_kg)>0).map(row=>['purchased:'+row.id,row.reference+' · '+row.species+' · '+num(row.available_kg)+' kg']),
     ...data.harvests.filter((row:Row)=>row.available_kg>0).sort((a:Row,b:Row)=>Number(b.farm_id===farmId)-Number(a.farm_id===farmId)).map((row:Row)=>['harvest:'+row.id,'Harvest #'+row.id+' · '+row.harvested_on+' · '+num(row.available_kg)+' kg']),
    ]}/><Field name="quantity_kg" label="Allocate weight (kg)" type="number"/></>)}
    {['allocated','in_progress'].includes(selected.status)&&<>
     {form('Record processing step',submit('/batches/'+selected.id+'/steps','Processing step recorded',d=>({
      method:str(d,'method'),occurred_on:str(d,'occurred_on'),details:str(d,'details'),
     })),<><Choice name="method" label="Method" items={methodChoices}/>{date('occurred_on','Process date')}
      <Field name="details" label="Preparation, equipment, duration, temperature or process observations"/></>)}
     {form('Complete and reconcile batch',submit('/batches/'+selected.id+'/complete','Batch completed and awaiting quality review',d=>({
      completed_on:str(d,'completed_on'),outputs:Array.from({length:outputCount},(_,i)=>({name:str(d,'output'+i),quantity_kg:str(d,'weight'+i),is_byproduct:d.has('byproduct'+i)})),
      ...Object.fromEntries(['byproducts_kg','waste_kg','moisture_loss_kg','spoilage_kg','other_loss_kg','additions_kg'].map(key=>[key,opt(d,key)??'0'])),
      reconciliation_note:opt(d,'reconciliation_note'),
     })),<>
      {date('completed_on','Completion date')}
      {Array.from({length:outputCount},(_,i)=><fieldset className="feeding-window" key={i}><legend>Finished output {i+1}</legend>
       <Field name={'output'+i} label="Product name"/><Field name={'weight'+i} label="Output weight (kg)" type="number"/>
       <label className="consent"><input type="checkbox" name={'byproduct'+i}/>Recoverable by-product</label></fieldset>)}
      <button type="button" className="outline" disabled={outputCount>=30} onClick={()=>setOutputCount(outputCount+1)}>Add output</button>
      {outputCount>1&&<button type="button" className="outline" onClick={()=>setOutputCount(outputCount-1)}>Remove last output</button>}
      {['byproducts_kg','waste_kg','moisture_loss_kg','spoilage_kg','other_loss_kg','additions_kg'].map(key=><Field key={key} name={key} label={label(key)} type="number" optional/>)}
      <Field name="reconciliation_note" label="Measurement discrepancy or additions notes" optional/>
     </>,'Complete batch')}
    </>}
    {selected.steps.map((row:Row,i:number)=><p key={i}>{row.occurred_on} · {row.method} · {row.details}</p>)}
    {selected.mass_balance.yield_pct&&<p>Saleable yield {selected.mass_balance.yield_pct}%</p>}
   </>}
  </>}


  {page==='expenses'&&<>
   {form('Record expense',submit('/expenses','Expense saved in the shared ledger',async d=>({
    ...await expenseBody(d),activity:str(d,'activity'),classification:str(d,'classification')||'operating',
    batch_id:optionalNumber(d,'batch_id'),finished_lot_id:optionalNumber(d,'finished_lot_id'),farm_id:optionalNumber(d,'farm_id'),
    quantity:opt(d,'quantity'),unit_label:opt(d,'unit_label'),unit_price:opt(d,'unit_price'),
   })),<>
    {date('occurred_on','Expense date')}<Choice name="activity" label="Activity" items={values(['processing','packaging','distribution','production','general'])}/>
    <Choice name="category" label="Expense category" items={values(data.categories)}/>
    <Choice name="classification" label="Classification (defaults to operating)" items={values(['operating','capital'])} optional/>
    <Choice name="batch_id" label="Processing batch" items={batchChoices} optional/>
    <Choice name="finished_lot_id" label="Finished lot" items={lotChoices} optional/>
    <Choice name="farm_id" label="Associated farm" items={data.farms.map((row:Row)=>[row.id,row.name])} optional/>
    <Field name="description" label="Description"/><Field name="supplier" label="Supplier or payee" optional/>
    <Field name="quantity" label="Quantity" type="number" optional/><Field name="unit_label" label="Unit" optional/>
    <Field name="unit_price" label="Unit price (GHS)" type="number" optional/><Field name="amount_ghs" label="Total amount (GHS)" type="number"/>
    <Paid/><Receipts/>
   </>)}
   {form('Allocate a shared operating expense',act('Shared cost allocated',async d=>{
    await load(root+'/expenses/'+str(d,'expense_id')+'/allocations',{batch_id:digits(d,'batch_id'),amount_ghs:str(d,'amount_ghs'),basis:str(d,'basis')});await refresh();
   }),<>
    <Choice name="expense_id" label="Unassigned expense" items={expenses.filter(row=>row.usage==='expense'&&!row.batch_id&&row.classification==='operating').map(row=>[row.id,row.reference+' · '+row.description])}/>
    <Choice name="batch_id" label="Receiving batch" items={batchChoices}/>
    <Field name="amount_ghs" label="Allocated amount (GHS)" type="number"/><Field name="basis" label="Documented allocation basis"/>
   </>)}
   {form('Record supplier payment',act('Supplier payment recorded',async d=>{
    await load(root+'/expenses/'+str(d,'expense_id')+'/payments',payment(d));await refresh();
   }),<>
    <Choice name="expense_id" label="Outstanding expense or purchase" items={expenses.filter(row=>row.outstanding_ghs>0).map(row=>[row.id,row.reference+' · '+row.description+' · '+money(row.outstanding_ghs)])}/>
    <PaymentFields/>
   </>)}
   <section className="panel"><h3>Expense ledger</h3>{expenseLines(expenses)}</section>
  </>}
  {page==='packaging'&&<>
   {form('Register packaging material',submit('/materials','Packaging material created',d=>({name:str(d,'name')})),<Field name="name" label="Material name"/>)}
   {form('Receive packaging materials',submit('/material-receipts','Material stock and expense recorded',async d=>({
    material_id:digits(d,'material_id'),quantity:digits(d,'quantity'),expense:await expenseBody(d),
   })),<>
    <Choice name="material_id" label="Material" items={data.materials.map((row:Row)=>[row.id,row.name])}/>
    <Field name="quantity" label="Units received" type="number" step="1"/>{date('occurred_on','Purchase date')}
    <input type="hidden" name="category" value="Packaging"/>
    <Field name="description" label="Purchase description"/><Field name="supplier" label="Supplier" optional/>
    <Field name="amount_ghs" label="Total cost (GHS)" type="number"/><Paid/><Receipts/>
   </>)}
   <section className="panel"><h3>Packaging material stock</h3>{data.materials.map((row:Row)=><p key={row.id}>{row.name} · {row.available_units} available</p>)}</section>
   {form('Record a completed packaging run',submit('/packages','Finished lot created. Record a quality release before sale.',d=>({
    output_id:digits(d,'output_id'),material_id:optionalNumber(d,'material_id'),material_used:digits(d,'material_used'),
    units:digits(d,'units'),weight_per_unit_kg:str(d,'weight_per_unit_kg'),packaged_on:str(d,'packaged_on'),
    packaging:str(d,'packaging'),storage:str(d,'storage'),best_before:opt(d,'best_before'),shelf_life_basis:opt(d,'shelf_life_basis'),
    label_details:Object.fromEntries(['brand','ingredients','manufacturer','manufacturer_address','premises_address','country_of_origin','directions','storage_instructions'].map(key=>[key,opt(d,key)])),
   })),<>
    <Choice name="output_id" label="Finished output" items={batches.flatMap(row=>row.outputs.filter((output:Row)=>Number(output.available_kg)>0).map((output:Row)=>[output.id,row.reference+' · '+output.name+' · '+num(output.available_kg)+' kg']))}/>
    <Field name="packaging" label="Packaging type"/><Field name="units" label="Number of packages" type="number" step="1"/>
    <Field name="weight_per_unit_kg" label="Net weight per package (kg)" type="number"/>{date('packaged_on','Packaging date')}
    <Choice name="material_id" label="Packaging material" items={data.materials.map((row:Row)=>[row.id,row.name+' · '+row.available_units+' available'])} optional/>
    <Field name="material_used" label="Material units actually used" type="number" step="1" optional/>
    <Field name="storage" label="Storage location or conditions"/><Field name="best_before" label="Validated best-before date" type="date" optional/>
    <Field name="shelf_life_basis" label="Shelf-life rule or validation reference" optional/>
    <fieldset className="feeding-window"><legend>Printable product label</legend>
     {(['brand','ingredients','manufacturer','manufacturer_address','premises_address','country_of_origin','directions','storage_instructions'] as const).map(key=>
      <Field key={key} name={key} label={label(key)} optional/>)}
     <a href="https://fdaghana.gov.gh/wp-content/uploads/2024/02/GENERAL-LABELLING-REQUIREMENTS.pdf" target="_blank" rel="noreferrer">Ghana FDA labelling requirements</a>
    </fieldset>
   </>)}
  </>}
  {page==='inventory'&&<>
   {form('Record quality decision',act('Quality decision saved',async d=>{
    await load(root+'/batches/'+str(d,'batch_id')+'/quality',{decision:str(d,'decision'),checked_on:str(d,'checked_on'),observations:str(d,'observations'),checks:d.getAll('check').map(String)});await refresh();
   }),<>
    <label className="field"><span>Batch</span><select name="batch_id" required value={qualityBatch} onChange={event=>setQualityBatch(event.target.value)}>
     <option value="">Choose?</option>{batchChoices.map(([id,text])=><option key={id} value={id}>{text}</option>)}
    </select></label>
    {batches.find(row=>row.id===Number(qualityBatch))?.required_checks.map((check:string)=><label className="consent" key={check}>
     <input type="checkbox" name="check" value={check}/>{check}</label>)}
    <Choice name="decision" label="Decision" items={values(['hold','release','reject'])}/>{date('checked_on','Review date')}
    <Field name="observations" label="Sanitation, process, storage, packaging checks and corrective actions"/>
    <p className="muted">Release records the reviewer’s decision. Log method-appropriate checks and supporting observations.</p>
   </>)}
   {form('Adjust stock or record a physical return',act('Stock movement recorded',async d=>{
    await load(root+'/lots/'+str(d,'lot_id')+'/movements',{units:digits(d,'units'),sale_id:optionalNumber(d,'sale_id'),reason:str(d,'reason'),credit_ghs:opt(d,'credit_ghs')??'0',refund_ghs:opt(d,'refund_ghs')??'0',refund_method:opt(d,'refund_method')});await refresh();
   }),<>
    <Choice name="lot_id" label="Finished lot" items={lotChoices}/><Field name="units" label="Packages affected" type="number" step="1"/>
    <Choice name="sale_id" label="Original invoice for a physical return" items={sales.map(row=>[row.id,row.invoice_number])} optional/>
    <Field name="reason" label="Damage, spoilage, adjustment or return reason"/>
    <Field name="credit_ghs" label="Invoice credit (GHS)" type="number" optional/><Field name="refund_ghs" label="Amount refunded (GHS)" type="number" optional/>
    <Choice name="refund_method" label="Refund method" items={values(methods)} optional/>
   </>)}
   <section className="panel"><h3>Finished lots</h3>{lots.map(row=><details key={row.id}><summary>
    {row.reference} · {row.product} · {row.available_units} of {row.units} packages · {label(row.status)}</summary>
    <p>{row.method} · {row.weight_per_unit_kg} kg net · {row.packaging} · {row.storage} · Packaged {row.packaged_on}</p>
    <p>Inventory value {money(row.inventory_value_ghs)}{row.best_before?' · Best before '+row.best_before:''}</p>
    {row.movements.map((movement:Row)=><p key={movement.id}>{movement.occurred_on} · {movement.quantity_delta} packages · {movement.reason}</p>)}
    <button className="outline small" onClick={()=>void download(root+'/lots/'+row.id+'/label.pdf',row.reference+'.pdf')}>Download printable lot label</button>
    <button className="outline small" onClick={()=>void download(root+'/lots/'+row.id+'/label.pdf?qr=true',row.reference+'-qr.pdf')}>Download label with lot QR</button>
   </details>)}{!lots.length&&<p className="empty">Package a finished output to create a lot.</p>}</section>
  </>}
  {page==='pricing'&&<>
   {form('Price scenario per package',act('Price scenario calculated',async d=>{
    const params=new URLSearchParams({margin:str(d,'margin')||'20'});
    if(opt(d,'proposed'))params.set('proposed',str(d,'proposed'));
    setQuote(await load(root+'/lots/'+str(d,'lot_id')+'/pricing?'+params));
   },false),<>
    <Choice name="lot_id" label="Finished lot" items={lotChoices}/>
    <Field name="margin" label="Target gross margin (%)" type="number" defaultValue="20"/>
    <Field name="proposed" label="Proposed price (GHS/package)" type="number" optional/>
   </>,'Calculate price')}
   {quote&&<section className="panel"><h3>Price estimate</h3>
    <p>Break-even {money(quote.break_even)} per package · {money(quote.per_kg)} per kg · Target {money(quote.suggested)} per package</p>
    {quote.scenario&&<p>Proposed price result {money(quote.scenario.profit_ghs)} profit or loss per package · {num(quote.scenario.margin_pct)}% margin</p>}
    {Object.entries(quote.scenarios??{}).map(([key,row])=>{const scenario=row as Row;return <p key={key}>{label(key)} · {money(scenario.revenue_ghs)} price · {money(scenario.profit_ghs)} profit per package</p>})}
   </section>}
   <section className="panel"><h3>Batch costs</h3>{batches.map(row=><details key={row.id}><summary>{row.reference} · {row.method} · {money(row.cost.total_cost_ghs)}</summary>
    <p>Raw fish {money(row.cost.raw_ghs)} · Shared overhead {money(row.cost.shared_ghs)} · Materials {money(row.cost.material_ghs)} · {money(row.cost.cost_per_kg)} per finished kg</p>
    {Object.entries(row.cost.direct_ghs).map(([key,value])=><p key={key}>{label(key)} · {money(value)}</p>)}
    {!!row.cost.missing_input_costs.length&&<p className="alert">Production cost is missing for one or more harvest allocations. Complete pricing is unavailable.</p>}
   </details>)}</section>
  </>}
  {page==='sales'&&may('sales.manage')&&<>
   {form('Add customer',submit('/customers','Customer added to the sales ledger',d=>({name:str(d,'name'),contact:opt(d,'contact')})),<>
    <Field name="name" label="Customer name"/><Field name="contact" label="Telephone" optional/>
   </>)}
   {form('Record a processed-product sale',act('Sale and invoice recorded',async d=>{
    await load(root+'/sales',{lot_id:digits(d,'lot_id'),customer_id:digits(d,'customer_id'),units:digits(d,'units'),
     sold_on:str(d,'sold_on'),due_on:opt(d,'due_on'),unit_price:str(d,'unit_price'),request_key:saleRequest});
    setSaleRequest(crypto.randomUUID());await refresh();
   }),<>
    <Choice name="lot_id" label="Available released lot" items={lots.filter(row=>row.status==='released'&&row.available_units>0).map(row=>[
     row.id,row.reference+' · '+row.product+' · '+row.available_units+' available · Suggested '+money(row.pricing.suggested)])}/>
    <Choice name="customer_id" label="Customer" items={data.customers.map((row:Row)=>[row.id,row.name])}/>
    <Field name="units" label="Number of packages" type="number" step="1"/><Field name="unit_price" label="Selling price (GHS per package)" type="number"/>
    {date('sold_on','Sale date')}<Field name="due_on" label="Credit payment due date" type="date" optional/>
   </>)}
   {form('Record customer payment',act('Customer payment recorded',async d=>{
    await load(root+'/sales/'+str(d,'sale_id')+'/payments',payment(d));await refresh();
   }),<><Choice name="sale_id" label="Outstanding invoice" items={sales.filter(row=>row.outstanding_ghs>0).map(row=>[row.id,row.invoice_number+' · '+money(row.outstanding_ghs)])}/><PaymentFields/></>)}
   <section className="panel"><h3>Processed product invoices</h3>{sales.map(row=><div className="item" key={row.id}>
    <b>{row.invoice_number}</b> · {row.packages_sold} packages · {money(row.total_ghs)} · {money(row.outstanding_ghs)} outstanding
    <button className="outline small" onClick={()=>void download(root+'/sales/'+row.id+'/invoice.pdf',row.invoice_number+'.pdf')}>Download invoice PDF</button>
   </div>)}</section>
  </>}
  {page==='reports'&&may('processing_reports.view')&&<>
   <ProcessingEvidenceLibrary load={load} api={api} download={download} batches={may('processing.create')?batches:undefined}/>
   {form('Processing report filters',act('Report generated',async d=>{
    const filters=new URLSearchParams();for(const key of ['start','end','batch_id','activity','method','product','species','farm_id','unit_id']){
     const value=opt(d,key);if(value)filters.set(key,value);
    }
    if(!filters.has('start')&&!filters.has('end')&&str(d,'period')){
     const now=new Date(),year=now.getUTCFullYear(),month=now.getUTCMonth();
     const monday=new Date(Date.UTC(year,month,now.getUTCDate()-((now.getUTCDay()+6)%7)));
     const start=({weekly:monday,monthly:new Date(Date.UTC(year,month,1)),quarterly:new Date(Date.UTC(year,Math.floor(month/3)*3,1)),
      yearly:new Date(Date.UTC(year,0,1))} as Record<string,Date>)[str(d,'period')];
     if(start){filters.set('start',start.toISOString().slice(0,10));filters.set('end',today())}
    }
    setReport(await load(root+'/report?'+filters));setReportQuery(filters.toString());
   },false),<>
    <Choice name="period" label="Period (used without custom dates)" items={values(['weekly','monthly','quarterly','yearly'])} optional/>
    <Field name="start" label="From" type="date" optional/><Field name="end" label="To" type="date" optional/>
    <Choice name="batch_id" label="Batch" items={batchChoices} optional/><Choice name="method" label="Method" items={methodChoices} optional/>
    <Choice name="activity" label="Expense activity" items={values(['production','processing','packaging','distribution','general'])} optional/>
    <Choice name="farm_id" label="Source farm" items={data.farms.map((row:Row)=>[row.id,row.name])} optional/>
    <Choice name="unit_id" label="Source production unit" items={[...new Map<number,string>(batches.flatMap(row=>row.sources.filter((item:Row)=>item.unit_id).map((item:Row)=>[item.unit_id,item.unit_name])))]} optional/>
    <Field name="product" label="Product name" optional/><Field name="species" label="Species" optional/>
   </>,'Generate report')}
   {report&&<section className="panel"><h3>Processing profitability</h3>
    <p>Revenue {money(report.revenue_ghs)} · Cost of sales {money(report.cost_of_sales_ghs)} · Gross profit {money(report.gross_profit_ghs)}</p>
    <p>Unallocated period expenses {money(report.unallocated_expenses_ghs)} · Processing result {money(report.processing_result_ghs)}</p>
    <button className="outline small" onClick={()=>void download(root+'/report?'+reportQuery+'&format=csv','processing-report.csv')}>Export CSV</button>
    <button className="outline small" onClick={()=>void download(root+'/report?'+reportQuery+'&format=pdf','processing-report.pdf')}>Download PDF</button>
    <p>Fresh fish revenue {money(report.fresh_revenue_ghs)} ? Consolidated gross profit {money(report.consolidated_gross_profit_ghs)} ? Result after unallocated business expenses {money(report.consolidated_result_ghs)}</p>
    <p className="muted">Fresh fish costs are indicative where production costs are available. Invoice credits reduce revenue on the return date.</p>
    <h3>Finished product profitability</h3>{report.by_product.map((row:Row)=><p key={row.lot}>{row.product} ? {row.lot} ? Revenue {money(row.revenue_ghs)} ? Gross profit {money(row.gross_profit_ghs)}</p>)}
    <h3>Batch profitability</h3>{report.by_batch.map((row:Row)=><p key={row.batch_id}>{row.reference} ? {row.method} ? Revenue {money(row.revenue_ghs)} ? Gross profit {money(row.gross_profit_ghs)}</p>)}
    <h3>Batch history and yield</h3>{report.batches.map((row:Row)=><p key={row.id}>{row.reference} · {row.method} · {row.facility} · {row.mass_balance.yield_pct??'—'}% yield · {money(row.cost.total_cost_ghs)} recorded cost</p>)}
    <h3>Expense detail</h3>{expenseLines(report.expenses)}
   </section>}
  </>}
 </>;
}
