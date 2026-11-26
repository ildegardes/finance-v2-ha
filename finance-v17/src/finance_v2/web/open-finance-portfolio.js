import {dateBR} from './privacy.js';

const DAY_MS=86400000;

function pointContext(point,esc){
  const references=point.references||[];
  const dates=references.length>1?dateBR(references[0])+' a '+dateBR(references.at(-1)):
    references.length===1?dateBR(references[0]):'';
  const rates=(point.fx_rates||[point.fx]).filter(Boolean).map(rate=>dateBR(rate.date));
  const details=[dates?'Referências financeiras '+dates:'',
    point.undated?'Há ativos sem referência financeira':'',
    rates.length?'PTAX '+rates.join(', '):''].filter(Boolean);
  return details.length?'<small>'+esc(details.join(' · '))+'</small>':'';
}

function series(points,amount,esc,currency=''){
  const values=points.map(point=>Number(point.value));
  const dates=points.map(point=>Date.parse(point.date+'T00:00:00Z'));
  const first=points[0],last=points.at(-1),lastIndex=points.length-1;
  const width=720,height=166,pad=14;
  const duration=dates.at(-1)-dates[0];
  const max=Math.max(...values),min=Math.min(...values);
  const x=index=>duration?pad+(width-2*pad)*(dates[index]-dates[0])/duration:width/2;
  const y=value=>height-pad-(height-2*pad)*(min===max?.5:(value-min)/(max-min));
  const horizontal=[pad,height/2,height-pad].map(level=>
    '<line class="of-series-grid" x1="'+pad+'" y1="'+level+'" x2="'+(width-pad)+'" y2="'+level+'"></line>').join('');
  const lines=values.slice(1).map((value,index)=>
    '<line class="of-series-line'+(dates[index+1]-dates[index]>DAY_MS?' of-series-gap':'')+'" x1="'+x(index)+
    '" y1="'+y(values[index])+'" x2="'+x(index+1)+'" y2="'+y(value)+'"></line>').join('');
  const marks=values.map((value,index)=>'<circle data-series-marker="'+index+'" class="'+(index===lastIndex?'of-series-selected':'')+
    '" cx="'+x(index)+'" cy="'+y(value)+'" r="'+(index===lastIndex?5:3)+'"><title>'+
    esc(dateBR(points[index].date))+'</title></circle>').join('');
  const ticks=[first.date];
  if(duration>=14*DAY_MS)ticks.push(new Date(dates[0]+duration/2).toISOString().slice(0,10));
  if(lastIndex)ticks.push(last.date);
  return '<div class="of-portfolio-series">'+(currency?'<h4>'+esc(currency)+'</h4>':'')+
    '<div class="of-portfolio-dates"><span>Mínimo '+amount(points[values.indexOf(min)].value)+
    '</span><span>Máximo '+amount(points[values.indexOf(max)].value)+'</span></div>'+
    '<svg class="of-portfolio-plot" viewBox="0 0 '+width+' '+height+'" preserveAspectRatio="none" role="img" aria-label="Observações da posição patrimonial">'+
    horizontal+lines+marks+'</svg><div class="of-portfolio-dates">'+
    ticks.map(date=>'<time datetime="'+esc(date)+'">'+esc(dateBR(date))+'</time>').join('')+'</div>'+
    '<div class="of-portfolio-inspect"><label>Inspecionar observação<select data-portfolio-point>'+
    points.map((point,index)=>'<option value="'+index+'" '+(index===lastIndex?'selected':'')+'>'+esc(dateBR(point.date))+'</option>').join('')+
    '</select></label><output aria-live="polite"><strong>'+amount(last.value)+'</strong>'+pointContext(last,esc)+'</output></div>'+
    '<details><summary>Observações em texto</summary><ul class="of-category-list">'+points.map(point=>
      '<li><time datetime="'+esc(point.date)+'">'+esc(dateBR(point.date))+'</time><div data-series-value><strong>'+
      amount(point.value)+'</strong>'+pointContext(point,esc)+'</div></li>').join('')+'</ul></details></div>';
}

