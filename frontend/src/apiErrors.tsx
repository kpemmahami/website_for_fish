import {AlertTriangle, X} from 'lucide-react';

const fields:Record<string,string>={
 email:'email address',full_name:'full name',phone_number:'mobile phone number',password:'password',business_type:'business type',name:'name',quantity_kg:'quantity',
 amount_ghs:'payment amount',requested_ghs:'requested amount',price_ghs_per_kg:'selling price',
 feed_id:'feed type',session_number:'feeding session',actual_fed_at:'actual feeding time',
 dead_count:'fish count',stocked_count:'stocking quantity',expected_harvest_on:'harvest date',
 ph:'pH',latitude:'latitude',longitude:'longitude',due_on:'due date',paid_on:'payment date',
};

const actionable=new Set([
 'Email already registered','Insufficient feed stock','Insufficient harvested fish inventory',
 'Payment exceeds outstanding balance','This payment reference is already recorded for the invoice',
 'This video is already linked to a different feeding entry','Video evidence has already been used or archived',
 'Choose a valid feeding session from the daily recommendation','The daily recommendation changed. Refresh the session schedule.',
 'Actual feeding time must be on the feeding date and cannot be in the future',
 'Choose a valid feeding session','Configure a feeding schedule for this date first',
 'Enter the actual feeding time','Explain why this feeding was unscheduled',
 'Actual feeding time is outside this session window. Record it as unscheduled.',
 'This session is completed. Choose Add feed entry to record additional feeding.',
 'The session schedule changed. Refresh and select the session again.',
 'Use ordered, non-overlapping same-day windows in Ghana time',
 'This date already has a saved session plan. Choose a later effective date.',
 'Choose today or a future date on an active cycle','Choose an unscheduled entry with a recorded feeding time',
 'Reconciliation requires a saved session window',
 'This session was marked skipped','Mark this unit ready before recording stocking',
 'Unit already has an open stocking cycle','Choose a date between stocking and today',
 'Expected harvest date must be after stocking','Sales of 500 kg or more require a registered customer',
 'Payment due date cannot predate the sale','A customer with this name and phone is already registered',
 'Explicit report-sharing consent is required','This offer is no longer awaiting a response',
 'Invitation is awaiting acceptance','Staff member already belongs to this institution',
 'Invitation is invalid, expired, or already used','Use the invited email to sign in',
 'The farm owner must confirm the advisory species profile before calculating a ration',
 'Resolve the safety and data warnings before approving this recommendation',
 'Feeding recommendation must be approved before use','Approve a feeding recommendation for this date first',
 'Each window end must be later than its start on the same day','Times cannot change after recording or skipping a session',
 'Choose a period of up to 31 days ending today or earlier',
 'Supporting evidence or a documented exception is required','Receipt exceeds the upload limit',
 'Upload a valid JPEG, PNG, WebP, or PDF receipt','Upload a readable PDF receipt','Receipt file could not be read',
 'Expense has already been reviewed','This expense payment reference is already recorded',
 'Enter percentages for all sessions totaling 100, or enter optional kilograms instead',
 'Farm records changed. Calculate and review a fresh recommendation.',
 'Selected feeding rate is outside the species and size profile range',
 'Advisory feeding profiles are available only for tilapia and catfish',
 'Narrow the filters to export 2,000 records or fewer',
 'Enable fish processing first','Select an existing processing method','Insufficient raw fish stock',
 'Only released, in-date stock can be sold','Insufficient finished stock','Insufficient packaging stock',
 'Packaging would exceed available finished weight','Allocation exceeds the unallocated expense balance',
 'Reconcile the batch mass balance and document any measurement difference','Quality release must follow packaging',
 'Enter a validated shelf-life basis and valid date','Document additions to the batch mass balance',
 'Batch start cannot predate raw fish receipt','Batch start cannot predate harvest',
 'Credit exceeds the original value of the returned packages','Enter the required refund or reduce the credit',
 'Choose the method used for the refund','A refund or credit requires the original invoice',
 'Purchase total is outside the supported accounting range','Use a margin below 100% and a non-negative proposed price',
 'Enter a valid reporting date range','Select up to ten years for weekly reporting',
]);

function friendlyResource(path:string){
 if(path.includes('production-activity'))return 'Production activity';
 if(path.includes('/loan-applications')||path.includes('/application-lookup')||path.includes('/applications'))return 'Loan application';
 if(path.includes('/customers'))return 'Customer';
 if(path.includes('/units/')||path.endsWith('/units'))return 'Production unit';
 if(path.includes('/institution'))return 'Financial institution';
 if(path.includes('/farms'))return 'Farm';
 return 'Requested record';
}

function actionFailure(path:string,method:string){
 if(path.includes('.pdf'))return 'Unable to download PDF.';
 if(path.includes('/production-activity'))return 'Unable to load production activity.';
 if(path.includes('loan-application-preview'))return 'Unable to load farm report.';
 if(path.includes('/appraise'))return 'Unable to record loan decision.';
 if(path.endsWith('/loan-applications')&&method!=='GET')return 'Unable to submit loan request.';
 if(path.includes('/loan-applications')||path.includes('/applications')||path.includes('/application-lookup'))return 'Unable to load loan application.';
 if(path.includes('/cash-activity'))return 'Unable to load cash activity.';
 if(path.includes('/expenses'))return method==='GET'?'Unable to load expense records.':
   path.includes('/payments')?'Unable to record supplier payment.':'Unable to save expense.';
 if(path.includes('/sales'))return method==='GET'?'Unable to load sales records.':
   path.includes('/payments')?'Unable to record payment.':path.includes('/customers')?'Unable to save customer.':'Unable to save sale.';
 if(method!=='GET'){
   if(path.endsWith('/feeding'))return 'Unable to record feeding session.';
   if(path.endsWith('/cycles'))return 'Unable to save stocking record.';
   if(path.endsWith('/water-quality'))return 'Unable to save water quality reading.';
   if(path.endsWith('/mortality'))return 'Unable to record mortality.';
   if(path.includes('harvest'))return 'Unable to save harvest record.';
 }
 if(path.includes('/samples'))return 'Unable to load fish sampling records.';
 if(path.includes('/units/')||path.includes('dashboard'))return 'Unable to load production records.';
 return 'Something went wrong. Please try again.';
}

