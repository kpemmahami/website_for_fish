import {useState} from 'react';

type Window = {name:string,start:string,end:string,recommended_kg:number|null,allocation_pct:number|null};
type Schedule = {id:number,effective_on:string,sessions:Window[]};
type Props = {
 path:string;
 today:string;
 suggestedCount?:number;
 load:(path:string,body?:Record<string,unknown>,method?:string)=>Promise<any>;
 changed:()=>void;
};

const emptyWindow=():Window=>({name:'',start:'',end:'',recommended_kg:null,allocation_pct:null});

export function feedingStatus(status:string){
 return ({recorded:'Completed',missed:'Overdue',upcoming:'Upcoming',due:'Due',skipped:'Skipped'} as Record<string,string>)[status]??status;
}

export function ghanaFeedingTime(value?:string){
 if(!value)return 'Actual time unavailable';
 const timestamp=new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value)?value:value+'Z');
 return Number.isNaN(timestamp.getTime())?'Actual time unavailable':new Intl.DateTimeFormat('en-GH',{
  timeZone:'Africa/Accra',hour:'2-digit',minute:'2-digit',hourCycle:'h23',
 }).format(timestamp);
}

export function FeedingScheduleEditor({path,today,suggestedCount,load,changed}:Props){
 const [schedules,setSchedules]=useState<Schedule[]|null>(null);
 const [effective,setEffective]=useState(today);
 const [windows,setWindows]=useState<Window[]>([emptyWindow()]);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [busy,setBusy]=useState(false);
 async function read(){
  const saved:Schedule[]=await load(path+'/schedule');
  setSchedules(saved);
  return saved;
 }
 function resize(count:number){
  setWindows(items=>Array.from({length:count},(_,index)=>items[index]??emptyWindow()));
 }
 function editWindow(index:number,value:Partial<Window>){
  setWindows(items=>items.map((item,i)=>i===index?{...item,...value}:item));
 }
 return <details id="manage-feeding-schedule" onToggle={event=>{
  if(event.currentTarget.open&&!schedules&&!busy){
   setBusy(true);
   void read().catch(problem=>setError(String(problem))).finally(()=>setBusy(false));
  }
 }}>
  <summary>Manage Feeding Schedule</summary>
  <p className="muted">Set Ghana-time windows for this cycle. Save a new effective date when the feeding frequency changes. Enter optional kilograms for an operational plan, or set percentages totaling 100% to split an approved daily ration.</p>
  {error&&<p className="alert" role="alert">{error}</p>}
  {notice&&<p role="status">{notice}</p>}
  {schedules?.length? <div className="farmactions">{schedules.map(schedule=>
   <button className="outline small" key={schedule.id} type="button" onClick={()=>{
    setWindows(schedule.sessions);setEffective(schedule.effective_on>=today?schedule.effective_on:today);setNotice('');
   }}>Use {schedule.effective_on} schedule ({schedule.sessions.length} sessions)</button>
  )}</div>:null}
  <form className="farmform" onSubmit={async event=>{
   event.preventDefault();setError('');setNotice('');setBusy(true);
   try{
    await load(path+'/schedule',{effective_on:effective,sessions:windows},'PUT');
    changed();setNotice('Schedule saved, effective '+effective);
    await read();
   }catch(problem){setError(String(problem))}
   finally{setBusy(false)}
  }}>
   <label className="field"><span>Effective date</span><input required type="date" min={today} value={effective} onChange={event=>setEffective(event.target.value)}/></label>
   <label className="field"><span>Daily sessions</span><select value={windows.length} onChange={event=>resize(Number(event.target.value))}>{Array.from({length:24},(_,index)=><option key={index} value={index+1}>{index+1}</option>)}</select></label>
   {suggestedCount&&suggestedCount!==windows.length&&<button className="outline" type="button"
    onClick={()=>resize(suggestedCount)}>Use suggested count ({suggestedCount})</button>}
   {windows.map((window,index)=><fieldset className="feeding-window" key={index}>
    <legend>Session {index+1}</legend>
    <label className="field"><span>Name</span><input required maxLength={60} value={window.name} onChange={event=>editWindow(index,{name:event.target.value})}/></label>
    <label className="field"><span>Start</span><input required type="time" value={window.start} onChange={event=>editWindow(index,{start:event.target.value})}/></label>
    <label className="field"><span>End</span><input required type="time" value={window.end} onChange={event=>editWindow(index,{end:event.target.value})}/></label>
    <label className="field"><span>Recommended feed (kg, optional)</span><input type="number" min="0" step="any" value={window.recommended_kg??''} onChange={event=>editWindow(index,{recommended_kg:event.target.value===''?null:Number(event.target.value)})}/></label>
    <label className="field"><span>Share of approved ration (%)</span><input type="number" min="0.01" max="100" step="any" value={window.allocation_pct??''} onChange={event=>editWindow(index,{allocation_pct:event.target.value===''?null:Number(event.target.value)})}/></label>
   </fieldset>)}
   <button className="primary" disabled={busy}>Save Feeding Schedule</button>
  </form>
 </details>;
}
