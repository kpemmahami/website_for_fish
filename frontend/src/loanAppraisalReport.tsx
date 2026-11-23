import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';

type Snapshot = Record<string, any>;
type Entry = [label:string, value:string];
type Group = {title?:string, entries?:Entry[], notes?:string[]};
type Section = {title:string, groups:Group[]};

const missing='Not provided';
const numberFormat=new Intl.NumberFormat('en-GH',{maximumFractionDigits:4});
const currencyFormat=new Intl.NumberFormat('en-GH',{minimumFractionDigits:2,maximumFractionDigits:2});
const present=(value:unknown)=>value!==undefined&&value!==null&&value!=='';
const text=(value:unknown)=>present(value)?String(value):missing;
const number=(value:unknown,unit='')=>present(value)?numberFormat.format(Number(value))+unit:missing;
const currency=(value:unknown)=>present(value)?'GH₵'+currencyFormat.format(Number(value)):missing;
const human=(value:unknown)=>present(value)?String(value).replace(/_/g,' ').replace(/^./,c=>c.toUpperCase()):missing;
const yesNo=(value:unknown)=>value===true?'Provided':value===false?missing:'Unavailable';
const date=(value:unknown)=>{
  if(!present(value))return missing;
  const parsed=new Date(String(value).length===10?String(value)+'T00:00:00Z':String(value));
  return Number.isNaN(parsed.getTime())?text(value):new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeZone:'Africa/Accra'}).format(parsed);
};
const group=(entries:Entry[],title?:string):Group=>({title,entries});
const note=(...notes:string[]):Group=>({notes});
const list=(rows:Snapshot[]|undefined,format:(row:Snapshot)=>Group,empty:string)=>rows?.length?rows.map(format):[note(empty)];

