import {resolveApiBase} from './apiBase';
import {ProcessingEvidenceLibrary} from './processingEvidence';
import {ProcessingWorkspace} from './processingWorkspace';
import {FarmActivityHistory, historyTabs, type HistoryContext, type HistoryTab} from './farmActivityHistory';
import {FeedOutlook} from './feedOutlook';
import {FeedingScheduleEditor, feedingStatus, ghanaFeedingTime} from './feedingSchedule';
import {ReportCards, ReportDetail, reports, type ReportView} from './farmReportViews';
import {PricingAdvisor} from './pricingAdvisor';
import { FarmExpenses} from './farmExpenses';
import {ErrorNotice, friendlyApiError, responseError, UserFacingError} from './apiErrors';
import {ProductionIntelligence} from './productionIntelligence';
import {LoanAppraisalReport} from './loanAppraisalReport';
import {InstitutionStaff} from './institutionStaff';
import React, {useEffect,useState,useCallback,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {Waves, LayoutDashboard, Fish, Wallet, Landmark, FileDown, LogOut, RefreshCw, CheckCircle2, AlertTriangle, PlusCircle, Building2, Sprout, Pencil, Archive, X, LocateFixed, Camera, RotateCcw, ChevronDown, ArrowLeft, CalendarDays, ClipboardList, Droplets, TrendingUp, Package, LifeBuoy, ShoppingBasket, Users, Settings} from 'lucide-react';
import './style.css';

type Obj = Record<string, any>;
type Page = 'overview'|'farms'|'units'|'production'|'finance'|'reports'|'lender'|'admin'|'sales'|'inventory'|'staff'|'settings'|'expenses'|'history'|'processing';
const productionActivities = [
 {key:'stocking', label:'Stocking', description:'Record new stock and plan harvest dates.', icon:Fish},
 {key:'feeding', label:'Feeding', description:'Check feed stock and record consumption.', icon:Package},
 {key:'growth', label:'Fish Sampling', description:'Record fish weights and track growth.', icon:TrendingUp},
 {key:'water_quality', label:'Water Quality', description:'Log measurements and review previous readings.', icon:Droplets},
 {key:'mortality', label:'Mortality', description:'Record losses and monitor survival.', icon:LifeBuoy},
 {key:'harvesting', label:'Harvesting', description:'Record harvested fish and review harvest lots.', icon:ShoppingBasket},
 {key:'schedule', label:'Harvest Schedule', description:'Review planned dates and reschedule harvests.', icon:CalendarDays},
 {key:'records', label:'Activity History', description:'Browse stocking, harvest and daily activity history.', icon:ClipboardList},
] as const;
type ProductionView = 'landing' | typeof productionActivities[number]['key'];
const overviewNumber=(value:any)=>value==null?'Unavailable':num(value);
const overviewMoney=(value:any)=>value==null?'Unavailable':money(value);
const money=(n:any)=>new Intl.NumberFormat('en-GH',{style:'currency',currency:'GHS',maximumFractionDigits:2}).format(Number(n)||0);
const num=(n:any)=>new Intl.NumberFormat('en-GH',{maximumFractionDigits:2}).format(Number(n)||0);
const localTestPortal=import.meta.env.MODE==='local-test';
const testAccounts=[
 {username:'admin',portal:'admin',label:'Super Admin'},
 {username:'farmer',portal:'farmer',label:'Farmer'},
 {username:'bank',portal:'institution',label:'Bank'},
] as const;
const initialToken=()=>sessionStorage.getItem('aquafarm_token')||'';
const ghanaDate=()=>new Date().toISOString().slice(0,10);
const localDate=()=>{const now=new Date();return new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,10)};
const nextLocalDate=()=>{const now=new Date();now.setDate(now.getDate()+1);return new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,10)};
const localDateTime=()=>{const now=new Date();return new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,16)};

/** Reusable permission-based GPS picker for farms and production units. */
function GpsFields({latitude,longitude,onChange}:{latitude:any;longitude:any;onChange:(latitude:string,longitude:string,source:'gps'|'manual',accuracy?:number)=>void}){
 const [locating,setLocating]=useState(false);
 const [message,setMessage]=useState('');
 const [accuracy,setAccuracy]=useState<number|null>(null);
 function capture(){
   if(!navigator.geolocation){setMessage('GPS is unavailable in this browser. You can enter coordinates manually.');return}
   if(!window.isSecureContext){setMessage('GPS requires HTTPS or localhost. Open the app using http://127.0.0.1:5173 or HTTPS.');return}
   setLocating(true);setMessage('Requesting location permission and GPS coordinates…');
   navigator.geolocation.getCurrentPosition(
     pos=>{const gpsAccuracy=Math.round(pos.coords.accuracy);onChange(pos.coords.latitude.toFixed(7),pos.coords.longitude.toFixed(7),'gps',gpsAccuracy);setAccuracy(gpsAccuracy);setMessage('GPS coordinates captured. Check the location before saving.');setLocating(false)},
     err=>{setLocating(false);setAccuracy(null);setMessage(err.code===1?'Location permission was denied. Allow location access in your browser settings or enter coordinates manually.':err.code===2?'Location unavailable. Try outdoors with location services enabled, or enter coordinates manually.':'GPS request timed out. Retry or enter coordinates manually.')},
     {enableHighAccuracy:true,timeout:20000,maximumAge:0}
   );
 }
 return <div className="gps-picker"><div className="farmcoordinates">
  <label className="field"><span>Latitude (optional)</span><input type="number" step="any" min={-90} max={90} value={latitude??''} onChange={e=>{setAccuracy(null);onChange(e.target.value,String(longitude??''),'manual')}}/></label>
  <label className="field"><span>Longitude (optional)</span><input type="number" step="any" min={-180} max={180} value={longitude??''} onChange={e=>{setAccuracy(null);onChange(String(latitude??''),e.target.value,'manual')}}/></label>
 </div><button className="outline gps-capture" type="button" disabled={locating} onClick={capture}><LocateFixed size={17}/>{locating?'Getting GPS location…':'Get GPS Location'}</button>
 {message&&<p className="muted gps-message" role="status">{message}{accuracy!==null?` Approximate accuracy: ±${accuracy} m.`:''}</p>}
 <p className="muted gps-hint">Capture GPS while physically at this location. Permission is required. You can also enter both coordinates manually.</p></div>
}

type RecordedVideo={
 blob:Blob;
 capturedAt:string;
 deviceRecordedAt:string;
 latitude?:number;
 longitude?:number;
 gpsAccuracy?:number;
 challengeId?:number;
 challengeCode?:string;
};

function EvidenceRecorder({activity,unit,onChange,getChallenge,requireFarmGps=true}:{activity:string;unit:Obj|null|undefined;onChange:(video:RecordedVideo|null)=>void;getChallenge:(activity:string,unitId:number)=>Promise<Obj|null>;requireFarmGps?:boolean}){
 const [recording,setRecording]=useState(false);
 const [secondsLeft,setSecondsLeft]=useState(15);
 const [message,setMessage]=useState('');
 const [video,setVideo]=useState<RecordedVideo|null>(null);
 const [previewUrl,setPreviewUrl]=useState('');
 const [challengeCode,setChallengeCode]=useState('');
 const recorderRef=useRef<MediaRecorder|null>(null);
 const streamRef=useRef<MediaStream|null>(null);
 const timeoutRef=useRef<number|null>(null);
 const intervalRef=useRef<number|null>(null);
 const loanInstruction=activity==='loan_application'
   ?'Show the farm and explain the intended use of funds. Do not show passwords, PINs, or full identity or payment numbers.'
   :activity==='disbursement'
     ?'Show the transfer confirmation or handover. Never show passwords, PINs, or full account/card numbers.'
     :activity==='repayment'
       ?'Show the payment confirmation or receipt. Never show passwords, PINs, or full account/card numbers.'
       :'';

 useEffect(()=>{
   if(!video){setPreviewUrl('');return}
   const url=URL.createObjectURL(video.blob);
   setPreviewUrl(url);
   return()=>URL.revokeObjectURL(url);
 },[video]);
 useEffect(()=>()=>{if(timeoutRef.current!==null)window.clearTimeout(timeoutRef.current);if(intervalRef.current!==null)window.clearInterval(intervalRef.current);recorderRef.current?.stop();streamRef.current?.getTracks().forEach(track=>track.stop())},[]);

 async function startRecording(){
   if(requireFarmGps&&!unit){setMessage('Select a production unit before recording evidence.');return}
   if(requireFarmGps&&(!navigator.geolocation||!window.isSecureContext)){setMessage('GPS evidence requires location permission over HTTPS or localhost.');return}
   if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined'){setMessage('Video recording is not supported in this browser. Use a current browser on HTTPS or localhost.');return}
   try{
     const challenge=requireFarmGps&&unit?await getChallenge(activity,unit.id):null;
     setChallengeCode(challenge?.code||'');
     const position=requireFarmGps?await new Promise<GeolocationPosition>((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,reject,{enableHighAccuracy:true,timeout:20000,maximumAge:0})):null;
     const stream=await navigator.mediaDevices.getUserMedia({
       video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},
       audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1}
     });
     streamRef.current=stream;
     const mimeType=['video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm','video/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
     const recorder=mimeType?new MediaRecorder(stream,{mimeType}):new MediaRecorder(stream);
     const chunks:BlobPart[]=[];
     recorderRef.current=recorder;
     recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data)};
     const capturedAt=new Date().toISOString();
     const startedAt=Date.now();
     recorder.onstop=()=>{
       stream.getTracks().forEach(track=>track.stop());
       streamRef.current=null;recorderRef.current=null;
       if(timeoutRef.current!==null)window.clearTimeout(timeoutRef.current);
       if(intervalRef.current!==null)window.clearInterval(intervalRef.current);
       const clip=new Blob(chunks,{type:recorder.mimeType||'video/webm'});
       setRecording(false);setSecondsLeft(0);
       if(Date.now()-startedAt<14900||!clip.size){setMessage('The 15-second recording did not complete. Please record again.');setVideo(null);onChange(null);return}
       if(clip.size>30*1024*1024){setMessage('Video exceeds the 30 MB limit. Record again at a lower camera resolution.');setVideo(null);onChange(null);return}
       const recorded:RecordedVideo={blob:clip,capturedAt,deviceRecordedAt:capturedAt,...(position?{latitude:position.coords.latitude,longitude:position.coords.longitude,gpsAccuracy:position.coords.accuracy}:{}),challengeId:challenge?.id,challengeCode:challenge?.code};
       setVideo(recorded);onChange(recorded);setMessage(requireFarmGps?'15-second video captured with GPS and timestamp. Review it before submitting.':'15-second video captured with timestamp. Review it before submitting.');
     };
     recorder.onerror=()=>{setMessage('The camera recording failed. Please try again.');setRecording(false);stream.getTracks().forEach(track=>track.stop());streamRef.current=null};
     recorder.start(250);
     setRecording(true);setSecondsLeft(15);setVideo(null);onChange(null);setMessage('Recording 15 seconds: speak the activity clearly and loudly.');
     intervalRef.current=window.setInterval(()=>setSecondsLeft(Math.max(0,15-Math.floor((Date.now()-startedAt)/1000))),250);
     timeoutRef.current=window.setTimeout(()=>{if(recorder.state!=='inactive')recorder.stop()},15000);
   }catch(error){
     setMessage(error instanceof Error&&error.name==='NotAllowedError'?(requireFarmGps?'Camera or location permission was denied. Allow both permissions and try again.':'Camera permission was denied. Allow camera access and try again.'):(requireFarmGps?'Unable to access GPS or the camera. Check permissions and try again.':'Unable to access the camera. Check permissions and try again.'));
   }
 }

 function retake(){setVideo(null);onChange(null);setSecondsLeft(15);setMessage('');setChallengeCode('')}
 return <div className="evidence-recorder">
   <div className="between"><div><b>15-second video evidence <span className="required">*</span></b><p className="muted">{requireFarmGps?'Required for this record. Speak the activity clearly and loudly in the recording. Video capture includes GPS and timestamps. Linked evidence is retained for supervisor review.':'Required for this loan submission. Speak clearly and loudly, then show the relevant evidence. Record a fresh video in this app; gallery uploads are not accepted. '+loanInstruction}</p></div>
     {!recording&&!video&&<button type="button" className="outline" onClick={()=>void startRecording()}><Camera size={16}/> Record video</button>}
     {recording&&<span className="pill evidence-countdown">Recording · {secondsLeft}s</span>}
     {video&&<button type="button" className="outline" onClick={retake}><RotateCcw size={15}/> Retake</button>}
   </div>
   {challengeCode&&<div className="infobox">Include this one-time activity code in the recording: <b>{challengeCode}</b></div>}
   {recording&&<div className="evidence-live"><span className="recording-dot"/>Keep the camera on the farm activity until recording finishes.</div>}
   {previewUrl&&<video className="evidence-preview" controls playsInline src={previewUrl}/>}
   {message&&<p className="muted evidence-message" role="status">{message}</p>}
 </div>
}

function TrendChart({title,points,dateKey,valueKey,seriesKey,unit}:{title:string;points:Obj[];dateKey:string;valueKey:string;seriesKey:string;unit:string}){
 const usable=points.filter(point=>point[valueKey]!=null&&Number.isFinite(Number(point[valueKey]))&&Number.isFinite(Date.parse(point[dateKey])));
 if(!usable.length)return <section className="chart-card"><h3>{title}</h3><p className="empty">No recorded measurements available yet.</p></section>;
 const times=usable.map(point=>new Date(point[dateKey]).getTime()).filter(Number.isFinite);
 const values=usable.map(point=>Number(point[valueKey]));
 const minTime=Math.min(...times),maxTime=Math.max(...times),rawMin=Math.min(...values),rawMax=Math.max(...values);
 const padding=rawMin===rawMax?Math.max(.3,Math.abs(rawMax)*.05):0;
 const minValue=Math.max(0,rawMin-padding),maxValue=rawMax+padding;
 const timeRange=maxTime-minTime||1,valueRange=maxValue-minValue||1;
 const groups=new Map<string,Obj[]>();
 usable.forEach(point=>{const key=String(point[seriesKey]??'Records');groups.set(key,[...(groups.get(key)||[]),point])});
 const colors=['#168064','#e5a84b','#5676b8','#b45b65','#835bb4'];
 return <section className="chart-card"><h3>{title}</h3><svg className="chart-svg" viewBox="0 0 680 250" role="img" aria-label={title}>
  {[0,1,2,3].map(step=><g key={step}><line x1="48" x2="660" y1={25+step*55} y2={25+step*55} stroke="#e8efeb"/><text x="5" y={29+step*55} className="chart-axis">{num(maxValue-(maxValue-minValue)*step/3)}{unit}</text></g>)}
  {Array.from(groups.entries()).map(([label,rows],index)=>{
    const ordered=[...rows].sort((a,b)=>new Date(a[dateKey]).getTime()-new Date(b[dateKey]).getTime());
    const coordinates=ordered.map(point=>{
      const x=48+(new Date(point[dateKey]).getTime()-minTime)/timeRange*600;
      const y=25+(maxValue-Number(point[valueKey]))/valueRange*165;
      return `${x},${y}`;
    }).join(' ');
    return <g key={label}><polyline points={coordinates} fill="none" stroke={colors[index%colors.length]} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round"/>{ordered.map((point,i)=>{const [x,y]=coordinates.split(' ')[i].split(',');return <circle key={`${label}-${i}`} cx={x} cy={y} r="4" fill={colors[index%colors.length]}><title>{label} · {new Date(point[dateKey]).toLocaleDateString()} · {num(point[valueKey])}{unit}</title></circle>})}</g>
  })}
  <text x="48" y="222" className="chart-axis">{new Date(minTime).toLocaleDateString()}</text><text x="660" y="222" textAnchor="end" className="chart-axis">{new Date(maxTime).toLocaleDateString()}</text>
 </svg><div className="chart-legend">{Array.from(groups.keys()).map((label,index)=><span key={label}><i style={{background:colors[index%colors.length]}}/>{label}</span>)}</div></section>
}

function BarChart({title,data,labelKey,series}:{title:string;data:Obj[];labelKey:string;series:{key:string;label:string;color:string}[]}){
 if(!data.length)return <section className="chart-card"><h3>{title}</h3><p className="empty">No recorded data available yet.</p></section>;
 const values=data.flatMap(row=>series.map(item=>Number(row[item.key])||0));
 const max=Math.max(1,...values),baseY=194,topY=22,chartHeight=baseY-topY,groupWidth=612/data.length;
 const barWidth=Math.max(3,Math.min(18,groupWidth/(series.length+1)));
 return <section className="chart-card"><h3>{title}</h3><svg className="chart-svg" viewBox="0 0 680 250" role="img" aria-label={title}>
  {[0,1,2,3].map(step=><g key={step}><line x1="48" x2="660" y1={topY+step*chartHeight/3} y2={topY+step*chartHeight/3} stroke="#e8efeb"/><text x="5" y={topY+4+step*chartHeight/3} className="chart-axis">{num(max*(1-step/3))}</text></g>)}
  {data.map((row,index)=>{const left=48+index*groupWidth+Math.max(1,(groupWidth-series.length*barWidth)/2);return <g key={String(row[labelKey])}>{series.map((item,seriesIndex)=>{const value=Math.max(0,Number(row[item.key])||0),height=value/max*chartHeight;return <rect key={item.key} x={left+seriesIndex*barWidth} y={baseY-height} width={barWidth-2} height={height} rx="2" fill={item.color}><title>{row[labelKey]} · {item.label}: {num(value)}</title></rect>})}<text x={left+series.length*barWidth/2} y="216" textAnchor="middle" className="chart-axis">{String(row[labelKey]).slice(-2)}</text></g>})}
 </svg><div className="chart-legend">{series.map(item=><span key={item.key}><i style={{background:item.color}}/>{item.label}</span>)}</div></section>
}

