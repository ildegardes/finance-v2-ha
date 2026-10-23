// Presentation privacy only: never changes API data, form values or financial records.
export const PRIVACY_KEY='finance-v17:money-visible';
export const MASK='R$ ••••••';
export const money=cents=>new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format((cents||0)/100);

// Native window.prompt is outside the DOM privacy boundary. Monetary edits use
// this shared dialog instead, preserving the original input value and result.
export function moneyPrompt(text,value,doc=document){
  return new Promise(resolve=>{
    const dialog=doc.createElement('dialog'),form=doc.createElement('form');form.className='form-card';
    const heading=doc.createElement('h2');heading.textContent='Editar valor';
    const label=doc.createElement('label');label.textContent=text;
    const input=doc.createElement('input');input.name='amount';input.inputMode='decimal';input.value=value;label.append(input);
    const actions=doc.createElement('div');actions.className='form-actions';
    const cancel=doc.createElement('button');cancel.type='button';cancel.className='quiet';cancel.textContent='Cancelar';cancel.onclick=()=>dialog.close();
    const confirm=doc.createElement('button');confirm.type='submit';confirm.textContent='Confirmar';actions.append(cancel,confirm);
    form.append(heading,label,actions);dialog.append(form);doc.body.append(dialog);let answer=null;
    form.onsubmit=event=>{event.preventDefault();answer=input.value;dialog.close()};
    dialog.onclose=()=>{dialog.remove();resolve(answer)};dialog.showModal();
  });
}

// Keep the provider's decimal precision and sign, without floating-point conversion.
export function bankMoney(value,currency){
  const match=/^(-?)(\d+)(?:\.(\d+))?$/.exec(String(value));
  if(!match||!(/^[A-Z]{3}$/).test(currency||''))return 'Valor indisponível';
  const [,sign,integer,fraction='']=match;
  return `${sign}${currency==='BRL'?'R$':currency} ${BigInt(integer).toLocaleString('pt-BR')},${fraction.padEnd(2,'0')}`;
}

export function dateBR(value){
  if(!value)return '—';
  // Bank dates are calendar dates, not instants to shift into the browser timezone.
  const match=/^(\d{4})-(\d{2})-(\d{2})(?:$|T| )/.exec(String(value));
  if(!match)return 'Data indisponível';
  const [,year,month,day]=match,check=new Date(`${year}-${month}-${day}T12:00:00Z`);
  if(!Number.isFinite(check.getTime())||check.toISOString().slice(0,10)!==`${year}-${month}-${day}`)return 'Data indisponível';
  return `${day}/${month}/${year}`;
}

// All monetary output uses a Brazilian decimal comma. Cover prose, SVG titles,
// options and accessible names as well as the visible financial components.
const monetary=/(?:[−+\-]\s*)?(?:R\$|US\$|[A-Z]{3}|€|£|¥)[\s\u00a0\u202f]*[−+\-]?\d(?:[\d.\u00a0\u202f]*\d)?,\d+/g;
export const maskText=value=>String(value).replace(monetary,MASK);
const moneyNames=new Set(['amount','total','amount_cents','total_cents','limit','balance']);

export function installPrivacy(doc=document,win=window){
  let visible=false;
  try{visible=win.localStorage.getItem(PRIVACY_KEY)==='true'}catch{/* Fail closed when storage is unavailable. */}
  const originals=new WeakMap(),attributes=new WeakMap(),inputs=new WeakMap();
  const button=doc.querySelector('#money-privacy-toggle');
  function project(current,entry){
    const original=entry&&current===entry.masked?entry.original:current;
    return {original,masked:maskText(original)};
  }
  function refresh(){
    const walker=doc.createTreeWalker(doc.body,win.NodeFilter.SHOW_TEXT);
    for(let node=walker.nextNode();node;node=walker.nextNode()){
      if(node.parentElement?.closest('script,style,textarea'))continue;
      const entry=project(node.data,originals.get(node));
      const next=visible?entry.original:entry.masked;
      if(entry.original!==entry.masked)originals.set(node,entry);else originals.delete(node);
      if(node.data!==next)node.data=next;
    }
    for(const element of doc.body.querySelectorAll('[title],[aria-label],[aria-valuetext]')){
      let records=attributes.get(element);if(!records){records={};attributes.set(element,records)}
      for(const name of ['title','aria-label','aria-valuetext']){
        if(!element.hasAttribute(name)){delete records[name];continue}
        const entry=project(element.getAttribute(name),records[name]);records[name]=entry;
        const next=visible?entry.original:entry.masked;
        if(element.getAttribute(name)!==next)element.setAttribute(name,next);
      }
    }
    for(const field of doc.body.querySelectorAll('input')){
      if(!moneyNames.has(field.name)&&!field.hasAttribute('data-money-input'))continue;
      let record=inputs.get(field);
      if(!record){record={type:field.type};inputs.set(field,record);field.setAttribute('data-money-input','');
        const wrapper=doc.createElement('span');wrapper.className='privacy-field';
        field.replaceWith(wrapper);wrapper.append(field);
        const cover=doc.createElement('span');cover.className='privacy-field-mask';cover.setAttribute('aria-hidden','true');cover.textContent=MASK;wrapper.append(cover);
      }
      // A password control prevents assistive technology from speaking its value.
      const type=visible?record.type:'password';if(field.type!==type)field.type=type;
    }
  }
  function apply(){
    doc.documentElement.dataset.moneyPrivacy=visible?'visible':'hidden';
    if(button){
      button.setAttribute('aria-pressed',String(visible));
      button.setAttribute('aria-label',visible?'Ocultar valores monetários':'Exibir valores monetários');
      button.title=visible?'Ocultar valores':'Exibir valores';
      button.innerHTML=`<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>${visible?'':'<path d="m3 3 18 18"/>'}</svg>`;
    }
    refresh();
  }
  if(button)button.addEventListener('click',()=>{
    visible=!visible;try{win.localStorage.setItem(PRIVACY_KEY,String(visible))}catch{/* In-memory control remains usable. */}
    apply();
  });
  // Mutation observers run before rendering: asynchronous screens and dialogs
  // are projected before the next paint. Originals live only in weak references.
  const observer=new win.MutationObserver(refresh);
  observer.observe(doc.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','aria-valuetext']});
  win.addEventListener('storage',event=>{if(event.key===PRIVACY_KEY||event.key===null){visible=event.key!==null&&event.newValue==='true';apply()}});
  apply();
  return {refresh,isVisible:()=>visible,disconnect:()=>observer.disconnect()};
}
