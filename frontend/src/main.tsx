import React, {useEffect,useState,useCallback,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {Waves, LayoutDashboard, Fish, Wallet, Landmark, FileDown, LogOut, RefreshCw, CheckCircle2, AlertTriangle, PlusCircle, Building2, Sprout, Pencil, Archive, X, LocateFixed, Camera, RotateCcw} from 'lucide-react';
import './style.css';

type Obj = Record<string, any>;
type Page = 'overview'|'farms'|'units'|'production'|'finance'|'reports'|'lender';
const money=(n:any)=>new Intl.NumberFormat('en-GH',{style:'currency',currency:'GHS',maximumFractionDigits:2}).format(Number(n)||0);
const num=(n:any)=>new Intl.NumberFormat('en-GH',{maximumFractionDigits:2}).format(Number(n)||0);
const initialToken=()=>sessionStorage.getItem('aquafarm_token')||'';
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
 const usable=points.filter(point=>Number.isFinite(Number(point[valueKey]))&&point[dateKey]);
 if(!usable.length)return <section className="chart-card"><h3>{title}</h3><p className="empty">No recorded measurements available yet.</p></section>;
 const times=usable.map(point=>new Date(point[dateKey]).getTime()).filter(Number.isFinite);
 const values=usable.map(point=>Number(point[valueKey]));
 const minTime=Math.min(...times),maxTime=Math.max(...times),minValue=Math.min(...values),maxValue=Math.max(...values);
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
 const [page,setPage]=useState<Page>('overview');const [dashboard,setDashboard]=useState<Obj|null>(null);const [analytics,setAnalytics]=useState<Obj|null>(null);
 const [reportSearch,setReportSearch]=useState('');
 const [pricingForm,setPricingForm]=useState<Obj>({});
 const [cycles,setCycles]=useState<Obj[]>([]);const [applications,setApplications]=useState<Obj[]>([]);
 const [dailyRecordStatus,setDailyRecordStatus]=useState<Obj|null>(null);
 const [loans,setLoans]=useState<Obj[]>([]);const [reminders,setReminders]=useState<Obj[]>([]);
 const [institutions,setInstitutions]=useState<Obj[]>([]);const [mine,setMine]=useState<Obj[]>([]);
 const [pendingInstitutions,setPendingInstitutions]=useState<Obj[]>([]);
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
 const [stockForm,setStockForm]=useState<Obj>({stocked_on:new Date().toISOString().slice(0,10)});
 const [cycleFilter,setCycleFilter]=useState<'active'|'completed'|'all'>('active');
 const [dailyTab,setDailyTab]=useState<'feeding'|'mortality'|'water_quality'|'growth'>('feeding');
 const [dailyCycleId,setDailyCycleId]=useState<number|''>('');
 const [feedProducts,setFeedProducts]=useState<Obj[]>([]);
 const [feedProductForm,setFeedProductForm]=useState<Obj>({});
 const [feedReceiptForm,setFeedReceiptForm]=useState<Obj>({occurred_on:localDate()});
 const [dailyForm,setDailyForm]=useState<Obj>({recorded_on:localDate(),observed_at:localDateTime()});
 const [dailyVideo,setDailyVideo]=useState<RecordedVideo|null>(null);
 const [stockVideo,setStockVideo]=useState<RecordedVideo|null>(null);
 const [receiptVideo,setReceiptVideo]=useState<RecordedVideo|null>(null);
 const [recorderKey,setRecorderKey]=useState(0);
 const [feedingHistory,setFeedingHistory]=useState<Obj[]>([]);
 const [mortalityHistory,setMortalityHistory]=useState<Obj[]>([]);
 const [waterHistory,setWaterHistory]=useState<Obj[]>([]);
 const [growthHistory,setGrowthHistory]=useState<Obj[]>([]);
 const [feedingCosts,setFeedingCosts]=useState<Obj|null>(null);
 const [feedingProfile,setFeedingProfile]=useState<Obj|null>(null);
 const [feedingRecommendation,setFeedingRecommendation]=useState<Obj|null>(null);
 const [feedForecast,setFeedForecast]=useState<Obj|null>(null);
 const [dailyEvidence,setDailyEvidence]=useState<Obj[]>([]);
 const [evidenceRetry,setEvidenceRetry]=useState<Obj|null>(null);
 const [profileForm,setProfileForm]=useState<Obj>({phone_number:'',sms_daily_records_enabled:false,sms_loan_reminders_enabled:false});
 const [authMode,setAuthMode]=useState<'login'|'register'>('login');const [form,setForm]=useState<Obj>({});
 const activeCycles=cycles.filter(c=>c.status==='active');
 const dailyCycle=activeCycles.find(c=>c.cycle_id===Number(dailyCycleId));
 const selectedApprovedAmount=Number(selectedApp?.appraisals?.filter((x:Obj)=>x.decision==='approved').slice(-1)[0]?.approved_ghs??selectedApp?.requested_ghs??0);
 const projectedLoanTotal=selectedApprovedAmount+selectedApprovedAmount*Number(form.annual_flat_interest_percent||0)/100*Number(selectedApp?.term_months||0)/12+Number(form.commitment_fee_ghs||0)+Number(form.processing_fee_ghs||0)+selectedApprovedAmount*0.01;
 useEffect(()=>{
   const species=farms.find(f=>f.id===farmId)?.species?.toLowerCase().includes('catfish')?'Catfish':'Tilapia';
   setStockForm({stocked_on:new Date().toISOString().slice(0,10),species});
   setCycleFilter('active');
 },[farmId]);
 useEffect(()=>{
   setApplicationVideo(null);setApplicationEvidenceId(null);setApplicationRecorderKey(key=>key+1);
 },[farmId]);
 useEffect(()=>{
   setDailyCycleId(previous=>activeCycles.some(c=>c.cycle_id===Number(previous))?previous:activeCycles[0]?.cycle_id??'');
 },[cycles]);
 useEffect(()=>{
   setDailyVideo(null);setRecorderKey(key=>key+1);
   setDailyForm({recorded_on:localDate(),observed_at:localDateTime()});
 },[dailyTab,dailyCycleId]);
 const api=useCallback(async(path:string,init:RequestInit={})=>{
   let res:Response;
   try{
     res=await fetch('/api'+path,{...init,headers:{...(init.body?{'Content-Type':'application/json'}:{}),...(token?{Authorization:`Bearer ${token}`}:{}) ,...init.headers}});
   }catch{
     throw new Error('Cannot connect to the AquaFarm API. Make sure the backend is running on http://127.0.0.1:8000.');
   }
   if(!res.ok){let detail='Request failed ('+res.status+')';try{const d=await res.json();detail=typeof d.detail==='string'?d.detail:JSON.stringify(d.detail||d)}catch{};if(res.status===401){sessionStorage.removeItem('aquafarm_token');setToken('')};throw new Error(detail)}return res
 },[token]);
 const json=useCallback(async(path:string,body?:Obj,method='POST')=>(await api(path,body?{method,body:JSON.stringify(body)}:{})).json(),[api]);
 const getEvidenceChallenge=useCallback(async(activity:string,unitId:number)=>{
   if(!farmId)throw new Error('Select a farm before recording evidence.');
   const challengeActivities=['feeding','growth','mortality','stocking','feed_stock_count','fish_transfer','harvest','treatment'];
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
 useEffect(()=>{
   if(!farmId||!dailyCycle||!token){setFeedingProfile(null);setFeedingRecommendation(null);setFeedForecast(null);return}
   const species=dailyCycle.species?.toLowerCase().includes('catfish')?'catfish':'tilapia';
   void Promise.all([
     json(`/farms/${farmId}/feeding-profiles`),
     json(`/farms/${farmId}/feeding-recommendations`),
     json(`/farms/${farmId}/feed-forecast`),
   ]).then(([profiles,recommendations,forecast])=>{
     setFeedingProfile(profiles.find((item:Obj)=>item.species===species)||null);
     const current=recommendations.find((item:Obj)=>item.cycle_id===dailyCycle.cycle_id)||null;
     setFeedingRecommendation(current);
     if(current?.status==='approved')setDailyForm((previous:Obj)=>({...previous,recommendation_id:current.id,feed_id:current.feed_id}));
     setFeedForecast(forecast);
   }).catch(e=>setError(String(e)));
 },[dailyCycle,farmId,json,token]);
 const loadBase=useCallback(async()=>{if(!token)return;try{const [u,f,i,m]=await Promise.all([json('/auth/me'),json('/farms'),json('/finance/institutions'),json('/finance/institutions/mine')]);setUser(u);setProfileForm({phone_number:u.phone_number??'',sms_daily_records_enabled:u.sms_daily_records_enabled??false,sms_loan_reminders_enabled:u.sms_loan_reminders_enabled??false});setFarms(f);setInstitutions(i);setMine(m);setPendingInstitutions(u.is_platform_admin?await json('/finance/admin/institutions/pending'):[]);setFarmId(old=>f.some((x:Obj)=>x.id===old)?old:f[0]?.id??null);setInstitutionId(old=>m.some((x:Obj)=>x.id===old)?old:m[0]?.id??null);setError('')}catch(e){setError(String(e))}},[json,token]);
 useEffect(()=>{void loadBase()},[loadBase]);
 const loadFarm=useCallback(async()=>{if(!farmId||!token){setDashboard(null);setAnalytics(null);setCycles([]);setApplications([]);setLoans([]);setReminders([]);setDailyRecordStatus(null);return;}try{const [d,c,a,l,r,daily,metrics]=await Promise.all([json(`/farms/${farmId}/dashboard`),json(`/farms/${farmId}/dashboard/cycles`),json(`/farms/${farmId}/loan-applications`),json(`/farms/${farmId}/loans`),json(`/farms/${farmId}/loan-reminders`),json(`/farms/${farmId}/daily-record-status`),json(`/farms/${farmId}/dashboard/analytics`)]);setDashboard(d);setAnalytics(metrics);setCycles(c.cycles||[]);setApplications(a);setLoans(l);setReminders(r);setDailyRecordStatus(daily);setError('')}catch(e){setError(String(e))}},[farmId,json,token]);
 useEffect(()=>{void loadFarm()},[loadFarm]);
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
 const loadDailyRecords=useCallback(async()=>{
   if(!farmId||!token||!dailyCycle){
     setFeedingHistory([]);setMortalityHistory([]);setWaterHistory([]);setGrowthHistory([]);setFeedingCosts(null);setDailyEvidence([]);
     return;
   }
   const root=`/farms/${farmId}/units/${dailyCycle.unit_id}`;
   const cycle=`${root}/cycles/${dailyCycle.cycle_id}`;
   try{
     const [feeding,mortality,water,growth,costs,evidence]=await Promise.all([
       json(`${cycle}/feeding`),json(`${cycle}/mortality`),json(`${root}/water-quality`),
       json(`${cycle}/samples`),json(`${cycle}/feeding-costs`),json(`/farms/${farmId}/evidence?cycle_id=${dailyCycle.cycle_id}`)
     ]);
     setFeedingHistory(feeding);setMortalityHistory(mortality);setWaterHistory(water);
     setGrowthHistory(growth);setFeedingCosts(costs);setDailyEvidence(evidence);
   }catch(e){setError(String(e))}
 },[dailyCycle,farmId,json,token]);
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
     setFeedReceiptForm({occurred_on:localDate()});setReceiptVideo(null);await loadFeedProducts();setNotice('Feed receipt recorded with video evidence and stock added');
   }catch(error){setError(String(error))}finally{setBusy(false)}
 }
 async function confirmFeedingProfile(){
   if(!farmId||!dailyCycle)return;
   const species=dailyCycle.species?.toLowerCase().includes('catfish')?'catfish':'tilapia';
   setBusy(true);setError('');setNotice('');
   try{
     await api(`/farms/${farmId}/feeding-profiles/${species}/approve`,{method:'POST'});
     setFeedingProfile((previous:Obj|null)=>previous?{...previous,approved:true}:previous);
     setNotice('Advisory feeding profile confirmed for this farm.');
   }catch(error){setError(String(error))}finally{setBusy(false)}
 }
 async function estimateFeeding(){
   if(!farmId||!dailyCycle||!dailyForm.feed_id){setError('Select a feed product before calculating the ration.');return}
   setBusy(true);setError('');setNotice('');
   try{
     const result=await json(`/farms/${farmId}/units/${dailyCycle.unit_id}/cycles/${dailyCycle.cycle_id}/feeding-estimate`,{
       feed_id:Number(dailyForm.feed_id),
     });
     setFeedingRecommendation(result);
     setDailyForm((previous:Obj)=>({...previous,recommendation_id:null,session_number:''}));
     const forecast=await json(`/farms/${farmId}/feed-forecast`);
     setFeedForecast(forecast);
   }catch(error){setError(String(error))}finally{setBusy(false)}
 }
 async function approveFeedingRecommendation(){
   const recommendationId=feedingRecommendation?.recommendation_id??feedingRecommendation?.id;
   if(!farmId||!recommendationId)return;
   setBusy(true);setError('');setNotice('');
   try{
     const approved=await (await api(`/farms/${farmId}/feeding-recommendations/${recommendationId}/approve`,{method:'POST'})).json();
     setFeedingRecommendation(approved);
     setDailyForm((previous:Obj)=>({...previous,recommendation_id:approved.id,session_number:1}));
     setNotice('Feeding recommendation approved. Choose a session and record the actual feed quantity.');
     setFeedForecast(await json(`/farms/${farmId}/feed-forecast`));
   }catch(error){setError(String(error))}finally{setBusy(false)}
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
     payload={feed_id:Number(dailyForm.feed_id),quantity_kg:Number(dailyForm.quantity_kg),fed_on:dailyForm.recorded_on,notes:String(dailyForm.notes||'').trim()||null,
       ...(dailyForm.recommendation_id?{recommendation_id:Number(dailyForm.recommendation_id),session_number:Number(dailyForm.session_number)}:{})};
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
     uploaded=await uploadOperationEvidence(activity,unit,dailyVideo,dailyCycle.cycle_id);
   }catch(error){setError(String(error));setBusy(false);return}

   try{
     const query=new URLSearchParams({evidence_id:String(uploaded.id)});
     if(dailyTab==='water_quality')query.set('cycle_id',String(dailyCycle.cycle_id));
     await json(`${path}?${query.toString()}`,payload);
   }catch(error){
     try{
       await api(`/farms/${farmId}/evidence/${uploaded.id}`,{method:'DELETE'});
       setError(String(error));
     }catch(cleanupError){
       setEvidenceRetry({farm_id:farmId,id:uploaded.id,record_id:null});
       setError(`${String(error)} The video was not linked and could not be removed; use the cleanup button below.`);
     }
     setBusy(false);return;
   }

   setDailyForm({recorded_on:localDate(),observed_at:localDateTime()});
   setDailyVideo(null);setRecorderKey(key=>key+1);
   setNotice('Daily operation saved with its 15-second video evidence');
   await loadFarm();await loadDailyRecords();
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
 async function deleteDailyEvidence(item:Obj){
   if(!window.confirm('Delete this stored video evidence? This cannot be undone.'))return;
   setBusy(true);setError('');setNotice('');
   try{
     await api(`/farms/${item.farm_id}/evidence/${item.id}`,{method:'DELETE'});
     setNotice('Video evidence deleted');
     await loadDailyRecords();
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
       notes:String(stockForm.notes||'').trim()||null
     });
     setStockForm({stocked_on:new Date().toISOString().slice(0,10)});
     setStockVideo(null);
     setNotice('Fish stocking recorded with video evidence');
     await loadFarm();
   }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function closeStocking(cycle:Obj){
   const unit=units.find(u=>u.id===cycle.unit_id);
   if(!farmId||!unit||!window.confirm(`Close the ${cycle.species} stocking cycle in ${unit.name}? This will stop new mortality, sampling, and feeding records for this cycle.`))return;
   setBusy(true);setError('');setNotice('');
   try{
     await api(`/farms/${farmId}/units/${unit.id}/cycles/${cycle.cycle_id}/close`,{method:'POST'});
     setNotice('Stocking cycle closed successfully');
     await loadFarm();
   }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function archiveUnit(u:Obj){
   if(!farmId||!window.confirm(`Archive ${u.name}? Historical records will be retained.`))return;
   setBusy(true);setError('');setNotice('');
   try{await api(`/farms/${farmId}/units/${u.id}`,{method:'DELETE'});setUnits(await json(`/farms/${farmId}/units`));setUnitFormOpen(false);setNotice('Production unit archived successfully');await loadFarm()}
   catch(e){setError(String(e))}finally{setBusy(false)}
 }

 const loadLender=useCallback(async()=>{if(!institutionId||!token){setPortfolio(null);setLenderApps([]);setLenderLoans([]);return}try{const [a,l,p]=await Promise.all([json(`/finance/institutions/${institutionId}/applications`),json(`/finance/institutions/${institutionId}/loans`),json(`/finance/institutions/${institutionId}/portfolio`)]);setLenderApps(a);setLenderLoans(l);setPortfolio(p)}catch(e){setPortfolio(null);setLenderApps([]);setLenderLoans([]);setError(String(e))}},[institutionId,json,token]);
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
 async function authenticate(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{if(authMode==='register'){await json('/auth/register',{full_name:form.full_name,email:form.email,password:form.password});setAuthMode('login');setNotice('Account created. Sign in to continue.')}else{const result=await json('/auth/login',{email:form.email,password:form.password});sessionStorage.setItem('aquafarm_token',result.access_token);setToken(result.access_token);setNotice('')}}catch(e){setError(String(e))}finally{setBusy(false)}}
 function logout(){sessionStorage.removeItem('aquafarm_token');setToken('');setUser(null);setDashboard(null);setFarms([]);setMine([])}
 async function openApp(id:number){try{setSelectedApp(await json(`/finance/institutions/${institutionId}/applications/${id}`));setForm({});setCustomSchedule([{due_on:'',principal_ghs:'',interest_ghs:'',fees_ghs:''}]);setError('')}catch(e){setError(String(e))}}
 async function openLoan(id:number){try{const [l,s,t]=await Promise.all([json(`/finance/loans/${id}`),json(`/finance/loans/${id}/schedule`),json(`/finance/loans/${id}/transactions`)]);setSelectedLoan(l);setSchedule(s);setTransactions(t);setTransactionVideo(null);setTransactionEvidenceId(null);setTransactionRecorderKey(key=>key+1);setError('')}catch(e){setError(String(e))}}
 async function submitLoanApplication(e:React.FormEvent){
   e.preventDefault();if(!farmId)return;
   if(!applicationVideo){setError('Record the required new 15-second application video before submitting.');return}
   setBusy(true);setError('');setNotice('');
   try{
     let evidenceId=applicationEvidenceId;
     if(evidenceId===null){const uploaded=await uploadLoanEvidence('loan_application',applicationVideo);evidenceId=uploaded.id;setApplicationEvidenceId(evidenceId)}
     await json(`/farms/${farmId}/loan-applications`,{
       institution_id:Number(form.institution_id),requested_ghs:Number(form.requested_ghs),
       term_months:Number(form.term_months),purpose:form.purpose,evidence_id:evidenceId,
       monthly_other_income_ghs:form.monthly_other_income_ghs===''||form.monthly_other_income_ghs===undefined?null:Number(form.monthly_other_income_ghs),
       monthly_household_expenses_ghs:form.monthly_household_expenses_ghs===''||form.monthly_household_expenses_ghs===undefined?null:Number(form.monthly_household_expenses_ghs),
       monthly_external_debt_ghs:form.monthly_external_debt_ghs===''||form.monthly_external_debt_ghs===undefined?null:Number(form.monthly_external_debt_ghs),
       share_report:!!form.share_report,
     });
     setNotice('Loan application submitted with its 15-second video evidence.');
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
     commitment_fee_ghs:Number(form.commitment_fee_ghs||0),processing_fee_ghs:Number(form.processing_fee_ghs||0),
     repayment_frequency:frequency,first_due_date:firstDue,
     ...(custom?{custom_schedule:customSchedule.map(item=>({due_on:item.due_on,principal_ghs:item.principal_ghs,interest_ghs:item.interest_ghs,fees_ghs:item.fees_ghs||0}))}:{})};
   setBusy(true);setError('');setNotice('');
   try{await json(`/finance/institutions/${institutionId}/loans`,payload);setNotice('Loan account opened. Record each disbursement as funds are transferred.');setSelectedApp(null);setForm({});await Promise.all([loadFarm(),loadLender()])}
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
 async function download(path:string,filename:string){try{const r=await api(path);const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();URL.revokeObjectURL(url)}catch(e){setError(String(e))}}
 const nav:[Page,string,React.ReactNode][]=[['overview','Overview',<LayoutDashboard size={18}/>],['farms','My farms',<Sprout size={18}/>],['units','Production units',<Building2 size={18}/>],['production','Production',<Fish size={18}/>],['finance','Farmer finance',<Wallet size={18}/>],['reports','Reports',<FileDown size={18}/>],['lender','Institution portal',<Landmark size={18}/>]];
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
 const monthlyChartRows=(analytics?.finance?.monthly_cashflow||[]).map((row:Obj)=>({...row,recorded_expenses_ghs:(Number(row.manual_expenses_ghs)||0)+(Number(row.shared_allocations_ghs)||0)}));
 const reportDefinitions=[
  {kind:'summary',label:'Farm summary',description:'Key farm indicators and warnings',csv:'summary.csv'},
  {kind:'production',label:'Production and growth',description:'Cycles, samples, mortality and harvest forecasts',csv:'analytics/production.csv'},
  {kind:'sales',label:'Sales and cash flow',description:'Sales, receipts, receivables and monthly activity',csv:'analytics/sales.csv'},
  {kind:'inventory',label:'Feed inventory',description:'Purchases, consumption, balances and feed forecast',csv:'analytics/inventory.csv'},
  {kind:'financial',label:'Financial analysis',description:'Recorded costs, cost per kg and recommended prices',csv:'analytics/financial.csv'},
  {kind:'bank-ready',label:'Investment-ready report',description:'Production, sales, costs, receivables and evidence caveats',csv:'bank-ready.csv'},
 ];
 if(!token)return <div className="authwrap"><div className="authcard"><div className="brand dark"><Waves size={30}/><span>AquaFarm <b>Manager Ghana</b></span></div><h1>{authMode==='login'?'Welcome back':'Create an account'}</h1><p>Farm operations and agricultural finance, in one place.</p>{error&&<div className="alert">{error}</div>}{notice&&<div className="success">{notice}</div>}<form onSubmit={authenticate}>{authMode==='register'&&field('full_name','Full name','text',{required:true,minLength:2})}{field('email','Email','email',{required:true})}{field('password','Password','password',{required:true,minLength:authMode==='register'?12:1})}<button className="primary" disabled={busy}>{busy?'Please wait...':authMode==='login'?'Sign in':'Register'}</button></form><button className="textbutton" onClick={()=>{setAuthMode(authMode==='login'?'register':'login');setError('');setForm({})}}>{authMode==='login'?'New here? Create account':'Already registered? Sign in'}</button><small>Development portal · Do not use real banking data</small></div></div>;
 return <div className="shell"><aside className="sidebar"><div className="brand"><Waves size={29}/><span>AquaFarm <b>Manager Ghana</b></span></div><div className="navlabel">WORKSPACE</div><nav>{nav.map(([key,label,ic])=><button key={key} className={page===key?'active':''} onClick={()=>{setPage(key);setForm({});setSelectedApp(null);setSelectedLoan(null);setNotice('')}}>{ic}{label}</button>)}</nav><div className="sidefoot"><div className="usericon">{user?.full_name?.slice(0,1)||'U'}</div><div className="who"><b>{user?.full_name||'Account'}</b><small>{user?.email||''}</small></div><button aria-label="Sign out" title="Sign out" onClick={logout}><LogOut size={18}/></button></div></aside><main className="main"><header><div><span className="eyebrow">AQUAFARM / {page.toUpperCase()}</span><h1>{nav.find(x=>x[0]===page)?.[1]}</h1></div><div className="headeractions">{page!=='lender'&&<select aria-label="Selected farm" value={farmId??''} onChange={e=>setFarmId(Number(e.target.value))}>{farms.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}{!farms.length&&<option value="">No farms</option>}</select>}<button className="outline" onClick={()=>{void loadBase();void loadFarm();void loadUnits();void loadLender()}}><RefreshCw size={16}/> Refresh</button></div></header>{error&&<div className="alert"><AlertTriangle size={17}/>{error}<button onClick={()=>setError('')}>×</button></div>}{page!=='finance'&&reminders.some(r=>r.status==='overdue')&&<div className="alert" role="status"><AlertTriangle size={17}/>{reminders.filter(r=>r.status==='overdue').length} loan instalment{reminders.filter(r=>r.status==='overdue').length===1?' is':'s are'} overdue. <button className="outline small" onClick={()=>setPage('finance')}>View repayments</button></div>}{notice&&<div className="success"><CheckCircle2 size={17}/>{notice}</div>}
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
 {page==='overview'&&dailyRecordStatus?.cycles?.some((cycle:Obj)=>cycle.is_overdue)&&<div className="alert daily-record-alert" role="alert"><AlertTriangle size={18}/><span>Feeding record missing after {dailyRecordStatus.reminder_time} for {dailyRecordStatus.cycles.filter((cycle:Obj)=>cycle.is_overdue).map((cycle:Obj)=>`${cycle.unit_name} (${cycle.species})`).join(', ')}.</span><button type="button" className="flag-link" onClick={()=>setPage('production')}>Review records</button></div>}
 {page==='overview'&&<section className="panel">
  <h2>Daily SMS reminder settings</h2><p className="muted">A feeding record is expected for each active cycle every day. Missing records are flagged red after {dailyRecordStatus?.reminder_time||'08:00'} Africa/Accra time.</p>
  <form className="farmform" onSubmit={saveSmsContact}>
   <label className="field"><span>Mobile number (international format, e.g. +233…)</span><input type="tel" autoComplete="tel" pattern="\+[1-9]\d{7,14}" required={Boolean(profileForm.sms_daily_records_enabled||profileForm.sms_loan_reminders_enabled)} value={profileForm.phone_number??''} onChange={e=>setProfileForm({...profileForm,phone_number:e.target.value})}/></label>
   <label className="consent"><input type="checkbox" checked={Boolean(profileForm.sms_daily_records_enabled)} onChange={e=>setProfileForm({...profileForm,sms_daily_records_enabled:e.target.checked})}/> I agree to receive one SMS reminder each morning if an active cycle has no feeding record for the day.</label>
   <label className="consent"><input type="checkbox" checked={Boolean(profileForm.sms_loan_reminders_enabled)} onChange={e=>setProfileForm({...profileForm,sms_loan_reminders_enabled:e.target.checked})}/> I agree to receive SMS reminders 7 days before an instalment is due and daily while it is overdue.</label>
   <button className="outline" disabled={busy}>Save reminder settings</button>
  </form>
  <p className="footnote">SMS delivery requires Hubtel credentials configured by the operator. You can disable reminders here at any time.</p>
 </section>}
 {page==='overview'&&<>
  {!farms.length&&<div className="infobox" style={{marginBottom:18}}>No farms registered under this account. <button className="outline" onClick={()=>{setPage('farms');newFarm()}}>Register your first farm</button></div>}
  <div className="statgrid">
   <Stat label="Total farms" value={num(farms.length)} sub="Owned farms"/>
   <Stat label="Active production units" value={num(analytics?.summary?.active_units)} sub="Selected farm"/>
   <Stat label="Fish stocked" value={num(analytics?.summary?.stocked_fish)} sub="Active cycles"/>
   <Stat label="Estimated surviving fish" value={num(analytics?.summary?.estimated_live_fish)} sub="Record-derived estimate"/>
   <Stat label="Estimated biomass" value={`${num(analytics?.summary?.estimated_biomass_kg)} kg`} sub="Sample-based estimate"/>
   <Stat label="Expected harvest" value={analytics?.summary?.expected_harvest_kg==null?'Not available':`${num(analytics.summary.expected_harvest_kg)} kg`} sub="Forecast for planned active cycles"/>
  </div>
  <div className="twocol">
   <section className="panel"><h2>Production overview</h2><div className="metricrows">
    <Line label="Active cycles" value={num(analytics?.summary?.active_cycles)}/>
    <Line label="Harvest available" value={`${num(dashboard?.sales?.available_harvest_kg)} kg`}/>
    <Line label="Upcoming harvest forecasts" value={num(analytics?.summary?.upcoming_harvest_count)}/>
    <Line label="Mortality recorded" value={`${num(analytics?.summary?.mortality_count)} fish`}/>
   </div></section>
   <section className="panel"><h2>Financial and inventory overview</h2><div className="metricrows">
    <Line label="Feed remaining" value={`${num(analytics?.summary?.remaining_feed_kg)} kg`}/>
    <Line label="Feed consumed" value={`${num(dashboard?.feed?.consumed_kg)} kg`}/>
    <Line label="Invoiced sales" value={money(dashboard?.sales?.invoiced_revenue_ghs)}/>
    <Line label="Payments received" value={money(analytics?.summary?.payments_received_ghs)}/>
    <Line label="Outstanding customer credit" value={money(analytics?.summary?.outstanding_customer_credit_ghs)}/>
    <Line label="Recorded costs to date" value={money(dashboard?.costs?.recorded_costs_to_date_ghs)}/>
   </div></section>
  </div>
  <div className="chart-grid">
   <TrendChart title="Fish growth history · average sample weight" points={analytics?.production?.growth_trends||[]} dateKey="sampled_on" valueKey="average_weight_g" seriesKey="unit_name" unit=" g"/>
   <BarChart title="Monthly cash activity · GHS" data={monthlyChartRows} labelKey="month" series={[{key:'payments_received_ghs',label:'Payments received',color:'#168064'},{key:'feed_purchase_cash_outflow_ghs',label:'Feed purchases',color:'#e5a84b'},{key:'recorded_expenses_ghs',label:'Other recorded expenses',color:'#5676b8'}]}/>
   <BarChart title="Feed stock by product" data={analytics?.feed?.inventory||[]} labelKey="feed_name" series={[{key:'remaining_stock_kg',label:'Remaining kg',color:'#168064'}]}/>
   <BarChart title="Estimated biomass by production unit" data={analytics?.production?.unit_comparisons||[]} labelKey="unit_name" series={[{key:'estimated_biomass_kg',label:'Biomass kg',color:'#5676b8'}]}/>
   <TrendChart title="Dissolved oxygen history" points={analytics?.water_quality?.history||[]} dateKey="observed_at" valueKey="dissolved_oxygen_mg_l" seriesKey="unit_name" unit=" mg/L"/>
  </div>
  <div className="twocol">
   <section className="panel"><h2>Production-unit comparison</h2><div className="tablewrap"><table><thead><tr><th>Unit</th><th>Type</th><th>Live fish</th><th>Biomass</th><th>Mortality</th><th>Indicative FCR</th></tr></thead><tbody>{(analytics?.production?.unit_comparisons||[]).map((unit:Obj)=><tr key={unit.unit_id}><td>{unit.unit_name}</td><td>{unit.unit_type}</td><td>{num(unit.estimated_live_fish)}</td><td>{num(unit.estimated_biomass_kg)} kg</td><td>{num(unit.mortality_count)} ({unit.mortality_pct==null?'—':`${num(unit.mortality_pct)}%`})</td><td>{unit.indicative_fcr==null?'—':num(unit.indicative_fcr)}</td></tr>)}</tbody></table>{!analytics?.production?.unit_comparisons?.length&&<p className="empty">No production units recorded.</p>}</div></section>
   <section className="panel"><h2>Latest water quality by unit</h2><div className="tablewrap"><table><thead><tr><th>Unit</th><th>Observed</th><th>Temp °C</th><th>O₂ mg/L</th><th>pH</th><th>Ammonia</th><th>Nitrite</th></tr></thead><tbody>{(analytics?.water_quality?.latest_by_unit||[]).map((reading:Obj)=><tr key={reading.unit_id}><td>{reading.unit_name}</td><td>{new Date(reading.observed_at).toLocaleString()}</td><td>{reading.temperature_c??'—'}</td><td>{reading.dissolved_oxygen_mg_l??'—'}</td><td>{reading.ph??'—'}</td><td>{reading.ammonia_mg_l??'—'}</td><td>{reading.nitrite_mg_l??'—'}</td></tr>)}</tbody></table>{!analytics?.water_quality?.latest_by_unit?.length&&<p className="empty">No water-quality measurements recorded.</p>}</div></section>
  </div>
  <section className="panel"><h2>Feed requirements · next 30 days</h2><p className="muted">{analytics?.feed?.forecast?.basis||'Based on approved daily feed recommendations.'}</p><div className="tablewrap"><table><thead><tr><th>Feed</th><th>Approved daily demand</th><th>Forecast use</th><th>Stock after forecast</th><th>Status</th></tr></thead><tbody>{(analytics?.feed?.forecast?.feeds||[]).map((feed:Obj)=><tr key={feed.feed_id}><td>{feed.feed_name}</td><td>{num(feed.approved_daily_demand_kg)} kg/day</td><td>{num(feed.expected_usage_kg)} kg</td><td>{num(feed.projected_stock_kg)} kg</td><td>{feed.shortage_expected?'Shortage expected':'No shortage projected'}</td></tr>)}</tbody></table>{!analytics?.feed?.forecast?.feeds?.length&&<p className="empty">No feed inventory products recorded.</p>}</div>{analytics?.feed?.forecast?.cycles_without_approved_recommendation?.length>0&&<p className="footnote">Feed demand may be understated: {num(analytics?.feed?.forecast?.cycles_without_approved_recommendation?.length)} active cycle(s) have no approved feeding recommendation.</p>}</section>
  <section className="panel"><h2>Upcoming harvest forecasts</h2>{(analytics?.production?.upcoming_harvests||[]).length?(analytics?.production?.upcoming_harvests||[]).map((harvest:Obj)=><div className="item" key={harvest.cycle_id}><b>{harvest.unit_name} · {harvest.species} · {num(harvest.expected_harvest_kg)} kg estimated</b><small>Target date: {harvest.expected_harvest_on} · {harvest.date_basis==='linear_projection_from_last_two_samples'?'Projected from the latest two fish samples':'Target weight reached; confirm actual harvest in the records.'}</small></div>):<p className="empty">No upcoming dates can be forecast. A linked plan and sufficient positive sample-growth history are needed.</p>}</section>
  {analytics?.warnings?.map((warning:string,index:number)=><p className="footnote" key={index}>{warning}</p>)}
 </>}
 {page==='production'&&<>
  {dailyRecordStatus?.cycles?.some((cycle:Obj)=>cycle.is_overdue)&&<div className="alert daily-record-alert" role="alert"><AlertTriangle size={18}/><span>Missing today's feeding record: {dailyRecordStatus.cycles.filter((cycle:Obj)=>cycle.is_overdue).map((cycle:Obj)=>`${cycle.unit_name} (${cycle.species})`).join(', ')}.</span></div>}
 <section className="panel">
  <h2>Record fish stocking</h2>
  {!farmId?<div className="infobox">Select or register a farm before recording fish stocking.</div>:!units.length?<div className="infobox">Add a production unit before stocking fish.</div>:<form className="farmform" onSubmit={stockFish}>
   <label className="field"><span>Production unit</span><select required value={stockForm.unit_id??''} onChange={e=>setStockForm({...stockForm,unit_id:Number(e.target.value)})}><option value="">Choose an available unit...</option>{units.map(u=>{const occupied=cycles.some(c=>c.unit_id===u.id&&c.status==='active');return <option key={u.id} value={u.id} disabled={occupied}>{u.name}{occupied?' · active cycle':''}</option>})}</select></label>
   <label className="field"><span>Species</span><select required value={stockForm.species??'Tilapia'} onChange={e=>setStockForm({...stockForm,species:e.target.value})}><option value="Catfish">Catfish</option><option value="Tilapia">Tilapia</option></select></label>
   <label className="field"><span>Number of fish stocked</span><input required type="number" min="1" step="1" value={stockForm.stocked_count??''} onChange={e=>setStockForm({...stockForm,stocked_count:e.target.value})}/></label>
   <label className="field"><span>Initial average weight (g per fish)</span><input required type="number" min="0.001" step="any" value={stockForm.initial_average_weight_g??''} onChange={e=>setStockForm({...stockForm,initial_average_weight_g:e.target.value})}/></label>
   <label className="field"><span>Stocking date</span><input required type="date" max={new Date().toISOString().slice(0,10)} value={stockForm.stocked_on??''} onChange={e=>setStockForm({...stockForm,stocked_on:e.target.value})}/></label>
   <label className="field"><span>Notes (optional)</span><textarea maxLength={2000} value={stockForm.notes??''} onChange={e=>setStockForm({...stockForm,notes:e.target.value})}/></label>
   <EvidenceRecorder activity="stocking" unit={units.find(u=>u.id===Number(stockForm.unit_id))} getChallenge={getEvidenceChallenge} onChange={setStockVideo}/>
   <button className="primary" disabled={busy||!stockVideo||!units.some(u=>u.id===Number(stockForm.unit_id)&&!cycles.some(c=>c.unit_id===u.id&&c.status==='active'))}>{busy?'Saving...':'Record stocking'}</button>
  </form>}
 </section>
 <section className="panel"><div className="between"><h2>Stocking cycles</h2><div className="farmactions" role="group" aria-label="Filter stocking cycles">{(['active','completed','all'] as const).map(filter=><button key={filter} type="button" className={`outline small${cycleFilter===filter?' active':''}`} aria-pressed={cycleFilter===filter} onClick={()=>setCycleFilter(filter)}>{filter==='all'?'All':filter==='active'?'Active':'Completed'}</button>)}</div></div><div className="tablewrap"><table><thead><tr><th>Unit</th><th>Species</th><th>Stocking date</th><th>Status</th><th>Stocked</th><th>Estimated live</th><th>Mortality</th><th>Avg weight</th><th>Biomass</th><th></th></tr></thead><tbody>{cycles.filter(c=>cycleFilter==='all'||c.status===(cycleFilter==='active'?'active':'closed')).map(c=><tr key={c.cycle_id}><td>{c.unit_name}</td><td>{c.species}</td><td>{c.stocked_on}</td><td><span className="pill">{c.status==='closed'?'completed':'active'}</span></td><td>{num(c.stocked_count)}</td><td>{num(c.estimated_live_count)}</td><td>{num(c.mortality_count)} ({num(c.mortality_pct)}%)</td><td>{num(c.latest_average_weight_g)} g</td><td>{num(c.estimated_biomass_kg)} kg</td><td>{c.status==='active'&&<button className="outline danger small" disabled={busy} onClick={()=>void closeStocking(c)}>Close cycle</button>}</td></tr>)}</tbody></table>{!cycles.length?<p className="empty">No stocking cycles yet. Record the first batch above.</p>:!cycles.some(c=>cycleFilter==='all'||c.status===(cycleFilter==='active'?'active':'closed'))&&<p className="empty">No {cycleFilter} cycles for this farm.</p>}</div></section>
 <section className="panel">
  <details className="feed-inventory"><summary>Feed inventory · products, receipts and purchase costs</summary>
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
 </section>
 <section className="panel daily-operations">
  <h2>Daily farm operations</h2>
  <p className="muted">Record daily activity against an active stocking cycle. Every entry requires a 15-second video saved privately with the record.</p>
  {!activeCycles.length?<div className="infobox">Record fish stocking and keep a cycle active before entering feeding, mortality, water-quality, or growth records.</div>:dailyCycle?<>
   <label className="field daily-cycle-select"><span>Active stocking cycle · production unit</span><select value={dailyCycleId} onChange={e=>setDailyCycleId(Number(e.target.value))}>{activeCycles.map(c=><option key={c.cycle_id} value={c.cycle_id}>{c.unit_name} · {c.species} · cycle #{c.cycle_id}</option>)}</select></label>
   {dailyCycle&&<div className="daily-cycle-summary"><span><b>Estimated live fish:</b> {num(dailyCycle.estimated_live_count)}</span><span><b>Biomass:</b> {num(dailyCycle.estimated_biomass_kg)} kg</span><span><b>Cumulative mortality:</b> {num(dailyCycle.mortality_count)} fish ({num(dailyCycle.mortality_pct)}%)</span></div>}
   <div className="daily-tabs" role="tablist" aria-label="Daily operation type">{([
     ['feeding','Feeding'],['mortality','Mortality'],['water_quality','Water quality'],['growth','Fish growth']
   ] as const).map(([key,label])=><button type="button" role="tab" aria-selected={dailyTab===key} className={`outline small${dailyTab===key?' selected':''}`} key={key} onClick={()=>setDailyTab(key)}>{label}</button>)}</div>
   {evidenceRetry&&<div className="alert evidence-retry"><span>Video evidence #{evidenceRetry.id} still needs attention.</span><button type="button" className="outline small" disabled={busy} onClick={()=>void resolveEvidenceIssue()}>{evidenceRetry.record_id?'Retry video link':'Delete unlinked video'}</button></div>}
   <form className="farmform daily-form" onSubmit={saveDailyOperation}>
    {dailyTab==='feeding'&&<>
     <label className="field"><span>Feed type · inventory balance</span><select required value={dailyForm.feed_id??''} onChange={e=>setDailyForm({...dailyForm,feed_id:Number(e.target.value)})}><option value="">Select feed...</option>{feedProducts.map(feed=><option key={feed.id} value={feed.id} disabled={Number(feed.stock_kg)<=0}>{feed.name} · {num(feed.stock_kg)} kg available</option>)}</select></label>
     {!feedProducts.length&&<div className="infobox">No feed products are registered for this farm yet. Add a feed product and receive stock into inventory before recording feeding.</div>}
     <label className="field"><span>Feed quantity (kg)</span><input required type="number" min="0.001" step="any" value={dailyForm.quantity_kg??''} onChange={e=>setDailyForm({...dailyForm,quantity_kg:e.target.value})}/></label>
     <label className="field"><span>Feeding date</span><input required type="date" max={localDate()} min={dailyCycle.stocked_on} value={dailyForm.recorded_on??''} onChange={e=>setDailyForm({...dailyForm,recorded_on:e.target.value})}/></label>
     <p className="muted">Inventory is automatically reduced when saved. Feeding cost is estimated from feed purchase receipts; it is not an independently entered expense.</p>
     {!feedingProfile?.approved&&<div className="infobox">The {dailyCycle.species} feeding profile is an advisory starter profile, not certified local guidance. The farm owner must confirm it before calculating a ration. <button type="button" className="outline small" disabled={busy} onClick={()=>void confirmFeedingProfile()}>Confirm advisory profile</button></div>}
     {feedingProfile?.approved&&<button type="button" className="outline" disabled={busy||!dailyForm.feed_id} onClick={()=>void estimateFeeding()}>Calculate advisory daily ration</button>}
     {feedingRecommendation&&<div className={feedingRecommendation.status==='suspended'?'alert':'infobox'}>
       <b>Feeding estimate · {feedingRecommendation.status}</b>
       <p>Biomass: {num(feedingRecommendation.estimated_biomass_kg)} kg · Daily ration: {num(feedingRecommendation.daily_ration_kg??feedingRecommendation.estimated_daily_feed_kg)} kg · {num(feedingRecommendation.session_count)} sessions/day · {num(feedingRecommendation.session_ration_kg??feedingRecommendation.feed_per_session_kg)} kg/session</p>
       {(feedingRecommendation.warnings||[]).map((warning:string,index:number)=><p key={index}>{warning}</p>)}
       {feedingRecommendation.status==='pending_approval'&&<button type="button" className="outline small" disabled={busy} onClick={()=>void approveFeedingRecommendation()}>Approve recommendation</button>}
       {feedingRecommendation.status==='approved'&&<label className="field"><span>Approved session to record</span><select required value={dailyForm.session_number??''} onChange={e=>setDailyForm({...dailyForm,session_number:Number(e.target.value)})}><option value="">Select session...</option>{Array.from({length:Number(feedingRecommendation.session_count||0)},(_,index)=><option key={index+1} value={index+1}>Session {index+1} · {num(feedingRecommendation.session_ration_kg)} kg recommended</option>)}</select></label>}
     </div>}
     {feedForecast?.feeds?.find((item:Obj)=>item.feed_id===Number(dailyForm.feed_id))&&<p className="muted">30-day feed forecast: {num(feedForecast.feeds.find((item:Obj)=>item.feed_id===Number(dailyForm.feed_id)).expected_usage_kg)} kg projected use; {feedForecast.feeds.find((item:Obj)=>item.feed_id===Number(dailyForm.feed_id)).shortage_expected?'shortage expected':'current stock covers this estimate'}.</p>}
    </>}
    {dailyTab==='mortality'&&<>
     <label className="field"><span>Dead fish count</span><input required type="number" min="1" step="1" max={dailyCycle.estimated_live_count} value={dailyForm.dead_count??''} onChange={e=>setDailyForm({...dailyForm,dead_count:e.target.value})}/></label>
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
    <label className="field"><span>Notes (optional)</span><textarea maxLength={1000} value={dailyForm.notes??''} onChange={e=>setDailyForm({...dailyForm,notes:e.target.value})}/></label>
    <EvidenceRecorder key={`${dailyTab}-${dailyCycleId}-${recorderKey}`} activity={dailyTab} unit={units.find(unit=>unit.id===dailyCycle.unit_id)} getChallenge={getEvidenceChallenge} onChange={setDailyVideo}/>
    <button className="primary" disabled={busy||!dailyVideo||!dailyCycle||Boolean(evidenceRetry)}>{busy?'Saving record and video...':'Save operation record'}</button>
   </form>
   {dailyTab==='feeding'&&<div className="metricrows daily-cost"><Line label="Indicative feed cost to date" value={feedingCosts?.total_indicative_cost_ghs==null?'Not available; record priced feed receipts':money(feedingCosts.total_indicative_cost_ghs)}/></div>}
   <section className="daily-history"><h3>{dailyTab==='feeding'?'Feeding history':dailyTab==='mortality'?'Mortality history':dailyTab==='water_quality'?'Water-quality history':'Growth samples'}</h3>
    {dailyTab==='feeding'&&<div className="tablewrap"><table><thead><tr><th>Date</th><th>Feed</th><th>Quantity</th><th>Indicative cost</th></tr></thead><tbody>{feedingHistory.map(row=>{const cost=feedingCosts?.lines?.find((line:Obj)=>line.feed_id===row.feed_id);return <tr key={row.id}><td>{row.occurred_on}</td><td>{feedProducts.find(f=>f.id===row.feed_id)?.name||`Feed #${row.feed_id}`}</td><td>{num(Math.abs(row.quantity_delta_kg))} kg</td><td>{cost?.indicative_cost_ghs==null?'—':money(cost.indicative_cost_ghs)}</td></tr>})}</tbody></table>{!feedingHistory.length&&<p className="empty">No feeding records for this cycle.</p>}</div>}
    {dailyTab==='mortality'&&<div className="tablewrap"><table><thead><tr><th>Date</th><th>Dead fish</th><th>Cause</th><th>Notes</th></tr></thead><tbody>{mortalityHistory.map(row=><tr key={row.id}><td>{row.observed_on}</td><td>{num(row.dead_count)}</td><td>{row.cause||'—'}</td><td>{row.notes||'—'}</td></tr>)}</tbody></table>{!mortalityHistory.length&&<p className="empty">No mortality records for this cycle.</p>}</div>}
    {dailyTab==='water_quality'&&<div className="tablewrap"><table><thead><tr><th>Observed</th><th>Temp °C</th><th>O₂ mg/L</th><th>pH</th><th>Ammonia</th><th>Nitrite</th></tr></thead><tbody>{waterHistory.map(row=><tr key={row.id}><td>{new Date(row.observed_at).toLocaleString()}</td><td>{row.temperature_c??'—'}</td><td>{row.dissolved_oxygen_mg_l??'—'}</td><td>{row.ph??'—'}</td><td>{row.ammonia_mg_l??'—'}</td><td>{row.nitrite_mg_l??'—'}</td></tr>)}</tbody></table>{!waterHistory.length&&<p className="empty">No water-quality records for this unit.</p>}</div>}
    {dailyTab==='growth'&&<div className="tablewrap"><table><thead><tr><th>Date</th><th>Sample count</th><th>Average weight</th></tr></thead><tbody>{growthHistory.map(row=><tr key={row.id}><td>{row.sampled_on}</td><td>{num(row.sample_count)}</td><td>{num(row.average_weight_g)} g</td></tr>)}</tbody></table>{!growthHistory.length&&<p className="empty">No growth samples for this cycle.</p>}</div>}
    <h3 className="spaced">Stored video evidence</h3>
    {dailyEvidence.length?dailyEvidence.map(item=><div className="item evidence-row" key={item.id}><div><b>{item.record_type.replace('_',' ')} · {item.record_id?`Record #${item.record_id}`:'Unlinked evidence'}</b><small>{new Date(item.created_at).toLocaleString()} · {num(item.size_bytes/1024/1024)} MB · {item.duration_seconds}s · {item.verification_status} · GPS {item.geofence_status}</small></div><div className="farmactions"><button type="button" className="outline small" onClick={()=>void download(`/farms/${item.farm_id}/evidence/${item.id}/video`,`aquafarm_evidence_${item.id}.${item.media_type==='video/mp4'?'mp4':'webm'}`)}>Download</button>{item.record_id?<span className="pill">Record locked</span>:<button type="button" className="outline danger small" disabled={busy} onClick={()=>void deleteDailyEvidence(item)}>Remove unlinked</button>}</div></div>):<p className="empty">No video evidence saved for this cycle.</p>}
   </section>
  </>:<div className="infobox">Loading active stocking cycle...</div>}
 </section>
 </>}
 {page==='finance'&&<>
  <div className="twocol">
   <section className="panel">
    <h2>Apply for agricultural financing</h2><p className="muted">A fixed farm performance summary is shared only with the institution you choose.</p>
    <form onSubmit={submitLoanApplication}>
     {dropdown('institution_id','Verified financial institution',institutions.map(i=>({value:i.id,label:i.name})))}
     {field('requested_ghs','Amount requested (GH₵)','number',{required:true,min:0.01,step:0.01})}
     {field('term_months','Term (months)','number',{required:true,min:1,max:240})}
     <label className="field"><span>Loan purpose</span><textarea required minLength={10} value={form.purpose||''} onChange={e=>setForm({...form,purpose:e.target.value})}/></label>
     <h3>Optional monthly repayment information</h3><p className="muted">Use your best estimate in GH₵. Leave unknown amounts blank; blanks are not treated as zero.</p>
     {field('monthly_other_income_ghs','Other monthly income (GH₵)','number',{min:0,step:0.01})}
     {field('monthly_household_expenses_ghs','Monthly household expenses (GH₵)','number',{min:0,step:0.01})}
     {field('monthly_external_debt_ghs','Monthly payments on debts outside AquaFarm (GH₵)','number',{min:0,step:0.01})}
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
  <section className="panel"><h2>Loan applications</h2><div className="tablewrap"><table><thead><tr><th>Application</th><th>Institution</th><th>Requested</th><th>Term</th><th>Status</th></tr></thead><tbody>{applications.map(a=><tr key={a.id}><td>#{a.id}</td><td>{institutions.find(i=>i.id===a.institution_id)?.name||`Institution #${a.institution_id}`}</td><td>{money(a.requested_ghs)}</td><td>{a.term_months} months</td><td><span className="pill">{a.status}</span></td></tr>)}</tbody></table>{!applications.length&&<p className="empty">No loan applications submitted.</p>}</div></section>
 </>}
 {page==='reports'&&<>
  <section className="panel"><h2>Automatically generated farm reports</h2><p className="muted">Reports are assembled from your recorded farm data; no report narrative or manual calculations are required. CSV files open in spreadsheet applications. Excel reports include separate analysis sheets.</p>
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
   <div className="reportgrid">{reportDefinitions.map(report=><div className="reportcard" key={report.kind}><FileDown size={25}/><b>{report.label}</b><p>{report.description}</p>
    {report.csv&&<button className="outline" disabled={!farmId} onClick={()=>void download(`/farms/${farmId}/reports/${report.csv}`,`aquafarm_${report.kind}_${farmId}.csv`)}>Download CSV</button>}
    <button className="primary" disabled={!farmId} onClick={()=>void download(`/farms/${farmId}/reports/${report.kind}.xlsx`,`aquafarm_${report.kind}_${farmId}.xlsx`)}>Download Excel</button>
   </div>)}</div>
   <div className="chart-grid">
    <TrendChart title="Growth samples" points={analytics?.production?.growth_trends||[]} dateKey="sampled_on" valueKey="average_weight_g" seriesKey="unit_name" unit=" g"/>
    <BarChart title="Monthly income and recorded outflows" data={monthlyChartRows} labelKey="month" series={[{key:'payments_received_ghs',label:'Payments received',color:'#168064'},{key:'feed_purchase_cash_outflow_ghs',label:'Feed purchases',color:'#e5a84b'},{key:'recorded_expenses_ghs',label:'Recorded expenses',color:'#5676b8'}]}/>
   </div>
   <label className="field report-search"><span>Search generated report data</span><input type="search" value={reportSearch} onChange={event=>setReportSearch(event.target.value)} placeholder="Search farm metrics, cycles, inventory or dates"/></label>
   <div className="tablewrap"><table><thead><tr><th>Report section</th><th>Record</th><th>Generated value</th></tr></thead><tbody>{filteredReportRows.slice(0,100).map((row,index)=><tr key={`${row.section}-${row.record}-${index}`}><td>{row.section}</td><td>{row.record}</td><td>{row.value}</td></tr>)}</tbody></table>
    {!filteredReportRows.length&&<p className="empty">{analytics?'No generated records match this search.':'Select a farm to generate report data.'}</p>}
    {filteredReportRows.length>100&&<p className="muted">Showing the first 100 matches. Download Excel for the complete report.</p>}
   </div>
   <div className="infobox">Investment report data is record-derived and may be incomplete or unverified. Forecast dates, harvest weights, FCR and pricing are estimates; this report is not an audited financial statement, bank certification or credit decision.</div>
  </section>
 </>}
 {page==='lender'&&<>
  <div className="twocol">
   <section className="panel">
    <h2>My financial institutions</h2>
    {mine.length>0?<label className="field"><span>Institution workspace</span><select value={institutionId??''} onChange={e=>{setInstitutionId(Number(e.target.value));setSelectedApp(null);setSelectedLoan(null)}}>{mine.map(i=><option key={i.id} value={i.id}>{i.name} ({i.status})</option>)}</select></label>:<p className="empty">No institution memberships found.</p>}
    <h3>Register an institution</h3><form onSubmit={e=>formSubmit(e,'/finance/institutions',{name:form.name,institution_type:form.institution_type,account_number:form.account_number},()=>setForm({}))}>{field('name','Institution name','text',{required:true,minLength:3})}{dropdown('institution_type','Institution type',[{value:'bank',label:'Bank'},{value:'rural_bank',label:'Rural bank'},{value:'microfinance',label:'Microfinance'},{value:'credit_union',label:'Credit union'},{value:'other',label:'Other'}])}{field('account_number','Account number','text',{required:true,minLength:3})}<button className="primary" disabled={busy}><Building2 size={17}/> Register institution</button></form>
    {user?.is_platform_admin&&<><h3>Institution verification queue</h3>{pendingInstitutions.map(institution=><div className="item" key={institution.id}><b>{institution.name}</b><small>{institution.institution_type} · Account number: {institution.account_number}</small><div className="row-actions"><button type="button" className="primary small" disabled={busy} onClick={()=>void submit(`/finance/institutions/${institution.id}/verify`,{})}>Approve</button><button type="button" className="outline small" disabled={busy} onClick={()=>{if(window.confirm(`Reject ${institution.name}?`))void submit(`/finance/institutions/${institution.id}/reject`,{})}}>Reject</button></div></div>)}{!pendingInstitutions.length&&<p className="empty">No institution registrations are waiting for approval.</p>}</>}
    <p className="footnote">New institutions require platform administrator verification before lender operations.</p>
    {mine.some(i=>i.id===institutionId&&i.status==='verified'&&i.role==='owner')&&<><h3>Manage institution staff</h3><form onSubmit={e=>formSubmit(e,`/finance/institutions/${institutionId}/members`,{user_email:form.staff_email,role:form.staff_role},()=>setForm({}))}>
     {field('staff_email','Registered staff email','email',{required:true})}
     <label className="field"><span>Access role</span><select required value={form.staff_role??''} onChange={e=>setForm({...form,staff_role:e.target.value})}><option value="">Choose role...</option><option value="officer">Officer · disbursements and repayments</option><option value="reviewer">Reviewer · appraisals and loan setup</option></select></label>
     <button className="outline" disabled={busy}>Add staff member</button>
    </form><p className="footnote">Staff must already have an AquaFarm account. Owners manage staff; roles restrict appraisal and transaction actions.</p></>}
   </section>
   <section className="panel">
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
   </section>
  </div>
  <section className="panel"><h2>Applications for appraisal</h2><div className="tablewrap"><table><thead><tr><th>ID</th><th>Farm ID</th><th>Requested</th><th>Purpose</th><th>Status</th><th></th></tr></thead><tbody>{lenderApps.map(a=><tr key={a.id}><td>#{a.id}</td><td>#{a.farm_id}</td><td>{money(a.requested_ghs)}</td><td>{a.purpose}</td><td><span className="pill">{a.status}</span></td><td><button className="outline small" onClick={()=>void openApp(a.id)}>{a.status==='approved'?'Open loan':'Review'}</button></td></tr>)}</tbody></table>{!lenderApps.length&&<p className="empty">No applications available.</p>}</div></section>
  {selectedApp&&<section className="panel">
   <div className="between"><h2>Application #{selectedApp.id}</h2><button className="textbutton" onClick={()=>setSelectedApp(null)}>Close</button></div>
   <p><b>Purpose:</b> {selectedApp.purpose}</p><p><b>Requested:</b> {money(selectedApp.requested_ghs)} · <b>Status:</b> {selectedApp.status}</p>
   <details open><summary>Farmer-authorized appraisal snapshot</summary>
    <div className="twocol">
     <div><h3>Applicant and farm</h3><p>{selectedApp.shared_report_snapshot?.farmer?.full_name||'Name not recorded'} · {selectedApp.shared_report_snapshot?.farmer?.email||'Email not recorded'}</p><p>{selectedApp.shared_report_snapshot?.farm?.name||'Farm'} · {selectedApp.shared_report_snapshot?.farm?.district||'District not recorded'}, {selectedApp.shared_report_snapshot?.farm?.region||'Region not recorded'}</p>
      <h3>Sales and credit</h3><p>Invoiced: {money(selectedApp.shared_report_snapshot?.sales?.invoiced_sales_revenue_ghs)} · Received: {money(selectedApp.shared_report_snapshot?.sales?.payments_received_ghs)} · Outstanding customer credit: {money(selectedApp.shared_report_snapshot?.sales?.outstanding_customer_credit_ghs)}</p>
      <h3>Production history and estimates</h3>{(selectedApp.shared_report_snapshot?.production_history||[]).map((cycle:Obj)=><p key={cycle.cycle_id}>Cycle #{cycle.cycle_id} · {cycle.species} · {cycle.status} · live estimate {num(cycle.estimated_live_fish)} fish / {num(cycle.estimated_live_biomass_kg)} kg</p>)}{!(selectedApp.shared_report_snapshot?.production_history||[]).length&&<p>No production cycles recorded.</p>}
      {selectedApp.shared_report_snapshot?.application_video_evidence_id&&<button type="button" className="outline small" onClick={()=>void download(`/finance/loan-evidence/${selectedApp.shared_report_snapshot.application_video_evidence_id}/video`,`loan_application_${selectedApp.id}.${selectedApp.shared_report_snapshot.application_video_media_type==='video/mp4'?'mp4':'webm'}`)}>Review application video</button>}
     </div>
     <div><h3>Indicative repayment capacity</h3><p>Monthly capacity: {selectedApp.shared_report_snapshot?.cash_flow?.estimated_monthly_repayment_capacity_ghs==null?'Not available':money(selectedApp.shared_report_snapshot.cash_flow.estimated_monthly_repayment_capacity_ghs)}</p><p>Average recorded monthly farm cash flow: {money(selectedApp.shared_report_snapshot?.cash_flow?.average_recorded_monthly_operating_cashflow_ghs)}</p><p>Tracked loans: {(selectedApp.shared_report_snapshot?.existing_loans||[]).length}</p>{(selectedApp.shared_report_snapshot?.existing_loans||[]).map((loan:Obj)=><p key={loan.loan_id}>Loan #{loan.loan_id} · {loan.status} · Outstanding {money(Number(loan.outstanding_principal_ghs)+Number(loan.outstanding_interest_ghs))} · overdue {money(loan.overdue_scheduled_amount_ghs)}</p>)}
      <h3>Projected cash flow</h3><p>{(selectedApp.shared_report_snapshot?.cash_flow?.projected_months||[]).length} months · based on historical operating cash flow and disclosed monthly obligations.</p>
     </div>
    </div>
    <pre>{JSON.stringify(selectedApp.shared_report_snapshot,null,2)}</pre>
   </details>
   {!['approved','rejected'].includes(selectedApp.status)&&<form onSubmit={e=>formSubmit(e,`/finance/institutions/${institutionId}/applications/${selectedApp.id}/appraise`,{decision:form.decision,rationale:form.rationale,...(form.decision==='approved'?{approved_ghs:Number(form.approved_ghs)}:{})},()=>{setSelectedApp(null);setForm({})})}>
    {dropdown('decision','Appraisal decision',['under_review','more_information','approved','rejected'].map(x=>({value:x,label:x.replace('_',' ')})))}
    <label className="field"><span>Decision rationale (minimum 10 characters)</span><textarea minLength={10} required value={form.rationale||''} onChange={e=>setForm({...form,rationale:e.target.value})}/></label>
    {form.decision==='approved'&&field('approved_ghs','Approved amount (GH₵)','number',{min:0.01,step:0.01,required:true})}
    <button className="primary" disabled={busy}>Record decision</button>
   </form>}
   {selectedApp.status==='approved'&&!lenderLoans.some(loan=>loan.application_id===selectedApp.id)&&<form className="farmform" onSubmit={openApprovedLoan}>
    <h3>Open approved loan account</h3>
    <p className="muted">Approved principal: {money(selectedApprovedAmount)}. Bank-entered interest is flat simple interest for the approved term; insurance is fixed at 1% of approved principal.</p>
    {field('annual_flat_interest_percent','Annual flat interest rate (%)','number',{required:true,min:0,max:100,step:0.01})}
    {field('commitment_fee_ghs','Commitment fee (GH₵)','number',{min:0,step:0.01})}
    {field('processing_fee_ghs','Processing fee (GH₵)','number',{min:0,step:0.01})}
    <div className="infobox">Estimated total repayment including interest, lender-entered fees and 1% agricultural insurance: <b>{money(projectedLoanTotal)}</b>. This amount is saved to the farmer’s loan account and divided across instalments.</div>
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
    <button className="primary" disabled={busy||!form.repayment_frequency}>Open loan account</button>
   </form>}
  </section>}
 </>}
 {selectedLoan&&<div className="overlay" onClick={()=>setSelectedLoan(null)}><div className="drawer" onClick={e=>e.stopPropagation()}>
  <div className="between"><h2>Loan #{selectedLoan.id}</h2><button className="outline" onClick={()=>setSelectedLoan(null)}>Close</button></div>
  <span className="pill">{selectedLoan.status}</span>
  <div className="metricrows loan-summary">
   <Line label="Approved amount" value={money(selectedLoan.approved_ghs)}/>
   <Line label="Total contract repayment" value={money(selectedLoan.total_contract_repayment_ghs)}/>
   <Line label="Disbursed" value={money(selectedLoan.disbursed_ghs)}/>
   <Line label="Undisbursed" value={money(selectedLoan.undisbursed_ghs)}/>
   <Line label="Outstanding principal" value={money(selectedLoan.outstanding_principal_ghs)}/>
   <Line label="Outstanding interest" value={money(selectedLoan.outstanding_scheduled_interest_ghs)}/>
   <Line label="Commitment fee" value={money(selectedLoan.commitment_fee_ghs)}/>
   <Line label="Processing fee" value={money(selectedLoan.processing_fee_ghs)}/>
   <Line label="Agricultural insurance (1%)" value={money(selectedLoan.insurance_fee_ghs)}/>
   <Line label="Outstanding fees" value={money(selectedLoan.outstanding_fees_ghs)}/>
   <Line label="Total scheduled balance" value={money(selectedLoan.total_scheduled_balance_ghs)}/>
   <Line label="Annual flat interest rate" value={`${num(selectedLoan.annual_flat_interest_percent)}%`}/>
   <Line label="Repayment schedule" value={selectedLoan.repayment_frequency}/>
  </div>
  {page==='lender'&&selectedLoan.status==='awaiting_disbursement'&&Number(selectedLoan.undisbursed_ghs)>0&&<form className="farmform" onSubmit={e=>void saveLoanTransaction(e,'disbursements')}>
   <h3>Record loan disbursement</h3>
   <label className="field"><span>Amount (GH₵)</span><input required type="number" min="0.01" max={selectedLoan.undisbursed_ghs} step="0.01" value={form.loan_amount_ghs??''} onChange={e=>setForm({...form,loan_amount_ghs:e.target.value})}/></label>
   <label className="field"><span>Transfer reference</span><input required minLength={3} maxLength={100} value={form.loan_reference??''} onChange={e=>setForm({...form,loan_reference:e.target.value})}/></label>
   <label className="field"><span>Disbursement date</span><input required type="date" max={localDate()} value={form.loan_transaction_date??''} onChange={e=>setForm({...form,loan_transaction_date:e.target.value})}/></label>
   <EvidenceRecorder key={`loan-${selectedLoan.id}-disbursement-${transactionRecorderKey}`} activity="disbursement" unit={null} requireFarmGps={false} onChange={video=>{setTransactionVideo(video);setTransactionEvidenceId(null)}} getChallenge={getEvidenceChallenge}/>
   <button className="primary" disabled={busy||!transactionVideo}>Record disbursement</button>
  </form>}
  {page==='lender'&&selectedLoan.status==='active'&&<form className="farmform" onSubmit={e=>void saveLoanTransaction(e,'repayments')}>
   <h3>Record loan repayment</h3>
   <label className="field"><span>Amount received (GH₵)</span><input required type="number" min="0.01" max={selectedLoan.total_scheduled_balance_ghs} step="0.01" value={form.loan_amount_ghs??''} onChange={e=>setForm({...form,loan_amount_ghs:e.target.value})}/></label>
   <label className="field"><span>Payment reference</span><input required minLength={3} maxLength={100} value={form.loan_reference??''} onChange={e=>setForm({...form,loan_reference:e.target.value})}/></label>
   <label className="field"><span>Payment date</span><input required type="date" max={localDate()} value={form.loan_transaction_date??''} onChange={e=>setForm({...form,loan_transaction_date:e.target.value})}/></label>
   <EvidenceRecorder key={`loan-${selectedLoan.id}-repayment-${transactionRecorderKey}`} activity="repayment" unit={null} requireFarmGps={false} onChange={video=>{setTransactionVideo(video);setTransactionEvidenceId(null)}} getChallenge={getEvidenceChallenge}/>
   <p className="muted">Partial payments are applied to scheduled interest, then fees, then principal. Do not record a payment until the institution has verified receipt.</p>
   <button className="primary" disabled={busy||!transactionVideo}>Record repayment</button>
  </form>}
  <h3>Repayment schedule</h3><div className="tablewrap"><table><thead><tr><th>#</th><th>Due</th><th>Principal</th><th>Interest</th><th>Fees</th><th>Total</th></tr></thead><tbody>{schedule.map(s=><tr key={s.number}><td>{s.number}</td><td>{s.due_on}</td><td>{money(s.principal_ghs)}</td><td>{money(s.interest_ghs)}</td><td>{money(s.fees_ghs)}</td><td>{money(s.total_ghs)}</td></tr>)}</tbody></table>{!schedule.length&&<p className="empty">Repayment schedule is available after full disbursement.</p>}</div>
  <h3>Transaction history</h3>{transactions.map((t,i)=><div className="item" key={`${t.type}-${t.reference}-${i}`}><b>{t.type==='repayment'?'Repayment':'Disbursement'} · {t.date} · {money(t.amount_ghs)}</b><small>{t.reference}{t.type==='repayment'?` · Principal ${money(t.principal_ghs)} · Interest ${money(t.interest_ghs)} · Fees ${money(t.fees_ghs)}`:''}</small>{t.evidence_id&&<button type="button" className="outline small" onClick={()=>void download(`/finance/loan-evidence/${t.evidence_id}/video`,`loan_${t.type}_${t.evidence_id}.${t.evidence_media_type==='video/mp4'?'mp4':'webm'}`)}>Review 15-second video</button>}</div>)}{!transactions.length&&<p className="empty">No transactions recorded.</p>}
  <p className="footnote">This is a manual ledger; it does not transfer money or verify bank settlement.</p>
 </div></div>}
 </main></div>;
}
function Stat({label,value,sub}:{label:string,value:string,sub:string}){return <div className="stat"><small>{label}</small><strong>{value}</strong><span>{sub}</span></div>}
function Line({label,value}:{label:string,value:string}){return <div className="line"><span>{label}</span><b>{value}</b></div>}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