function App(){
 const [token,setToken]=useState(initialToken); const [user,setUser]=useState<Obj|null>(null);
 const [farms,setFarms]=useState<Obj[]>([]);const [farmId,setFarmId]=useState<number|null>(null);
 const [processingEntry,setProcessingEntry]=useState<'overview'|'batches'|'sales'|'reports'|'expenses'>('overview');
 const [processingRevision,setProcessingRevision]=useState(0);
 const [processingBusiness,setProcessingBusiness]=useState<Obj|null>(null);
 function openProcessing(view:typeof processingEntry='overview'){
   setProcessingEntry(view);setProcessingRevision(value=>value+1);setPage('processing');
   window.history.replaceState(null,'',window.location.pathname+window.location.search);
   window.scrollTo(0,0);
 }
 const [page,setPage]=useState<Page>('overview');const [dashboard,setDashboard]=useState<Obj|null>(null);const [analytics,setAnalytics]=useState<Obj|null>(null);
 const [reportView,setReportView]=useState<ReportView|null>(null);
 const [historyContext,setHistoryContext]=useState<HistoryContext>({tab:'all'});
 function openHistory(context:HistoryContext){
   setHistoryContext(context);setPage('history');
   const params=new URLSearchParams();
   if(context.unit)params.set('unit',String(context.unit));
   if(context.cycle)params.set('cycle',String(context.cycle));
   const hash='#activity-history/'+context.tab+(params.size?'?'+params:'');
   if(window.location.hash!==hash)window.location.hash=hash;
 }
 function openReport(view:ReportView|null){
   setReportView(view);setPage('reports');
   const hash=view?'#reports/'+view:'#reports';
   if(window.location.hash!==hash)window.location.hash=hash;
   window.scrollTo(0,0);
 }
 function backToDashboard(){
   setPage('overview');setReportView(null);window.location.hash='dashboard';window.scrollTo(0,0);
 }
 useEffect(()=>{
   if(!user||user.is_platform_admin||user.account_type==='institution')return;
   function syncReportLocation(){
     const hash=window.location.hash;
     if(!hash||hash==='#dashboard'){setPage('overview');setReportView(null);return}
     if(hash.startsWith('#activity-history/')){
       const [route,query]=hash.split('?');
       const tab=historyTabs.find(([key])=>route==='#activity-history/'+key)?.[0]??'all';
       const params=new URLSearchParams(query);
       setHistoryContext({tab,unit:Number(params.get('unit'))||undefined,cycle:Number(params.get('cycle'))||undefined});
       setPage('history');return;
     }
     if(hash==='#reports'||hash.startsWith('#reports/')){
       setPage('reports');
       setReportView(reports.find(([key])=>hash==='#reports/'+key)?.[0]??null);
     }
   }
   if(window.location.hash)syncReportLocation();
   window.addEventListener('hashchange',syncReportLocation);
   return ()=>window.removeEventListener('hashchange',syncReportLocation);
 },[user?.id,user?.account_type,user?.is_platform_admin]);
 const [reportSearch,setReportSearch]=useState('');
 const [pricingForm,setPricingForm]=useState<Obj>({});
 const [cycles,setCycles]=useState<Obj[]>([]);const [applications,setApplications]=useState<Obj[]>([]);
 const [dailyRecordStatus,setDailyRecordStatus]=useState<Obj|null>(null);
 const [loans,setLoans]=useState<Obj[]>([]);const [reminders,setReminders]=useState<Obj[]>([]);
 const [institutions,setInstitutions]=useState<Obj[]>([]);const [mine,setMine]=useState<Obj[]>([]);
 const [pendingInstitutions,setPendingInstitutions]=useState<Obj[]>([]);
 const [institutionReviewFilter,setInstitutionReviewFilter]=useState('all');
 const [institutionReviewSearch,setInstitutionReviewSearch]=useState('');

 const [institutionId,setInstitutionId]=useState<number|null>(null);const [lenderApps,setLenderApps]=useState<Obj[]>([]);
 const [lenderLoans,setLenderLoans]=useState<Obj[]>([]);const [portfolio,setPortfolio]=useState<Obj|null>(null);const [selectedApp,setSelectedApp]=useState<Obj|null>(null);
 const [selectedLoan,setSelectedLoan]=useState<Obj|null>(null);const [schedule,setSchedule]=useState<Obj[]>([]);const [transactions,setTransactions]=useState<Obj[]>([]);
 const [customSchedule,setCustomSchedule]=useState<Obj[]>([{due_on:'',principal_ghs:'',interest_ghs:''}]);
 const [applicationVideo,setApplicationVideo]=useState<RecordedVideo|null>(null);const [applicationEvidenceId,setApplicationEvidenceId]=useState<number|null>(null);
 const [transactionVideo,setTransactionVideo]=useState<RecordedVideo|null>(null);const [transactionEvidenceId,setTransactionEvidenceId]=useState<number|null>(null);
 const [applicationRecorderKey,setApplicationRecorderKey]=useState(0);const [transactionRecorderKey,setTransactionRecorderKey]=useState(0);
 const [error,setError]=useState('');const [notice,setNotice]=useState('');const [busy,setBusy]=useState(false);
 const [units,setUnits]=useState<Obj[]>([]);
 const [unitEditing,setUnitEditing]=useState<number|null>(null);
 const [unitForm,setUnitForm]=useState<Obj>({unit_type:'pond'});
 const [unitFormOpen,setUnitFormOpen]=useState(false);
 const [farmEditing,setFarmEditing]=useState<number|null>(null);const [farmForm,setFarmForm]=useState<Obj>({farm_type:'pond'});const [farmFormOpen,setFarmFormOpen]=useState(false);
 const [harvestSchedule,setHarvestSchedule]=useState<Obj[]>([]);
 const upcomingHarvests=harvestSchedule.filter(row=>row.farm_id===farmId&&row.status!=='Completed'&&row.days_remaining!=null&&row.days_remaining>=0);
 const overdueHarvests=harvestSchedule.filter(row=>row.farm_id===farmId&&row.status!=='Completed'&&row.days_remaining!=null&&row.days_remaining<0);
 const nextHarvest=upcomingHarvests[0];
 const [harvestEdit,setHarvestEdit]=useState<Obj|null>(null);
 const [harvestFilter,setHarvestFilter]=useState<Obj>({});
 const [stockForm,setStockForm]=useState<Obj>({stocked_on:new Date().toISOString().slice(0,10)});
 const harvestMonths=Number(stockForm.harvest_duration_months||0);
 const calculatedHarvestDate=(()=>{
   if(!stockForm.stocked_on||!Number.isInteger(harvestMonths)||harvestMonths<1||harvestMonths>120)return '';
   const [year,month,day]=String(stockForm.stocked_on).split('-').map(Number);
   const lastDay=new Date(Date.UTC(year,month-1+harvestMonths+1,0)).getUTCDate();
   return new Date(Date.UTC(year,month-1+harvestMonths,Math.min(day,lastDay))).toISOString().slice(0,10);
 })();

 const [productionView,setProductionView]=useState<ProductionView>('landing');
 const [productionExpanded,setProductionExpanded]=useState(false);
 const [harvestForm,setHarvestForm]=useState<Obj>({});
 const [harvestVideo,setHarvestVideo]=useState<RecordedVideo|null>(null);
 const [harvestMonth,setHarvestMonth]=useState(()=>localDate().slice(0,7));
 const dailyActivity=productionView==='feeding'||productionView==='growth'||productionView==='water_quality'||productionView==='mortality';
 const [dailyTab,setDailyTab]=useState<'feeding'|'mortality'|'water_quality'|'growth'>('feeding');
 function openProduction(view:ProductionView){
   if(view==='records'){openHistory({tab:'all'});window.scrollTo(0,0);return}
   if(window.location.hash.startsWith('#activity-history/'))window.history.replaceState(null,'',window.location.pathname+window.location.search);
   setProductionExpanded(true);
   setProductionView(view);
   setPage('production');
   if(view==='feeding'||view==='growth'||view==='water_quality'||view==='mortality')setDailyTab(view);
   if(view==='feeding')setDailyForm(previous=>({...previous,recorded_on:ghanaDate(),session_number:'',actual_time:undefined}));
   window.scrollTo(0,0);
 }
 function showProductionSuccess(message:string){
   setNotice(message);
   openProduction('landing');
 }
 const [dailyCycleId,setDailyCycleId]=useState<number|''>('');
 const [feedProducts,setFeedProducts]=useState<Obj[]>([]);
 const [feedProductForm,setFeedProductForm]=useState<Obj>({});
 const [feedReceiptForm,setFeedReceiptForm]=useState<Obj>({occurred_on:localDate()});
 const [dashboardSession,setDashboardSession]=useState<{cycleId:number,number:number}|null>(null);
 const [sessionOverview,setSessionOverview]=useState<Obj|null>(null);
 const [sessionEnds,setSessionEnds]=useState<Record<string,string>>({});
 const [activityStatus,setActivityStatus]=useState<Obj|null>(null);
 const [activityError,setActivityError]=useState('');
 const [attentionMode,setAttentionMode]=useState(false);
 const [sessionTimes,setSessionTimes]=useState<Record<string,string>>({});
 const [sessionRevision,setSessionRevision]=useState(0);
 const [sessionError,setSessionError]=useState('');
 const [dailyForm,setDailyForm]=useState<Obj>({recorded_on:localDate(),observed_at:localDateTime()});
 const [dailyVideo,setDailyVideo]=useState<RecordedVideo|null>(null);
 const pendingFeedingSave=useRef<{path:string,video:RecordedVideo,evidence:Obj,payload:Obj}|null>(null);
 const [stockVideo,setStockVideo]=useState<RecordedVideo|null>(null);
 const [receiptVideo,setReceiptVideo]=useState<RecordedVideo|null>(null);
 const [recorderKey,setRecorderKey]=useState(0);
 const [feedingCosts,setFeedingCosts]=useState<Obj|null>(null);
 const [evidenceRetry,setEvidenceRetry]=useState<Obj|null>(null);
 const [profileForm,setProfileForm]=useState<Obj>({phone_number:'',sms_daily_records_enabled:false,sms_loan_reminders_enabled:false});
 const [portal,setPortal]=useState<'farmer'|'institution'|'admin'>('farmer');
 const [authMode,setAuthMode]=useState<'login'|'register'>('login');const [form,setForm]=useState<Obj>({});
 const [showLoginPassword,setShowLoginPassword]=useState(false);
 const activeCycles=cycles.filter(c=>c.status==='active');
 const dailyCycle=activeCycles.find(c=>c.cycle_id===Number(dailyCycleId));
 const selectedApprovedAmount=Number(selectedApp?.appraisals?.filter((x:Obj)=>x.decision==='approved').slice(-1)[0]?.approved_ghs??selectedApp?.requested_ghs??0);
 const insuranceRate=form.insurance_fee_percent ?? '1';
 const quotePrincipalPesewas=Math.round(selectedApprovedAmount*100);
 const quoteInterest=Math.round(quotePrincipalPesewas*Math.round(Number(form.annual_flat_interest_percent||0)*100)*Number(selectedApp?.term_months||0)/120000)/100;
 const quoteInsurance=Math.round(quotePrincipalPesewas*Math.round(Number(insuranceRate)*100)/10000)/100;
 const quoteProcessing=Math.round(quotePrincipalPesewas*Math.round(Number(form.processing_fee_percent||0)*100)/10000)/100;
 const quoteCommitment=Number(form.commitment_fee_ghs||0);
 const projectedLoanTotal=selectedApprovedAmount+quoteInterest+quoteInsurance+quoteProcessing+quoteCommitment;
 useEffect(()=>{
   const species=farms.find(f=>f.id===farmId)?.species?.toLowerCase().includes('catfish')?'Catfish':'Tilapia';
   setStockForm({stocked_on:new Date().toISOString().slice(0,10),species});
 },[farmId]);
 useEffect(()=>{
   setApplicationVideo(null);setApplicationEvidenceId(null);setApplicationRecorderKey(key=>key+1);
 },[farmId]);
 useEffect(()=>{
   setDailyCycleId(previous=>activeCycles.some(c=>c.cycle_id===Number(previous))?previous:activeCycles[0]?.cycle_id??'');
 },[cycles]);
 useEffect(()=>{
   setDailyVideo(null);setRecorderKey(key=>key+1);
   setDailyForm({recorded_on:dailyTab==='feeding'?ghanaDate():localDate(),observed_at:localDateTime()});
 },[dailyTab,dailyCycleId]);
 const api=useCallback(async(path:string,init:RequestInit={})=>{
   const method=init.method??'GET';
   let response:Response;
   try{
     response=await fetch(resolveApiBase(import.meta.env.VITE_API_BASE_URL)+path,{...init,headers:{...(init.body?{'Content-Type':'application/json'}:{}),...(token?{Authorization:'Bearer '+token}:{}),...init.headers}});
   }catch{
     throw new UserFacingError(friendlyApiError(path,method,0,null),0);
   }
   if(!response.ok){
     const error=await responseError(path,method,response);
     if(response.status===401&&token){
       sessionStorage.removeItem('aquafarm_token');
       setToken('');
       setError(error.message);
     }
     throw error;
   }
   return response;
 },[token]);
 const json=useCallback(async(path:string,body?:Obj,method='POST')=>{
   const response=await api(path,body?{method,body:JSON.stringify(body)}:{});
   try{return await response.json()}
   catch{
     if(import.meta.env.DEV)console.warn('AquaFarm API response was not JSON',{route:path.split('?')[0],status:response.status,requestId:response.headers.get('X-Request-ID')});
     throw new UserFacingError(friendlyApiError(path,body?method:'GET',503,null),503);
   }
 },[api]);
 const refreshProcessingBusiness=useCallback(async()=>{
   if(!token){setProcessingBusiness(null);return}
   const info=await json('/processing/business');setProcessingBusiness(info);
 },[json,token]);
 useEffect(()=>{
   if(user&&user.account_type!=='institution'&&!user.is_platform_admin)void refreshProcessingBusiness().catch(()=>setProcessingBusiness(null));
 },[user,refreshProcessingBusiness]);
 const processorOnly=processingBusiness?.business_type==='processor'&&processingBusiness?.is_owner!==false;
 const loadHarvestSchedule=useCallback(async()=>{
   setHarvestSchedule(await json('/harvest-schedule'));
 },[json]);
 useEffect(()=>{
   if(token&&farms.length)void loadHarvestSchedule().catch(e=>setError(String(e)));
 },[token,farms.length,cycles,loadHarvestSchedule]);
 async function saveHarvestPlan(e:React.FormEvent){
   e.preventDefault();
   if(!harvestEdit)return;
   const {farm_id,unit_id,cycle_id,expected_harvest_on,reason}=harvestEdit;
   setBusy(true);setError('');
   try{
     await json('/farms/'+farm_id+'/units/'+unit_id+'/cycles/'+cycle_id+'/harvest-plan',{expected_harvest_on,reason},'PUT');
     setHarvestEdit(null);
     showProductionSuccess('Harvest plan saved');
     await Promise.all([loadHarvestSchedule(),loadFarm()]);
   }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 const getEvidenceChallenge=useCallback(async(activity:string,unitId:number)=>{
   if(!farmId)throw new Error('Select a farm before recording evidence.');
   const challengeActivities=['feeding','growth','mortality','stocking','feed_stock_count','fish_transfer','harvest','sale_dispatch','treatment'];
   if(!challengeActivities.includes(activity))return null;
   return json(`/farms/${farmId}/evidence-challenges`,{unit_id:unitId,activity_type:activity});
 },[farmId,json]);
 async function uploadOperationEvidence(activity:string,unit:Obj,recording:RecordedVideo,cycleId?:number){
   if(!farmId)throw new Error('Select a farm before uploading evidence.');
   const query=new URLSearchParams({
     unit_id:String(unit.id),
     unit_tag:String(unit.evidence_tag),
     record_type:activity,
     captured_at:recording.capturedAt,
     device_recorded_at:recording.deviceRecordedAt,
     latitude:String(recording.latitude),
     longitude:String(recording.longitude),
     gps_accuracy_m:String(recording.gpsAccuracy),
     duration_seconds:'15',
   });
   if(cycleId!==undefined)query.set('cycle_id',String(cycleId));
   if(recording.challengeId!==undefined)query.set('challenge_id',String(recording.challengeId));
   if(recording.challengeCode)query.set('challenge_code',recording.challengeCode);
   const response=await api(`/farms/${farmId}/evidence?${query.toString()}`,{
     method:'POST',
     headers:{'Content-Type':recording.blob.type||'video/webm'},
     body:recording.blob,
   });
   return response.json();
 }
 async function uploadLoanEvidence(activity:'loan_application'|'disbursement'|'repayment',recording:RecordedVideo,loanId?:number){
   if(!farmId)throw new Error('Select a farm before submitting a loan application.');
   const query=new URLSearchParams({
     record_type:activity,
     captured_at:recording.capturedAt,
     device_recorded_at:recording.deviceRecordedAt,
     duration_seconds:'15',
   });
   const path=loanId===undefined
     ?`/farms/${farmId}/loan-evidence?${query.toString()}`
     :`/finance/loans/${loanId}/evidence?${query.toString()}`;
   return (await api(path,{method:'POST',headers:{'Content-Type':recording.blob.type||'video/webm'},body:recording.blob})).json();
 }
 const loadBase=useCallback(async()=>{if(!token)return;try{const [u,f,i,m]=await Promise.all([json('/auth/me'),json('/farms'),json('/finance/institutions'),json('/finance/institutions/mine')]);setUser(u);setPage(old=>u.is_platform_admin?'admin':u.account_type==='institution'?'lender':old==='admin'?'overview':old);setProfileForm({phone_number:u.phone_number??'',sms_daily_records_enabled:u.sms_daily_records_enabled??false,sms_loan_reminders_enabled:u.sms_loan_reminders_enabled??false});setFarms(f);setInstitutions(i);setMine(m);setPendingInstitutions(u.is_platform_admin?await json('/finance/admin/institutions'):[]);setFarmId(old=>{
  const saved=Number(sessionStorage.getItem('aquafarm-selected-farm:'+u.id));
  return f.some((x:Obj)=>x.id===old)?old:f.some((x:Obj)=>x.id===saved)?saved:f[0]?.id??null;
 });setInstitutionId(old=>m.some((x:Obj)=>x.id===old)?old:m[0]?.id??null);setError('')}catch(e){setError(String(e))}},[json,token]);
 useEffect(()=>{void loadBase()},[loadBase]);
 const farmLoadRevision=React.useRef(0);
 const [overviewLoading,setOverviewLoading]=useState(false);
 const [overviewError,setOverviewError]=useState(false);
 const loadFarm=useCallback(async()=>{
   const revision=++farmLoadRevision.current;
   if(!farmId||!token){setDashboard(null);setAnalytics(null);setCycles([]);setApplications([]);setLoans([]);setReminders([]);setDailyRecordStatus(null);setOverviewLoading(false);return;}
   const base='/farms/'+farmId;
   setOverviewLoading(true);setOverviewError(false);setDashboard(null);setAnalytics(null);
   const refresh=async(path:string, apply:(data:any)=>void, overview=false)=>{
     try{const result=await json(base+path);if(revision===farmLoadRevision.current)apply(result)}
     catch(e){if(revision===farmLoadRevision.current){if(overview)setOverviewError(true);setError(String(e));apply(null)}}
   };
   await Promise.all([
     Promise.all([
       refresh('/dashboard',setDashboard,true),
       refresh('/dashboard/analytics',setAnalytics,true),
     ]).then(()=>{if(revision===farmLoadRevision.current)setOverviewLoading(false)}),
     refresh('/dashboard/cycles',data=>setCycles(data?.cycles??[])),
     refresh('/loan-applications',data=>setApplications(data??[])),
     refresh('/loans',data=>setLoans(data??[])),
     refresh('/loan-reminders',data=>setReminders(data??[])),
     refresh('/daily-record-status',setDailyRecordStatus),
   ]);
 },[farmId,json,token]);
 useEffect(()=>{void loadFarm()},[loadFarm]);
 useEffect(()=>{
   if(user?.id&&farmId&&farms.some(farm=>farm.id===farmId)){
     sessionStorage.setItem('aquafarm-selected-farm:'+user.id,String(farmId));
   }
 },[user?.id,farmId,farms]);
 useEffect(()=>{
   const rows=analytics?.finance?.pricing_by_plan||[];
   setPricingForm(Object.fromEntries(rows.map((row:Obj)=>[row.plan_id,{
     desired_profit_pct:row.desired_profit_pct,
     profit_method:row.profit_method,
     market_price_ghs_per_kg:row.market_price_ghs_per_kg??''
   }])));
 },[analytics]);
 useEffect(()=>{if(!farmId||!token)return;const interval=window.setInterval(()=>{void json(`/farms/${farmId}/daily-record-status`).then(setDailyRecordStatus).catch(e=>setError(String(e)))},60_000);return()=>window.clearInterval(interval)},[farmId,json,token]);
 const loadUnits=useCallback(async()=>{
   if(!farmId||!token){setUnits([]);return}
   try{setUnits(await json(`/farms/${farmId}/units`))}catch(e){setUnits([]);setError(String(e))}
 },[farmId,json,token]);
 useEffect(()=>{void loadUnits()},[loadUnits]);
 const loadFeedProducts=useCallback(async()=>{
   if(!farmId||!token){setFeedProducts([]);return}
   try{setFeedProducts(await json(`/farms/${farmId}/feeds`))}catch(e){setFeedProducts([]);setError(String(e))}
 },[farmId,json,token]);
 useEffect(()=>{void loadFeedProducts()},[loadFeedProducts]);
 useEffect(()=>{
   setHarvestForm({harvested_on:localDate()});
   setHarvestVideo(null);
 },[farmId]);

 async function saveHarvest(e:React.FormEvent){
   e.preventDefault();
   if(!farmId||!harvestVideo)return;
   const cycle=activeCycles.find(row=>row.cycle_id===Number(harvestForm.cycle_id));
   const unit=units.find(row=>row.id===cycle?.unit_id);
   if(!cycle||!unit)return;
   const final=harvestForm.kind==='final';
   if(final&&!window.confirm('Record the final harvest and close this stocking cycle?'))return;
   setBusy(true);setError('');setNotice('');
   let evidenceId:number|undefined;
   let saved=false;
   try{
     const evidence=await uploadOperationEvidence('harvest',unit,harvestVideo,cycle.cycle_id);
     evidenceId=evidence.id;
     await json('/farms/'+farmId+'/sales/harvests?evidence_id='+evidenceId,{
       cycle_id:cycle.cycle_id, harvested_on:harvestForm.harvested_on, quantity_kg:Number(harvestForm.quantity_kg),
       fish_count:Number(harvestForm.fish_count), notes:harvestForm.notes||null,
     });
     saved=true;
     setHarvestForm({harvested_on:localDate()});setHarvestVideo(null);
     showProductionSuccess('Harvest recorded');
     if(final){
       await api('/farms/'+farmId+'/units/'+unit.id+'/cycles/'+cycle.cycle_id+'/close',{method:'POST'});
       setNotice('Final harvest recorded and cycle closed');
     }
   }catch(error){
     if(!saved&&evidenceId!==undefined){
       try{await api('/farms/'+farmId+'/evidence/'+evidenceId,{method:'DELETE'})}catch(cleanupError){setError(String(error)+' Evidence cleanup failed. '+String(cleanupError));return}
     }
     setError(saved?'Harvest saved. Close the cycle from Stocking. '+String(error):String(error));
   }finally{
     if(saved)await loadFarm();
     setBusy(false);
   }
 }
 const loadDailyRecords=useCallback(async()=>{
   setFeedingCosts(null);
   if(page!=='production'||productionView!=='feeding'||!farmId||!token||!dailyCycle)return;
   try{
     const summary=await json(`/farms/${farmId}/units/${dailyCycle.unit_id}/cycles/${dailyCycle.cycle_id}/feeding-costs`);
     setFeedingCosts(summary);
   }catch(e){setError(String(e))}
 },[dailyCycle,farmId,json,token,page,productionView]);
 useEffect(()=>{void loadDailyRecords()},[loadDailyRecords]);
 async function saveUnit(e:React.FormEvent){
   e.preventDefault();if(!farmId)return;
   const hasLatitude=unitForm.latitude!==''&&unitForm.latitude!=null;
   const hasLongitude=unitForm.longitude!==''&&unitForm.longitude!=null;
   if(hasLatitude!==hasLongitude){setError('Enter both latitude and longitude, or leave both blank.');return}
   setBusy(true);setError('');setNotice('');
   try{
     const payload={
       name:String(unitForm.name||'').trim(),unit_type:unitForm.unit_type,
       capacity_m3:unitForm.capacity_m3!==''&&unitForm.capacity_m3!=null?Number(unitForm.capacity_m3):null,
       latitude:hasLatitude?Number(unitForm.latitude):null,
       longitude:hasLongitude?Number(unitForm.longitude):null,
       notes:String(unitForm.notes||'').trim()||null
     };
     await json(unitEditing!==null?`/farms/${farmId}/units/${unitEditing}`:`/farms/${farmId}/units`,payload,unitEditing!==null?'PUT':'POST');
     setUnits(await json(`/farms/${farmId}/units`));
     setUnitFormOpen(false);setUnitEditing(null);setUnitForm({unit_type:'pond'});
     setNotice(unitEditing!==null?'Production unit updated successfully':'Production unit registered successfully');
     await loadFarm();
   }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function savePricing(e:React.FormEvent,planId:number){
   e.preventDefault();if(!farmId)return;
   const values=pricingForm[planId];
   if(!values)return;
   setBusy(true);setError('');setNotice('');
   try{
     await json(`/farms/${farmId}/production-plans/${planId}/pricing`,{
       desired_profit_pct:Number(values.desired_profit_pct),
       profit_method:values.profit_method,
       market_price_ghs_per_kg:values.market_price_ghs_per_kg===''?null:Number(values.market_price_ghs_per_kg)
     },'PATCH');
     setNotice('Pricing assumptions saved. Cost, break-even price and projections have been recalculated.');
     await loadFarm();
   }catch(error){setError(String(error))}
   finally{setBusy(false)}
 }
 function newUnit(){setUnitEditing(null);setUnitForm({unit_type:'pond'});setUnitFormOpen(true);setError('')}
 function editUnit(u:Obj){setUnitEditing(u.id);setUnitForm({name:u.name,unit_type:u.unit_type,capacity_m3:u.capacity_m3??'',latitude:u.latitude??'',longitude:u.longitude??'',notes:u.notes??''});setUnitFormOpen(true);setError('')}
 async function createFeedProduct(e:React.FormEvent){
   e.preventDefault();if(!farmId)return;
   setBusy(true);setError('');setNotice('');
   try{
     await json(`/farms/${farmId}/feeds`,{
       name:String(feedProductForm.name||'').trim(),
       supplier:String(feedProductForm.supplier||'').trim()||null,
       protein_pct:feedProductForm.protein_pct===''||feedProductForm.protein_pct==null?null:Number(feedProductForm.protein_pct)
     });
     setFeedProductForm({});await loadFeedProducts();setNotice('Feed product added to farm inventory');
   }catch(error){setError(String(error))}finally{setBusy(false)}
 }
 async function receiveFeedStock(e:React.FormEvent){
   e.preventDefault();if(!farmId||!feedReceiptForm.feed_id||!feedReceiptForm.unit_id||!receiptVideo)return;
   setBusy(true);setError('');setNotice('');
   try{
     const unit=units.find(item=>item.id===Number(feedReceiptForm.unit_id));
     if(!unit)throw new Error('Select a production unit for this feed delivery.');
     const evidence=await uploadOperationEvidence('feed_delivery',unit,receiptVideo);
     const query=new URLSearchParams({unit_id:String(unit.id),evidence_id:String(evidence.id)});
     await json(`/farms/${farmId}/feeds/${feedReceiptForm.feed_id}/receipts?${query.toString()}`,{
       quantity_kg:Number(feedReceiptForm.quantity_kg),
       total_cost_ghs:Number(feedReceiptForm.total_cost_ghs),
       occurred_on:feedReceiptForm.occurred_on,
       notes:String(feedReceiptForm.notes||'').trim()||null
     });
     setFeedReceiptForm({occurred_on:localDate()});setReceiptVideo(null);setNotice('Feed receipt recorded with video evidence and stock added');await Promise.all([loadFeedProducts(),loadFarm()]);
   }catch(error){setError(String(error))}finally{setBusy(false)}
 }
 const refreshActivity=useCallback(async()=>{
   if(!farmId)return;
   try{setActivityStatus({...await json('/farms/'+farmId+'/production-activity'),farm_id:farmId});setActivityError('')}
   catch(problem){setActivityStatus(null);setActivityError(String(problem))}
 },[farmId,json]);
 useEffect(()=>{
   if(page!=='production')return;
   void refreshActivity();
   const timer=window.setInterval(()=>void refreshActivity(),15_000);
   return ()=>window.clearInterval(timer);
 },[page,refreshActivity,cycles,sessionRevision]);
 const farmActivity=activityStatus?.farm_id===farmId?activityStatus:null;
 const stockingTasks:Obj[]=farmActivity?.stocking_required??[];
 const attention:Obj[]=farmActivity?.feeding_attention??[];
 const dueCount=attention.filter(row=>row.status==='due').length;
 const overdueCount=attention.length-dueCount;
 function openProductionCard(key:ProductionView){
   setAttentionMode(key==='feeding'&&attention.length>0);
   if(key==='stocking'&&stockingTasks.length===1){
     setStockForm(previous=>({...previous,unit_id:stockingTasks[0].unit_id}));
     setStockVideo(null);
   }
   if(key==='feeding'&&attention.length>0){setDailyVideo(null);setRecorderKey(key=>key+1);openUnitActivity('feeding',attention[0],attention[0]);}
   else openProduction(key);
 }
 async function changeReadiness(unit:Obj,status:string){
   const reason=window.prompt('Why is the stocking readiness changing?');
   if(!reason?.trim()||!farmId)return;
   try{
     await json('/farms/'+farmId+'/units/'+unit.unit_id+'/stocking-readiness',{status,reason},'PUT');
     if(Number(stockForm.unit_id)===unit.unit_id&&status!=='ready'){setStockForm(previous=>({...previous,unit_id:''}));setStockVideo(null)}
     setNotice('Stocking readiness updated');await refreshActivity();
   }catch(problem){setError(String(problem))}
 }
 const sessionPath=farmId&&dailyCycle?'/farms/'+farmId+'/units/'+dailyCycle.unit_id+'/cycles/'+dailyCycle.cycle_id+'/feeding-sessions':'';
 const feedingDate=dailyForm.recorded_on||ghanaDate();
 const sessionForDay=sessionOverview?.path===sessionPath&&sessionOverview.date===feedingDate?sessionOverview:null;
 const retryingFeeding=Boolean(dailyVideo&&pendingFeedingSave.current?.video===dailyVideo&&pendingFeedingSave.current.path===sessionPath.replace(/-sessions$/,''));
 const chosenSession=sessionForDay?.sessions.find((row:Obj)=>row.number===Number(dailyForm.session_number));
 useEffect(()=>{
   let current=true;
   setSessionError('');
   if(page!=='production'||productionView!=='feeding'||!sessionPath)return;
   function loadSessions(initialize:boolean){
     void json(sessionPath+'?day='+encodeURIComponent(feedingDate)).then(data=>{
       if(current){
         setSessionOverview({...data,path:sessionPath});
         if(initialize){
           setSessionTimes(Object.fromEntries(data.sessions.filter((row:Obj)=>row.scheduled_time).map((row:Obj)=>[row.number,row.scheduled_time])));
           setSessionEnds(Object.fromEntries(data.sessions.filter((row:Obj)=>row.scheduled_end).map((row:Obj)=>[row.number,row.scheduled_end])));
         }
         setSessionError('');
       }
     }).catch(error=>{if(current)setSessionError(String(error))});
   }
   loadSessions(true);
   const timer=feedingDate===ghanaDate()?window.setInterval(()=>loadSessions(false),15_000):undefined;
   return ()=>{current=false;window.clearInterval(timer)};
 },[page,productionView,sessionPath,feedingDate,json,sessionRevision]);
 async function editFeedingSession(action:'times'|'skip',session?:number){
   if(!sessionPath)return;
   let body:Obj={times:Object.fromEntries(Object.entries(sessionTimes).filter(([,value])=>value)),ends:Object.fromEntries(Object.entries(sessionEnds).filter(([,value])=>value))};
   if(action==='skip'){
     const reason=window.prompt('Why was this feeding session skipped?');
     if(!reason?.trim())return;
     body={reason:reason.trim()};
   }
   setBusy(true);setSessionError('');
   try{
     const result=await json(sessionPath+(action==='times'?'/times':'/'+session+'/skip')+'?day='+encodeURIComponent(feedingDate),body,action==='times'?'PUT':'POST');
     setSessionOverview({...result,path:sessionPath});
     void refreshActivity();setNotice(action==='times'?'Feeding times saved':'Feeding session marked skipped');
   }catch(error){setSessionError(String(error))}
   finally{setBusy(false)}
 }
 async function reconcileFeeding(entry:Obj, sessionNumber:number, reason:string){
   setBusy(true);setSessionError('');
   try{
     const result=await json(sessionPath+'/reconcile/'+entry.id,{session_number:sessionNumber,reason});
     setSessionOverview({...result,path:sessionPath});void refreshActivity();
     setNotice('Feeding linked to the session');
   }catch(error){setSessionError(String(error))}
   finally{setBusy(false)}
 }
 function selectFeedingSession(session:Obj){
   if(Number(dailyForm.session_number)!==session.number){setDailyVideo(null);setRecorderKey(key=>key+1)}
   setDailyForm(current=>({...current,session_number:session.number,quantity_kg:'',additional_session_event:session.status==='recorded',
     actual_time:feedingDate===ghanaDate()?(current.actual_time||new Date().toISOString().slice(11,16)):current.actual_time,
     feed_id:sessionForDay?.recommended_feed_id??current.feed_id}));
   document.getElementById('feeding-entry')?.scrollIntoView({block:'start',behavior:'smooth'});
 }
 useEffect(()=>{
   if(!dashboardSession||page!=='production'||productionView!=='feeding'||dailyCycleId!==dashboardSession.cycleId||!sessionForDay)return;
   const row=sessionForDay.sessions.find((item:Obj)=>item.number===dashboardSession.number&&item.status!=='skipped');
   if(row){
     setDailyForm(previous=>({...previous,session_number:row.number,quantity_kg:'',additional_session_event:false,actual_time:new Date().toISOString().slice(11,16),feed_id:sessionForDay.recommended_feed_id??previous.feed_id}));
     requestAnimationFrame(()=>document.getElementById('feeding-entry')?.scrollIntoView({block:'start'}));
   }
   setDashboardSession(null);
 },[dashboardSession,page,productionView,dailyCycleId,sessionForDay]);
 function openUnitActivity(section:'feeding'|'growth'|'water_quality'|'schedule'|'harvesting'|'inventory',row:Obj,session?:Obj){
   if(section==='inventory'){setPage('inventory');window.scrollTo(0,0);return}
   if(section==='schedule'){
     setHarvestFilter({farm:row.farm_id??farmId,unit:row.unit_id});
     setHarvestEdit(null);
   }else if(section==='harvesting'){
     if(row.status==='active')setHarvestForm({harvested_on:localDate(),cycle_id:row.cycle_id});
   }else{
     setDailyCycleId(row.cycle_id);
     setDashboardSession(session?{cycleId:row.cycle_id,number:session.number}:null);
     if(section==='feeding')setDailyForm(previous=>({...previous,recorded_on:ghanaDate(),session_number:''}));
   }
   openProduction(section);
 }
 function openOutlookAction(action:'feeding'|'growth'|'water_quality'|'schedule'|'inventory',row?:Obj){
   if(action==='inventory'){setPage('inventory');return}
   if(row)openUnitActivity(action==='schedule'?'feeding':action,row);
   else openProduction('feeding');
   if(action==='feeding'||action==='schedule'){
     const target=action==='schedule'?'manage-feeding-schedule':row?'feeding-entry':'seven-day-feed-outlook';
     requestAnimationFrame(()=>{
       const element=document.getElementById(target);
       if(element instanceof HTMLDetailsElement)element.open=true;
       element?.scrollIntoView({block:'start'});
     });
   }
 }
 async function saveDailyOperation(e:React.FormEvent){
   e.preventDefault();
   if(!farmId||!dailyCycle){setError('Select an active stocking cycle before recording a daily operation.');return}
   if(!dailyVideo){setError('Record the required 15-second video before saving this operation.');return}

   const root=`/farms/${farmId}/units/${dailyCycle.unit_id}`;
   const cycle=`${root}/cycles/${dailyCycle.cycle_id}`;
   let path:string;
   let payload:Obj;
   if(dailyTab==='feeding'){
     path=`${cycle}/feeding`;
     const retry=pendingFeedingSave.current;
     if(retry?.path===path&&retry.video===dailyVideo)payload=retry.payload;
     else {
     if(!sessionForDay){setError('Load the feeding session schedule before saving.');setBusy(false);return}
     if(!chosenSession&&sessionForDay.scheduled_count&&dailyForm.session_number!=='unscheduled'){setError('Select a session or choose unscheduled feeding.');return}
     const actualTime=dailyForm.actual_time??(feedingDate===ghanaDate()?new Date().toISOString().slice(11,16):'');
     if(!actualTime){setError('Enter the actual feeding time.');return}
     if(!(Number(dailyForm.quantity_kg)>0)){setError('Enter a feed quantity greater than zero.');return}
     if(chosenSession?.scheduled_time){
       const start=chosenSession.scheduled_time;
       const end=chosenSession.scheduled_end??ghanaFeedingTime(chosenSession.deadline);
       if(actualTime<start||(end!=='00:00'&&actualTime>=end)){
         setError('Actual feeding time is outside this session window. Choose Unscheduled feeding.');return;
       }
     }
     payload={feed_id:Number(dailyForm.feed_id),quantity_kg:Number(dailyForm.quantity_kg),fed_on:feedingDate,notes:String(dailyForm.notes||'').trim()||null,
       actual_fed_at:feedingDate+'T'+actualTime+':00Z',
       feeding_response:dailyForm.feeding_response||null,
       ...(chosenSession?{recommendation_id:sessionForDay.recommendation_id,schedule_id:sessionForDay.schedule_id,session_number:chosenSession.number,additional_session_event:Boolean(dailyForm.additional_session_event)}:{})};
     }
   }else if(dailyTab==='mortality'){
     path=`${cycle}/mortality`;
     payload={dead_count:Number(dailyForm.dead_count),observed_on:dailyForm.recorded_on,cause:String(dailyForm.cause||'').trim()||null,notes:String(dailyForm.notes||'').trim()||null};
   }else if(dailyTab==='water_quality'){
     path=`${root}/water-quality`;
     payload={observed_at:new Date(dailyForm.observed_at).toISOString(),
       temperature_c:dailyForm.temperature_c===''||dailyForm.temperature_c==null?null:Number(dailyForm.temperature_c),
       dissolved_oxygen_mg_l:dailyForm.dissolved_oxygen_mg_l===''||dailyForm.dissolved_oxygen_mg_l==null?null:Number(dailyForm.dissolved_oxygen_mg_l),
       ph:dailyForm.ph===''||dailyForm.ph==null?null:Number(dailyForm.ph),
       ammonia_mg_l:dailyForm.ammonia_mg_l===''||dailyForm.ammonia_mg_l==null?null:Number(dailyForm.ammonia_mg_l),
       nitrite_mg_l:dailyForm.nitrite_mg_l===''||dailyForm.nitrite_mg_l==null?null:Number(dailyForm.nitrite_mg_l),
       notes:String(dailyForm.notes||'').trim()||null};
     if(['temperature_c','dissolved_oxygen_mg_l','ph','ammonia_mg_l','nitrite_mg_l'].every(key=>payload[key]===null)){
       setError('Enter at least one water-quality measurement.');return;
     }
   }else{
     const weights=String(dailyForm.weights_g||'').split(/[,\s]+/).filter(Boolean).map(Number);
     if(!weights.length||weights.some(weight=>!Number.isFinite(weight)||weight<=0)){
       setError('Enter one or more valid positive sample weights in grams, separated by commas or spaces.');return;
     }
     path=`${cycle}/samples`;
     payload={sampled_on:dailyForm.recorded_on,weights_g:weights,notes:String(dailyForm.notes||'').trim()||null};
   }

   setBusy(true);setError('');setNotice('');
   let uploaded:Obj;
   try{
     const unit=units.find(item=>item.id===dailyCycle.unit_id);
     if(!unit)throw new Error('Production unit not found; refresh the page and try again.');
     const activity=dailyTab==='feeding'?'feeding':dailyTab;
     const retry=pendingFeedingSave.current;
     uploaded=activity==='feeding'&&retry?.path===path&&retry.video===dailyVideo
       ?retry.evidence:await uploadOperationEvidence(activity,unit,dailyVideo,dailyCycle.cycle_id);
     if(activity==='feeding')pendingFeedingSave.current={path,video:dailyVideo,evidence:uploaded,payload};
   }catch(error){setError(String(error));setBusy(false);return}

   try{
     const query=new URLSearchParams({evidence_id:String(uploaded.id)});
     if(dailyTab==='water_quality')query.set('cycle_id',String(dailyCycle.cycle_id));
     await json(`${path}?${query.toString()}`,payload);
     if(dailyTab==='feeding')pendingFeedingSave.current=null;
   }catch(error){
     if(dailyTab==='feeding'&&(!(error instanceof UserFacingError)||error.status==null||error.status===0||error.status>=500)){
       setError('The save could not be confirmed. Press Save again to retry the original details and video.');
       setBusy(false);return;
     }
     if(dailyTab==='feeding')pendingFeedingSave.current=null;
     try{
       await api(`/farms/${farmId}/evidence/${uploaded.id}`,{method:'DELETE'});
       setError(String(error));
     }catch(cleanupError){
       setEvidenceRetry({farm_id:farmId,id:uploaded.id,record_id:null});
       setError(`${String(error)} The video was not linked and could not be removed; use the cleanup button below.`);
     }
     setBusy(false);return;
   }

   setDailyForm({recorded_on:dailyTab==='feeding'?ghanaDate():localDate(),observed_at:localDateTime()});
   setDailyVideo(null);setRecorderKey(key=>key+1);
   if(dailyTab==='feeding'){
     setDailyForm({recorded_on:feedingDate,observed_at:localDateTime()});
     setSessionRevision(value=>value+1);
     setNotice('Feeding entry saved and inventory updated');void refreshActivity();
     document.getElementById(attentionMode?'feeding-attention':'feeding-session-overview')?.scrollIntoView({block:'start'});
     await Promise.all([loadFarm(),loadDailyRecords(),loadFeedProducts()]);
   }else{
     showProductionSuccess('Daily operation recorded with video evidence');
     await loadFarm();await loadDailyRecords();
   }
   setBusy(false);
 }
 async function resolveEvidenceIssue(){
   if(!evidenceRetry)return;
   setBusy(true);
   try{
     if(evidenceRetry.record_id){
       await json(`/farms/${evidenceRetry.farm_id}/evidence/${evidenceRetry.id}/attach`,{record_id:evidenceRetry.record_id});
       setDailyVideo(null);setRecorderKey(key=>key+1);setNotice('Video evidence linked successfully');
     }else{
       await api(`/farms/${evidenceRetry.farm_id}/evidence/${evidenceRetry.id}`,{method:'DELETE'});
       setNotice('Unlinked video evidence deleted');
     }
     setEvidenceRetry(null);setError('');
     await loadFarm();await loadDailyRecords();
   }catch(error){setError(String(error))}finally{setBusy(false)}
 }
 async function stockFish(e:React.FormEvent){
   e.preventDefault();
   if(!farmId||!stockForm.unit_id||!stockVideo){setError('Select a unit and record the required 15-second stocking video.');return}
   setBusy(true);setError('');setNotice('');
   try{
     const unit=units.find(item=>item.id===Number(stockForm.unit_id));
     if(!unit)throw new Error('Production unit not found; refresh the page and try again.');
     const evidence=await uploadOperationEvidence('stocking',unit,stockVideo);
     const query=new URLSearchParams({evidence_id:String(evidence.id)});
     await json(`/farms/${farmId}/units/${stockForm.unit_id}/cycles?${query.toString()}`,{
       species:String(stockForm.species||'').trim(),
       stocked_count:Number(stockForm.stocked_count),
       initial_average_weight_g:Number(stockForm.initial_average_weight_g),
       stocked_on:stockForm.stocked_on,
       harvest_duration_months:harvestMonths||null,
       expected_harvest_on:stockForm.expected_harvest_on||null,
       target_harvest_weight_g:stockForm.target_harvest_weight_g||null,
       expected_survival_pct:stockForm.expected_survival_pct||null,
       notes:String(stockForm.notes||'').trim()||null
     });
     setStockForm({stocked_on:new Date().toISOString().slice(0,10)});
     setStockVideo(null);
     showProductionSuccess('Fish stocking recorded with video evidence');
     await loadFarm();
   }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function closeStocking(cycle:Obj){
   const unit=units.find(u=>u.id===cycle.unit_id);
   if(!farmId||!unit||!window.confirm(`Close the ${cycle.species} stocking cycle in ${unit.name}? This will stop new mortality, sampling, and feeding records for this cycle.`))return;
   setBusy(true);setError('');setNotice('');
   try{
     await api(`/farms/${farmId}/units/${unit.id}/cycles/${cycle.cycle_id}/close`,{method:'POST'});
     showProductionSuccess('Stocking cycle closed successfully');
     await loadFarm();
   }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function archiveUnit(u:Obj){
   if(!farmId||!window.confirm(`Archive ${u.name}? Historical records will be retained.`))return;
   setBusy(true);setError('');setNotice('');
   try{await api(`/farms/${farmId}/units/${u.id}`,{method:'DELETE'});setUnits(await json(`/farms/${farmId}/units`));setUnitFormOpen(false);setNotice('Production unit archived successfully');await loadFarm()}
   catch(e){setError(String(e))}finally{setBusy(false)}
 }

 const selectedInstitution=mine.find(i=>i.id===institutionId);
 const loadLender=useCallback(async()=>{
   if(!institutionId||!token||selectedInstitution?.status!=='verified'){
     setPortfolio(null);setLenderApps([]);setLenderLoans([]);return;
   }
   const endpoints=[`/finance/institutions/${institutionId}/applications`,`/finance/institutions/${institutionId}/loans`,`/finance/institutions/${institutionId}/portfolio`];
   const results=await Promise.allSettled(endpoints.map(path=>json(path)));
   setLenderApps(results[0].status==='fulfilled'?results[0].value:[]);
   setLenderLoans(results[1].status==='fulfilled'?results[1].value:[]);
   setPortfolio(results[2].status==='fulfilled'?results[2].value:null);
   const failed=results.map((r,i)=>r.status==='rejected'?`${endpoints[i]}: ${String((r as PromiseRejectedResult).reason)}`:null).filter(Boolean);
   if(failed.length)setError(failed.join(' | '));
 },[institutionId,json,token,selectedInstitution?.status]);
 useEffect(()=>{void loadLender()},[loadLender]);
 async function submit(path:string,body:Obj,done?:()=>void){setBusy(true);setError('');setNotice('');try{await json(path,body);setNotice('Saved successfully');done?.();await Promise.all([loadFarm(),loadLender(),loadBase()])}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function saveFarm(e:React.FormEvent){e.preventDefault();
 const hasLatitude=farmForm.latitude!==''&&farmForm.latitude!=null;
 const hasLongitude=farmForm.longitude!==''&&farmForm.longitude!=null;
 if(hasLatitude!==hasLongitude){setError('Enter both latitude and longitude, or leave both blank.');return}
 setBusy(true);setError('');setNotice('');try{
 const locationMethod=hasLatitude?(farmForm.location_method||'manual'):null;
 const payload={name:String(farmForm.name||'').trim(),region:String(farmForm.region||'').trim(),district:String(farmForm.district||'').trim(),farm_type:farmForm.farm_type,species:String(farmForm.species||'').trim(),latitude:hasLatitude?Number(farmForm.latitude):null,longitude:hasLongitude?Number(farmForm.longitude):null,location_method:locationMethod,gps_captured_at:locationMethod==='gps'?farmForm.gps_captured_at||new Date().toISOString():null,gps_accuracy_m:farmForm.gps_accuracy_m??null,farm_address:String(farmForm.farm_address||'').trim()||null,nearest_landmark:String(farmForm.nearest_landmark||'').trim()||null};
 const saved=await json(farmEditing!==null?`/farms/${farmEditing}`:'/farms',payload,farmEditing!==null?'PUT':'POST');
 const updated=await json('/farms');setFarms(updated);setFarmId(saved.id);setFarmFormOpen(false);setFarmEditing(null);setFarmForm({farm_type:'pond'});setNotice(farmEditing!==null?'Farm updated successfully':'Farm registered successfully');setPage('farms');
 }catch(e){setError(String(e))}finally{setBusy(false)}}
 async function saveSmsContact(e:React.FormEvent){
   e.preventDefault();setBusy(true);setError('');setNotice('');
   const phone=String(profileForm.phone_number||'').trim();
   try{
     const updated=await json('/auth/me',{phone_number:phone||null,sms_daily_records_enabled:Boolean(profileForm.sms_daily_records_enabled),sms_loan_reminders_enabled:Boolean(profileForm.sms_loan_reminders_enabled)},'PATCH');
     setUser(updated);setProfileForm({phone_number:updated.phone_number??'',sms_daily_records_enabled:updated.sms_daily_records_enabled,sms_loan_reminders_enabled:updated.sms_loan_reminders_enabled});
     setNotice('SMS contact and reminder preferences saved.');
   }catch(error){setError(String(error))}
   finally{setBusy(false)}
 }
 function editFarm(f:Obj){setFarmEditing(f.id);setFarmForm({name:f.name,region:f.region,district:f.district,farm_type:f.farm_type,species:f.species,latitude:f.latitude??'',longitude:f.longitude??'',location_method:f.location_method??'manual',gps_captured_at:f.gps_captured_at??null,gps_accuracy_m:f.gps_accuracy_m??null,farm_address:f.farm_address??'',nearest_landmark:f.nearest_landmark??''});setFarmFormOpen(true);setError('')}
 function newFarm(){setFarmEditing(null);setFarmForm({farm_type:'pond'});setFarmFormOpen(true);setError('')}
 async function archiveFarm(f:Obj){if(!window.confirm(`Archive ${f.name}? It will be hidden from your active farms. Existing production and financial records are not deleted.`))return;setBusy(true);setError('');try{await api(`/farms/${f.id}`,{method:'DELETE'});const updated=await json('/farms');setFarms(updated);setFarmId(old=>old===f.id?(updated[0]?.id??null):old);setNotice('Farm archived. Historical records were retained.');setFarmFormOpen(false)}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function authenticate(e:React.FormEvent){
   e.preventDefault();setError('');setNotice('');
   const identifier=String(form.email??'').trim();
   const testAccount=testAccounts.find(account=>account.username===identifier.toLowerCase());
   if(authMode==='login'&&testAccount){
     if(!localTestPortal){setError('Test accounts sign in through the isolated local test portal.');return}
     if(testAccount.portal!==portal){
       setPortal(testAccount.portal);
       setError('Switched to '+testAccount.label+'. Select Sign in again to continue.');
       return;
     }
   }
   setBusy(true);
   const credentials={email:identifier,password:form.password};
   try{
     if(authMode==='register'){
       if(portal!=='farmer')return;
       await json('/auth/farmer/register',{...credentials,full_name:form.full_name,business_type:form.business_type??'farmer'});
       setAuthMode('login');setForm({email:form.email});
       setNotice('Account created. Sign in to continue.');
     }else{
       const result=await json(`/auth/${portal}/login`,credentials);
       sessionStorage.setItem('aquafarm_token',result.access_token);
       setPage(portal==='admin'?'admin':portal==='institution'?'lender':'overview');
       setForm({});setToken(result.access_token);
     }
   }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 function logout(){sessionStorage.removeItem('aquafarm_token');window.location.reload()}
 async function openApp(id:number){try{setSelectedApp(await json(`/finance/institutions/${institutionId}/applications/${id}`));setForm({});setCustomSchedule([{due_on:'',principal_ghs:'',interest_ghs:'',fees_ghs:''}]);setError('')}catch(e){setError(String(e))}}
 async function openLoan(id:number){try{const [l,s,t]=await Promise.all([json(`/finance/loans/${id}`),json(`/finance/loans/${id}/schedule`),json(`/finance/loans/${id}/transactions`)]);setSelectedLoan(l);setSchedule(s);setTransactions(t);setTransactionVideo(null);setTransactionEvidenceId(null);setTransactionRecorderKey(key=>key+1);setError('')}catch(e){setError(String(e))}}
 const [referenceSearch,setReferenceSearch]=useState('');
 const [applicationPdfBusy,setApplicationPdfBusy]=useState(false);
 const [farmerApplication,setFarmerApplication]=useState<Obj|null>(null);
 const [reportOpen,setReportOpen]=useState(false);
 useEffect(()=>setReportOpen(false),[page,institutionId,farmId]);
 const [applicationPreview,setApplicationPreview]=useState<Obj|null>(null);
 useEffect(()=>setApplicationPreview(null),[farmId,form]);
 useEffect(()=>setFarmerApplication(null),[farmId,page]);
 useEffect(()=>setReferenceSearch(''),[institutionId]);

 function applicationInput(){
   return {...form,institution_id:Number(form.institution_id),term_months:Number(form.term_months),
     monthly_other_income_ghs:form.monthly_other_income_ghs||null,
     monthly_household_expenses_ghs:form.monthly_household_expenses_ghs||null,
     monthly_external_debt_ghs:form.monthly_external_debt_ghs||null};
 }
 async function previewLoanApplication(){
   if(!farmId)return;
   setBusy(true);setError('');
   try{setApplicationPreview(await json('/farms/'+farmId+'/loan-application-preview',applicationInput()))}
   catch(error){setError(String(error))}
   finally{setBusy(false)}
 }
 async function findLoanApplication(e:React.FormEvent){
   e.preventDefault();
   if(!institutionId)return;
   setSelectedApp(null);setError('');setBusy(true);
   try{
     const result=await json('/finance/institutions/'+institutionId+'/application-lookup?reference='+encodeURIComponent(referenceSearch.trim()));
     setSelectedApp(result);setForm({});setCustomSchedule([{due_on:'',principal_ghs:'',interest_ghs:'',fees_ghs:''}]);
   }catch(error){setError(String(error))}
   finally{setBusy(false)}
 }
 async function viewFarmerApplication(id:number){
   if(!farmId)return;
   setError('');setFarmerApplication(null);
   try{setFarmerApplication(await json('/farms/'+farmId+'/loan-applications/'+id))}
   catch(error){setError(String(error))}
 }
 async function respondToLoanOffer(id:number,decision:'accept'|'decline'){
   if(!window.confirm(decision==='accept'?'Accept the terms and proposed repayment schedule shown?':'Decline this loan offer?'))return;
   setBusy(true);setError('');
   try{
     await json('/finance/loans/'+id+'/offer-response',{decision});
     setNotice(decision==='accept'?'Loan offer accepted. Awaiting disbursement.':'Loan offer declined.');
     await Promise.all([loadFarm(),openLoan(id)]);
   }catch(error){setError(String(error))}
   finally{setBusy(false)}
 }
 async function submitLoanApplication(e:React.FormEvent){
   e.preventDefault();if(!farmId)return;
   if(!applicationVideo){setError('Record the required new 15-second application video before submitting.');return}
   setBusy(true);setError('');setNotice('');
   try{
     let evidenceId=applicationEvidenceId;
     if(evidenceId===null){const uploaded=await uploadLoanEvidence('loan_application',applicationVideo);evidenceId=uploaded.id;setApplicationEvidenceId(evidenceId)}
     const submitted=await json('/farms/'+farmId+'/loan-applications',{
       ...applicationInput(),evidence_id:evidenceId,share_report:!!form.share_report,
     });
     setNotice('Loan application submitted. Reference '+submitted.reference);
     setApplicationVideo(null);setApplicationEvidenceId(null);setApplicationRecorderKey(key=>key+1);setForm({});
     await loadFarm();
   }catch(error){setError(String(error))}
   finally{setBusy(false)}
 }
 async function openApprovedLoan(e:React.FormEvent){
   e.preventDefault();if(!institutionId||!selectedApp)return;
   const frequency=String(form.repayment_frequency||'');
   const custom=frequency==='custom';
   const firstDue=custom?customSchedule[0]?.due_on:form.first_due_date;
   const payload={application_id:selectedApp.id,annual_flat_interest_percent:form.annual_flat_interest_percent,
     commitment_fee_ghs:Number(form.commitment_fee_ghs||0),processing_fee_percent:form.processing_fee_percent||'0',
     insurance_fee_percent:insuranceRate,
     repayment_frequency:frequency,first_due_date:firstDue,
     ...(custom?{custom_schedule:customSchedule.map(item=>({due_on:item.due_on,principal_ghs:item.principal_ghs,interest_ghs:item.interest_ghs,fees_ghs:item.fees_ghs||0}))}:{})};
   setBusy(true);setError('');setNotice('');
   try{await json(`/finance/institutions/${institutionId}/loans`,payload);setNotice('Loan offer sent. The farmer must accept before disbursement.');setSelectedApp(null);setForm({});await Promise.all([loadFarm(),loadLender()])}
   catch(error){setError(String(error))}
   finally{setBusy(false)}
 }
 async function saveLoanTransaction(e:React.FormEvent,kind:'disbursements'|'repayments'){
   e.preventDefault();if(!selectedLoan)return;
   if(!transactionVideo){setError('Record the required new 15-second video before submitting this transaction.');return}
   const id=selectedLoan.id;
   setBusy(true);setError('');setNotice('');
   try{
     let evidenceId=transactionEvidenceId;
     if(evidenceId===null){const uploaded=await uploadLoanEvidence(kind==='disbursements'?'disbursement':'repayment',transactionVideo,id);evidenceId=uploaded.id;setTransactionEvidenceId(evidenceId)}
     await json(`/finance/loans/${id}/${kind}`,{amount_ghs:form.loan_amount_ghs,reference:form.loan_reference,transaction_date:form.loan_transaction_date,evidence_id:evidenceId});
     setNotice(kind==='disbursements'?'Disbursement recorded with video evidence.':'Repayment recorded with video evidence.');
     setForm({});setTransactionVideo(null);setTransactionEvidenceId(null);setTransactionRecorderKey(key=>key+1);
     await Promise.all([loadFarm(),loadLender()]);await openLoan(id)
   }
   catch(error){setError(String(error))}
   finally{setBusy(false)}
 }
 async function downloadPricingPdf(path:string,body:Obj,filename:string){
   const response=await api(path,{method:'POST',body:JSON.stringify(body)});
   const blob=await response.blob();
   if(blob.type!=='application/pdf'||await blob.slice(0,5).text()!=='%PDF-')throw new UserFacingError('Unable to download pricing PDF.');
   const url=URL.createObjectURL(blob);
   const link=document.createElement('a');
   link.href=url;link.download=filename;link.click();
   window.setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 async function downloadApplicationPdf(path:string,reference:string){
   const response=await api(path);
   if(response.headers.get('Content-Type')?.split(';')[0]!=='application/pdf')throw new Error('The server did not return a PDF.');
   const blob=await response.blob();
   if(await blob.slice(0,5).text()!=='%PDF-')throw new Error('The downloaded report is not a valid PDF.');
   const url=URL.createObjectURL(blob);
   const link=document.createElement('a');
   link.href=url;link.download=reference+'.pdf';link.click();
   window.setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 async function downloadFarmerSummary(){
   if(!farmerApplication||!farmId||applicationPdfBusy)return;
   setApplicationPdfBusy(true);setError('');
   try{await downloadApplicationPdf('/farms/'+farmId+'/loan-applications/'+farmerApplication.id+'/report.pdf',farmerApplication.reference)}
   catch(error){setError('Could not download the application PDF. '+String(error))}
   finally{setApplicationPdfBusy(false)}
 }
 async function download(path:string,filename:string){try{const r=await api(path);const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();URL.revokeObjectURL(url)}catch(e){setError(String(e))}}
 const institutionRole=selectedInstitution?.role;
 const canAppraise=['owner','reviewer','credit_manager'].includes(institutionRole);
 const canAssess=canAppraise||institutionRole==='loan_officer';
 const canDisburse=['owner','officer','disbursement'].includes(institutionRole);
 const canRepay=['owner','officer','collections'].includes(institutionRole);
 const [salesTab,setSalesTab]=useState<'sales'|'customers'|'invoices'|'payments'|'credit'>('sales');
 const [salesData,setSalesData]=useState<{customers:Obj[],sales:Obj[],summary:Obj,harvests:Obj[]}|null>(null);
 const [salesAction,setSalesAction]=useState<'customer'|'sale'|'payment'|null>(null);
 const [salesForm,setSalesForm]=useState<Obj>({});
 const [saleVideo,setSaleVideo]=useState<RecordedVideo|null>(null);
 const [salesSaving,setSalesSaving]=useState(false);
 const [salesSearch,setSalesSearch]=useState('');
 const [balanceFilter,setBalanceFilter]=useState('outstanding');
 const dispatchLot=salesData?.harvests.find(lot=>lot.id===Number(salesForm.harvest_lot_id));
 const dispatchUnit=units.find(unit=>unit.id===cycles.find(cycle=>cycle.cycle_id===dispatchLot?.cycle_id)?.unit_id);
 const paymentSale=salesData?.sales.find(sale=>sale.id===Number(salesForm.sale_id));
 useEffect(()=>{setSalesAction(null);setSalesForm({});setSaleVideo(null);setSaleId('')},[farmId,page]);

 function startSalesAction(action:'customer'|'sale'|'payment',values:Obj={}){
   setSalesTab(action==='customer'?'customers':action==='sale'?'sales':'payments');
   setSalesAction(action);setSaleVideo(null);setError('');setNotice('');
   setSalesForm({sold_on:localDate(),paid_on:localDate(),customer_type:'individual',method:'cash',terms:'credit',...values});
 }
 async function saveSalesEntry(event:React.FormEvent){
   event.preventDefault();
   if(!farmId||!salesAction||salesSaving)return;
   setSalesSaving(true);setError('');setNotice('');
   const root='/farms/'+farmId+'/sales';
   let evidenceId:number|undefined;
   try{
     if(salesAction==='customer'){
       await json(root+'/customers'+(salesForm.id?'/'+salesForm.id:''),{
         name:salesForm.name,customer_type:salesForm.customer_type,phone:salesForm.phone||null,notes:salesForm.notes||null,
         email:salesForm.email||null,region:salesForm.region||null,district:salesForm.district||null,address:salesForm.address||null,
       },salesForm.id?'PUT':'POST');
     }else if(salesAction==='payment'){
       await json(root+'/transactions/'+salesForm.sale_id+'/payments',{
         amount_ghs:salesForm.amount_ghs,paid_on:salesForm.paid_on,method:salesForm.method,reference:salesForm.reference||null,
       });
     }else{
       if(!dispatchLot||!dispatchUnit||!saleVideo)throw new Error('Select a harvest lot and record dispatch evidence.');
       const evidence=await uploadOperationEvidence('sale_dispatch',dispatchUnit,saleVideo,dispatchLot.cycle_id);
       evidenceId=evidence.id;
       await json(root+'/transactions?evidence_id='+evidenceId,{
         harvest_lot_id:dispatchLot.id,customer_id:salesForm.customer_id?Number(salesForm.customer_id):null,
         sold_on:salesForm.sold_on,quantity_kg:Number(salesForm.quantity_kg),price_ghs_per_kg:salesForm.price_ghs_per_kg,
         notes:salesForm.notes||null,due_on:salesForm.terms==='full'?null:salesForm.due_on,
         initial_payment:salesForm.terms==='partial'?{paid_on:salesForm.sold_on,amount_ghs:salesForm.amount_ghs,method:salesForm.method,reference:salesForm.reference||null}:null,
         paid_in_full:salesForm.terms==='full'?{method:salesForm.method,reference:salesForm.reference||null}:null,
       });
       evidenceId=undefined;
     }
     if(salesAction==='payment')setSaleId(String(salesForm.sale_id));
     setNotice(salesAction==='customer'?'Customer saved':salesAction==='payment'?'Payment recorded':'Sale recorded and invoice available');
     setSalesAction(null);setSaleVideo(null);setWorkspaceRefresh(value=>value+1);
     await loadFarm();
   }catch(problem){
     if(evidenceId){
       try{await api('/farms/'+farmId+'/evidence/'+evidenceId,{method:'DELETE'})}
       catch{setError(String(problem)+' The unused dispatch video could not be removed.');return}
     }
     setError(String(problem));
   }finally{setSalesSaving(false)}
 }
 function salesField(key:string,label:string,type='text',extra:Obj={}){
   return <label className="field"><span>{label}</span><input type={type} value={salesForm[key]??''}
    onChange={event=>setSalesForm({...salesForm,[key]:event.target.value})} {...extra}/></label>;
 }
 const paymentMethods=[['cash','Cash'],['mobile_money','Mobile Money'],['bank_transfer','Bank Transfer'],['cheque','Cheque'],['other','Other']];
 const [staffRows,setStaffRows]=useState<Obj[]|null>(null);
 const [saleId,setSaleId]=useState('');
 const [salePayments,setSalePayments]=useState<Obj[]|null>(null);
 const [workspaceError,setWorkspaceError]=useState('');
 const [workspaceRefresh,setWorkspaceRefresh]=useState(0);
 useEffect(()=>{
   let current=true;
   setWorkspaceError('');
   setSalesData(null);
   setStaffRows(null);
   if(farmId&&(page==='sales'||page==='staff')){
     const root='/farms/'+farmId;
     const request=page==='sales'?Promise.all([
       json(root+'/sales/customers'),json(root+'/sales/transactions'),json(root+'/sales/summary'),json(root+'/sales/harvests'),
     ]).then(([customers,sales,summary,harvests])=>{if(current)setSalesData({customers,sales,summary,harvests})}):
       json(root+'/supervisors').then(rows=>{if(current)setStaffRows(rows)});
     request.catch(error=>{if(current)setWorkspaceError(String(error))});
   }
   return ()=>{current=false};
 },[page,farmId,json,workspaceRefresh]);
 useEffect(()=>{
   let current=true;
   setSalePayments(null);
   if(page==='sales'&&salesTab==='payments'&&farmId&&saleId){
     json('/farms/'+farmId+'/sales/transactions/'+saleId+'/payments')
       .then(rows=>{if(current)setSalePayments(rows)})
       .catch(error=>{if(current)setError(String(error))});
   }
   return ()=>{current=false};
 },[page,salesTab,farmId,saleId,json,workspaceRefresh]);
 const nav=([
   ['overview','Dashboard',<LayoutDashboard size={18}/>],
   ['farms','My Farms',<Building2 size={18}/>],
   ['production','Production',<Fish size={18}/>],
   ['processing','Processing & Value Addition',<Package size={18}/>],
   ['sales','Sales & Invoices',<ShoppingBasket size={18}/>],
   ['inventory','Inventory',<Package size={18}/>],
   ['finance','Finance',<Wallet size={18}/>],
   ['reports','Reports & Analytics',<FileDown size={18}/>],
   ['staff','Staff Management',<Users size={18}/>],
   ['settings','Settings',<Settings size={18}/>],
   ['lender','Institution Portal',<Landmark size={18}/>],
   ['admin','Platform Administration',<Building2 size={18}/>],
 ] as [Page,string,React.ReactNode][]).filter(([key])=>{
   if(!user)return false;
   if(user.is_platform_admin)return key==='admin';
   if(key==='admin')return false;
   if(processorOnly&&['farms','production','inventory','finance','staff'].includes(key))return false;
   if(key==='lender')return user.account_type==='institution'||user.account_type==='legacy'||mine.length>0;
   return user.account_type!=='institution';
 });
 const field=(name:string,label:string,type='text',extra:Obj={})=><label className="field" key={name}><span>{label}</span><input type={type} value={form[name]??''} onChange={e=>setForm({...form,[name]:e.target.value})} {...extra}/></label>;
 const dropdown=(name:string,label:string,options:{value:string|number,label:string}[])=><label className="field"><span>{label}</span><select value={form[name]??''} onChange={e=>setForm({...form,[name]:e.target.value})}><option value="">Choose...</option>{options.map(x=><option value={x.value} key={x.value}>{x.label}</option>)}</select></label>;
 const formSubmit=(e:React.FormEvent,path:string,body:Obj,done?:()=>void)=>{e.preventDefault();void submit(path,body,done)};
 const reportRows:Obj[]=analytics?[
  ...Object.entries(analytics.summary||{}).map(([metric,value])=>({section:'Farm summary',record:metric,value})),
  ...(analytics.production?.cycles||[]).map((row:Obj)=>({section:'Production cycle',record:`Cycle ${row.cycle_id} · ${row.unit_name}`,value:`${row.species} · ${num(row.estimated_live_count)} live · ${num(row.estimated_biomass_kg)} kg`})),
  ...(analytics.production?.growth_trends||[]).map((row:Obj)=>({section:'Growth sample',record:`${row.unit_name} · ${row.sampled_on}`,value:`${num(row.average_weight_g)} g · ${row.sample_count} fish`})),
  ...(analytics.production?.harvest_forecasts||[]).map((row:Obj)=>({section:'Harvest forecast',record:`${row.unit_name} · ${row.species}`,value:`${row.expected_harvest_kg==null?'No estimate':`${num(row.expected_harvest_kg)} kg`} · ${row.expected_harvest_on||'date unavailable'}`})),
  ...(analytics.feed?.inventory||[]).map((row:Obj)=>({section:'Feed inventory',record:row.feed_name,value:`${num(row.remaining_stock_kg)} kg · purchased ${num(row.purchased_kg)} kg · consumed ${num(row.consumed_kg)} kg`})),
  ...(analytics.feed?.forecast?.feeds||[]).map((row:Obj)=>({section:'Feed forecast',record:row.feed_name,value:`${num(row.expected_usage_kg)} kg needed in ${row.forecast_days} days · ${row.shortage_expected?'shortage expected':'stock estimate available'}`})),
  ...(analytics.water_quality?.latest_by_unit||[]).map((row:Obj)=>({section:'Water quality',record:`${row.unit_name} · ${new Date(row.observed_at).toLocaleDateString()}`,value:`DO ${row.dissolved_oxygen_mg_l??'—'} · pH ${row.ph??'—'} · ${row.temperature_c??'—'} °C`})),
  ...(analytics.finance?.pricing_by_plan||[]).map((row:Obj)=>({section:'Pricing estimate',record:`Plan ${row.plan_id} · ${row.species}`,value:`Break-even ${row.break_even_ghs_per_kg==null?'unavailable':money(row.break_even_ghs_per_kg)+'/kg'} · recommended ${row.recommended_price_ghs_per_kg==null?'unavailable':money(row.recommended_price_ghs_per_kg)+'/kg'} · projected profit ${row.projected_profit_ghs==null?'unavailable':money(row.projected_profit_ghs)}`})),
 ]:[];
 const filteredReportRows=reportRows.filter(row=>!reportSearch.trim()||JSON.stringify(row).toLowerCase().includes(reportSearch.trim().toLowerCase()));
 const cashChart=(title:string,data:Obj[])=><BarChart title={title} data={data} labelKey="period" series={[
   {key:'payments_received_ghs',label:'Payments received',color:'#168064'},
   {key:'feed_purchase_cash_outflow_ghs',label:'Feed purchases',color:'#e5a84b'},
   {key:'recorded_expenses_ghs',label:'Other expenses paid',color:'#5676b8'},
 ]}/>;
 const reportDefinitions=[
  {kind:'summary',label:'Farm summary',description:'Key farm indicators and warnings',csv:'summary.csv'},
  {kind:'production',label:'Production and growth',description:'Cycles, samples, mortality and harvest forecasts',csv:'analytics/production.csv'},
  {kind:'sales',label:'Sales and cash flow',description:'Sales, receipts, receivables and monthly activity',csv:'analytics/sales.csv'},
  {kind:'inventory',label:'Feed inventory',description:'Purchases, consumption, balances and feed forecast',csv:'analytics/inventory.csv'},
  {kind:'financial',label:'Financial analysis',description:'Recorded costs, cost per kg and recommended prices',csv:'analytics/financial.csv'},
  {kind:'bank-ready',label:'Investment-ready report',description:'Production, sales, costs, receivables and evidence caveats',csv:'bank-ready.csv'},
 ];
 if(!token)return <div className="authwrap"><div className="authcard">
   <div className="brand dark"><Waves size={30}/><span>AquaFarm <b>Manager Ghana</b></span></div>
   <label className="field"><span>Portal</span><select value={portal} disabled={busy} onChange={e=>{
     setPortal(e.target.value as typeof portal);setAuthMode('login');setShowLoginPassword(false);setForm({});setError('');setNotice('');
   }}><option value="farmer">Farmer</option><option value="institution">Bank or financial institution</option><option value="admin">Super Admin / Platform administrator</option></select></label>
   {authMode==='login'&&(localTestPortal?<div className="workspace-tabs">
     <p className="muted">Choose a local test account to fill in its username and select its portal.</p>
     <div className="farmactions">{testAccounts.map(account=><button key={account.username} type="button" className="outline small" disabled={busy} onClick={()=>{
       setPortal(account.portal);setForm({email:account.username});setError('');setNotice('');
     }}>{account.label}</button>)}</div>
   </div>:import.meta.env.DEV&&<p className="muted">Using a seeded test account? <a href="http://127.0.0.1:5174/">Open the local test portal</a>.</p>)}
   {portal==='institution'&&<p className="muted">Authorized AquaFarm Manager Ghana administrators create institution accounts.</p>}
   <h1>{authMode==='login'?'Sign in':'Register as a farmer'}</h1>
   {error&&<ErrorNotice message={error} dismiss={()=>setError('')}/>}{notice&&<div className="success">{notice}</div>}
   <form onSubmit={authenticate}>
     {authMode==='register'&&field('full_name','Full Name','text',{required:true,maxLength:120,autoComplete:'name'})}
     {authMode==='register'?field('email','Email','email',{required:true,autoComplete:'email'}):field('email','Username or email','text',{required:true,maxLength:255,autoComplete:'username'})}
     {field('password','Password',authMode==='login'&&showLoginPassword?'text':'password',{required:true,minLength:authMode==='register'?8:1,maxLength:128,autoComplete:authMode==='register'?'new-password':'current-password'})}
     {authMode==='login'&&<button type="button" className="textbutton" onClick={()=>setShowLoginPassword(value=>!value)}>{showLoginPassword?'Hide password':'Show password'}</button>}
     {authMode==='register'&&portal==='farmer'&&<label className="field"><span>Business type</span><select value={form.business_type??'farmer'} onChange={event=>setForm({...form,business_type:event.target.value})}>
      <option value="farmer">Fish Farmer</option><option value="processor">Fish Processor</option><option value="integrated">Integrated Fish Farmer and Processor</option>
     </select></label>}
     <button className="primary" disabled={busy}>{busy?'Please wait?':authMode==='login'?'Sign in':'Register'}</button>
   </form>
   {portal==='farmer'&&<button className="textbutton" disabled={busy} onClick={()=>{setAuthMode(authMode==='login'?'register':'login');setShowLoginPassword(false);setError('');setNotice('');setForm({})}}>
     {authMode==='register'?'Back to sign in':'Create a farmer account'}
   </button>}
 </div></div>;
 if(!user)return <div className="authwrap"><div className="authcard">
   {error?<><div className="alert">{error}</div><button onClick={logout}>Return to sign in</button></>:<p role="status">Loading your workspace?</p>}
 </div></div>;
 const currentSales=salesData?.sales.filter(row=>{
   if(salesTab!=='credit'||balanceFilter==='all')return true;
   if(balanceFilter==='paid')return row.outstanding_ghs===0;
   if(row.outstanding_ghs<=0)return false;
   if(balanceFilter==='overdue')return Boolean(row.due_on&&row.due_on<localDate());
   if(balanceFilter==='due_soon')return Boolean(row.due_on&&row.due_on>=localDate()&&Date.parse(row.due_on)-Date.parse(localDate())<=7*86400000);
   if(balanceFilter==='current')return Boolean(!row.due_on||row.due_on>=localDate());
   return true;
 })??[];
 return <div className="shell"><aside className="sidebar"><div className="brand"><Waves size={29}/><span>AquaFarm <b>Manager Ghana</b></span></div><div className="navlabel">WORKSPACE</div><nav>{nav.map(([key,label,ic])=>key==='production'?<div className="production-nav" key={key}>
 <button type="button" className={page==='production'?'active':''} aria-expanded={productionExpanded} aria-controls="production-menu" onClick={()=>{
   if(page==='production'&&productionExpanded)setProductionExpanded(false);
   else if(page==='production')setProductionExpanded(true);
   else openProduction('landing');
 }}>{ic}{label}<ChevronDown className={productionExpanded?'expanded':''} size={16}/></button>
 <div id="production-menu" hidden={!productionExpanded}>
 <button type="button" aria-current={page==='production'&&productionView==='landing'?'page':undefined} onClick={()=>openProduction('landing')}>Production Overview</button>
 {productionActivities.map(activity=><button type="button" key={activity.key} aria-current={page==='production'&&productionView===activity.key?'page':undefined} onClick={()=>openProduction(activity.key)}>{activity.label}</button>)}
 </div>
 </div>:<button key={key} className={(page===key||(page==='units'&&key==='farms')||(page==='expenses'&&key==='finance'))?'active':''} onClick={()=>{if(key==='overview'){backToDashboard();void loadFarm()}else if(key==='processing'){openProcessing()}else if(key==='sales'&&processorOnly){openProcessing('sales')}else if(key==='reports'){openReport(null)}else{setPage(key);window.history.replaceState(null,'',window.location.pathname+window.location.search)}setProductionExpanded(false);setForm({});setSelectedApp(null);setSelectedLoan(null);setNotice('')}}>{ic}{label}</button>)}</nav><div className="sidefoot"><div className="usericon">{user?.full_name?.slice(0,1)||'U'}</div><div className="who"><b>{user?.full_name||'Account'}</b><small>{user?.email||''}</small></div><button aria-label="Sign out" title="Switch account" onClick={logout}><LogOut size={18}/></button></div></aside><main className="main"><header><div><span className="eyebrow">AQUAFARM / {page.toUpperCase()}</span><h1>{page==='production'?(productionView==='landing'?'Production Management':productionActivities.find(item=>item.key===productionView)?.label):page==='units'?'Production units':page==='history'?'Farm Activity History':page==='reports'?(reports.find(([key])=>key===reportView)?.[1]??'Farm Reports & Analytics'):page==='expenses'?'Farm Expenses':nav.find(x=>x[0]===page)?.[1]}</h1></div><div className="headeractions"><button type="button" className="outline" onClick={logout}><LogOut size={16}/> Switch account</button>{page!=='lender'&&page!=='admin'&&<select aria-label="Selected farm" value={farmId??''} onChange={e=>{setFarmId(Number(e.target.value));if(page==='history')openHistory({tab:historyContext.tab})}}>{farms.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}{!farms.length&&<option value="">No farms</option>}</select>}<button className="outline" onClick={()=>{void loadBase();void loadFarm();void loadUnits();void loadLender();setWorkspaceRefresh(value=>value+1)}}><RefreshCw size={16}/> Refresh</button></div></header>{error&&<div className="alert"><AlertTriangle size={17}/>{error}<button onClick={()=>setError('')}>×</button></div>}{page!=='finance'&&reminders.some(r=>r.status==='overdue')&&<div className="alert" role="status"><AlertTriangle size={17}/>{reminders.filter(r=>r.status==='overdue').length} loan instalment{reminders.filter(r=>r.status==='overdue').length===1?' is':'s are'} overdue. <button className="outline small" onClick={()=>setPage('finance')}>View repayments</button></div>}{notice&&<div className="success"><CheckCircle2 size={17}/>{notice}</div>}
 {(page==='farms'||page==='units')&&<div className="farmactions workspace-tabs" aria-label="Farm management">
  <button className="outline" aria-pressed={page==='farms'} onClick={()=>setPage('farms')}>Farms</button>
  <button className="outline" aria-pressed={page==='units'} onClick={()=>setPage('units')}>Production units</button>
 </div>}
 {(page==='finance'||page==='reports'||page==='expenses')&&<div className="farmactions workspace-tabs" aria-label="Finance navigation">
  <button className="outline" aria-pressed={page==='finance'} onClick={()=>setPage('finance')}>Financing and loans</button>
  <button className="outline" aria-pressed={page==='reports'} onClick={()=>openReport(null)}>Reports &amp; Analytics</button>
  <button className="outline" aria-pressed={page==='expenses'} onClick={()=>setPage('expenses')}>Farm Expenses</button>
 </div>}
 {page==='staff'&&<section className="panel"><h2>Farm supervisors</h2>
  <p className="muted">Supervisors verify farm evidence. Delegated operational roles and permissions are not available in this workspace.</p>
  {!farmId?<p className="empty">Select a farm.</p>:workspaceError?<ErrorNotice message={workspaceError} retry={()=>setWorkspaceRefresh(value=>value+1)}/>:staffRows===null?<p role="status">Loading supervisors?</p>:staffRows.length?staffRows.map(row=><div className="item" key={row.id}><b>{row.full_name}</b><small>{row.email}</small></div>):<p className="empty">No supervisors assigned to this farm.</p>}
 </section>}
 {page==='sales'&&<section className="panel">
  {processingBusiness?.business_type==='integrated'&&<button className="outline" onClick={()=>openProcessing('sales')}>Processed Product Sales</button>}
  <div className="farmactions workspace-tabs" aria-label="Sales views">
   {([['sales','Sales'],['customers','Customers'],['invoices','Invoices'],['payments','Payments'],['credit','Receivables']] as const).map(([key,label])=><button className="outline" key={key} aria-pressed={salesTab===key} onClick={()=>{setSalesAction(null);setSalesTab(key)}}>{label}</button>)}
  </div>
  {farmId&&<div className="farmactions workspace-tabs" aria-label="Sales quick actions">
   <button className="primary" onClick={()=>startSalesAction('sale')}>{salesData?.sales.length===0?'Record Your First Sale':'Record New Sale'}</button>
   <button className="outline" onClick={()=>startSalesAction('customer')}>{salesData?.customers.length===0?'Add Your First Customer':'Add Customer'}</button>
   <button className="outline" onClick={()=>startSalesAction('payment')}>Record Payment</button>
   <button className="outline" onClick={()=>{setSalesAction(null);setSalesTab('invoices')}}>View invoices</button>
  </div>}
  {salesAction&&salesData&&<form className="farmform workspace-tabs" onSubmit={saveSalesEntry}>
   <h3>{salesAction==='customer'?(salesForm.id?'Edit customer':'Add customer'):salesAction==='sale'?'Record new sale':'Record payment'}</h3>
   {salesAction==='customer'&&<>
    {salesField('name','Customer full name or business name','text',{required:true,maxLength:150})}
    <label className="field"><span>Customer type</span><select value={salesForm.customer_type} onChange={event=>setSalesForm({...salesForm,customer_type:event.target.value})}>
     {['individual','retailer','wholesaler','restaurant','supermarket','fish_processor','other'].map(key=><option key={key} value={key}>{key.replace(/_/g,' ')}</option>)}
    </select></label>
    {salesField('phone','Phone','tel',{maxLength:40})}
    {salesField('email','Email (optional)','email',{maxLength:255})}
    {salesField('region','Region','text',{maxLength:100})}
    {salesField('district','District or town','text',{maxLength:100})}
    {salesField('address','Address','text',{maxLength:250})}
   </>}
   {salesAction==='sale'&&<>
    <label className="field"><span>Harvest batch</span><select required value={salesForm.harvest_lot_id??''} onChange={event=>{setSalesForm({...salesForm,harvest_lot_id:event.target.value});setSaleVideo(null)}}>
     <option value="">Choose a harvest</option>{salesData.harvests.filter(lot=>lot.available_kg>0).map(lot=><option key={lot.id} value={lot.id}>Batch #{lot.id} | {lot.harvested_on} | {num(lot.available_kg)} kg available</option>)}
    </select></label>
    {!salesData.harvests.some(lot=>lot.available_kg>0)&&<p className="muted">Record a harvest with available stock in Production before recording a sale.</p>}
    <label className="field"><span>Customer</span><select value={salesForm.customer_id??''} onChange={event=>setSalesForm({...salesForm,customer_id:event.target.value})}>
     <option value="">Walk-in buyer (under 500 kg)</option>{salesData.customers.map(customer=><option key={customer.id} value={customer.id}>{customer.name}</option>)}
    </select></label>
    {salesField('sold_on','Sale date','date',{required:true,min:dispatchLot?.harvested_on,max:localDate()})}
    {salesField('quantity_kg','Quantity sold (kg)','number',{required:true,min:0.001,step:'any',max:dispatchLot?.available_kg})}
    {salesField('price_ghs_per_kg','Selling price per kg (GH?)','number',{required:true,min:0.01,step:0.01})}
    {farmId&&dispatchLot&&<PricingAdvisor key={dispatchLot.cycle_id} farmId={farmId} cycleId={dispatchLot.cycle_id} load={json}
     download={downloadPricingPdf} revision={analytics} price={String(salesForm.price_ghs_per_kg??'')} quantity={String(salesForm.quantity_kg??'')}
     onUsePrice={value=>setSalesForm(previous=>({...previous,price_ghs_per_kg:value}))}/>}
    <Line label="Estimated sale total" value={money(Number(salesForm.quantity_kg||0)*Number(salesForm.price_ghs_per_kg||0))}/>
    <label className="field"><span>Payment terms</span><select value={salesForm.terms} onChange={event=>setSalesForm({...salesForm,terms:event.target.value})}>
     <option value="credit">Credit sale (no payment now)</option><option value="partial">Partially paid</option><option value="full">Fully paid</option>
    </select></label>
    {salesForm.terms!=='full'&&salesField('due_on','Payment due date','date',{required:true,min:salesForm.sold_on})}
    {dispatchLot&&<EvidenceRecorder key={dispatchLot.id} activity="sale_dispatch" unit={dispatchUnit} getChallenge={getEvidenceChallenge} onChange={setSaleVideo}/>}
   </>}
   {salesAction==='payment'&&<>
    <label className="field"><span>Invoice with outstanding balance</span><select required value={salesForm.sale_id??''} onChange={event=>setSalesForm({...salesForm,sale_id:event.target.value})}>
     <option value="">Choose an invoice</option>{salesData.sales.filter(sale=>sale.outstanding_ghs>0).map(sale=><option key={sale.id} value={sale.id}>{sale.invoice_number} | {money(sale.outstanding_ghs)} outstanding</option>)}
    </select></label>
    {salesField('paid_on','Payment date','date',{required:true,min:paymentSale?.sold_on,max:localDate()})}
   </>}
   {(salesAction==='payment'||(salesAction==='sale'&&salesForm.terms!=='credit'))&&<>
    {(salesAction==='payment'||salesForm.terms==='partial')&&salesField('amount_ghs','Amount received (GH?)','number',{required:true,min:0.01,step:0.01,max:paymentSale?.outstanding_ghs})}
    <label className="field"><span>Payment method</span><select value={salesForm.method} onChange={event=>setSalesForm({...salesForm,method:event.target.value})}>
     {paymentMethods.map(([key,label])=><option key={key} value={key}>{label}</option>)}
    </select></label>
    {salesField('reference','Payment reference','text',{maxLength:120})}
   </>}
   {salesAction!=='payment'&&salesField('notes','Notes','text',{maxLength:1000})}
   <div className="farmactions"><button className="primary" disabled={salesSaving||(salesAction==='sale'&&!saleVideo)}>{salesSaving?'Saving?':'Save '+salesAction}</button>
    <button type="button" className="outline" disabled={salesSaving} onClick={()=>setSalesAction(null)}>Cancel</button></div>
  </form>}
  {!farmId?<p className="empty">Select a farm.</p>:workspaceError?<ErrorNotice message={workspaceError} retry={()=>setWorkspaceRefresh(value=>value+1)}/>:!salesData?<p role="status">Loading sales records?</p>:<>
   {salesTab==='customers'&&<>
    <label className="field"><span>Search customers</span><input type="search" value={salesSearch} onChange={event=>setSalesSearch(event.target.value)}/></label>
    {salesData.customers.length?salesData.customers.filter(row=>String(row.name).toLowerCase().includes(salesSearch.trim().toLowerCase())).map(row=><div className="item" key={row.id}>
     <b>{row.name}</b><small>{row.phone||'Phone not provided'}</small>
     <button className="outline small" onClick={()=>startSalesAction('customer',row)}>Edit customer</button>
     <details><summary>Customer sales history</summary>{salesData.sales.filter(sale=>sale.customer_id===row.id).map(sale=><Line key={sale.id} label={sale.invoice_number} value={money(sale.total_ghs)+' | Outstanding '+money(sale.outstanding_ghs)}/>)}</details>
    </div>):<p className="empty">No customers registered yet.</p>}
   </>}
   {salesTab==='payments'&&<>
    <Line label="Customer payments received" value={money(salesData.summary.cash_received_ghs)}/>
    <label className="field"><span>Sale</span><select value={saleId} onChange={e=>setSaleId(e.target.value)}><option value="">Select a sale</option>{salesData.sales.map(row=><option value={row.id} key={row.id}>Sale #{row.id} ? {row.sold_on}</option>)}</select></label>
    {salePayments?.map(row=><div className="item" key={row.id}>{row.paid_on} ? {money(row.amount_ghs)} ? {row.method}</div>)}
    {salePayments?.length===0&&<p className="empty">No payments recorded for this sale.</p>}
   </>}
   {salesTab==='credit'&&<label className="field"><span>View outstanding credit</span><select value={balanceFilter} onChange={event=>setBalanceFilter(event.target.value)}>
    <option value="outstanding">Outstanding</option><option value="current">Current</option><option value="due_soon">Due within 7 days</option><option value="overdue">Overdue</option><option value="paid">Fully paid</option><option value="all">All invoices</option>
   </select></label>}
   {salesTab!=='customers'&&salesTab!=='payments'&&<>
    <Line label={salesTab==='credit'?'Outstanding receivables':'Invoiced sales'} value={money(salesTab==='credit'?salesData.summary.outstanding_receivables_ghs:salesData.summary.invoiced_revenue_ghs)}/>
    <div className="tablewrap"><table><thead><tr><th>Sale</th><th>Date</th><th>Customer</th><th>Total</th><th>Paid</th><th>Outstanding</th><th>Due date</th><th>Status</th><th>Actions</th></tr></thead><tbody>
    {currentSales.map(row=><tr key={row.id}><td>{row.invoice_number}</td><td>{row.sold_on}</td><td>{salesData.customers.find(customer=>customer.id===row.customer_id)?.name??'?'}</td><td>{money(row.total_ghs)}</td><td>{money(row.paid_ghs)}</td><td>{money(row.outstanding_ghs)}</td><td>{row.due_on??'Not set'}</td><td>{row.outstanding_ghs>0&&row.due_on&&row.due_on<localDate()?Math.round((Date.parse(localDate())-Date.parse(row.due_on))/86400000)+' days overdue':row.payment_status}</td><td><div className="farmactions">
     <button className="outline small" onClick={()=>void download('/farms/'+farmId+'/sales/transactions/'+row.id+'/invoice.pdf',row.invoice_number+'.pdf')}>Download invoice</button>
     {row.outstanding_ghs>0&&<button className="outline small" onClick={()=>startSalesAction('payment',{sale_id:row.id})}>Record payment</button>}
    </div></td></tr>)}
    </tbody></table></div>
    {!currentSales.length&&<p className="empty">{salesTab==='credit'?'No outstanding receivables.':'No sales recorded yet.'}</p>}
   </>}
  </>}
 </section>}
 {page==='farms'&&<><section className="panel"><div className="between"><div><h2>My farms</h2><p className="muted">Register, view and manage farms associated with your account.</p></div><button className="primary" onClick={newFarm}><PlusCircle size={16}/> Add farm</button></div>{farms.length?<div className="farmgrid">{farms.map(f=><div className="farmcard" key={f.id}><div className="between"><b>{f.name}</b><span className="pill">{f.farm_type}</span></div><p>{f.district}, {f.region}</p><p>Species: {f.species}</p><div className="farmactions"><button className="outline" onClick={()=>{setFarmId(f.id);setPage('overview')}}>View dashboard</button><button className="outline" onClick={()=>editFarm(f)}><Pencil size={14}/> Edit</button><button className="outline danger" disabled={busy} onClick={()=>void archiveFarm(f)}><Archive size={14}/> Archive</button></div></div>)}</div>:<div className="farmempty"><Sprout size={32}/><h3>No farms registered yet</h3><p>Register your first farm to begin tracking production and finances.</p><button className="primary" onClick={newFarm}><PlusCircle size={16}/> Register a farm</button></div>}</section>{farmFormOpen&&<section className="panel" id="farm-form"><div className="between"><h2>{farmEditing!==null?'Edit farm':'Register a new farm'}</h2><button className="outline" onClick={()=>setFarmFormOpen(false)}><X size={15}/> Cancel</button></div><form onSubmit={saveFarm} className="farmform"><label className="field"><span>Farm name</span><input required minLength={2} maxLength={150} value={farmForm.name??''} onChange={e=>setFarmForm({...farmForm,name:e.target.value})}/></label><label className="field"><span>Region</span><input required minLength={2} maxLength={100} value={farmForm.region??''} onChange={e=>setFarmForm({...farmForm,region:e.target.value})}/></label><label className="field"><span>District</span><input required minLength={2} maxLength={100} value={farmForm.district??''} onChange={e=>setFarmForm({...farmForm,district:e.target.value})}/></label><label className="field"><span>Farm type</span><select value={farmForm.farm_type||'pond'} onChange={e=>setFarmForm({...farmForm,farm_type:e.target.value})}><option value="pond">Pond</option><option value="cage">Cage</option><option value="tank">Tank</option><option value="mixed">Mixed</option></select></label><label className="field"><span>Species</span><input required minLength={2} maxLength={100} placeholder="e.g. Nile tilapia" value={farmForm.species??''} onChange={e=>setFarmForm({...farmForm,species:e.target.value})}/></label><label className="field"><span>Farm address (optional)</span><input maxLength={500} placeholder="Community, road, or local address" value={farmForm.farm_address??''} onChange={e=>setFarmForm({...farmForm,farm_address:e.target.value})}/></label><label className="field"><span>Nearest landmark (optional)</span><input maxLength={200} placeholder="e.g. Near the community market" value={farmForm.nearest_landmark??''} onChange={e=>setFarmForm({...farmForm,nearest_landmark:e.target.value})}/></label>  <GpsFields latitude={farmForm.latitude} longitude={farmForm.longitude} onChange={(latitude,longitude,source,accuracy)=>{setFarmForm(prev=>({...prev,latitude,longitude,location_method:source,gps_captured_at:source==='gps'?new Date().toISOString():null,gps_accuracy_m:source==='gps'&&accuracy!=null?accuracy:null}))}}/><p className="muted">If using coordinates, enter both latitude and longitude. Location is optional.</p><button className="primary" disabled={busy}>{busy?'Saving...':farmEditing!==null?'Save changes':'Register farm'}</button></form></section>}</>}
 {page==='units'&&<> <section className="panel"><div className="between"><div><h2>Production units</h2><p className="muted">Manage ponds, cages and tanks within the selected farm.</p></div><button className="primary" disabled={!farmId} onClick={newUnit}><PlusCircle size={16}/> Add unit</button></div>
 {!farmId?<div className="infobox">Select or register a farm before creating production units.</div>:units.length?<div className="farmgrid">{units.map(u=><div className="farmcard" key={u.id}><div className="between"><b>{u.name}</b><span className="pill">{u.unit_type}</span></div><p>Capacity: {u.capacity_m3==null?'Not specified':`${num(u.capacity_m3)} m³`}</p><p className="muted">Evidence tag: <code>{u.evidence_tag}</code></p>{u.notes&&<p>{u.notes}</p>}<div className="farmactions"><button className="outline" onClick={()=>editUnit(u)}><Pencil size={14}/> Edit</button><button className="outline danger" disabled={busy} onClick={()=>void archiveUnit(u)}><Archive size={14}/> Archive</button></div></div>)}</div>:<div className="farmempty"><Building2 size={32}/><h3>No production units yet</h3><p>Add a pond, cage or tank to your farm.</p><button className="primary" onClick={newUnit}><PlusCircle size={16}/> Add first unit</button></div>}</section>
 {unitFormOpen&&farmId&&<section className="panel" id="unit-form"><div className="between"><h2>{unitEditing!==null?'Edit production unit':'Register production unit'}</h2><button className="outline" onClick={()=>setUnitFormOpen(false)}><X size={15}/> Cancel</button></div>
 <form className="farmform" onSubmit={saveUnit}>
 <label className="field"><span>Unit name</span><input required minLength={2} maxLength={120} placeholder="e.g. Pond 1" value={unitForm.name??''} onChange={e=>setUnitForm({...unitForm,name:e.target.value})}/></label>
 <label className="field"><span>Unit type</span><select value={unitForm.unit_type||'pond'} onChange={e=>setUnitForm({...unitForm,unit_type:e.target.value})}><option value="pond">Pond</option><option value="cage">Cage</option><option value="tank">Tank</option></select></label>
 <label className="field"><span>Capacity in cubic metres (optional)</span><input type="number" step="any" min="0.000001" value={unitForm.capacity_m3??''} onChange={e=>setUnitForm({...unitForm,capacity_m3:e.target.value})}/></label>
 <GpsFields latitude={unitForm.latitude} longitude={unitForm.longitude} onChange={(latitude,longitude)=>{setUnitForm(prev=>({...prev,latitude,longitude}))}}/>
 <label className="field"><span>Notes (optional)</span><textarea maxLength={2000} value={unitForm.notes??''} onChange={e=>setUnitForm({...unitForm,notes:e.target.value})}/></label>
 <button className="primary" disabled={busy}>{busy?'Saving...':unitEditing!==null?'Save changes':'Register unit'}</button></form></section>}</>}
 {page==='overview'&&dailyRecordStatus?.cycles?.some((cycle:Obj)=>cycle.is_overdue)&&<div className="alert daily-record-alert" role="alert"><AlertTriangle size={18}/><span>Feeding record missing after {dailyRecordStatus.reminder_time} for {dailyRecordStatus.cycles.filter((cycle:Obj)=>cycle.is_overdue).map((cycle:Obj)=>`${cycle.unit_name} (${cycle.species})`).join(', ')}.</span><button type="button" className="flag-link" onClick={()=>openProduction('feeding')}>Review records</button></div>}
 {page==='settings'&&<section className="panel">
  <h2>Account</h2><Line label="Name" value={user?.full_name??'Unavailable'}/><Line label="Email" value={user?.email??'Unavailable'}/>
  <h2 className="spaced">Daily SMS reminder settings</h2><p className="muted">A feeding record is expected for each active cycle every day. Missing records are flagged red after {dailyRecordStatus?.reminder_time||'08:00'} Africa/Accra time.</p>
  <form className="farmform" onSubmit={saveSmsContact}>
   <label className="field"><span>Mobile number (international format, e.g. +233…)</span><input type="tel" autoComplete="tel" pattern="\+[1-9]\d{7,14}" required={Boolean(profileForm.sms_daily_records_enabled||profileForm.sms_loan_reminders_enabled)} value={profileForm.phone_number??''} onChange={e=>setProfileForm({...profileForm,phone_number:e.target.value})}/></label>
   <label className="consent"><input type="checkbox" checked={Boolean(profileForm.sms_daily_records_enabled)} onChange={e=>setProfileForm({...profileForm,sms_daily_records_enabled:e.target.checked})}/> I agree to receive one SMS reminder each morning if an active cycle has no feeding record for the day.</label>
   <label className="consent"><input type="checkbox" checked={Boolean(profileForm.sms_loan_reminders_enabled)} onChange={e=>setProfileForm({...profileForm,sms_loan_reminders_enabled:e.target.checked})}/> I agree to receive SMS reminders 7 days before an instalment is due and daily while it is overdue.</label>
   <button className="outline" disabled={busy}>Save reminder settings</button>
  </form>
  <p className="footnote">SMS delivery requires Hubtel credentials configured by the operator. You can disable reminders here at any time.</p>
 </section>}
 {page==='overview'&&farmId&&<div className="workspace-tabs"><button className="primary" onClick={()=>{setPage('finance');setForm({});setSelectedLoan(null);window.scrollTo(0,0)}}>Request a Loan</button></div>}
 {page==='overview'&&processorOnly&&<section className="panel"><h2>{processingBusiness.name}</h2><p>Manage raw fish purchases, processing batches, finished stock and customer invoices.</p>
  <button className="primary" onClick={()=>openProcessing()}>Processing Overview</button></section>}
 {page==='overview'&&!processorOnly&&<>
  {processingBusiness?.business_type==='integrated'&&<section className="panel"><h2>Fish processing</h2><button className="outline" onClick={()=>openProcessing()}>Processing Overview</button></section>}
  {!farms.length&&<div className="infobox" style={{marginBottom:18}}>No farms registered under this account. <button className="outline" onClick={()=>{setPage('farms');newFarm()}}>Register your first farm</button></div>}
  {overviewLoading&&<p role="status">Loading dashboard?</p>}
  {overviewError&&<div className="alert" role="alert">Some dashboard figures are unavailable. <button className="outline small" onClick={()=>void loadFarm()}>Retry</button></div>}
  <h2>Farm-wide overview</h2>
  <div className="statgrid">
   <Stat label="Total farms" value={num(farms.length)} sub="Owned farms"/>
   <Stat label="Active production units" value={overviewNumber(analytics?.summary?.active_units)} sub="Selected farm"/>
   <Stat label="Fish stocked" value={overviewNumber(analytics?.summary?.stocked_fish)} sub="Active cycles"/>
   <Stat label="Estimated surviving fish" value={overviewNumber(analytics?.summary?.estimated_live_fish)} sub="Record-derived estimate"/>
   <Stat label="Estimated biomass" value={`${overviewNumber(analytics?.summary?.estimated_biomass_kg)} kg`} sub="Sample-based estimate"/>
   <Stat label="Next scheduled harvest" value={nextHarvest?.expected_harvest_on??'Not scheduled'} sub={nextHarvest?nextHarvest.unit_name+' ? '+nextHarvest.species+' ? '+nextHarvest.days_remaining+' days remaining':'Set a date in the stocking workspace'}/>
   <Stat label="Scheduled harvests" value={num(upcomingHarvests.length)} sub={num(overdueHarvests.length)+' past planned date'}/>
  </div>
  <div className="twocol">
   <section className="panel"><h2>Production overview</h2><div className="metricrows">
    <Line label="Active cycles" value={overviewNumber(analytics?.summary?.active_cycles)}/>
    <Line label="Harvested stock available for sale" value={`${overviewNumber(dashboard?.sales?.available_harvest_kg)} kg`}/>
    <Line label="Upcoming harvest dates and forecasts" value={overviewNumber(analytics?.summary?.upcoming_harvest_count)}/>
    <Line label="Mortality recorded" value={`${overviewNumber(analytics?.summary?.mortality_count)} fish`}/>
   </div></section>
   <section className="panel"><h2>Financial and inventory overview</h2><div className="metricrows">
    <Line label="Feed remaining (current stock)" value={`${overviewNumber(analytics?.summary?.remaining_feed_kg)} kg`}/>
    <Line label="Recorded feed consumed (lifetime)" value={`${overviewNumber(dashboard?.feed?.consumed_kg)} kg`}/>
    <Line label="Invoiced sales" value={overviewMoney(dashboard?.sales?.invoiced_revenue_ghs)}/>
    <Line label="Payments received" value={overviewMoney(analytics?.summary?.payments_received_ghs)}/>
    <Line label="Outstanding customer credit" value={overviewMoney(analytics?.summary?.outstanding_customer_credit_ghs)}/>
    <Line label="Known costs including estimated feed use" value={overviewMoney(dashboard?.costs?.recorded_costs_to_date_ghs)}/>
   </div>{dashboard?.costs?.missing_feed_prices&&<p className="muted">Some consumed feed has no recorded receipt price and is excluded from the known cost total.</p>}</section>
  </div>
  {farmId&&<FeedOutlook key={farmId} farmId={farmId} load={json} api={api} revision={analytics} compact navigate={openOutlookAction} changed={()=>{}}/>}
  <ReportCards open={openReport}/>

  {(overdueHarvests.length>0||upcomingHarvests.some(row=>row.days_remaining<=30))&&<section className="panel">
   <h2>Harvest reminders</h2>
   {[...overdueHarvests,...upcomingHarvests.filter(row=>row.days_remaining<=30)].map(row=><div className="item" key={row.cycle_id}>
    <b>{row.farm_name} ? {row.unit_name}</b>
    <small>{row.days_remaining===0?'Planned harvest date is today':row.days_remaining<0?Math.abs(row.days_remaining)+' days past the planned harvest date':row.days_remaining+' days until the planned harvest date'}</small>
   </div>)}
  </section>}
 </>}
 {page==='inventory'&&<section className="panel">
  <details className="feed-inventory" open><summary>Feed inventory · products, receipts and purchase costs</summary>
   <div className="tablewrap"><table><thead><tr><th>Feed product</th><th>Supplier</th><th>Protein</th><th>Available stock</th></tr></thead><tbody>{feedProducts.map(feed=><tr key={feed.id}><td>{feed.name}</td><td>{feed.supplier||'—'}</td><td>{feed.protein_pct==null?'—':`${num(feed.protein_pct)}%`}</td><td>{num(feed.stock_kg)} kg</td></tr>)}</tbody></table>{!feedProducts.length&&<p className="empty">No feed products registered for this farm.</p>}</div>
   <div className="twocol feed-inventory-forms">
    <form className="farmform" onSubmit={createFeedProduct}><h3>Add feed product</h3>
     <label className="field"><span>Product name</span><input required minLength={2} maxLength={120} value={feedProductForm.name??''} onChange={e=>setFeedProductForm({...feedProductForm,name:e.target.value})}/></label>
     <label className="field"><span>Supplier (optional)</span><input maxLength={120} value={feedProductForm.supplier??''} onChange={e=>setFeedProductForm({...feedProductForm,supplier:e.target.value})}/></label>
     <label className="field"><span>Protein (%) (optional)</span><input type="number" min="0" max="100" step="any" value={feedProductForm.protein_pct??''} onChange={e=>setFeedProductForm({...feedProductForm,protein_pct:e.target.value})}/></label>
     <button className="outline" disabled={busy}>Add product</button>
    </form>
    <form className="farmform" onSubmit={receiveFeedStock}><h3>Receive feed stock</h3>
     <label className="field"><span>Feed product</span><select required value={feedReceiptForm.feed_id??''} onChange={e=>setFeedReceiptForm({...feedReceiptForm,feed_id:Number(e.target.value)})}><option value="">Select feed...</option>{feedProducts.map(feed=><option key={feed.id} value={feed.id}>{feed.name}</option>)}</select></label>
     <label className="field"><span>Quantity received (kg)</span><input required type="number" min="0.001" step="any" value={feedReceiptForm.quantity_kg??''} onChange={e=>setFeedReceiptForm({...feedReceiptForm,quantity_kg:e.target.value})}/></label>
     <label className="field"><span>Total purchase cost (GH₵)</span><input required type="number" min="0" step="0.01" value={feedReceiptForm.total_cost_ghs??''} onChange={e=>setFeedReceiptForm({...feedReceiptForm,total_cost_ghs:e.target.value})}/></label>
     <label className="field"><span>Receipt date</span><input required type="date" max={localDate()} value={feedReceiptForm.occurred_on??''} onChange={e=>setFeedReceiptForm({...feedReceiptForm,occurred_on:e.target.value})}/></label>
     <label className="field"><span>Production unit being supplied</span><select required value={feedReceiptForm.unit_id??''} onChange={e=>setFeedReceiptForm({...feedReceiptForm,unit_id:Number(e.target.value)})}><option value="">Select unit...</option>{units.map(unit=><option key={unit.id} value={unit.id}>{unit.name}</option>)}</select></label>
     <EvidenceRecorder activity="feed_delivery" unit={units.find(unit=>unit.id===Number(feedReceiptForm.unit_id))} getChallenge={getEvidenceChallenge} onChange={setReceiptVideo}/>
     <button className="outline" disabled={busy||!feedProducts.length||!receiptVideo}>Record receipt</button>
    </form>
   </div>
   <p className="muted">Feed purchase costs are used to estimate daily feed-consumption costs. Product setup and stock receipts are inventory tasks; daily operation logs below require video evidence.</p>
  </details>
 </section>}
 {page==='production'&&nav.some(([key])=>key==='production')&&<>
  {(productionView==='landing'||productionView==='feeding')&&dailyRecordStatus?.cycles?.some((cycle:Obj)=>cycle.is_overdue)&&<div className="alert daily-record-alert" role="alert"><AlertTriangle size={18}/><span>Missing today's feeding record: {dailyRecordStatus.cycles.filter((cycle:Obj)=>cycle.is_overdue).map((cycle:Obj)=>`${cycle.unit_name} (${cycle.species})`).join(', ')}.</span></div>}
 {productionView==='landing'&&<>
  <p className="production-intro">Manage stocking, feeding, fish growth, water quality, harvesting and production records.</p>
  <div className="statgrid">
   <Stat label="Active production cycles" value={overviewNumber(analytics?.summary?.active_cycles)} sub="Selected farm"/>
   <Stat label="Estimated live fish" value={overviewNumber(analytics?.summary?.estimated_live_fish)} sub="Active cycles"/>
   <Stat label="Estimated biomass" value={analytics?.summary?.estimated_biomass_kg==null?'Unavailable':num(analytics.summary.estimated_biomass_kg)+' kg'} sub="Active cycles"/>
   <Stat label="Upcoming harvests" value={analytics?num(upcomingHarvests.filter(row=>row.farm_id===farmId).length):'Unavailable'} sub="Planned dates for selected farm"/>
  </div>
  <div className="production-grid">
   {productionActivities.map(({key,label,description,icon:Icon})=>{
    const red=key==='stocking'?stockingTasks.length>0:key==='feeding'?attention.length>0:
      key==='growth'?farmActivity?.sampling_overdue>0:key==='water_quality'?farmActivity?.water_overdue>0:key==='harvesting'&&farmActivity?.harvest_due>0;
    const amber=key==='harvesting'&&!red&&farmActivity?.harvest_approaching>0;
    const status=key==='stocking'?(stockingTasks.length===1&&stockingTasks[0].restocking?stockingTasks[0].unit_name+' is ready for restocking.':stockingTasks.length?stockingTasks.length+' production unit(s) awaiting stocking.':farmActivity?.unit_count===0?'Register your first pond, cage or tank.':''):
      key==='feeding'&&farmActivity?dueCount+' due now | '+overdueCount+' overdue | '+farmActivity.feeding_recorded+' recorded'+(farmActivity.next_feeding?' | Next '+farmActivity.next_feeding.scheduled_time:'')+(farmActivity.feeding_suspended.length?' | Safety review required':''):
      key==='growth'&&red?farmActivity?.sampling_overdue+' cycle(s) overdue for sampling':
      key==='water_quality'&&red?farmActivity?.water_overdue+' unit(s) overdue for readings':
      key==='harvesting'&&red?farmActivity?.harvest_due+' harvest(s) due or overdue':amber?farmActivity?.harvest_approaching+' harvest(s) approaching':'';
    return <button type="button" className={'production-card'+(red?' activity-red':amber?' activity-amber':'')} key={key} onClick={()=>{if(key==='stocking'&&farmActivity?.unit_count===0){setPage('units');return}openProductionCard(key)}}>
     <Icon size={23} aria-hidden="true"/><strong>{label}</strong><span>{description}</span>{status&&<span className="production-status">{status}</span>}<b>Open {label}</b>
    </button>;
   })}
  </div>
 </>}
 {productionView!=='landing'&&<button type="button" className="outline production-back" onClick={()=>openProduction('landing')}><ArrowLeft size={16}/> Back to Production</button>}

 {activityError&&<ErrorNotice message={activityError} retry={()=>void refreshActivity()}/>}
 {productionView==='stocking'&&farmActivity?.unstocked_units.length>0&&<section className="panel"><h2>Stocking readiness</h2>
  {farmActivity?.unstocked_units.map((unit:Obj)=><div className="item" key={unit.unit_id}><b>{unit.unit_name} | {unit.status.replaceAll('_',' ')}</b>{unit.reason&&<small>{unit.reason}</small>}
    {unit.status==='ready'&&<button type="button" className="outline small" onClick={()=>{setStockForm({...stockForm,unit_id:unit.unit_id});setStockVideo(null);document.getElementById('stocking-form')?.scrollIntoView({block:'start'})}}>Record stocking</button>}
    <label className="field"><span>Readiness for {unit.unit_name}</span><select value={unit.status} onChange={event=>void changeReadiness(unit,event.target.value)}>{['ready','cleaning','drying','maintenance','repair','preparation','temporarily_closed'].map(status=><option key={status} value={status}>{status.replaceAll('_',' ')}</option>)}</select></label>
  </div>)}
 </section>}
 {productionView==='feeding'&&(attentionMode||farmActivity?.feeding_suspended.length>0)&&<section id="feeding-attention" className="panel">
  <h2>Feeding Sessions Requiring Attention</h2>
  {attention.length?attention.map(row=><div className="item" key={row.cycle_id+'-'+row.number}>
   <b>{row.unit_name} | {row.species} | Cycle #{row.cycle_id} | Session {row.number}</b>
   <small>{row.status==='missed'?'Overdue':'Due now'} | {row.scheduled_time??'No start time'}{row.scheduled_end?' to '+row.scheduled_end:''} | {num(row.recommended_kg)} kg recommended</small>
   <button type="button" className="outline small" onClick={()=>{setDailyVideo(null);setRecorderKey(key=>key+1);openUnitActivity('feeding',row,row)}}>Record Session</button>
  </div>):<p className="muted">No sessions are due or overdue today.</p>}
  {farmActivity?.feeding_suspended.map((row:Obj)=><div className="item" key={row.cycle_id}><b>{row.unit_name} | Feeding advisory suspended</b>{row.warnings.map((warning:string)=><small key={warning}>{warning}</small>)}</div>)}
 </section>}
 {productionView==='stocking'&& <section className="panel">
  <h2>Record fish stocking</h2>
  {!farmId?<div className="infobox">Select or register a farm before recording fish stocking.</div>:!units.length?<div className="infobox">Add a production unit before stocking fish.</div>:<form id="stocking-form" className="farmform" onSubmit={stockFish}>
   <label className="field"><span>Production unit</span><select required value={stockForm.unit_id??''} onChange={e=>setStockForm({...stockForm,unit_id:Number(e.target.value)})}><option value="">Choose an available unit...</option>{units.map(u=>{const occupied=cycles.some(c=>c.unit_id===u.id&&c.status==='active');const unavailable=farmActivity?.unstocked_units.some((item:Obj)=>item.unit_id===u.id&&item.status!=='ready');return <option key={u.id} value={u.id} disabled={occupied||unavailable}>{u.name}{occupied?' · active cycle':''}</option>})}</select></label>
   <label className="field"><span>Species</span><select required value={stockForm.species??'Tilapia'} onChange={e=>setStockForm({...stockForm,species:e.target.value})}><option value="Catfish">Catfish</option><option value="Tilapia">Tilapia</option></select></label>
   <label className="field"><span>Number of fish stocked</span><input required type="number" min="1" step="1" value={stockForm.stocked_count??''} onChange={e=>setStockForm({...stockForm,stocked_count:e.target.value})}/></label>
   <label className="field"><span>Initial average weight (g per fish)</span><input required type="number" min="0.001" step="any" value={stockForm.initial_average_weight_g??''} onChange={e=>setStockForm({...stockForm,initial_average_weight_g:e.target.value})}/></label>
   <label className="field"><span>Stocking date</span><input required type="date" max={new Date().toISOString().slice(0,10)} value={stockForm.stocked_on??''} onChange={e=>setStockForm({...stockForm,stocked_on:e.target.value})}/></label>
   <label className="field"><span>Harvest duration</span><select value={stockForm.harvest_mode??''} onChange={e=>setStockForm({...stockForm,harvest_mode:e.target.value,harvest_duration_months:Number(e.target.value)||'',expected_harvest_on:''})}><option value="">Not scheduled</option>{[3,4,5,6,7,8,9,12].map(months=><option key={months} value={months}>{months} months</option>)}<option value="custom">Custom number of months</option><option value="date">Specific harvest date</option></select></label>
   {stockForm.harvest_mode==='custom'&&<label className="field"><span>Months until harvest</span><input required type="number" min="1" max="120" step="1" value={stockForm.harvest_duration_months??''} onChange={e=>setStockForm({...stockForm,harvest_duration_months:e.target.value,expected_harvest_on:''})}/></label>}
   {stockForm.harvest_mode&&<>
    <label className="field"><span>Expected harvest date</span><input required type="date" min={stockForm.stocked_on} value={stockForm.expected_harvest_on||calculatedHarvestDate} onChange={e=>setStockForm({...stockForm,expected_harvest_on:e.target.value})}/></label>
    <label className="field"><span>Target harvest weight (g per fish)</span><input type="number" min="0.001" step="any" value={stockForm.target_harvest_weight_g??''} onChange={e=>setStockForm({...stockForm,target_harvest_weight_g:e.target.value})}/></label>
    <label className="field"><span>Expected survival (%)</span><input type="number" min="0" max="100" step="any" value={stockForm.expected_survival_pct??''} onChange={e=>setStockForm({...stockForm,expected_survival_pct:e.target.value})}/></label>
   </>}
   <label className="field"><span>Notes (optional)</span><textarea maxLength={2000} value={stockForm.notes??''} onChange={e=>setStockForm({...stockForm,notes:e.target.value})}/></label>
   <EvidenceRecorder activity="stocking" unit={units.find(u=>u.id===Number(stockForm.unit_id))} getChallenge={getEvidenceChallenge} onChange={setStockVideo}/>
   <button className="primary" disabled={busy||!stockVideo||!units.some(u=>u.id===Number(stockForm.unit_id)&&!cycles.some(c=>c.unit_id===u.id&&c.status==='active'))}>{busy?'Saving...':'Record stocking'}</button>
  </form>}
 </section>}
 {productionView==='harvesting'&&<section className="panel">
  {productionView==='harvesting'&&<>
   <h2>Record a harvest</h2>
   {!activeCycles.length?<p className="empty">Select a farm with an active stocking cycle.</p>:<form className="farmform" onSubmit={saveHarvest}>
    <label className="field"><span>Production unit and cycle</span><select required value={harvestForm.cycle_id??''} onChange={e=>{setHarvestForm({...harvestForm,cycle_id:e.target.value});setHarvestVideo(null)}}>
     <option value="">Choose a cycle</option>{activeCycles.map(cycle=><option key={cycle.cycle_id} value={cycle.cycle_id}>{cycle.unit_name} ? {cycle.species}</option>)}
    </select></label>
    {farmId&&harvestForm.cycle_id&&<PricingAdvisor key={harvestForm.cycle_id} farmId={farmId} cycleId={Number(harvestForm.cycle_id)} load={json} download={downloadPricingPdf} revision={analytics}/>}
    <label className="field"><span>Harvest type</span><select value={harvestForm.kind??'partial'} onChange={e=>setHarvestForm({...harvestForm,kind:e.target.value})}><option value="partial">Partial harvest</option><option value="final">Final harvest and close cycle</option></select></label>
    <label className="field"><span>Harvest date</span><input required type="date" min={activeCycles.find(cycle=>cycle.cycle_id===Number(harvestForm.cycle_id))?.stocked_on} max={localDate()} value={harvestForm.harvested_on??''} onChange={e=>setHarvestForm({...harvestForm,harvested_on:e.target.value})}/></label>
    <label className="field"><span>Fish harvested</span><input required type="number" min="1" step="1" max={activeCycles.find(cycle=>cycle.cycle_id===Number(harvestForm.cycle_id))?.estimated_live_count} value={harvestForm.fish_count??''} onChange={e=>setHarvestForm({...harvestForm,fish_count:e.target.value})}/></label>
    <label className="field"><span>Harvest weight (kg)</span><input required type="number" min="0.001" step="any" value={harvestForm.quantity_kg??''} onChange={e=>setHarvestForm({...harvestForm,quantity_kg:e.target.value})}/></label>
    <label className="field"><span>Notes</span><textarea maxLength={1000} value={harvestForm.notes??''} onChange={e=>setHarvestForm({...harvestForm,notes:e.target.value})}/></label>
    <EvidenceRecorder key={harvestForm.cycle_id??'none'} activity="harvest" unit={units.find(unit=>unit.id===activeCycles.find(cycle=>cycle.cycle_id===Number(harvestForm.cycle_id))?.unit_id)} getChallenge={getEvidenceChallenge} onChange={setHarvestVideo}/>
    <button className="primary" disabled={busy||!harvestVideo}>Save harvest</button>
   </form>}
  </>}
  {processingBusiness?.business_type==='integrated'&&<button type="button" className="outline" onClick={()=>openProcessing('batches')}>Allocate Harvest to Processing</button>}
  <button type="button" className="outline" onClick={()=>openHistory({tab:'harvest',cycle:Number(harvestForm.cycle_id)||undefined})}>View Harvest History</button>
 </section>}
 {productionView==='schedule'&&<section className="panel">
  <h2>Harvest schedule</h2>
  <div className="farmform">
   <label className="field"><span>Farm</span><select value={harvestFilter.farm??''} onChange={e=>setHarvestFilter({...harvestFilter,farm:e.target.value})}><option value="">All farms</option>{farms.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}</select></label>
   <label className="field"><span>Species</span><select value={harvestFilter.species??''} onChange={e=>setHarvestFilter({...harvestFilter,species:e.target.value})}><option value="">All species</option>{[...new Set(harvestSchedule.map(row=>String(row.species)))].sort().map(species=><option key={species}>{species}</option>)}</select></label>
   <label className="field"><span>Production unit</span><select value={harvestFilter.unit??''} onChange={e=>setHarvestFilter({...harvestFilter,unit:e.target.value})}><option value="">All units</option>{[...new Map(harvestSchedule.map(row=>[row.unit_id,row])).values()].map(row=><option key={row.unit_id} value={row.unit_id}>{row.farm_name} ? {row.unit_name}</option>)}</select></label>
   {['from','to'].map(bound=><label className="field" key={bound}><span>Expected date {bound}</span><input type="date" value={harvestFilter[bound]??''} onChange={e=>setHarvestFilter({...harvestFilter,[bound]:e.target.value})}/></label>)}
  </div>
  <details><summary>Harvest calendar</summary>
   <label className="field production-record-filter"><span>Calendar month</span><input type="month" value={harvestMonth} onChange={e=>setHarvestMonth(e.target.value)}/></label>
   <div className="harvest-calendar">
    {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day=><b key={day}>{day}</b>)}
    {harvestMonth&&Array.from({length:new Date(Number(harvestMonth.slice(0,4)),Number(harvestMonth.slice(5)),0).getDate()},(_,index)=>{
      const day=index+1;
      const date=harvestMonth+'-'+String(day).padStart(2,'0');
      const weekday=(new Date(Number(harvestMonth.slice(0,4)),Number(harvestMonth.slice(5))-1,1).getDay()+6)%7;
     return <div key={date} style={index===0?{gridColumnStart:weekday+1}:undefined}><time dateTime={date}>{day}</time>{harvestSchedule.filter(row=>row.expected_harvest_on===date&&(!harvestFilter.farm||Number(harvestFilter.farm)===row.farm_id)&&(!harvestFilter.species||harvestFilter.species===row.species)&&(!harvestFilter.unit||Number(harvestFilter.unit)===row.unit_id)&&(!harvestFilter.from||date>=harvestFilter.from)&&(!harvestFilter.to||date<=harvestFilter.to)).map(row=><small key={row.cycle_id}>{row.farm_name} ? {row.unit_name}</small>)}</div>;
    })}
   </div>
  </details>
  {harvestSchedule.filter(row=>(!harvestFilter.farm||Number(harvestFilter.farm)===row.farm_id)&&
    (!harvestFilter.species||harvestFilter.species===row.species)&&(!harvestFilter.unit||Number(harvestFilter.unit)===row.unit_id)&&
    (!harvestFilter.from||row.expected_harvest_on>=harvestFilter.from)&&(!harvestFilter.to||(row.expected_harvest_on&&row.expected_harvest_on<=harvestFilter.to))).map(row=><div className="item" key={row.cycle_id}>
    <b>{row.farm_name} ? {row.unit_name} ? {row.species}</b>
    <small>Stocked {row.stocked_on} ? {row.status}{row.expected_harvest_on?' ? '+row.expected_harvest_on:''}{row.days_remaining==null||row.status==='Completed'?'':row.days_remaining<0?' ? '+Math.abs(row.days_remaining)+' days past planned date':' ? '+row.days_remaining+' days remaining'}</small>
    <small>Estimated remaining harvest {row.estimated_harvest_kg==null?' ? Insufficient data':' ? '+num(row.estimated_harvest_kg)+' kg'}{row.estimated_harvest_count==null?'':' ? '+num(row.estimated_harvest_count)+' fish'}{row.last_harvest_on?' ? Actual '+num(row.actual_harvest_kg)+' kg through '+row.last_harvest_on:''}</small>
    {row.status!=='Completed'&&<button type="button" className="outline small" onClick={()=>setHarvestEdit({...row,reason:''})}>{row.expected_harvest_on?'Reschedule':'Schedule harvest'}</button>}
  </div>)}
  {harvestEdit&&<form className="farmform" onSubmit={saveHarvestPlan}>
   <h3>{harvestEdit.unit_name} harvest plan</h3>
   <label className="field"><span>Expected harvest date</span><input required type="date" min={harvestEdit.stocked_on} value={harvestEdit.expected_harvest_on??''} onChange={e=>setHarvestEdit({...harvestEdit,expected_harvest_on:e.target.value})}/></label>
   <label className="field"><span>Reason for change</span><input required maxLength={500} value={harvestEdit.reason} onChange={e=>setHarvestEdit({...harvestEdit,reason:e.target.value})}/></label>
   <button className="primary" disabled={busy}>Save harvest date</button>
   <button type="button" className="outline" onClick={()=>setHarvestEdit(null)}>Cancel</button>
  </form>}
 </section>}
 {productionView==='stocking'&&<section className="panel">
  <h2>Active stocking cycles</h2>
  {activeCycles.map(c=><div className="item" key={c.cycle_id}><b>{c.unit_name} ? {c.species}</b>
   <small>Stocked {c.stocked_on} ? {num(c.estimated_live_count)} estimated live fish ? {num(c.estimated_biomass_kg)} kg</small>
   <button className="outline danger small" disabled={busy} onClick={()=>void closeStocking(c)}>Close cycle</button>
  </div>)}
  <button type="button" className="outline" onClick={()=>openHistory({tab:'stocking',unit:Number(stockForm.unit_id)||undefined})}>View Stocking History</button>
 </section>}
 {productionView==='feeding'&&farmId&&<FeedOutlook key={farmId} farmId={farmId} load={json} api={api} revision={analytics}
  navigate={openOutlookAction} changed={()=>{setSessionRevision(value=>value+1);void refreshActivity()}}/>}
 {productionView==='feeding'&&<button className="outline production-back" onClick={()=>setPage('inventory')}>Open feed inventory</button>}
 {dailyActivity&&<section className="panel daily-operations">
  <h2>Record activity</h2>
  {dailyActivity&&<p className="muted">Select an active cycle and capture a private 15-second video for the record.</p>}
  {!activeCycles.length?<div className="infobox">Record fish stocking and keep a cycle active before entering feeding, mortality, water-quality, or growth records.</div>:dailyCycle?<>
   <label className="field daily-cycle-select"><span>Active stocking cycle · production unit</span><select value={dailyCycleId} onChange={e=>{
    setDailyCycleId(Number(e.target.value));
    if(dailyTab==='feeding'){
      setDailyForm({recorded_on:ghanaDate()});setDailyVideo(null);setRecorderKey(value=>value+1);
    }
   }}>{activeCycles.map(c=><option key={c.cycle_id} value={c.cycle_id}>{c.unit_name} · {c.species} · cycle #{c.cycle_id}</option>)}</select></label>
   {dailyCycle&&<div className="daily-cycle-summary"><span><b>Estimated live fish:</b> {num(dailyCycle.estimated_live_count)}</span><span><b>Biomass:</b> {num(dailyCycle.estimated_biomass_kg)} kg</span><span><b>Cumulative mortality:</b> {num(dailyCycle.mortality_count)} fish ({num(dailyCycle.mortality_pct)}%)</span></div>}
   {evidenceRetry&&<div className="alert evidence-retry"><span>Video evidence #{evidenceRetry.id} still needs attention.</span><button type="button" className="outline small" disabled={busy} onClick={()=>void resolveEvidenceIssue()}>{evidenceRetry.record_id?'Retry video link':'Delete unlinked video'}</button></div>}
   {dailyActivity&&dailyTab==='feeding'&&<section id="feeding-session-overview" className="daily-history">
    <h3>{feedingDate===ghanaDate()?"Today's Feeding Sessions":"Feeding Sessions"}</h3>
    <label className="field"><span>Feeding date</span><input required type="date" max={ghanaDate()} min={dailyCycle.stocked_on} value={feedingDate} onChange={e=>{if(e.target.value){setDailyForm({...dailyForm,recorded_on:e.target.value,session_number:'',actual_time:e.target.value===ghanaDate()?new Date().toISOString().slice(11,16):''});setDailyVideo(null);setRecorderKey(value=>value+1)}}}/></label>
    {sessionError&&<p className="alert" role="alert">{sessionError}</p>}
    {sessionForDay?<>
     <p className="muted">{dailyCycle.unit_name} | {dailyCycle.species} | Africa/Accra. An unrecorded session becomes overdue at the end of its window. A start without an end uses one hour, and a session without a start is missed at day-end.</p>
     <Line label="Recommended daily feed" value={sessionForDay.daily_ration_kg==null?'Unavailable':num(sessionForDay.daily_ration_kg)+' kg'}/>
     {!sessionForDay.scheduled_count&&<p className="infobox">No feeding schedule for this date. Use Manage Feeding Schedule to set up sessions. Actual feeding can still be recorded.</p>}
     {sessionForDay.schedule_id&&sessionForDay.daily_ration_kg==null&&<p className="infobox">Feeding schedule active ? recommended ration unavailable.</p>}
     {sessionForDay.scheduled_count>0&&<Line label="Completed sessions" value={sessionForDay.recorded_count+' of '+sessionForDay.scheduled_count}/>}
     <Line label="Due / overdue / upcoming / skipped / unscheduled" value={[sessionForDay.due_count,sessionForDay.missed_count,sessionForDay.upcoming_count,sessionForDay.skipped_count,sessionForDay.unscheduled_count].join(' / ')}/>
     <Line label="Actual feed" value={num(sessionForDay.actual_kg)+' kg'}/>
     <Line label="Remaining recommended feed" value={sessionForDay.remaining_kg==null?'Unavailable':num(sessionForDay.remaining_kg)+' kg'}/>
     <Line label="Actual minus recommended" value={sessionForDay.difference_kg==null?'Unavailable':num(sessionForDay.difference_kg)+' kg'}/>
     {sessionForDay.frequency_advisory&&<div className="infobox">
      <b>Feeding frequency as fish grow</b>
      <p>{sessionForDay.frequency_advisory.sampled_on?'Latest sample ('+sessionForDay.frequency_advisory.sampled_on+')':'Initial stocking weight'}: {num(sessionForDay.frequency_advisory.average_weight_g)} g average. The species profile suggests {sessionForDay.frequency_advisory.suggested_sessions} sessions per day.</p>
      {sessionForDay.frequency_advisory.next_threshold_g!=null&&<p>When a later sample averages more than {num(sessionForDay.frequency_advisory.next_threshold_g)} g, this profile suggests {sessionForDay.frequency_advisory.next_sessions} sessions per day.</p>}
      {sessionForDay.frequency_advisory.active_sessions!==sessionForDay.frequency_advisory.suggested_sessions&&<>
       <p>Current sessions per day: {sessionForDay.frequency_advisory.active_sessions??'No schedule'}. {sessionForDay.schedule_id?'Use Manage Feeding Schedule to apply a new frequency from your chosen date.':'A newly approved recommendation applies to days that do not already have a saved plan.'}</p>
       <button type="button" className="outline" disabled={busy} onClick={()=>document.getElementById('seven-day-feed-outlook')?.scrollIntoView({block:'start'})}>Review feeding recommendation</button>
      </>}
     </div>}
     {sessionForDay.sessions.map((session:Obj)=><div className="item feeding-session-card" data-status={session.status} key={session.number}>
      <b>Session {session.number}{session.name?' ? '+session.name:''} | {session.scheduled_time??'Time not set'}{session.scheduled_end?' to '+session.scheduled_end:''} | {feedingStatus(session.status)}</b>
      <small>Recommended {session.recommended_kg==null?'unavailable':num(session.recommended_kg)+' kg'} | Recorded {num(session.actual_kg)} kg</small>
      {session.skip&&<small>Skipped by {session.skip.recorder} | {session.skip.reason}</small>}
      {session.entries.map((entry:Obj)=><small key={entry.id}>{entry.feed_name} | {num(entry.actual_kg)} kg | {entry.recorder??'Recorder unavailable'} | {ghanaFeedingTime(entry.actual_fed_at)} | Submitted {entry.submitted_at} | Evidence {entry.evidence_status}</small>)}
      {session.status!=='skipped'&&<div className="farmactions">
       <button type="button" className="outline small" aria-pressed={chosenSession?.number===session.number} onClick={()=>selectFeedingSession(session)}>{session.status==='recorded'?'Add feed entry':'Record Session'}</button>
       {session.status!=='recorded'&&<button type="button" disabled={busy} className="outline small" onClick={()=>void editFeedingSession('skip',session.number)}>Mark skipped</button>}
      </div>}
     </div>)}
     {sessionForDay.unassigned_entries.length>0&&<details><summary>Unscheduled feeding events ({sessionForDay.unassigned_entries.length})</summary>
      {sessionForDay.unassigned_entries.map((entry:Obj)=><div className="item" key={entry.id}>
       <b>{entry.feed_name} | {num(entry.actual_kg)} kg | {ghanaFeedingTime(entry.actual_fed_at)} | {entry.recorder??'Recorder unavailable'}</b>
       {entry.notes&&<small>{entry.notes}</small>}
       {entry.actual_fed_at&&sessionForDay.sessions.some((row:Obj)=>row.scheduled_time&&row.status!=='skipped')&&
        <form className="farmactions" onSubmit={event=>{
          event.preventDefault();
          const data=new FormData(event.currentTarget);
          void reconcileFeeding(entry,Number(data.get('session')),String(data.get('reason')));
        }}>
         <label className="field"><span>Reconcile with session</span><select name="session" required defaultValue=""><option value="">Select session</option>
          {sessionForDay.sessions.filter((row:Obj)=>row.scheduled_time&&row.status!=='skipped').map((row:Obj)=><option key={row.number} value={row.number}>Session {row.number} ? {row.scheduled_time}</option>)}
         </select></label>
         <label className="field"><span>Reason</span><input name="reason" required maxLength={500}/></label>
         <button className="outline small" disabled={busy}>Link to session</button>
        </form>}
      </div>)}
     </details>}
     {feedingDate===ghanaDate()&&!sessionForDay.schedule_id&&sessionForDay.scheduled_count>0&&!sessionForDay.recorded_count&&!sessionForDay.skipped_count&&<details><summary>Set today's advisory session times</summary>
      {sessionForDay.sessions.map((row:Obj)=><div className="farmactions" key={row.number}>
       <label className="field"><span>Session {row.number} start</span><input type="time" value={sessionTimes[row.number]??''} onChange={e=>setSessionTimes({...sessionTimes,[row.number]:e.target.value})}/></label>
       <label className="field"><span>Session {row.number} end</span><input type="time" value={sessionEnds[row.number]??''} onChange={e=>setSessionEnds({...sessionEnds,[row.number]:e.target.value})}/></label>
      </div>)}
      <button type="button" disabled={busy} className="outline" onClick={()=>void editFeedingSession('times')}>Save scheduled times</button>
     </details>}
    </>:!sessionError&&<p role="status">Loading feeding sessions...</p>}
    <FeedingScheduleEditor key={sessionPath} path={sessionPath} today={ghanaDate()} suggestedCount={sessionForDay?.frequency_advisory?.suggested_sessions} load={json}
     changed={()=>{setSessionRevision(value=>value+1);void refreshActivity()}}/>

   </section>}
   {dailyActivity&&<form id={dailyTab==='feeding'?'feeding-entry':undefined} className="farmform daily-form" onSubmit={saveDailyOperation}>
    <fieldset className="daily-operation-fields" disabled={dailyTab==='feeding'&&retryingFeeding}>
    {dailyTab==='feeding'&&<>
     <h3>{chosenSession?'Record Session '+chosenSession.number+(chosenSession.name?' ? '+chosenSession.name:''):'Record feeding'}</h3>
     <Line label="Farm / unit / cycle / date" value={[farms.find(row=>row.id===farmId)?.name,dailyCycle.unit_name,'Cycle #'+dailyCycle.cycle_id,feedingDate].join(' / ')}/>
     <label className="field"><span>Feed type · inventory balance</span><select required value={dailyForm.feed_id??''} onChange={e=>setDailyForm({...dailyForm,feed_id:Number(e.target.value)})}><option value="">Select feed...</option>{feedProducts.map(feed=><option key={feed.id} value={feed.id} disabled={Number(feed.stock_kg)<=0}>{feed.name} · {num(feed.stock_kg)} kg available</option>)}</select></label>
     {!feedProducts.length&&<div className="infobox">No feed products are registered for this farm yet. Add a feed product and receive stock into inventory before recording feeding.</div>}
     <label className="field"><span>Feed quantity (kg)</span><input required type="number" min="0" step="any" value={dailyForm.quantity_kg??''} onChange={e=>setDailyForm({...dailyForm,quantity_kg:e.target.value})}/></label>
     {sessionForDay&&sessionForDay.scheduled_count>0&&<label className="field"><span>Feeding Session</span><select required value={dailyForm.session_number??''} onChange={e=>{
      const row=sessionForDay.sessions.find((item:Obj)=>item.number===Number(e.target.value));
      if(row)selectFeedingSession(row);else {setDailyVideo(null);setRecorderKey(value=>value+1);setDailyForm({...dailyForm,session_number:e.target.value,additional_session_event:false})}
     }}><option value="">Choose a session</option><option value="unscheduled">Unscheduled feeding</option>{sessionForDay.sessions.filter((row:Obj)=>row.status!=='skipped').map((row:Obj)=><option key={row.number} value={row.number}>Session {row.number}{row.name?' ? '+row.name:''}{row.scheduled_time?' | '+row.scheduled_time:''}{row.status==='recorded'?' (add feed entry)':''}</option>)}</select></label>}
     {chosenSession&&<Line label="Scheduled time and recommended quantity" value={(chosenSession.scheduled_time??'Time not set')+(chosenSession.scheduled_end?' ? '+chosenSession.scheduled_end:'')+' | '+(chosenSession.recommended_kg==null?'Ration unavailable':num(chosenSession.recommended_kg)+' kg')}/>}
     <label className="field"><span>Actual feeding time (Ghana)</span><input required type="time" value={dailyForm.actual_time??(feedingDate===ghanaDate()?new Date().toISOString().slice(11,16):'')} onChange={e=>setDailyForm({...dailyForm,actual_time:e.target.value})}/></label>
     <label className="field"><span>Feeding response (optional)</span><input maxLength={200} value={dailyForm.feeding_response??''} onChange={e=>setDailyForm({...dailyForm,feeding_response:e.target.value})}/></label>
     <Line label="Recorded by" value={user?.full_name??'Signed-in user'}/>
     {chosenSession?.recommended_kg!=null&&Number(dailyForm.quantity_kg)+Number(chosenSession.actual_kg)>chosenSession.recommended_kg&&<p className="muted">The total for this session will exceed the recommended quantity.</p>}
     <p className="muted">Inventory is automatically reduced when saved. Feeding cost is estimated from feed purchase receipts; it is not an independently entered expense.</p>
    </>}
    {dailyTab==='mortality'&&<>
     <label className="field"><span>Dead fish count</span><input required type="number" min="0" step="1" max={dailyCycle.estimated_live_count} value={dailyForm.dead_count??''} onChange={e=>setDailyForm({...dailyForm,dead_count:e.target.value})}/></label>
     <label className="field"><span>Observation date</span><input required type="date" max={localDate()} min={dailyCycle.stocked_on} value={dailyForm.recorded_on??''} onChange={e=>setDailyForm({...dailyForm,recorded_on:e.target.value})}/></label>
     <label className="field"><span>Cause (optional)</span><input maxLength={200} value={dailyForm.cause??''} onChange={e=>setDailyForm({...dailyForm,cause:e.target.value})}/></label>
    </>}
    {dailyTab==='water_quality'&&<>
     <label className="field"><span>Measurement date and time</span><input required type="datetime-local" max={localDateTime()} value={dailyForm.observed_at??''} onChange={e=>setDailyForm({...dailyForm,observed_at:e.target.value})}/></label>
     <div className="farmcoordinates">
      <label className="field"><span>Temperature (°C)</span><input type="number" step="any" min="-5" max="60" value={dailyForm.temperature_c??''} onChange={e=>setDailyForm({...dailyForm,temperature_c:e.target.value})}/></label>
      <label className="field"><span>Dissolved oxygen (mg/L)</span><input type="number" step="any" min="0" value={dailyForm.dissolved_oxygen_mg_l??''} onChange={e=>setDailyForm({...dailyForm,dissolved_oxygen_mg_l:e.target.value})}/></label>
      <label className="field"><span>pH</span><input type="number" step="any" min="0" max="14" value={dailyForm.ph??''} onChange={e=>setDailyForm({...dailyForm,ph:e.target.value})}/></label>
      <label className="field"><span>Ammonia (mg/L)</span><input type="number" step="any" min="0" value={dailyForm.ammonia_mg_l??''} onChange={e=>setDailyForm({...dailyForm,ammonia_mg_l:e.target.value})}/></label>
      <label className="field"><span>Nitrite (mg/L)</span><input type="number" step="any" min="0" value={dailyForm.nitrite_mg_l??''} onChange={e=>setDailyForm({...dailyForm,nitrite_mg_l:e.target.value})}/></label>
     </div>
     <div className="infobox">Enter readings from your test equipment. Species- and farm-specific alert thresholds are not configured yet; do not treat these measurements as automated safety advice.</div>
    </>}
    {dailyTab==='growth'&&<>
     <label className="field"><span>Sample date</span><input required type="date" max={localDate()} min={dailyCycle.stocked_on} value={dailyForm.recorded_on??''} onChange={e=>setDailyForm({...dailyForm,recorded_on:e.target.value})}/></label>
     <label className="field"><span>Sample fish weights (grams)</span><textarea required placeholder="Example: 125, 132, 118, 140" value={dailyForm.weights_g??''} onChange={e=>setDailyForm({...dailyForm,weights_g:e.target.value})}/><small className="muted">Enter up to 1,000 positive weights separated by commas or spaces. Average weight and estimated biomass are recalculated.</small></label>
    </>}
    <label className="field"><span>{dailyTab==='feeding'&&dailyForm.session_number==='unscheduled'?'Reason for unscheduled feeding':'Notes (optional)'}</span><textarea required={dailyTab==='feeding'&&dailyForm.session_number==='unscheduled'} maxLength={1000} value={dailyForm.notes??''} onChange={e=>setDailyForm({...dailyForm,notes:e.target.value})}/></label>
    <EvidenceRecorder key={`${dailyTab}-${dailyCycleId}-${recorderKey}`} activity={dailyTab} unit={units.find(unit=>unit.id===dailyCycle.unit_id)} getChallenge={getEvidenceChallenge} onChange={setDailyVideo}/>
    </fieldset>
    <button className="primary" disabled={busy||!dailyVideo||!dailyCycle||Boolean(evidenceRetry)}>{busy?'Saving record and video...':dailyTab==='feeding'?(chosenSession?'Save Session Feeding':'Save Unscheduled Feeding'):'Save operation record'}</button>
   </form>}
   {dailyTab==='feeding'&&<div className="metricrows daily-cost"><Line label="Indicative feed cost to date" value={feedingCosts?.total_indicative_cost_ghs==null?'Not available; record priced feed receipts':money(feedingCosts.total_indicative_cost_ghs)}/></div>}
   <div className="farmactions">
    <button type="button" className="outline" onClick={()=>openHistory({tab:dailyTab as HistoryTab,unit:dailyCycle.unit_id,cycle:dailyCycle.cycle_id})}>
     View {historyTabs.find(([key])=>key===dailyTab)?.[1]}
    </button>
    <button type="button" className="outline" onClick={()=>openHistory({tab:'evidence',unit:dailyCycle.unit_id})}>View Evidence Library</button>
   </div>
  </>:<div className="infobox">Loading active stocking cycle...</div>}
 </section>}
 </>}
 {page==='processing'&&<ProcessingWorkspace key={processingRevision} initial={processingEntry} farmId={farmId} load={json} api={api} download={download} onBusinessChange={()=>void refreshProcessingBusiness()}/>}
 {page==='history'&&(farmId?<><FarmActivityHistory key={farmId+':'+(historyContext.unit??'')+':'+(historyContext.cycle??'')}
  farmId={farmId} context={historyContext} load={json} api={api} change={openHistory} revision={workspaceRefresh}/>
  {historyContext.tab==='evidence'&&processingBusiness?.business_type==='integrated'&&
   <ProcessingEvidenceLibrary key={farmId} farmId={farmId} load={json} api={api} download={download}/>}</>:
  <p className="empty">Select a farm to view activity history.</p>)}
 {page==='expenses'&&(farmId?<FarmExpenses key={farmId} farmId={farmId} units={units} cycles={cycles} load={json}
   download={download} onSaved={loadFarm} refreshKey={analytics} chart={cashChart}/>:<p className="empty">Select a farm first.</p>)}
 {page==='finance'&&<>
  <div className="workspace-tabs"><button className="primary" onClick={()=>setPage('expenses')}>Record Expense</button></div>
  <div className="twocol">
   <section className="panel">
    <h2>Request a Loan</h2><p className="muted">A fixed farm performance summary is shared only with the institution you choose.</p>
    <form onSubmit={submitLoanApplication}>
     {dropdown('institution_id','Verified financial institution',institutions.map(i=>({value:i.id,label:i.name})))}
     {field('requested_ghs','Amount requested (GH₵)','number',{required:true,min:0.01,step:0.01})}
     {field('term_months','Term (months)','number',{required:true,min:1,max:240})}
     <label className="field"><span>Loan purpose</span><textarea required minLength={10} value={form.purpose||''} onChange={e=>setForm({...form,purpose:e.target.value})}/></label>
     <h3>Optional monthly repayment information</h3><p className="muted">Use your best estimate in GH₵. Leave unknown amounts blank; blanks are not treated as zero.</p>
     {field('monthly_other_income_ghs','Other monthly income (GH₵)','number',{min:0,step:0.01})}
     {field('monthly_household_expenses_ghs','Monthly household expenses (GH₵)','number',{min:0,step:0.01})}
     {field('monthly_external_debt_ghs','Monthly payments on debts outside AquaFarm (GH₵)','number',{min:0,step:0.01})}
     <button type="button" className="outline" disabled={busy||!farmId||!form.institution_id} onClick={()=>void previewLoanApplication()}>Preview Report</button>
      {applicationPreview&&<LoanAppraisalReport snapshot={applicationPreview} application={{}} institution={institutions.find(i=>i.id===Number(form.institution_id))?.name} onClose={()=>setApplicationPreview(null)}/>}
     <EvidenceRecorder key={`loan-application-${applicationRecorderKey}`} activity="loan_application" unit={null} requireFarmGps={false} onChange={video=>{setApplicationVideo(video);setApplicationEvidenceId(null)}} getChallenge={getEvidenceChallenge}/>
     <label className="consent"><input type="checkbox" checked={!!form.share_report} onChange={e=>setForm({...form,share_report:e.target.checked})}/> I authorize sharing my identity, this farm’s performance summary, tracked AquaFarm loans across my farms and any monthly financial figures I provide with the selected institution for this application. GPS coordinates and customer identities are excluded.</label>
     <button className="primary" disabled={busy||!farmId||!form.share_report||!applicationVideo}><PlusCircle size={17}/> Submit application</button>
    </form>
   </section>
   <section className="panel">
    <h2>Loan repayment reminders</h2>
    {reminders.some(r=>r.status==='overdue')&&<div className="alert" role="status">Action needed: {reminders.filter(r=>r.status==='overdue').length} loan instalment{reminders.filter(r=>r.status==='overdue').length===1?' is':'s are'} overdue.</div>}
    {reminders.some(r=>r.status==='upcoming')&&<div className="infobox" role="status">{reminders.filter(r=>r.status==='upcoming').length} instalment{reminders.filter(r=>r.status==='upcoming').length===1?' is':'s are'} due within 30 days.</div>}
    {reminders.length?reminders.map((r,i)=><div className="item" key={`${r.loan_id}-${r.installment}-${i}`}><b>Loan #{r.loan_id} · Instalment {r.installment} · {r.status}</b><small>Due {r.due_on} · Outstanding to date {money(r.amount_due_to_date_ghs)}</small></div>):<p className="empty">No upcoming or overdue instalments reported.</p>}
    <h2 className="spaced">My loan accounts</h2>{loans.map(l=><button className="item clickable" key={l.id} onClick={()=>void openLoan(l.id)}>Loan #{l.id} · {l.status} · Outstanding {money(l.total_scheduled_balance_ghs)} <span>View details →</span></button>)}{!loans.length&&<p className="empty">No loan accounts yet.</p>}
   </section>
  </div>
  <section className="panel"><h2>Loan applications</h2><div className="tablewrap"><table><thead><tr><th>Application</th><th>Institution</th><th>Requested</th><th>Term</th><th>Status</th></tr></thead><tbody>{applications.map(a=><tr key={a.id}><td><button className="outline small" onClick={()=>void viewFarmerApplication(a.id)}>{a.reference}</button></td><td>{institutions.find(i=>i.id===a.institution_id)?.name||`Institution #${a.institution_id}`}</td><td>{money(a.requested_ghs)}</td><td>{a.term_months} months</td><td><span className="pill">{a.status}</span></td></tr>)}</tbody></table>{!applications.length&&<p className="empty">No loan applications submitted.</p>}</div></section>
 {farmerApplication&&<section className="panel">
   <h2>{farmerApplication.reference}</h2>
   <Line label="Requested amount" value={money(farmerApplication.requested_ghs)}/>
   <Line label="Loan purpose" value={farmerApplication.purpose}/>
   <Line label="Status" value={String(farmerApplication.status).replace(/_/g,' ')}/>
   <button className="outline small" onClick={()=>void navigator.clipboard.writeText(farmerApplication.reference).then(()=>setNotice('Application reference copied')).catch(error=>setError(String(error)))}>Copy reference</button>
   <button type="button" className="outline small" disabled={applicationPdfBusy} onClick={()=>void downloadFarmerSummary()}>{applicationPdfBusy?'Generating PDF?':'Download application summary'}</button>
   {farmerApplication.shared_report_snapshot&&<button className="outline small" onClick={()=>setReportOpen(true)}>Preview Report</button>}
   {reportOpen&&farmerApplication.shared_report_snapshot&&<LoanAppraisalReport snapshot={farmerApplication.shared_report_snapshot} application={farmerApplication}
    institution={institutions.find(i=>i.id===farmerApplication.institution_id)?.name}
    onDownload={()=>downloadApplicationPdf('/farms/'+farmId+'/loan-applications/'+farmerApplication.id+'/report.pdf',farmerApplication.reference)} onClose={()=>setReportOpen(false)}/>}

   <h3>Decision history</h3>
   {farmerApplication.appraisals.length?farmerApplication.appraisals.map((decision:Obj,index:number)=><div className="item" key={index}><b>{String(decision.decision).replace(/_/g,' ')}</b><small>{decision.rationale}</small>{decision.approved_ghs!=null&&<small>Amount approved for an offer {money(decision.approved_ghs)}</small>}</div>):<p className="empty">No assessment decisions recorded.</p>}
 </section>}

 </>}
 {page==='reports'&&<>
  <nav className="farmactions workspace-tabs" aria-label="Report breadcrumbs">
    <button className="outline" onClick={backToDashboard}>Back to Dashboard</button>
    {reportView&&<><button className="outline" onClick={()=>openReport(null)}>Back to Reports</button><span aria-current="page">{reports.find(([key])=>key===reportView)?.[1]}</span></>}
  </nav>
  {reportView&&<p className="muted">{farms.find(row=>row.id===farmId)?.name??'No farm selected'} | {reports.find(([key])=>key===reportView)?.[2]}</p>}
  {!reportView?<><ReportCards open={openReport}/><button type="button" className="outline" onClick={()=>openHistory({tab:'all'})}>Farm Activity History</button>{processingBusiness&&processingBusiness.business_type!=='farmer'&&<button className="outline" onClick={()=>openProcessing('reports')}>Processing History & Reports</button>}</>:!farmId?<p className="empty">Select a farm to open this report.</p>:
   <ReportDetail key={farmId+'-'+reportView} view={reportView} farmId={farmId}
    analytics={analytics?.farm?.farm_id===farmId?analytics:null}
    harvests={harvestSchedule.filter(row=>row.farm_id===farmId)} loading={overviewLoading} loadError={overviewError}
    load={json} download={download} downloadPdf={downloadPricingPdf} cashChart={cashChart}
    trend={(title,points,dateKey,valueKey,seriesKey,unit)=><TrendChart {...{title,points,dateKey,valueKey,seriesKey,unit}}/>}
    stockChart={data=><BarChart title="Feed stock by product" data={data} labelKey="feed_name" series={[{key:'remaining_stock_kg',label:'Remaining kg',color:'#168064'}]}/>}
    navigate={(destination,view)=>{window.history.replaceState(null,'',window.location.pathname+window.location.search);if(view)openProduction(view);else setPage(destination)}}
    refresh={()=>void loadFarm()}>
    {reportView==='pricing'&&<details><summary>Existing production plan pricing</summary>
   <h3>Production cost and selling-price estimates</h3>
   <p className="muted">Prices recalculate from recorded feed use and costs, allocated expenses, current fish population, and the latest sample. Change your profit target or market-price assumption whenever needed.</p>
   {(analytics?.finance?.pricing_by_plan||[]).length?
    <div className="pricing-grid">{analytics?.finance?.pricing_by_plan?.map((row:Obj)=>{
     const values=pricingForm[row.plan_id]||{desired_profit_pct:row.desired_profit_pct,profit_method:row.profit_method,market_price_ghs_per_kg:row.market_price_ghs_per_kg??''};
     const difference=row.market_price_difference_ghs_per_kg;
     return <article className="pricing-card" key={row.plan_id}>
      <div className="between"><b>Plan #{row.plan_id} · {row.species}</b><span className="pill">{num(row.projected_harvest_kg)} kg forecast</span></div>
      <div className="metricrows">
       <Line label="Projected production cost" value={money(row.projected_cycle_total_cost_ghs)}/>
       <Line label="Minimum break-even price" value={row.break_even_ghs_per_kg==null?'Not available':`${money(row.break_even_ghs_per_kg)}/kg`}/>
       <Line label="Recommended selling price" value={row.recommended_price_ghs_per_kg==null?'Not available':`${money(row.recommended_price_ghs_per_kg)}/kg`}/>
       <Line label="Projected revenue at recommended price" value={row.projected_revenue_ghs==null?'Not available':money(row.projected_revenue_ghs)}/>
       <Line label="Projected profit at recommended price" value={row.projected_profit_ghs==null?'Not available':money(row.projected_profit_ghs)}/>
       {row.market_price_ghs_per_kg!=null&&<Line label="Farmer-entered market price" value={`${money(row.market_price_ghs_per_kg)}/kg`}/>}
       {difference!=null&&<Line label="Recommended price vs market" value={`${difference>=0?'Above':'Below'} by ${money(Math.abs(difference))}/kg`}/>}
       {row.market_projected_profit_ghs!=null&&<Line label="Projected profit at market price" value={money(row.market_projected_profit_ghs)}/>}
      </div>
      <form className="pricing-form" onSubmit={event=>void savePricing(event,row.plan_id)}>
       <label className="field"><span>Desired profit percentage</span><input type="number" min="0" max={values.profit_method==='margin'?99.99:500} step="0.1" required value={values.desired_profit_pct} onChange={event=>setPricingForm((previous:Obj)=>({...previous,[row.plan_id]:{...values,desired_profit_pct:event.target.value}}))}/></label>
       <label className="field"><span>Profit calculation</span><select value={values.profit_method} onChange={event=>setPricingForm((previous:Obj)=>({...previous,[row.plan_id]:{...values,profit_method:event.target.value}}))}><option value="markup">Markup on cost</option><option value="margin">Profit margin</option></select></label>
       <label className="field"><span>Market price per kg (GH₵, optional)</span><input type="number" min="0" step="0.01" value={values.market_price_ghs_per_kg} onChange={event=>setPricingForm((previous:Obj)=>({...previous,[row.plan_id]:{...values,market_price_ghs_per_kg:event.target.value}}))}/></label>
       <button className="outline" disabled={busy||!farmId}>Save and recalculate</button>
      </form>
      {!!row.warnings?.length&&<p className="footnote">{row.warnings.join(' ')}</p>}
     </article>
    })}</div>:<p className="empty">No production plans are recorded for this farm yet.</p>}
    </details>}
    {reportView==='complete'&&<details><summary>Existing Excel and CSV reports</summary>
   <div className="reportgrid">{reportDefinitions.map(report=><div className="reportcard" key={report.kind}><FileDown size={25}/><b>{report.label}</b><p>{report.description}</p>
    {report.csv&&<button className="outline" disabled={!farmId} onClick={()=>void download(`/farms/${farmId}/reports/${report.csv}`,`aquafarm_${report.kind}_${farmId}.csv`)}>Download CSV</button>}
    <button className="primary" disabled={!farmId} onClick={()=>void download(`/farms/${farmId}/reports/${report.kind}.xlsx`,`aquafarm_${report.kind}_${farmId}.xlsx`)}>Download Excel</button>
   </div>)}</div>
   <label className="field report-search"><span>Search generated report data</span><input type="search" value={reportSearch} onChange={event=>setReportSearch(event.target.value)} placeholder="Search farm metrics, cycles, inventory or dates"/></label>
   <div className="tablewrap"><table><thead><tr><th>Report section</th><th>Record</th><th>Generated value</th></tr></thead><tbody>{filteredReportRows.slice(0,100).map((row,index)=><tr key={`${row.section}-${row.record}-${index}`}><td>{row.section}</td><td>{row.record}</td><td>{row.value}</td></tr>)}</tbody></table>
    {!filteredReportRows.length&&<p className="empty">{analytics?'No generated records match this search.':'Select a farm to generate report data.'}</p>}
    {filteredReportRows.length>100&&<p className="muted">Showing the first 100 matches. Download Excel for the complete report.</p>}
   </div>
   <div className="infobox">Investment report data is record-derived and may be incomplete or unverified. Forecast dates, harvest weights, FCR and pricing are estimates; this report is not an audited financial statement, bank certification or credit decision.</div>
    </details>}
   </ReportDetail>}
  {reportView==='growth'&&<details><summary>Production Unit Intelligence</summary>
  {farmId&&analytics?.farm?.farm_id===farmId&&<ProductionIntelligence key={farmId} farmId={farmId} analytics={analytics}
    harvests={harvestSchedule.filter(row=>row.farm_id===farmId)} load={json} open={openUnitActivity} pricingDownload={downloadPricingPdf}/>}
  </details>}
 </>}
 {page==='admin'&&user?.is_platform_admin&&<><section className="panel">
 <h2>Stakeholder Approvals</h2>
 <h3>Financial institutions</h3>
 <details><summary>Register institution</summary>
 <form className="farmform" autoComplete="off" onSubmit={e=>formSubmit(e,'/finance/admin/institutions',{
   full_name:form.institution_admin_name,email:form.institution_admin_email,password:form.institution_admin_password,
   institution:{name:form.institution_name,institution_type:form.institution_type,account_number:form.institution_reference}
 },()=>setForm({}))}>
   {field('institution_name','Official institution name','text',{required:true,minLength:3,maxLength:180})}
   {dropdown('institution_type','Institution type',[{value:'bank',label:'Commercial bank'},{value:'rural_bank',label:'Rural or community bank'},{value:'microfinance',label:'Microfinance'},{value:'credit_union',label:'Credit union'},{value:'other',label:'Other'}])}
   {field('institution_reference','Institution registration or account reference','text',{required:true,minLength:3,maxLength:100})}
   {field('institution_admin_name','Initial administrator full name','text',{required:true,maxLength:120})}
   {field('institution_admin_email','Initial administrator official email','email',{required:true})}
   {field('institution_admin_password','Initial administrator password','password',{required:true,minLength:8,maxLength:128,autoComplete:'new-password'})}
   <button className="primary" disabled={busy}>Register institution</button>
 </form>
 </details>
 <div className="farmform">
 <label className="field"><span>Search institutions</span><input type="search" value={institutionReviewSearch} onChange={e=>setInstitutionReviewSearch(e.target.value)}/></label>
 <label className="field"><span>Status</span><select value={institutionReviewFilter} onChange={e=>setInstitutionReviewFilter(e.target.value)}>
 {Object.entries({all:'All',pending:'Pending',under_review:'Under review',more_info_required:'More information required',verified:'Approved',rejected:'Rejected',suspended:'Suspended'}).map(([value,label])=><option key={value} value={value}>{label}</option>)}
 </select></label>
 </div>
 {pendingInstitutions.filter(inst=>(institutionReviewFilter==='all'||inst.status===institutionReviewFilter)&&String(inst.name+' '+inst.registration_number).toLowerCase().includes(institutionReviewSearch.trim().toLowerCase())).map(inst=>{
   const actions:Record<string,string>={};
   if(inst.status==='pending'||inst.status==='more_info_required')actions.under_review='Start review';
   if(inst.status==='pending'||inst.status==='under_review')actions.more_info_required='Request more information';
   if(['pending','under_review','more_info_required'].includes(inst.status)){actions.verified='Approve';actions.rejected='Reject'}
   if(user.is_platform_owner&&inst.status==='verified')actions.suspended='Suspend';
   if(user.is_platform_owner&&inst.status==='suspended')actions.verified='Reactivate';
   return <div className="item" key={inst.id}><b>{inst.name} ? {inst.status==='verified'?'approved':inst.status.replace(/_/g,' ')}</b>
    <p className="muted">{inst.institution_type} ? {inst.registration_number}</p>
    <div className="row-actions">{Object.entries(actions).map(([status,label])=><button key={status} type="button" className="outline small" disabled={busy} onClick={()=>{
      const reason=window.prompt(label+' '+inst.name+' ? enter a reason');
      if(reason?.trim()&&window.confirm(label+' '+inst.name+'?'))void submit('/finance/admin/institutions/'+inst.id+'/status',{status,reason:reason.trim()});
    }}>{label}</button>)}</div>
   </div>
 })}
 <button className="outline" type="button" onClick={()=>void loadBase()}>Refresh institutions</button>
 </section>
</>}
 {page==='lender'&&<>
  <div className="twocol">
   <section className="panel">
    <h2>My financial institutions</h2>
    {mine.length>0?<label className="field"><span>Institution workspace</span><select value={institutionId??''} onChange={e=>{setInstitutionId(Number(e.target.value));setSelectedApp(null);setSelectedLoan(null)}}>{mine.map(i=><option key={i.id} value={i.id}>{i.name} ({i.status})</option>)}</select></label>:<p className="empty">No institution memberships found.</p>}
    {selectedInstitution?.status==='pending'&&<div className="infobox">This institution is awaiting platform administrator verification. Lending features will become available after approval.</div>}
    {selectedInstitution?.status==='under_review'&&<div className="infobox">The platform administrator is reviewing this institution.</div>}
    {selectedInstitution?.status==='more_info_required'&&<div className="infobox">More information is required. Contact the platform administrator to continue the review.</div>}
    {selectedInstitution?.status==='suspended'&&<div className="alert">This institution is suspended. Contact the platform administrator for review.</div>}
    {selectedInstitution?.status==='rejected'&&<div className="alert">This institution was rejected. Contact the platform administrator for review.</div>}
    {['legacy','institution'].includes(user.account_type)&&<div>

    <p className="footnote">New institutions require platform administrator verification before lender operations.</p>
    </div>}
   </section>
   {selectedInstitution?.status==='verified'&&institutionRole==='owner'&&institutionId!=null&&
     <InstitutionStaff key={institutionId} id={institutionId} name={selectedInstitution.name} api={json}/>}
   {selectedInstitution?.status==='verified'&&<section className="panel">
    <h2>Loan portfolio dashboard</h2>
    <div className="metricrows">
     <Line label="Loan accounts" value={num(portfolio?.loan_accounts??lenderLoans.length)}/>
     <Line label="Active loans" value={num(portfolio?.active_loans??lenderLoans.filter(l=>l.status==='active').length)}/>
     <Line label="Total disbursements" value={money(portfolio?.total_disbursements_ghs??0)}/>
     <Line label="Outstanding balances" value={money(portfolio?.outstanding_balance_ghs??0)}/>
     <Line label="Outstanding fees" value={money(portfolio?.outstanding_fees_ghs??0)}/>
     <Line label="Collections" value={money(portfolio?.total_collections_ghs??0)}/>
     <Line label="Overdue loans" value={num(portfolio?.overdue_loans??0)}/>
     <Line label="Arrears" value={money(portfolio?.arrears_ghs??0)}/>
     <Line label="Repayment performance" value={portfolio?.repayment_performance_pct==null?'No instalments due':`${num(portfolio.repayment_performance_pct)}%`}/>
    </div>
    <h3 className="spaced">Loan accounts</h3>{lenderLoans.map(l=><button className="item clickable" key={l.id} onClick={()=>void openLoan(l.id)}>Loan #{l.id} · {l.status} · Outstanding {money(l.total_scheduled_balance_ghs)}<span>Manage →</span></button>)}{!lenderLoans.length&&<p className="empty">No loan accounts for this institution.</p>}
   </section>}
  </div>
  {selectedInstitution?.status==='verified'&&<section className="panel"><h2>Applications for appraisal</h2><form className="farmform" onSubmit={findLoanApplication}>
 <label className="field"><span>Application reference</span><input required maxLength={35} value={referenceSearch} onChange={e=>setReferenceSearch(e.target.value)}/></label>
 <button className="outline" disabled={busy}>Find Loan Application</button>
 </form><div className="tablewrap"><table><thead><tr><th>ID</th><th>Farm ID</th><th>Requested</th><th>Purpose</th><th>Status</th><th></th></tr></thead><tbody>{lenderApps.map(a=><tr key={a.id}><td>{a.reference}</td><td>#{a.farm_id}</td><td>{money(a.requested_ghs)}</td><td>{a.purpose}</td><td><span className="pill">{a.status}</span></td><td><button className="outline small" onClick={()=>void openApp(a.id)}>{a.status==='approved'?'Open loan':'Review'}</button></td></tr>)}</tbody></table>{!lenderApps.length&&<p className="empty">No applications available.</p>}</div></section>}
  {selectedApp&&<section className="panel">
   <div className="between"><h2>Application #{selectedApp.id}</h2><button className="textbutton" onClick={()=>setSelectedApp(null)}>Close</button></div>
   <p><b>Purpose:</b> {selectedApp.purpose}</p><p><b>Requested:</b> {money(selectedApp.requested_ghs)} · <b>Status:</b> {selectedApp.status}</p>
   {selectedApp.shared_report_snapshot&&<>
    <button type="button" className="outline" onClick={()=>setReportOpen(true)}>Preview Report</button>
    {selectedApp.shared_report_snapshot.application_video_evidence_id&&<button type="button" className="outline" onClick={()=>void download(
      '/finance/loan-evidence/'+selectedApp.shared_report_snapshot.application_video_evidence_id+'/video',
      'loan_application_'+selectedApp.id+(selectedApp.shared_report_snapshot.application_video_media_type==='video/mp4'?'.mp4':'.webm')
    )}>Review application video</button>}
    {reportOpen&&<LoanAppraisalReport snapshot={selectedApp.shared_report_snapshot} application={selectedApp}
      institution={selectedInstitution?.name}
      onDownload={()=>downloadApplicationPdf('/finance/institutions/'+institutionId+'/applications/'+selectedApp.id+'/report.pdf',selectedApp.reference)} onClose={()=>setReportOpen(false)}/>}
   </>}

   {canAssess&&!['approved','rejected'].includes(selectedApp.status)&&<form onSubmit={e=>formSubmit(e,`/finance/institutions/${institutionId}/applications/${selectedApp.id}/appraise`,{decision:form.decision,rationale:form.rationale,...(form.decision==='approved'?{approved_ghs:Number(form.approved_ghs)}:{})},()=>{setSelectedApp(null);setForm({})})}>
    {dropdown('decision','Appraisal decision',(canAppraise?['under_review','more_information','approved','rejected']:['under_review','more_information']).map(x=>({value:x,label:x.replace('_',' ')})))}
    <label className="field"><span>Decision rationale (minimum 10 characters)</span><textarea minLength={10} required value={form.rationale||''} onChange={e=>setForm({...form,rationale:e.target.value})}/></label>
    {form.decision==='approved'&&field('approved_ghs','Approved amount (GH₵)','number',{min:0.01,step:0.01,required:true})}
    <button className="primary" disabled={busy}>Record decision</button>
   </form>}
   {canAppraise&&selectedApp.status==='approved'&&!lenderLoans.some(loan=>loan.application_id===selectedApp.id)&&<form className="farmform" onSubmit={openApprovedLoan}>
    <h3>Open approved loan account</h3>
    <p className="muted">Approved principal: {money(selectedApprovedAmount)}. Flat interest applies over the approved term. Insurance and processing each apply once to the approved principal.</p>
    {field('annual_flat_interest_percent','Annual flat interest rate (%)','number',{required:true,min:0,max:100,step:0.01})}
    {field('commitment_fee_ghs','Commitment fee (GH₵)','number',{min:0,step:0.01})}
    <label className="field"><span>Agricultural insurance (%)</span><input type="number" required min="0" max="100" step="0.01" value={insuranceRate} onChange={e=>setForm({...form,insurance_fee_percent:e.target.value})}/></label>
    {field('processing_fee_percent','Processing fee (%)','number',{min:0,max:100,step:0.01})}
    <div className="infobox">
     <Line label="Interest for the approved term" value={money(quoteInterest)}/>
     <Line label="Agricultural insurance" value={money(quoteInsurance)}/>
     <Line label="Processing fee" value={money(quoteProcessing)}/>
     <Line label="Commitment fee" value={money(quoteCommitment)}/>
     <Line label="Estimated total repayment" value={money(projectedLoanTotal)}/>
    </div>
    <label className="field"><span>Repayment schedule</span><select required value={form.repayment_frequency??''} onChange={e=>setForm({...form,repayment_frequency:e.target.value})}><option value="">Choose...</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="harvest">Harvest-based (single due date)</option><option value="custom">Customized instalments</option></select></label>
    {form.repayment_frequency==='custom'?<>
     <p className="muted">Enter each due date and its principal, interest and fee amounts. Their totals must match the loan quote above.</p>
     {customSchedule.map((item,index)=><div className="farmcoordinates custom-schedule-row" key={index}>
      <label className="field"><span>Instalment {index+1} due date</span><input required type="date" min={nextLocalDate()} value={item.due_on} onChange={e=>setCustomSchedule(rows=>rows.map((row,i)=>i===index?{...row,due_on:e.target.value}:row))}/></label>
      <label className="field"><span>Principal (GH₵)</span><input required type="number" min="0" step="0.01" value={item.principal_ghs} onChange={e=>setCustomSchedule(rows=>rows.map((row,i)=>i===index?{...row,principal_ghs:e.target.value}:row))}/></label>
      <label className="field"><span>Interest (GH₵)</span><input required type="number" min="0" step="0.01" value={item.interest_ghs} onChange={e=>setCustomSchedule(rows=>rows.map((row,i)=>i===index?{...row,interest_ghs:e.target.value}:row))}/></label>
      <label className="field"><span>Fees (GH₵)</span><input required type="number" min="0" step="0.01" value={item.fees_ghs} onChange={e=>setCustomSchedule(rows=>rows.map((row,i)=>i===index?{...row,fees_ghs:e.target.value}:row))}/></label>
      <button type="button" className="outline danger small" disabled={customSchedule.length===1} onClick={()=>setCustomSchedule(rows=>rows.filter((_,i)=>i!==index))}>Remove</button>
     </div>)}
     <button type="button" className="outline small" onClick={()=>setCustomSchedule(rows=>[...rows,{due_on:'',principal_ghs:'',interest_ghs:'',fees_ghs:''}])}>Add instalment</button>
    </>:form.repayment_frequency&&<>
     {field('first_due_date','First repayment due date','date',{required:true,min:nextLocalDate()})}
    </>}
    <button className="primary" disabled={busy||!form.repayment_frequency}>Send loan offer</button>
   </form>}
  </section>}
 </>}
 {selectedLoan&&<div className="overlay" onClick={()=>setSelectedLoan(null)}><div className="drawer" onClick={e=>e.stopPropagation()}>
  <div className="between"><h2>Loan #{selectedLoan.id}</h2><button className="outline" onClick={()=>setSelectedLoan(null)}>Close</button></div>
  <span className="pill">{selectedLoan.status}</span>
  <div className="metricrows loan-summary">
   <Line label="Approved amount" value={money(selectedLoan.approved_ghs)}/>
   <Line label="Interest over approved term" value={money(selectedLoan.expected_interest_ghs)}/>
   <Line label="Term" value={num(selectedLoan.term_months)+' months'}/>
   <Line label="Total contract repayment" value={money(selectedLoan.total_contract_repayment_ghs)}/>
   <Line label="Disbursed" value={money(selectedLoan.disbursed_ghs)}/>
   <Line label="Undisbursed" value={money(selectedLoan.undisbursed_ghs)}/>
   <Line label="Outstanding principal" value={money(selectedLoan.outstanding_principal_ghs)}/>
   <Line label="Outstanding interest" value={money(selectedLoan.outstanding_scheduled_interest_ghs)}/>
   <Line label="Commitment fee" value={money(selectedLoan.commitment_fee_ghs)}/>
   <Line label={selectedLoan.processing_fee_percent == null ? "Processing fee" : "Processing fee ("+num(selectedLoan.processing_fee_percent)+"%)"} value={money(selectedLoan.processing_fee_ghs)}/>
   <Line label={selectedLoan.insurance_fee_percent == null ? "Agricultural insurance" : "Agricultural insurance ("+num(selectedLoan.insurance_fee_percent)+"%)"} value={money(selectedLoan.insurance_fee_ghs)}/>
   <Line label="Outstanding fees" value={money(selectedLoan.outstanding_fees_ghs)}/>
   <Line label="Total scheduled balance" value={money(selectedLoan.total_scheduled_balance_ghs)}/>
   <Line label="Annual flat interest rate" value={`${num(selectedLoan.annual_flat_interest_percent)}%`}/>
   <Line label="Repayment schedule" value={selectedLoan.repayment_frequency}/>
  </div>
  {page==='lender'&&canDisburse&&selectedLoan.status==='awaiting_disbursement'&&Number(selectedLoan.undisbursed_ghs)>0&&<form className="farmform" onSubmit={e=>void saveLoanTransaction(e,'disbursements')}>
   <h3>Record loan disbursement</h3>
   <label className="field"><span>Amount (GH₵)</span><input required type="number" min="0.01" max={selectedLoan.undisbursed_ghs} step="0.01" value={form.loan_amount_ghs??''} onChange={e=>setForm({...form,loan_amount_ghs:e.target.value})}/></label>
   <label className="field"><span>Transfer reference</span><input required minLength={3} maxLength={100} value={form.loan_reference??''} onChange={e=>setForm({...form,loan_reference:e.target.value})}/></label>
   <label className="field"><span>Disbursement date</span><input required type="date" max={localDate()} value={form.loan_transaction_date??''} onChange={e=>setForm({...form,loan_transaction_date:e.target.value})}/></label>
   <EvidenceRecorder key={`loan-${selectedLoan.id}-disbursement-${transactionRecorderKey}`} activity="disbursement" unit={null} requireFarmGps={false} onChange={video=>{setTransactionVideo(video);setTransactionEvidenceId(null)}} getChallenge={getEvidenceChallenge}/>
   <button className="primary" disabled={busy||!transactionVideo}>Record disbursement</button>
  </form>}
  {page==='lender'&&canRepay&&selectedLoan.status==='active'&&<form className="farmform" onSubmit={e=>void saveLoanTransaction(e,'repayments')}>
   <h3>Record loan repayment</h3>
   <label className="field"><span>Amount received (GH₵)</span><input required type="number" min="0.01" max={selectedLoan.total_scheduled_balance_ghs} step="0.01" value={form.loan_amount_ghs??''} onChange={e=>setForm({...form,loan_amount_ghs:e.target.value})}/></label>
   <label className="field"><span>Payment reference</span><input required minLength={3} maxLength={100} value={form.loan_reference??''} onChange={e=>setForm({...form,loan_reference:e.target.value})}/></label>
   <label className="field"><span>Payment date</span><input required type="date" max={localDate()} value={form.loan_transaction_date??''} onChange={e=>setForm({...form,loan_transaction_date:e.target.value})}/></label>
   <EvidenceRecorder key={`loan-${selectedLoan.id}-repayment-${transactionRecorderKey}`} activity="repayment" unit={null} requireFarmGps={false} onChange={video=>{setTransactionVideo(video);setTransactionEvidenceId(null)}} getChallenge={getEvidenceChallenge}/>
   <p className="muted">Partial payments are applied to scheduled interest, then fees, then principal. Do not record a payment until the institution has verified receipt.</p>
   <button className="primary" disabled={busy||!transactionVideo}>Record repayment</button>
  </form>}
  <h3>{selectedLoan.status==='offered'?'Proposed repayment schedule':'Repayment schedule'}</h3>
  {page==='finance'&&selectedLoan.status==='offered'&&<div className="farmactions">
    <button className="primary" disabled={busy||!schedule.length} onClick={()=>void respondToLoanOffer(selectedLoan.id,'accept')}>Accept offer</button>
    <button className="outline" disabled={busy} onClick={()=>void respondToLoanOffer(selectedLoan.id,'decline')}>Decline offer</button>
  </div>}<div className="tablewrap"><table><thead><tr><th>#</th><th>Due</th><th>Principal</th><th>Interest</th><th>Fees</th><th>Total</th></tr></thead><tbody>{schedule.map(s=><tr key={s.number}><td>{s.number}</td><td>{s.due_on}</td><td>{money(s.principal_ghs)}</td><td>{money(s.interest_ghs)}</td><td>{money(s.fees_ghs)}</td><td>{money(s.total_ghs)}</td></tr>)}</tbody></table>{!schedule.length&&<p className="empty">No repayment schedule available for this loan.</p>}</div>
  <h3>Transaction history</h3>{transactions.map((t,i)=><div className="item" key={`${t.type}-${t.reference}-${i}`}><b>{t.type==='repayment'?'Repayment':'Disbursement'} · {t.date} · {money(t.amount_ghs)}</b><small>{t.reference}{t.type==='repayment'?` · Principal ${money(t.principal_ghs)} · Interest ${money(t.interest_ghs)} · Fees ${money(t.fees_ghs)}`:''}</small>{t.evidence_id&&<button type="button" className="outline small" onClick={()=>void download(`/finance/loan-evidence/${t.evidence_id}/video`,`loan_${t.type}_${t.evidence_id}.${t.evidence_media_type==='video/mp4'?'mp4':'webm'}`)}>Review 15-second video</button>}</div>)}{!transactions.length&&<p className="empty">No transactions recorded.</p>}
  <p className="footnote">This is a manual ledger; it does not transfer money or verify bank settlement.</p>
 </div></div>}
 </main></div>;
}
function Stat({label,value,sub}:{label:string,value:string,sub:string}){return <div className="stat"><small>{label}</small><strong>{value}</strong><span>{sub}</span></div>}
function Line({label,value}:{label:string,value:string}){return <div className="line"><span>{label}</span><b>{value}</b></div>}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