export function appraisalSections(snapshot:Snapshot, application:Snapshot, institution?:string):Section[]{
  const farmer=snapshot.farmer??{}, farm=snapshot.farm??{}, request=snapshot.application??{};
  const production=snapshot.production??{}, feed=snapshot.feed??{}, sales=snapshot.sales??{};
  const costs=snapshot.costs??{}, feedCosts=snapshot.feed_costs??{}, cash=snapshot.cash_flow??{};
  const completeness=snapshot.appraisal_data_completeness??{}, evidence=snapshot.application_video_evidence;
  const recentActivity=Number(completeness.recent_cashflow_transaction_count)>0;
  const cycles=snapshot.production_history as Snapshot[]|undefined;
  const reportDate=snapshot.generated_at??snapshot.consent?.granted_at??application.created_at;
  return [
    {title:'Farmer information',groups:[group([
      ['Farmer',text(farmer.full_name)],['Farm or business',text(farm.name)],['Authorized email',text(farmer.email)],
      ['Farm location',[farm.district,farm.region].filter(Boolean).join(', ')||missing],['Farm type',human(farm.farm_type)],
      ['Application reference',text(application.reference)],['Report date',date(reportDate)],
    ])]},
    {title:'Loan application',groups:[group([
      ['Requested amount',currency(application.requested_ghs??request.requested_ghs)],['Purpose',text(application.purpose??request.purpose)],
      ['Proposed repayment period',number(application.term_months??request.term_months,' months')],
      ['Financial institution',text(snapshot.consent?.institution_name??institution)],['Application status',human(application.status??'preview')],
      ['Application date',date(application.created_at)],
    ])]},
    {title:'Farm production assessment',groups:[
      group([['Registered units',number(production.total_units)],['Active units',number(production.active_units)],['Species',text(farm.species)],
        ['Active cycles',number(production.active_cycles)],['Fish stocked in active cycles',number(production.stocked_fish_in_active_cycles)],
        ['Estimated live fish',number(production.estimated_live_fish)],['Estimated live biomass',number(production.estimated_live_biomass_kg,' kg')],
        ['Feed consumed',number(feed.consumed_kg,' kg')],['Feed inventory balance',number(feed.remaining_stock_kg,' kg')],
        ['Recorded harvest weight',number(sales.harvested_kg,' kg')],['Water quality observations','Unavailable in this appraisal snapshot']]),
      ...list(cycles,cycle=>group([
        ['Species and status',[text(cycle.species),human(cycle.status)].join(' · ')],['Stocking date',date(cycle.stocked_on)],
        ['Originally stocked',number(cycle.fingerlings_stocked)],['Recorded mortality',number(cycle.cumulative_mortality)],
        ['Estimated surviving fish',number(cycle.estimated_live_fish)],['Estimated survival',number(cycle.estimated_survival_pct,'%')],
        ['Latest sampled average weight',cycle.latest_sampled_on?number(cycle.latest_average_weight_g,' g'):missing],
        ['Sample date',date(cycle.latest_sampled_on)],['Initial stocking weight',number(cycle.initial_average_weight_g,' g')],
        ['Estimated biomass',number(cycle.estimated_live_biomass_kg,' kg')],['Planned harvest date',date(cycle.planned_harvest_on)],
        ['Target harvest weight',number(cycle.target_harvest_weight_g,' g')],['Expected survival assumption',number(cycle.expected_survival_pct,'%')],
        ['Fish already harvested',number(cycle.total_harvested_fish)],
        ...((cycle.harvests??[]) as Snapshot[]).map((harvest):Entry=>['Recorded harvest on '+date(harvest.harvested_on),number(harvest.quantity_kg,' kg')+' · '+number(harvest.fish_count,' fish')]),
        ...((cycle.sampling_history??[]) as Snapshot[]).map((sample):Entry=>['Sample on '+date(sample.sampled_on),number(sample.average_weight_g,' g average')+' · '+number(sample.sample_count,' sampled')]),
      ],text(cycle.production_unit)), 'No production cycles recorded.'),
      ...list(snapshot.production_estimates,estimate=>group([
        ['Species',text(estimate.species)],['Target weight',number(estimate.target_weight_g,' g')],
        ['Projected harvest',number(estimate.expected_harvest_kg,' kg')],['Projected revenue',currency(estimate.expected_revenue_ghs)],
        ['Projected profit',currency(estimate.expected_profit_ghs)],
      ],'Production plan #'+text(estimate.plan_id)), 'No plan-linked forecasts available.'),
    ]},
    {title:'Financial performance',groups:[
      group([['Invoiced sales',currency(sales.invoiced_sales_revenue_ghs??sales.invoiced_revenue_ghs)],
        ['Payments received',currency(sales.payments_received_ghs)],['Customer receivables',currency(sales.outstanding_customer_credit_ghs??sales.outstanding_receivables_ghs)],
        ['Recorded production costs',currency(costs.recorded_costs_to_date_ghs)],['Projected cycle costs',currency(costs.projected_cycle_costs_ghs)],
        ['Estimated cost of consumed feed',currency(feedCosts.estimated_consumed_feed_cost_ghs)],
        ['Average monthly operating cash flow',recentActivity?currency(cash.average_recorded_monthly_operating_cashflow_ghs):'Insufficient recorded activity']]),
      ...(Object.keys(feedCosts.recorded_operating_expenses_by_category_ghs??{}).length?
        [group(Object.entries(feedCosts.recorded_operating_expenses_by_category_ghs).map(([category,amount])=>[human(category),currency(amount)]),'Recorded expenses by category')]:
        [note('No operating expenses recorded by category.')]),
      ...list(feedCosts.by_product,product=>group([
        ['Feed received',number(product.received_kg,' kg')],['Feed consumed',number(product.consumed_kg,' kg')],
        ['Purchase cash outflow',currency(product.purchase_cash_outflow_ghs)],['Estimated consumed-feed cost',currency(product.estimated_consumed_cost_ghs)],
      ],text(product.feed_product)), 'No feed product cost records.'),
      ...(feedCosts.note?[note(feedCosts.note)]:[]),
      ...(recentActivity?list(cash.historical_months,month=>group([
        ['Sale payments',currency(month.sales_payments_received_ghs)],
        ['Feed purchase outflow',currency(month.feed_purchase_cash_outflow_ghs)],
        ['Recorded operating expenses',currency(month.recorded_operating_expenses_ghs)],
        ['Operating cash flow',currency(month.net_recorded_operating_cashflow_ghs)],
      ],'Recorded month '+text(month.month)), 'No monthly records available.'):[note('Operating cash-flow and repayment estimates require recorded financial activity.')]),
      ...(recentActivity?list(cash.projected_months,month=>group([
        ['Projected farm operating cash flow',currency(month.assumed_farm_operating_cashflow_ghs)],
        ['Projected net after obligations',currency(month.projected_net_cashflow_after_obligations_ghs)],
        ['Tracked scheduled payments',currency(month.tracked_loan_scheduled_payments_ghs)],
      ],'Projected month '+text(month.month)), 'No monthly projections available.'):[]),
    ]},
    {title:'Existing financial obligations',groups:[
      group([['Other monthly income declared',currency(cash.farmer_declared_monthly_other_income_ghs)],
        ['Monthly household expenses declared',currency(cash.farmer_declared_monthly_household_expenses_ghs)],
        ['Monthly external debt payments declared',currency(cash.farmer_declared_monthly_external_debt_payments_ghs)],
        ['Tracked monthly scheduled payments',currency(cash.tracked_existing_loans_monthly_scheduled_payment_ghs)],
        ['Tracked obligations in the next 12 months',currency(cash.tracked_existing_loans_next_12_months_scheduled_payments_ghs)],
        ['Overdue tracked obligations',currency(cash.tracked_existing_loans_overdue_scheduled_payments_ghs)]]),
      ...list(snapshot.existing_loans,loan=>group([
        ['Status',human(loan.status)],['Repayment frequency',human(loan.repayment_frequency)],['Term',number(loan.term_months,' months')],
        ['Approved amount',currency(loan.approved_ghs)],['Disbursed amount',currency(loan.disbursed_ghs)],
        ['Outstanding principal',currency(loan.outstanding_principal_ghs)],['Outstanding interest',currency(loan.outstanding_interest_ghs)],
        ['Outstanding fees',currency(loan.outstanding_fees_ghs)],['Scheduled balance',currency(loan.total_scheduled_balance_ghs)],
        ['Scheduled payments in the next 12 months',currency(loan.next_12_months_scheduled_payments_ghs)],
        ['Overdue instalments',currency(loan.overdue_scheduled_amount_ghs)],['Next due date',date(loan.next_due_on)],
      ],'Tracked loan #'+text(loan.loan_id)), 'No tracked loans recorded.'),
    ]},
    {title:'Assessment and risk observations',groups:[
      group([['Estimated monthly repayment capacity',recentActivity?currency(cash.estimated_monthly_repayment_capacity_ghs):'Insufficient recorded activity'],
        ['Estimated monthly surplus',recentActivity?currency(cash.estimated_monthly_surplus_after_obligations_ghs):'Insufficient recorded activity'],
        ['Requested principal per month, before interest and fees',currency(cash.requested_principal_divided_by_term_ghs)]]),
      note('The financial institution makes the credit decision after reviewing the underlying records.',...(snapshot.warnings??[]),...(cash.notes??[])),
    ]},
    {title:'Data verification and disclaimer',groups:[
      group([['Source','AquaFarm farm records and farmer declarations'],['Report date',date(reportDate)],
        ['Authorization',application.reference?(snapshot.consent?.granted_at?'Farmer-authorized snapshot · '+date(snapshot.consent.granted_at):'Farmer-authorized snapshot'):'Farmer-only preview before submission'],
        ['Household expenses information',yesNo(completeness.household_expenses_provided)],['External debt information',yesNo(completeness.external_debt_obligations_provided)],
        ['External income information',yesNo(completeness.external_income_provided)],['Production plans recorded',number(completeness.production_plan_count)],
        ['Existing loans recorded',number(completeness.tracked_loan_count)],['Recorded sales',number(completeness.sales_count)],
        ['Recorded sales payments',number(completeness.sales_payment_count)],['Recent cash-flow transactions',number(completeness.recent_cashflow_transaction_count)],
        ['Application video',evidence?'Recorded · '+number(evidence.duration_seconds,' seconds'):missing],
        ['Video received',date(evidence?.server_received_at)]]),
      note('Review sampling dates against the application date to judge how current the growth and biomass estimates are.',text(snapshot.disclaimer)),
    ]},
  ];
}