export function selectPortfolioPoint(control){
  const chart=control.closest('.of-portfolio-series');
  const index=Number(control.value);
  const value=chart.querySelectorAll('[data-series-value]')[index];
  if(!value)return;
  chart.querySelector('output').replaceChildren(...[...value.children].map(node=>node.cloneNode(true)));
  for(const marker of chart.querySelectorAll('[data-series-marker]')){
    const selected=Number(marker.dataset.seriesMarker)===index;
    marker.classList.toggle('of-series-selected',selected);
    marker.setAttribute('r',selected?'5':'3');
  }
}

export function portfolioPanel(history,amount,mode,esc,originalAmount=amount){
  if(!history)return '';
  const points=history.points;
  const observed=history.basis==='COLLECTION_DATE';
  const periods=[['1','1 mês'],['3','3 meses'],['6','6 meses'],['12','12 meses'],['all','Todo o histórico']];
  const select='<label>Intervalo patrimonial<select data-portfolio-window aria-label="Intervalo patrimonial">'+periods.map(
    ([key,label])=>'<option value="'+key+'" '+(key===history.window?'selected':'')+'>'+label+'</option>'
  ).join('')+'</select></label>';
  const banks=history.connections?.length?'<label>Instituição da série<select data-portfolio-connection>'+
    '<option value="">'+(history.consolidated?'Patrimônio consolidado':'Seleção automática')+'</option>'+history.connections.map(row=>'<option value="'+esc(row.id)+'" '+
      (row.id===history.connection_id?'selected':'')+'>'+esc(row.label)+(row.eligible?'':' · sem observações')+'</option>').join('')+
    '</select></label>':'';
  let content='<p class="of-chart-placeholder">'+(history.state==='SELECT_CONNECTION'?'Selecione uma conexão para comparar posições sem sobreposição.':
    history.state==='OVERLAP'?'Possível sobreposição. Selecione uma instituição.':
    history.state==='LIMIT'?'Selecione um intervalo menor para consultar o histórico.':
    history.consolidated&&!history.connection_id?'Sem série consolidada neste intervalo. Selecione uma instituição para ver suas observações.':
    'Nenhuma observação de carteira disponível neste intervalo.')+'</p>';
  if(points.length&&mode==='full'){
    content='<p class="of-chart-placeholder">Evolução oculta em privacidade total.</p>';
  }else if(points.length){
    const first=points[0],last=points.at(-1);
    if(first.original){
      content=Object.keys(first.original).map(currency=>{
        const rows=points.filter(point=>point.original?.[currency]!=null).map(point=>({...point,value:point.original[currency]}));
        return series(rows,value=>originalAmount(value,currency),esc,currency);
      }).join('');
    }else{
      content=(points.length>1?'<div class="of-portfolio-values"><span>Posição inicial <strong>'+amount(first.value)+
        '</strong></span><span>Última posição da série <strong>'+amount(last.value)+'</strong></span>'+
        '<span>Variação entre observações <strong>'+amount(history.change)+'</strong>'+
        (history.percent==null?'':' · '+esc(new Intl.NumberFormat('pt-BR',{maximumFractionDigits:2}).format(Number(history.percent)))+'%')+
        '</span></div>':'<p>Uma observação registrada neste intervalo.</p>')+series(points,amount,esc);
    }
  }else if(history.latest_position!=null){
    content+='<p>Última posição disponível <strong>'+amount(history.latest_position)+'</strong></p>';
  }
  const basis=observed?'Posições por data de coleta (UTC) · referências dos ativos podem diferir':
    'Posições por data de referência financeira';
  const count=points.length?' · '+new Intl.NumberFormat('pt-BR').format(points.length)+(points.length===1?' observação':' observações'):'';
  return '<section class="of-summary-card of-portfolio"><div class="of-section-heading"><div><h3>Evolução dos investimentos</h3><p>'+
    esc(basis+count)+'</p></div><div class="of-portfolio-filters">'+banks+select+'</div></div>'+content+
    '<p>Variações podem incluir aportes, resgates e mudanças de mercado.</p>'+
    '<button class="of-link" type="button" data-open-assets>Ver investimentos</button></section>';
}
