import {useEffect,useState} from 'react';

type Row=Record<string,any>;
type Load=(path:string,body?:Row)=>Promise<any>;
const today=()=>new Date().toISOString().slice(0,10);
const ghs=(n:number)=>'GH₵'+n.toLocaleString('en-GH',{minimumFractionDigits:2,maximumFractionDigits:2});
const paymentMethods=[['cash','Cash'],['mobile_money','Mobile Money'],['bank_transfer','Bank transfer'],['cheque','Cheque'],['other','Other']];
const readFile=(file:File)=>new Promise<string>((resolve,reject)=>{
 const reader=new FileReader();
 reader.onload=()=>resolve(String(reader.result).split(',')[1]??'');
 reader.onerror=()=>reject(new Error('Could not read the receipt.'));
 reader.readAsDataURL(file);
});

export function FarmExpenses({farmId,units,cycles,load,download,onSaved,refreshKey,chart}:{farmId:number,units:Row[],cycles:Row[],load:Load,download:(path:string,name:string)=>Promise<void>,onSaved:()=>Promise<void>,refreshKey:unknown,chart:(title:string,data:Row[])=>React.ReactNode}){
 const root='/farms/'+farmId+'/expenses';
 const [tab,setTab]=useState('Record Expense');
 const [records,setRecords]=useState<Row|null>(null);
 const [form,setForm]=useState<Row>({occurred_on:today(),classification:'operating',method:'cash',paid_on:today()});
 const [files,setFiles]=useState<File[]>([]);
 const [search,setSearch]=useState('');
 const [statusFilter,setStatusFilter]=useState('');
 const [selected,setSelected]=useState<number|null>(null);
 const [payment,setPayment]=useState<Row>({method:'cash',paid_on:today()});
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [revision,setRevision]=useState(0);
 const [since,setSince]=useState('');
 const [until,setUntil]=useState('');
 const [unitFilter,setUnitFilter]=useState('');
 const [categoryFilter,setCategoryFilter]=useState('');
 useEffect(()=>{
   let current=true;
   load(root).then(data=>{if(current)setRecords(data)}).catch(problem=>{if(current){setRecords(null);setError(String(problem))}});
   return ()=>{current=false};
 },[root,load,revision]);
 const rows:Row[]=records?.expenses??[];
 const shown=rows.filter(row=>(row.description+' '+(row.supplier??'')+' '+row.reference).toLowerCase().includes(search.toLowerCase())&&
  (!statusFilter||row.payment_status===statusFilter)&&(!since||row.occurred_on>=since)&&(!until||row.occurred_on<=until)&&
  (!unitFilter||String(row.unit_id)===unitFilter)&&(!categoryFilter||row.category===categoryFilter));
 const detail=rows.find(row=>row.id===selected);
 function field(name:string,label:string,type='text',props:Row={}){
   return <label className="field"><span>{label}</span><input type={type} value={form[name]??''} onChange={event=>setForm({...form,[name]:event.target.value})} {...props}/></label>;
 }
 async function save(event:React.FormEvent){
   event.preventDefault();setBusy(true);setError('');setNotice('');
   try{
     if(files.length>3||files.some(file=>file.size>5*1024*1024))throw new Error('Select up to three receipts, each 5 MB or smaller.');
     const attachments=await Promise.all(files.map(readFile));
     const result=await load(root,{...form,unit_id:form.unit_id?Number(form.unit_id):null,cycle_id:form.cycle_id?Number(form.cycle_id):null,
       attachments,initial_payment:form.paid_amount?{amount_ghs:form.paid_amount,paid_on:form.paid_on,method:form.method,reference:form.reference||null}:null});
     setSelected(result.id);setFiles([]);setForm({occurred_on:today(),classification:'operating',method:'cash',paid_on:today()});setTab('Expense History');
     setNotice('Expense recorded.');setRevision(value=>value+1);await onSaved();
   }catch(problem){setError(String(problem))}
   finally{setBusy(false)}
 }
 async function update(path:string,body:Row,success:string){
   setBusy(true);setError('');setNotice('');
   try{await load(root+path,body);setNotice(success);setRevision(value=>value+1);await onSaved()}
   catch(problem){setError(String(problem))}
   finally{setBusy(false)}
 }
 return <section className="panel">
  <h2>Farm Expenses</h2>
  <div className="farmactions workspace-tabs">{['Record Expense','Expense History','Receipts and Evidence','Expense Reports'].map(label=><button type="button" className="outline" key={label} aria-pressed={tab===label} onClick={()=>{setTab(label);setError('')}}>{label}</button>)}</div>
  {error&&<p className="alert" role="alert">{error}</p>}
  {notice&&<p className="success" role="status">{notice}</p>}
  {!records&&!error&&<p role="status">Loading farm expenses…</p>}
  {tab==='Record Expense'&&records&&<form className="farmform" onSubmit={save}>
   <p className="muted">Record feed purchases in Inventory. Record loan principal repayments in Loan Management.</p>
   {field('occurred_on','Expense date','date',{required:true,max:today()})}
   <label className="field"><span>Category</span><select value={form.category??''} required onChange={event=>setForm({...form,category:event.target.value})}><option value="">Choose a category</option>{records.categories.map((name:string)=><option key={name}>{name}</option>)}</select></label>
   {field('description','Description','text',{required:true,maxLength:300})}
   {field('amount_ghs','Expense amount (GH₵)','number',{required:true,min:.01,step:.01})}
   {field('supplier','Supplier or payee','text',{maxLength:150})}
   <label className="field"><span>Classification</span><select value={form.classification} onChange={event=>setForm({...form,classification:event.target.value})}><option value="operating">Operating expense</option><option value="capital">Capital expenditure</option></select></label>
   <label className="field"><span>Production unit</span><select value={form.unit_id??''} onChange={event=>setForm({...form,unit_id:event.target.value,cycle_id:''})}><option value="">Farm-wide</option>{units.map(unit=><option key={unit.id} value={unit.id}>{unit.name}</option>)}</select></label>
   {form.unit_id&&<label className="field"><span>Stocking cycle</span><select value={form.cycle_id??''} onChange={event=>setForm({...form,cycle_id:event.target.value})}><option value="">Unit-wide</option>{cycles.filter(cycle=>cycle.unit_id===Number(form.unit_id)).map(cycle=><option key={cycle.cycle_id} value={cycle.cycle_id}>#{cycle.cycle_id} | {cycle.species} | {cycle.stocked_on}</option>)}</select></label>}
   {field('notes','Notes','text',{maxLength:1000})}
   <label className="field"><span>Receipt images or PDFs</span><input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" multiple onChange={event=>setFiles(Array.from(event.target.files??[]))}/></label>
   {files.length>0&&<p>{files.length} receipt file(s) selected <button type="button" className="outline small" onClick={()=>setFiles([])}>Clear receipts</button></p>}
   {!files.length&&field('exception_reason','Reason a receipt is unavailable','text',{required:true,maxLength:1000})}
   {field('paid_amount','Amount already paid (GH₵, leave blank if unpaid)','number',{min:.01,step:.01,max:form.amount_ghs})}
   {form.paid_amount&&<>
    {field('paid_on','Payment date','date',{required:true,min:form.occurred_on,max:today()})}
    <label className="field"><span>Payment method</span><select value={form.method} onChange={event=>setForm({...form,method:event.target.value})}>{paymentMethods.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
    {field('reference','Payment reference','text',{maxLength:120})}
   </>}
   <button className="primary" disabled={busy}>{busy?'Saving…':'Save expense'}</button>
  </form>}
  {(tab==='Expense History'||tab==='Receipts and Evidence')&&records&&<>
   <div className="farmform">
    <label className="field"><span>Search expenses</span><input value={search} onChange={event=>setSearch(event.target.value)}/></label>
    <label className="field"><span>From</span><input type="date" value={since} onChange={event=>setSince(event.target.value)}/></label>
    <label className="field"><span>To</span><input type="date" value={until} onChange={event=>setUntil(event.target.value)}/></label>
    <label className="field"><span>Category</span><select value={categoryFilter} onChange={event=>setCategoryFilter(event.target.value)}><option value="">All</option>{records.categories.map((name:string)=><option key={name}>{name}</option>)}</select></label>
    <label className="field"><span>Unit</span><select value={unitFilter} onChange={event=>setUnitFilter(event.target.value)}><option value="">All</option>{units.map(unit=><option key={unit.id} value={unit.id}>{unit.name}</option>)}</select></label>
    <label className="field"><span>Payment status</span><select value={statusFilter} onChange={event=>setStatusFilter(event.target.value)}><option value="">All</option><option value="unpaid">Unpaid</option><option value="partial">Partially paid</option><option value="paid">Paid</option></select></label>
   </div>
   {shown.length?<div className="tablewrap"><table><thead><tr>{['Reference','Date','Category','Description','Supplier','Amount','Outstanding','Status','Evidence'].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>
    {shown.map(row=><tr key={row.id}><td><button type="button" className="outline small" onClick={()=>{setSelected(row.id);setPayment({method:'cash',paid_on:today()})}}>{row.reference}</button></td><td>{row.occurred_on}</td><td>{row.category}</td><td>{row.description}</td><td>{row.supplier??'Not provided'}</td><td>{ghs(row.amount_ghs)}</td><td>{ghs(row.outstanding_ghs)}</td><td>{row.payment_status} | {row.review_status.replaceAll('_',' ')}</td><td>{row.attachments.length?row.attachments.length+' receipt(s)':'Exception'}</td></tr>)}
   </tbody></table></div>:<p className="empty">No expenses match this view.</p>}
   {detail&&<section className="panel"><h3>{detail.reference} | {detail.description}</h3>
    <p>{detail.category} | {detail.classification} | Recorded by user #{detail.recorded_by} | {detail.created_at}</p>
    <p>{detail.notes}</p><p>Expense {ghs(detail.amount_ghs)} | Paid {ghs(detail.paid_ghs)} | Outstanding {ghs(detail.outstanding_ghs)}</p>
    {detail.exception_reason&&<p>Receipt exception: {detail.exception_reason}</p>}
    {detail.attachments.map((file:Row)=><button type="button" key={file.id} className="outline small" onClick={()=>void download(root+'/'+detail.id+'/attachments/'+file.id,'receipt-'+file.id+'.'+({'application/pdf':'pdf','image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[String(file.media_type)]??'bin'))}>Download receipt #{file.id}</button>)}
    {detail.review_status!=='approved'&&<button type="button" className="outline" disabled={busy} onClick={()=>{const reason=window.prompt('Approval reason');if(reason?.trim())void update('/'+detail.id+'/approve',{reason},'Expense approved.')}}>Approve expense</button>}
    {detail.payments.map((item:Row)=><p className="item" key={item.id}>{item.paid_on} | {ghs(item.amount_ghs)} | {item.method.replaceAll('_',' ')} | {item.reference??'No reference'}</p>)}
    {detail.outstanding_ghs>0&&<form className="farmform" onSubmit={event=>{event.preventDefault();void update('/'+detail.id+'/payments',payment,'Supplier payment recorded.')}}>
     <label className="field"><span>Payment date</span><input type="date" required min={detail.occurred_on} max={today()} value={payment.paid_on} onChange={event=>setPayment({...payment,paid_on:event.target.value})}/></label>
     <label className="field"><span>Amount (GH₵)</span><input type="number" required min=".01" step=".01" max={detail.outstanding_ghs} value={payment.amount_ghs??''} onChange={event=>setPayment({...payment,amount_ghs:event.target.value})}/></label>
     <label className="field"><span>Method</span><select value={payment.method} onChange={event=>setPayment({...payment,method:event.target.value})}>{paymentMethods.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
     <label className="field"><span>Reference</span><input maxLength={120} value={payment.reference??''} onChange={event=>setPayment({...payment,reference:event.target.value})}/></label>
     <button className="primary" disabled={busy}>Record supplier payment</button>
    </form>}
   </section>}
  </>}
  {tab==='Expense Reports'&&<CashActivity farmId={farmId} load={load} refreshKey={refreshKey} chart={chart} download={download}/>}
 </section>;
}

export function CashActivity({farmId,load,refreshKey,chart,download,persistKey}:{persistKey?:string,farmId:number,load:Load,refreshKey:unknown,chart:(title:string,data:Row[])=>React.ReactNode,download:(path:string,name:string)=>Promise<void>}){
 const initial={grouping:'monthly',start:today().slice(0,4)+'-01-01',end:today().slice(0,4)+'-12-31'};
 const [selection,setSelection]=useState(()=>{
  try{return persistKey?{...initial,...JSON.parse(sessionStorage.getItem(persistKey)??'{}')}:initial}
  catch{return initial}
 });
 const [draft,setDraft]=useState(selection);
 function applyFilter(filter:typeof initial){
  setSelection(filter);
  if(persistKey)sessionStorage.setItem(persistKey,JSON.stringify(filter));
 }
 const [report,setReport]=useState<Row|null>(null);
 const [error,setError]=useState('');
 useEffect(()=>{
   let current=true;setError('');setReport(null);
   load('/farms/'+farmId+'/cash-activity?'+new URLSearchParams(selection)).then(data=>{if(current)setReport(data)})
    .catch(problem=>{if(current)setError(String(problem))});
   return ()=>{current=false};
 },[farmId,load,refreshKey,selection]);
 const title=selection.grouping[0].toUpperCase()+selection.grouping.slice(1)+' Cash Activity · GHS';
 return <section className="panel">
  <h2>Cash Activity</h2>
  <form className="farmform" onSubmit={event=>{event.preventDefault();applyFilter({...draft})}}>
   <label className="field"><span>Reporting period</span><select value={draft.grouping} onChange={event=>setDraft({...draft,grouping:event.target.value})}>
    {['weekly','monthly','quarterly','yearly','custom'].map(value=><option key={value}>{value}</option>)}
   </select></label>
   <label className="field"><span>Start date</span><input type="date" required max={draft.end} value={draft.start} onChange={event=>setDraft({...draft,start:event.target.value})}/></label>
   <label className="field"><span>End date</span><input type="date" required min={draft.start} value={draft.end} onChange={event=>setDraft({...draft,end:event.target.value})}/></label>
   <div className="farmactions"><button className="primary">Apply Filter</button><button type="button" className="outline" onClick={()=>{setDraft(initial);applyFilter(initial)}}>Reset Filter</button></div>
  </form>
  <p className="muted">Weeks start Monday. Balances are as of the reporting end date. Cash activity uses customer and supplier payment dates and dated feed receipts. Legacy plan expenses do not establish cash payment.</p>
  {error?<p role="alert" className="alert">{error}</p>:!report?<p role="status">Loading cash activity…</p>:<>
   <div className="statgrid">{[['Total inflows (customer payments)','payments_received_ghs'],['Feed purchases','feed_purchase_cash_outflow_ghs'],['Other expenses paid','recorded_expenses_ghs'],['Total cash outflows','total_outflows_ghs'],['Net cash movement','net_cash_ghs'],['Customer receivables as of end date','customer_receivables_ghs'],['Supplier payables as of end date','supplier_payables_ghs']].map(([label,key])=><div className="stat" key={key}><small>{label}</small><strong>{ghs(report.summary[key])}</strong></div>)}</div>
   <div className="farmactions">
    <button className="outline" onClick={()=>void download('/farms/'+farmId+'/cash-activity.pdf?'+new URLSearchParams(selection),'cash-activity.pdf')}>Download PDF</button>
    <button className="outline" onClick={()=>void download('/farms/'+farmId+'/cash-activity.csv?'+new URLSearchParams(selection),'cash-activity.csv')}>Download CSV</button>
   </div>
   {chart(title,report.periods)}
   <details><summary>Cash activity by period</summary><div className="tablewrap"><table><thead><tr><th>Period</th><th>Received</th><th>Feed purchases</th><th>Other paid</th><th>Net cash</th></tr></thead><tbody>{report.periods.map((row:Row)=><tr key={row.period}><td>{row.period}</td><td>{ghs(row.payments_received_ghs)}</td><td>{ghs(row.feed_purchase_cash_outflow_ghs)}</td><td>{ghs(row.recorded_expenses_ghs)}</td><td>{ghs(row.net_cash_ghs)}</td></tr>)}</tbody></table></div></details>
   <details><summary>Recent cash transactions in this period</summary>
    {report.recent_transactions?.length?<div className="tablewrap"><table><thead><tr><th>Date</th><th>Type</th><th>Cash movement</th></tr></thead><tbody>
     {report.recent_transactions.map((row:Row,index:number)=><tr key={index}><td>{row.date}</td><td>{row.type}</td><td>{ghs(row.amount_ghs)}</td></tr>)}
    </tbody></table></div>:<p className="empty">No cash transactions recorded for this period.</p>}
   </details>
   <details><summary>Accrued expenses by category</summary>{report.accrued_by_category.length?report.accrued_by_category.map((row:Row)=><p className="item" key={row.category}>{row.category} | {ghs(row.amount_ghs)}</p>):<p className="empty">No expenses recorded for this period.</p>}</details>
  </>}
 </section>;
}