export async function appraisalPdf(sections:Section[], reference?:string){
  const {jsPDF}=await import('jspdf');
  const pdf=new jsPDF({unit:'mm',format:'a4'});
  const margin=18, width=174, bottom=276;
  let y=margin;
  function line(value:string, size:number, bold=false){
    pdf.setFont('helvetica',bold?'bold':'normal');
    pdf.setFontSize(size);
    pdf.setTextColor(bold?'#164f40':'#243832');
    const leading=size*0.44;
    const safe=value.replaceAll('GH₵','GHS ');
    const lines=pdf.splitTextToSize(safe,width) as string[];
    for(const row of lines){
      if(y+leading>bottom){pdf.addPage();y=margin}
      if(/[^\x20-\x7e]/.test(row)){
        const canvas=document.createElement('canvas');
        canvas.width=width*10;canvas.height=Math.ceil(leading*10);
        const context=canvas.getContext('2d');
        if(!context)throw new Error('Could not render the PDF text');
        context.fillStyle='#fff';context.fillRect(0,0,canvas.width,canvas.height);
        context.fillStyle=bold?'#164f40':'#243832';context.font=(bold?'bold ':'')+(size*3.53)+'px sans-serif';
        context.textBaseline='middle';context.fillText(row,0,canvas.height/2,canvas.width);
        pdf.addImage(canvas,'PNG',margin,y-leading*0.75,width,leading);
      }else pdf.text(row,margin,y);
      y+=leading;
    }
  }
  pdf.setProperties({title:'Farmer Loan Appraisal Report'});
  line('AquaFarm Manager Ghana',11,true);y+=3;
  line('Farmer Loan Appraisal Report',21,true);
  if(reference)line(reference,11);
  for(const section of sections){
    if(y+24>bottom){pdf.addPage();y=margin}
    y+=5;line(section.title,14,true);
    for(const item of section.groups){
      if(item.title){y+=2;line(item.title,11,true)}
      for(const [label,value] of item.entries??[])line(label+': '+value,10);
      for(const paragraph of item.notes??[])line(paragraph,10);
      y+=2;
    }
  }
  for(let page=1;page<=pdf.getNumberOfPages();page++){
    pdf.setPage(page);pdf.setFont('helvetica','normal');pdf.setFontSize(9);
    pdf.text(page+' / '+pdf.getNumberOfPages(),192,287,{align:'right'});
  }
  return pdf;
}

