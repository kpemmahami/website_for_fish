
import {useEffect,useState,type FormEvent} from 'react';
import {ErrorNotice} from './apiErrors';

type Row=Record<string,any>;
type Props={load:(path:string,body?:Row,method?:string)=>Promise<any>,
 api:(path:string,init?:RequestInit)=>Promise<Response>,farmId?:number,batches?:Row[],
 download:(path:string,name:string)=>Promise<void>};
const types=['harvest_transfer','processing','packaging','quality','spoilage','stock_adjustment'];
const names:Record<string,string>={'video/mp4':'mp4','video/webm':'webm','image/jpeg':'jpg','image/png':'png','image/webp':'webp','application/pdf':'pdf'};

export function ProcessingEvidenceLibrary({load,api,farmId,batches,download}:Props){
 const [data,setData]=useState<Row|null>(null);
 const [page,setPage]=useState(1);
 const [revision,refresh]=useState(0);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [preview,setPreview]=useState<{url:string,type:string}|null>(null);
 const [filter,setFilter]=useState({start:'',end:''});
 useEffect(()=>{
  let active=true;
  const query=new URLSearchParams({page:String(page)});
  if(farmId)query.set('farm_id',String(farmId));
  if(filter.start)query.set('start',filter.start);
  if(filter.end)query.set('end',filter.end);
  void load('/processing/evidence?'+query).then(result=>{if(active){setData(result);setError('')}})
   .catch(()=>{if(active)setError('Unable to load processing evidence.')});
  return ()=>{active=false};
 },[load,page,farmId,revision,filter]);
 useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview.url)},[preview]);
 async function upload(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const form=event.currentTarget;
  const input=new FormData(form);
  const file=input.get('file');
  if(!(file instanceof File)||!names[file.type]){setError('Choose a supported evidence file.');return}
  if(file.size>(file.type.startsWith('video/')?30:5)*1024*1024){setError('The evidence file exceeds its upload size limit.');return}
  setBusy(true);setError('');
  try{
   const content=await new Promise<string>((resolve,reject)=>{
    const reader=new FileReader();reader.onerror=()=>reject(new Error('Unable to read evidence.'));
    reader.onload=()=>resolve(String(reader.result).split(',',2)[1]);reader.readAsDataURL(file);
   });
   await load('/processing/evidence',{batch_id:Number(input.get('batch_id')),stage:String(input.get('stage')),
    recorded_on:String(input.get('recorded_on')),notes:String(input.get('notes'))||null,media_type:file.type,content});
   form.reset();refresh(value=>value+1);setPage(1);
  }catch(problem){setError(String(problem))}
  finally{setBusy(false)}
 }
 return <section className="panel">
  <h3>Processing Evidence Library</h3>
  {batches&&<details><summary>Attach evidence to a batch</summary><form className="farmform" onSubmit={upload}>
   <label className="field"><span>Batch</span><select name="batch_id" required defaultValue=""><option value="">Choose…</option>
    {batches.map(row=><option value={row.id} key={row.id}>{row.reference}</option>)}</select></label>
   <label className="field"><span>Activity</span><select name="stage" required>{types.map(type=><option value={type} key={type}>{type.replaceAll('_',' ')}</option>)}</select></label>
   <label className="field"><span>Evidence date</span><input type="date" name="recorded_on" required defaultValue={new Date().toISOString().slice(0,10)}/></label>
   <label className="field"><span>Evidence file</span><input name="file" type="file" required accept="image/jpeg,image/png,image/webp,application/pdf,video/mp4,video/webm"/></label>
   <label className="field"><span>Notes or linked event reference</span><input name="notes" maxLength={1000}/></label>
   <button className="primary" disabled={busy}>Attach evidence</button>
  </form></details>}
  <form className="farmactions" onSubmit={event=>{
   event.preventDefault();const values=new FormData(event.currentTarget);
   setPage(1);setFilter({start:String(values.get('start')??''),end:String(values.get('end')??'')});
  }}>
   <label className="field"><span>From</span><input name="start" type="date"/></label>
   <label className="field"><span>To</span><input name="end" type="date"/></label>
   <button className="outline small">Filter evidence</button>
  </form>
  {error&&<ErrorNotice message={error} retry={()=>refresh(value=>value+1)}/>}
  {data?.items?.length?data.items.map((row:Row)=><div className="item" key={row.id}>
   <b>{row.batch_reference} · {row.stage.replaceAll('_',' ')}</b><small>{row.recorded_on} · {row.recorded_by} · {Math.round(row.size_bytes/1024)} KB · Locked</small>
   {row.notes&&<p>{row.notes}</p>}
   <div className="farmactions">
    {row.media_type!=='application/pdf'&&<button className="outline small" disabled={busy} onClick={async()=>{
     setBusy(true);setError('');
     try{const response=await api('/processing/evidence/'+row.id+'/content');setPreview({url:URL.createObjectURL(await response.blob()),type:row.media_type})}
     catch{setError('Evidence unavailable.')}finally{setBusy(false)}
    }}>Preview</button>}
    <button className="outline small" onClick={()=>void download('/processing/evidence/'+row.id+'/content','processing-evidence-'+row.id+'.'+names[row.media_type])}>Download</button>
   </div>
  </div>):data&&<p className="empty">No processing evidence matches these filters.</p>}
  {preview&&<div className="item">
   {preview.type.startsWith('video/')?<video controls className="activity-media" src={preview.url}/>:<img className="activity-media" src={preview.url} alt="Processing evidence"/>}
   <button className="outline" onClick={()=>setPreview(null)}>Close preview</button>
  </div>}
  {data&&<div className="farmactions"><button className="outline small" disabled={page<=1} onClick={()=>setPage(page-1)}>Previous</button>
   <span>{data.total} matching files</span><button className="outline small" disabled={page*data.size>=data.total} onClick={()=>setPage(page+1)}>Next</button></div>}
 </section>;
}
