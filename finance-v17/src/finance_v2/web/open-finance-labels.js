const key=value=>String(value??'').normalize('NFKC').trim().toUpperCase().replace(/[_-]+/g,' ').replace(/\s+/g,' ');

const investments=new Map([
  ['EQUITY','Renda variável'],['FIXED INCOME','Renda fixa'],['MUTUAL FUND','Fundos de investimento'],
  ['FUND','Fundos de investimento'],['OTHER','Outros investimentos'],['SECURITY','Previdência'],['STOCK','Ações'],['ETF','ETF'],['CDB','CDB'],['LCI','LCI'],
  ['LCA','LCA'],['TREASURY','Títulos do Tesouro'],['PENSION','Previdência'],['CRYPTO','Criptoativos'],
  ['COE','COE'],['SAVINGS','Poupança'],['DEBENTURE','Debêntures'],['FII','Fundos imobiliários'],
]);
const categories=new Map([
  ['INVESTMENTS','Investimentos'],['INVESTMENT','Investimentos'],['SAME PERSON TRANSFER','Transferência entre contas próprias'],['KINDERGARTEN','Educação infantil'],
  ['BOOKSTORE','Livrarias'],['BOOKSTORES','Livrarias'],['LIVRARIAS','Livrarias'],['SERVICES','Serviços'],
  ['CHILDCARE','Educação infantil'],['ELECTRICITY','Energia elétrica'],['SUPERMERCADOS','Supermercados'],
  ['RESTAURANTES','Restaurantes'],['INTERNET','Internet'],['TELEFONIA','Telefonia'],
  ['FOOD','Alimentação'],['RESTAURANTS','Restaurantes'],['GROCERIES','Supermercado'],
  ['SHOPPING','Compras'],['TRANSPORTATION','Transporte'],['HEALTH','Saúde'],['PHARMACY','Farmácia'],
  ['EDUCATION','Educação'],['ENTERTAINMENT','Entretenimento'],['HOUSING','Moradia'],
  ['SALARY','Salário'],['TAXES','Tributos'],['TRANSFER','Transferência'],['CREDIT CARD PAYMENT','Pagamento de fatura'],
]);
const states=new Map([
  ['POSTED','Efetivada'],['PENDING','Pendente'],['ACTIVE','Ativa'],['DISABLED','Desativada'],
  ['ARCHIVED','Arquivada'],['DRAFT','Em preparação'],['REMOVED','Removida'],
  ['PAID','Paga'],['OPEN','Em aberto'],['CLOSED','Encerrada'],['CANCELLED','Cancelada'],
  ['OVERDUE','Em atraso'],['UNRECONCILED','Sem conciliação'],['NOT ESTABLISHED','Não estabelecida'],
  ['AVAILABLE','Disponível'],['COMPLETE','Cobertura informada'],['EMPTY','Consulta sem registros'],
  ['PARTIAL','Cobertura parcial'],['NOT AUTHORIZED','Acesso não autorizado'],
  ['NOT AVAILABLE','Indisponível'],['NOT COLLECTED','Ainda não coletado'],
  ['FAILED','Falha na coleta'],['RUNNING','Em andamento'],['SUCCEEDED','Concluída'],
  ['INTERRUPTED','Interrompida'],['STALE','Desatualização informada'],['NOT QUERIED','Consulta não realizada'],
]);
const types=new Map([
  ['BANK','Conta bancária'],['CHECKING ACCOUNT','Conta corrente'],['SAVINGS ACCOUNT','Conta poupança'],['CREDIT','Crédito'],['DEBIT','Débito'],['CHECKING','Conta corrente'],
  ['SAVINGS','Poupança'],['CREDIT CARD','Cartão de crédito'],['PERSONAL LOAN','Empréstimo pessoal'],
  ['LOAN','Empréstimo'],['PAYROLL LOAN','Consignado'],['FINANCING','Financiamento'],
  ['MORTGAGE','Crédito imobiliário'],['OVERDRAFT','Cheque especial'],
]);

export const statusLabel=(value,fallback='Situação não informada')=>states.get(key(value))??(key(value)?'Situação não identificada':fallback);
export const runStateLabel=value=>key(value)==='FAILED'?'Falhou':statusLabel(value);
export const coverageLabel=value=>states.get(key(value))??'Cobertura não estabelecida';
const internationalClasses={FIXED_INCOME:'Renda fixa',STOCK:'Stocks',REIT:'REITs',ETF:'ETFs',
  FUND:'Fundos de investimento',FII:'FIIs',OTHER:'Outros instrumentos',UNKNOWN:'Não classificado'};

export const investmentClassLabel=value=>String(value).startsWith('PLUGGY:')?
  classLabel(value.slice(7)):internationalClasses[value]||classLabel(value);

export const classLabel=value=>investments.get(key(value))??(key(value)&&key(value)!=='NÃO INFORMADA'?'Classe não identificada':'Classe não informada');
export const typeLabel=value=>types.get(key(value))??(key(value)?'Tipo não identificado':'Tipo não informado');
export function categoryLabel(category){
  if(!category || category.key==='missing')return 'Sem categoria';
  if(category.key==='other')return 'Outras';
  if(category.translated)return category.name;
  const raw=String(category.name??'').trim();
  if(!raw||category.has_name===false)return 'Categoria não identificada';
  // Retain recognizable Portuguese source names, including owner-entered labels.
  return categories.get(key(raw))??(/[áàâãéêíóôõúç]/iu.test(raw)?raw:'Categoria não identificada');
}

export function institutionName(value){
  const name=String(value??'').trim();
  if(/^Santander(?:\s*[-–]\s*Banco Santander(?: Pessoa Física)?)?$/i.test(name))return 'Santander';
  if(/^Ita[uú](?:\s*[-–]\s*ita[uú])?$/i.test(name))return 'Itaú';
  return name||'Instituição indisponível';
}

export const percentBR=new Intl.NumberFormat('pt-BR',{style:'percent',maximumFractionDigits:1});
export const countBR=new Intl.NumberFormat('pt-BR');