export function LoanAppraisalReport({snapshot,application,institution,onClose,onDownload}:{snapshot:Snapshot,application:Snapshot,institution?:string,onClose:()=>void,onDownload?:()=>Promise<void>}){
  const sections=appraisalSections(snapshot,application,institution);
  const [error,setError]=useState('');
  const [saving,setSaving]=useState(false);
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{dialog.current?.showModal()},[]);
  return createPortal(<dialog className="appraisal-overlay" ref={dialog} aria-labelledby="appraisal-title" onCancel={event=>{event.preventDefault();onClose()}}>
    <div className="appraisal-actions">
      <button className="outline" onClick={onClose} autoFocus>Return to Loan Application</button>
      <button className="outline" onClick={()=>window.print()}>Print Report</button>
      <button className="primary" disabled={saving} onClick={async()=>{
        setSaving(true);setError('');
        try{
          if(onDownload)await onDownload();
          else{const pdf=await appraisalPdf(sections,application.reference);pdf.save((application.reference??'farmer-loan-appraisal')+'.pdf')}
        }
        catch{setError('PDF download is unavailable. You can still print the report.')}
        finally{setSaving(false)}
      }}>{saving?'Preparing PDF…':'Download PDF'}</button>
    </div>
    {error&&<p className="alert" role="alert">{error}</p>}
    <article className="appraisal-report">
      <header><div><span className="eyebrow">AQUAFARM MANAGER GHANA</span><h1 id="appraisal-title">Farmer Loan Appraisal Report</h1>
      <p>{text(snapshot.farm?.name)}{application.reference?' · '+application.reference:''}</p></div><span className="pill">{human(application.status??'preview')}</span></header>
      <div className="appraisal-summary">
        <div><small>Requested amount</small><strong>{currency(application.requested_ghs??snapshot.application?.requested_ghs)}</strong></div>
        <div><small>Active production cycles</small><strong>{number(snapshot.production?.active_cycles)}</strong></div>
        <div><small>Customer payments received</small><strong>{currency(snapshot.sales?.payments_received_ghs)}</strong></div>
      </div>
      {sections.map(section=><section key={section.title}><h2>{section.title}</h2>
        {section.groups.filter(item=>item.notes?.length||item.entries?.length).map((item,index)=><div className="appraisal-group" key={index}>
          {item.title&&<h3>{item.title}</h3>}{item.entries&&<dl>{item.entries.map(([label,value],row)=><div key={row}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
          {item.notes?.map((paragraph,row)=><p key={row}>{paragraph}</p>)}
        </div>)}
      </section>)}
    </article>
  </dialog>,document.body);
}
