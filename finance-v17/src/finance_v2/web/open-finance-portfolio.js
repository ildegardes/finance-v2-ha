import {dateBR} from './privacy.js';

export function portfolioPanel(history,amount,mode,esc){
  if(!history)return '';
  const points=history.points;
  const periods=[['3','3 meses'],['6','6 meses'],['12','12 meses'],['all','Todo o histórico']];
  const select='<label>Intervalo patrimonial<select data-portfolio-window aria-label="Intervalo patrimonial">'+periods.map(
    ([key,label])=>'<option value="'+key+'" '+(key===history.window?'selected':'')+'>'+label+'</option>'
  ).join('')+'</select></label>';
  const available=history.state==='AVAILABLE';
  let content='<p class="of-chart-placeholder">'+(history.state==='SELECT_CONNECTION'?'Selecione uma conexão para comparar posições sem sobreposição.':
    history.state==='LIMIT'?'O histórico ultrapassa o orçamento de consulta. Selecione um intervalo menor.':'Histórico patrimonial em formação.')+'</p>';
  if(history.first_observed_at)content+='<p>Primeira observação registrada '+esc(dateBR(history.first_observed_at))+'.</p>';
  if(available&&mode!=='full'){
    const width=700,height=138,pad=10;
    const values=points.map(point=>Number(point.value));
    const dates=points.map(point=>Date.parse(point.date+'T00:00:00Z'));
    const max=values.reduce((a,b)=>Math.max(a,b),-Infinity),min=values.reduce((a,b)=>Math.min(a,b),Infinity);
    const x=index=>pad+(width-2*pad)*(dates[index]-dates[0])/(dates.at(-1)-dates[0]);
    const y=value=>height-pad-(height-2*pad)*(max===min?.5:(value-min)/(max-min));
    const line=values.map((value,index)=>x(index)+','+y(value)).join(' ');
    const marks=values.map((value,index)=>'<circle cx="'+x(index)+'" cy="'+y(value)+'" r="3"></circle>').join('');
    const first=points[0],last=points.at(-1);
    content='<div class="of-portfolio-values"><span>Posição inicial <strong>'+amount(first.value)+'</strong></span><span>Última posição da série <strong>'+amount(last.value)+'</strong></span><span>Variação patrimonial <strong>'+amount(history.change)+'</strong>'+
      (history.percent==null?'':' · '+esc(new Intl.NumberFormat('pt-BR',{maximumFractionDigits:2}).format(Number(history.percent)))+'%')+'</span></div>'+
      '<svg class="of-portfolio-plot" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="Observações da posição patrimonial"><polyline points="'+line+'"></polyline>'+marks+'</svg>'+
      '<div class="of-portfolio-dates"><time>'+esc(dateBR(first.date))+'</time><time>'+esc(dateBR(last.date))+'</time></div>'+
      '<details><summary>Observações em texto</summary><ul class="of-category-list">'+points.map(point=>'<li><span>'+esc(dateBR(point.date))+'</span><strong>'+amount(point.value)+'</strong></li>').join('')+'</ul></details>';
  }else if(available)content='<p class="of-chart-placeholder">Evolução oculta em privacidade total.</p>';
  return '<section class="of-summary-card of-portfolio"><div class="of-section-heading"><div><h3>Evolução dos investimentos</h3><p>Posições observadas em datas comparáveis</p></div>'+select+'</div>'+content+'<p>Variações podem incluir aportes, resgates e mudanças de mercado.</p><button class="of-link" type="button" data-open-assets>Ver investimentos</button></section>';
}