function validationMessage(detail:unknown){
 if(!Array.isArray(detail))return null;
 const messages:string[]=[];
 for(const issue of detail){
   if(!Array.isArray(issue?.loc))continue;
   const key=issue.loc.find((part:unknown)=>typeof part==='string'&&Object.hasOwn(fields,part));
   if(!key)continue;
   const field=fields[key];
   const message=issue.type==='missing'?'Please enter '+field+'.':'Please enter a valid '+field+'.';
   if(!messages.includes(message))messages.push(message);
 }
 return messages.slice(0,2).join(' ')||null;
}

export class UserFacingError extends Error{
 constructor(message:string,readonly status?:number){super(message)}

 override toString(){return this.message}
}

export function friendlyApiError(path:string,method:string,status:number,detail:unknown){
 const registration=method==='POST'&&['/auth/register','/auth/farmer/register'].includes(path);
 if(registration){
  if(status===0)return 'Unable to connect to the server. Check your internet connection.';
  if(status===409&&detail==='Email already registered')return 'This email address is already registered.';
  if(status===409&&detail==='This phone number is already assigned to an account')return 'This phone number is already assigned to an account.';
  if(status===422||status===400)return validationMessage(detail)||'Please check the information you entered.';
  if(status===429)return 'Too many requests. Please wait and try again.';
  return 'Registration is temporarily unavailable. Please try again.';
 }
 const login=/^\/auth\/(?:[^/]+\/)?login$/.test(path);
 if(path==='/auth/me/phone-verification/confirm'&&status===400)return 'The SMS code is invalid or expired.';
 if(path==='/auth/me/phone-verification/request'&&status===429)return 'Wait two minutes before requesting another code.';
 if(path==='/auth/me/phone-verification/request'&&status===503)return 'The verification SMS could not be sent. Try again later.';
 if(path==='/auth/institution/initial-password'&&status===400)return 'This password setup session expired or was already used. Return to sign in.';
 if(path==='/auth/institution/initial-password'&&status===422&&detail==='Choose a password different from the initial password')return detail+'.';
 if(path==='/auth/admin/login'&&status===401&&detail==='Invalid or already used authenticator code')return 'Enter a fresh code from your authenticator app.';
 if(['/auth/admin/contact-verification','/auth/admin/activate'].includes(path)&&status===400)
   return 'The code or setup link is invalid or expired. If it expired, ask the Platform Owner to restart setup.';
 if(path==='/auth/password-recovery/request'&&status===503)return 'Password recovery email is unavailable. Contact support.';
 if(path==='/auth/password-recovery/reset'&&status===400)return 'This password reset link is invalid or expired. Request a new link.';
 if(path==='/auth/password-recovery/reset'&&status===422&&detail==='Use at least 12 characters for an administrator password.')return detail;
 if(status===0)return 'Unable to connect. Please check your connection.';
 if(status===401)return login?'Incorrect email, phone number, or password.':'Your session has expired. Please log in again.';
 if(status===403)return 'You do not have permission to perform this action.';
 if(status===429)return 'Too many requests. Please wait and try again.';
 if(status===404)return friendlyResource(path)+' not found.';
 if(status>=500)return actionFailure(path,method);
 if(typeof detail==='string'){
   if(status===409&&detail==='This phone number is already assigned to an account')return detail+'.';
   if(actionable.has(detail))return detail.endsWith('.')?detail:detail+'.';
   if(/^Insufficient feed stock\. Only [0-9]+(?:\.[0-9]+)? kg is available\.$/.test(detail))return detail;
 }
 if(status===422)return validationMessage(detail)||'Check the required fields and try again.';
 if(status===400)return 'Check the information you entered and try again.';
 if(status===409)return path.endsWith('/feeding')?'This feeding session may already be recorded.':'This record has changed or already exists. Refresh and try again.';
 return actionFailure(path,method);
}

export async function responseError(path:string,method:string,response:Response){
 let detail:unknown;
 try{detail=(await response.json()).detail}catch{/* Some proxies return an empty or HTML error. */}
 if(import.meta.env.DEV)console.warn('AquaFarm API request failed',{
   at:new Date().toISOString(), route:path.split('?')[0], method,status:response.status,
   requestId:response.headers.get('X-Request-ID'),
   category:response.status===404&&detail==='Not Found'?'route_not_found':response.status===404?'resource_unavailable':response.status===422?'validation':'http',
 });
 return new UserFacingError(friendlyApiError(path,method,response.status,detail),response.status);
}

export function ErrorNotice({message,retry,dismiss}:{message:string,retry?:()=>void,dismiss?:()=>void}){
 return <div className="alert app-error-notice" role="alert">
   <AlertTriangle size={17} aria-hidden="true"/><span>{message}</span>
   {retry&&<button type="button" className="outline small" onClick={retry}>Try again</button>}
   {dismiss&&<button type="button" aria-label="Dismiss message" onClick={dismiss}><X size={17}/></button>}
 </div>;
}
