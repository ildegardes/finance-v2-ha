// Presentation only: every mutation is authorized again by the domain.
export function expenseActions(x){
 const active=x.lifecycle_state==='ACTIVE',card=x.planned_payment_method==='CREDIT_CARD',paid=x.effective_status==='PAID';
 return ['detail','history',...(active?['edit']:[]),...(active&&!card&&x.requires_manual_action&&!paid?['pay']:[]),...(active&&!card&&paid?['reverse','replace']:[]),...(active&&!paid?['cancel']:[]),...(active&&!paid&&!card&&!x.invoice_id&&!x.installment_series_id?['delete']:[]),...(x.lifecycle_state==='CANCELLED'?['reactivate']:[])];
}
export function revenueActions(x){return ['detail','history',...(['PENDING','OVERDUE'].includes(x.financial_status)?['edit','receive','cancel']:[]),...(x.financial_status==='RECEIVED'?['reverse']:[])]}
export function invoiceActions(x){return ['detail','history',...(x.state==='OPEN'?['close','config']:[]),...(x.state==='CLOSED'?['correct','config',...(x.requires_manual_action?['pay']:[])]:[]),...((x.payments||[]).some(p=>!p.reversed_at)?['reverse']:[]),...(['OPEN','CLOSED'].includes(x.state)&&!(x.payments||[]).some(p=>!p.reversed_at)?['cancel']:[])]}
export function expenseEditFields(x){return x.effective_status==='PAID'?['description','category_id','notes','tag_ids']:['description','amount_cents',...(x.planned_payment_method==='CREDIT_CARD'?[]:['due_date']),'category_id','notes','tag_ids']}
export function occurrenceActions(x,s){if(x.lifecycle_state!=='ACTIVE')return [];return ['edit',...(s.ended_at?[]:[...(x.effective_status==='PAID'?[]:['only','future','change']),...(x.override&&!x.override.removed_at?['unprotect']:['override'])])]}
export function installmentCancellationCuts(items,invoices){
 return items.filter(x=>x.lifecycle_state==='ACTIVE').filter(x=>{
  const deductions=new Map();
  for(const y of items.filter(y=>y.installment_number>=x.installment_number)){
   if(y.lifecycle_state==='CANCELLED')continue;
   if(y.invoice_id==null){if(!y.effective_status||y.effective_status==='PAID')return false;continue;}
   const invoice=invoices.find(i=>i.id===y.invoice_id);
   if(!invoice||!['OPEN','CLOSED'].includes(invoice.state))return false;
   deductions.set(invoice.id,(deductions.get(invoice.id)||0)+y.amount_cents);
   if(invoice.state==='CLOSED'&&invoice.effective_total_cents-deductions.get(invoice.id)<invoice.paid_cents)return false;
  }
  return true;
 });
}
