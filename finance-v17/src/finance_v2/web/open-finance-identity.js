const normalized=value=>String(value??'').normalize('NFD').replace(/\p{M}/gu,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();

function bankType(value){
  const name=normalized(value);
  if(/^(itau(?:\s|$)|banco itau(?:\s|$))/.test(name))return 'itau';
  if(/^(santander(?:\s|$)|banco santander(?:\s|$))/.test(name))return 'santander';
  return 'generic';
}

export function bankMark(value,esc){
  const kind=bankType(value);
  const label=kind==='itau'?'IT':kind==='santander'?'SA':String(value||'Instituição').trim().slice(0,2).toLocaleUpperCase('pt-BR');
  return '<span class="of-bank-mark '+kind+'" aria-hidden="true">'+esc(label)+'</span>';
}

export function cardIdentity(card,esc){
  const bank=bankType(card.institution),name=normalized(card.name),brand=normalized(card.brand);
  let product='generic',label=card.name||'Cartão sem nome';
  if(bank==='itau'&&/\bthe one\b/.test(name)){product='one';label='Personnalité The One';}
  if(bank==='itau'&&/\bazul\b/.test(name)&&/\binfinite\b/.test(name)){product='azul';label='Azul Itaú Visa Infinite';}
  if(bank==='santander'&&/\bunlimited\b/.test(name)){
    if(/\bvisa\b/.test(brand||name)&&/\binfinite\b/.test(name)){product='infinite';label='Unlimited Visa Infinite';}
    if(/\b(?:mastercard|mc)\b/.test(brand||name)&&/\bblack\b/.test(name)){product='black';label='Unlimited Mastercard Black';}
  }
  const network=/\bvisa\b/.test(brand||name)?'Visa':/\b(?:mastercard|mc)\b/.test(brand||name)?'Mastercard':'';
  const tail=/[•*]{2,}\s*(\d{4})(?!\d)/.exec(card.name||'')?.[1];
  return {label:label.replace(/\s*[•*]{2,}\s*\d{4}(?!\d)/,'').trim(),tail,network,
    mark:'<span class="of-card-mark '+product+'" aria-hidden="true"><i></i></span>'};
}
