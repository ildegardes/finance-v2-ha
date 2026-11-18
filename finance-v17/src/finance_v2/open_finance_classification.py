"""Deterministic local classification over imported transaction identities."""
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import unicodedata

from .open_finance import SyncError

NATURES = {
    'INCOME': 'Receita pessoal ou operacional', 'EXPENSE': 'Despesa', 'SALARY': 'Salário',
    'INVESTMENT_INCOME': 'Receita de investimento', 'APPLICATION': 'Aplicação financeira',
    'REDEMPTION': 'Resgate financeiro', 'CAPITAL_RETURN': 'Restituição de capital',
    'INVESTMENT_SETTLEMENT': 'Liquidação de operação de investimento',
    'OWN_TRANSFER': 'Transferência entre contas próprias', 'SETTLEMENT': 'Liquidação de obrigação',
    'CARD_PAYMENT': 'Pagamento de fatura', 'BORROWING': 'Crédito recebido',
    'DEBT_PRINCIPAL': 'Amortização de dívida', 'CHARGE': 'Juros e encargos',
    'TAX': 'Tributo', 'REVERSAL': 'Estorno', 'INTERNAL': 'Movimentação interna',
    'UNKNOWN': 'Natureza não estabelecida',
}
REVIEW = {'CONFIRMED', 'SUGGESTED'}
ORIGINS = {'MANUAL', 'CUSTOM', 'NATIVE', 'PROVIDER', 'UNCLASSIFIED'}
PROVENTS = {'dividend':'Dividendos', 'interest_equity':'Juros sobre capital próprio',
            'distribution':'Rendimentos','fund_distribution':'Rendimentos de FIIs', 'fixed_income':'Rendimentos de renda fixa',
            'automatic':'Rendimentos de aplicação automática', 'other':'Outros proventos'}
AUTOMATIC = 'Aplic Aut Mais'
RESULT_FIELDS = {'category', 'nature', 'subcategory', 'investment', 'provent', 'asset', 'review', 'note', 'principal_only'}
CONDITION_FIELDS = {'connection_id', 'account_id', 'product', 'direction', 'category', 'operation', 'currency', 'match', 'description'}
MATCH_MODES = {'exact', 'original', 'contains', 'prefix', 'terms'}


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',',':'))


def invalid(code='CLASSIFICATION_INVALID'):
    raise SyncError(code, 422)


def string(value, limit, *, optional=False):
    if not isinstance(value, str) or len(value) > limit or (not value.strip() and not optional) or (
        value and (not value.isprintable() or any('\ud800' <= char <= '\udfff' for char in value))
    ):
        invalid()
    return value


def normalize(value):
    decomposed = unicodedata.normalize('NFKD', value.casefold())
    plain = ''.join(char for char in decomposed if not unicodedata.combining(char))
    return ' '.join(re.findall(r'[^\W_]+', plain, re.UNICODE))


def result_definition(raw):
    if not isinstance(raw, dict) or not {'category','nature'} <= raw.keys() or raw.keys() - RESULT_FIELDS:
        invalid()
    result = {'category': string(raw['category'], 120).strip(), 'nature': string(raw['nature'], 48),
              'review': string(raw.get('review','CONFIRMED'), 24)}
    if result['nature'] not in NATURES or result['review'] not in REVIEW:
        invalid()
    for field in ('subcategory','investment','note','provent','asset'):
        if field in raw:
            value = string(raw[field], 256 if field=='note' else 80, optional=True).strip()
            if value:
                result[field] = value
    if result.get('provent') and (result['nature'] != 'INVESTMENT_INCOME' or result['provent'] not in PROVENTS):
        invalid()
    if 'asset' in result:
        result['asset'] = result['asset'].upper()
        if not re.fullmatch(r'[A-Z]{4}[0-9]{1,2}', result['asset']):
            invalid()
    if 'principal_only' in raw:
        if type(raw['principal_only']) is not bool or result['nature'] != 'REDEMPTION':
            invalid()
        result['principal_only'] = raw['principal_only']
    return result


def rule_definition(raw):
    if not isinstance(raw, dict) or not {'name','description','priority','enabled','conditions','result'} <= raw.keys() or raw.keys()-{'name','description','priority','enabled','conditions','result','prospective'}:
        invalid()
    priority, enabled, conditions = raw['priority'], raw['enabled'], raw['conditions']
    if type(raw.get('prospective',True)) is not bool or type(priority) is not int or not 0 <= priority <= 999 or type(enabled) is not bool:
        invalid()
    if not isinstance(conditions, dict) or not {'connection_id','match','description'} <= conditions.keys() or conditions.keys()-CONDITION_FIELDS:
        invalid('CLASSIFICATION_SCOPE_REQUIRED')
    conditions = {key:string(value, 600 if key=='description' else 256) for key,value in conditions.items()}
    conditions = {key:value if key=='description' and conditions['match']=='original' else value.strip()
                  for key,value in conditions.items()}
    if conditions['match'] not in MATCH_MODES or not normalize(conditions['description']):
        invalid()
    if conditions.get('direction','incoming') not in ('incoming','outgoing','unknown'):
        invalid()
    if conditions.get('product','BANK') not in ('BANK','CREDIT'):
        invalid()
    if not re.fullmatch(r'[A-Z]{3}', conditions.get('currency','BRL')):
        invalid()
    return {'name':string(raw['name'],120).strip(), 'description':string(raw['description'],400,optional=True),
            'priority':priority,'enabled':enabled,'prospective':raw.get('prospective',True),'conditions':conditions,'result':result_definition(raw['result'])}


@dataclass(frozen=True)
class Facts:
    key: tuple
    institution: str
    product: str
    direction: str
    description: str
    normalized: str
    category: str
    operation: str
    currency: str
    sequence: int

    @classmethod
    def from_row(cls, row, institution, product, category):
        data = row['data']
        description = data.get('descriptionRaw') or data.get('description') or ''
        direction = {'CREDIT':'incoming','DEBIT':'outgoing'}.get(data.get('type'),'unknown')
        return cls((row['connection_id'],row['parent_id'],row['external_id']), institution, product,
                   direction, description, normalize(description), category, data.get('operationType'),
                   data.get('currencyCode'), row.get('first_sequence', 0))


def matches(conditions, facts, normalized=None):
    context = dict(connection_id=facts.key[0], account_id=facts.key[1], product=facts.product,
                   direction=facts.direction, category=facts.category, operation=facts.operation,currency=facts.currency)
    if any(context[key] != value for key,value in conditions.items() if key in context):
        return False
    source, mode = conditions['description'], conditions['match']
    if mode == 'original':
        return facts.description == source
    expected = normalized if normalized is not None else normalize(source)
    if mode == 'exact':
        return facts.normalized == expected
    if mode == 'prefix':
        return facts.normalized == expected or facts.normalized.startswith(expected+' ')
    if mode == 'contains':
        return ' '+expected+' ' in ' '+facts.normalized+' '
    return set(expected.split()) <= set(facts.normalized.split())


def _native(id, name, nature, direction, pattern, *, review='CONFIRMED', **extra):
    return (id, direction, re.compile(pattern), {'category':name,'nature':nature,'review':review,**extra})


NATIVE_RULES = (
    _native('itau-card','Pagamento de fatura','CARD_PAYMENT','outgoing',
            r'debito automatico (?:cartao itau the one|itau visa(?: [0-9]{4} [0-9]{4})?)'),
    _native('itau-automatic-apply','Aplicação automática','APPLICATION','outgoing',
            r'(?:aplicacao )?apl aplic aut mais',investment=AUTOMATIC),
    _native('itau-automatic-redeem','Resgate automático','REDEMPTION','incoming',
            r'(?:resgate )?res aplic aut mais',investment=AUTOMATIC,
            note='A composição entre principal e rendimento não foi informada.'),
    _native('itau-automatic-income','Rendimentos de aplicação automática','INVESTMENT_INCOME','incoming',
            r'(?:rendimentos? )?rend pago aplic aut mais',investment=AUTOMATIC,provent='automatic'),
    _native('itau-automatic-tax','Tributos sobre aplicações','TAX','outgoing',
            r'(?:ir|irrf|iof) (?:sobre )?aplic aut mais',investment=AUTOMATIC),
    _native('itau-automatic-charge','Encargos de aplicação automática','CHARGE','outgoing',
            r'(?:tarifa|encargo) aplic aut mais',investment=AUTOMATIC),
    _native('itau-treasury-buy','Aplicação em Tesouro Direto','APPLICATION','outgoing',
            r'(?:saida )?cor (?:itaucor )?compra td',investment='Tesouro Direto'),
    _native('itau-treasury-redeem','Resgate de Tesouro Direto','REDEMPTION','incoming',
            r'(?:entrada )?cor (?:itaucor )?(?:venda|resgate) td',investment='Tesouro Direto'),
    _native('itau-b3','Operações de investimento','INVESTMENT_SETTLEMENT','outgoing',
            r'(?:saida )?cor operacoes b3',review='SUGGESTED',note='A descrição não discrimina os componentes da liquidação.'),
    _native('itau-distribution','Rendimentos de investimentos','INVESTMENT_INCOME','incoming',
            r'(?:entrada )?cor rendimentos?(?: (?P<asset>[a-z]{4}[0-9]{1,2}))?',provent='distribution'),
    _native('itau-dividend','Dividendos','INVESTMENT_INCOME','incoming',
            r'(?:entrada )?cor dividendos?(?: (?P<asset>[a-z]{4}[0-9]{1,2}))?',provent='dividend'),
    _native('itau-jscp','Juros sobre capital próprio','INVESTMENT_INCOME','incoming',
            r'(?:entrada )?cor (?:jscp|jcp|juros sobre capital proprio)(?: (?P<asset>[a-z]{4}[0-9]{1,2}))?',
            provent='interest_equity'),
    _native('itau-fixed-income','Rendimentos de renda fixa','INVESTMENT_INCOME','incoming',
            r'(?:entrada )?cor (?:juros|cupom|rendimentos?) (?:renda fixa|tesouro direto)',provent='fixed_income'),
    _native('itau-capital-return','Restituição de capital','CAPITAL_RETURN','incoming',
            r'(?:entrada )?cor (?:amortizacao|restituicao de capital)(?: (?P<asset>[a-z]{4}[0-9]{1,2}))?'),
)
NATIVE_VERSION = 1


def native_catalog():
    return [{'id':id,'direction':direction,'bank':'Itaú','pattern':pattern.pattern,'revision':NATIVE_VERSION,
             'result':result} for id,direction,pattern,result in NATIVE_RULES]


def native(facts):
    name = normalize(facts.institution)
    if facts.product != 'BANK' or facts.currency != 'BRL' or not re.fullmatch(
        r'itau(?: (?:unibanco|itau|personnalite|banco itau|unibanco s a))?', name
    ):
        return None
    for id,direction,pattern,result in NATIVE_RULES:
        match = pattern.fullmatch(facts.normalized) if direction == facts.direction else None
        if match:
            asset = match.groupdict().get('asset')
            return {**result, 'origin':'NATIVE','rule_id':id,'rule_revision':NATIVE_VERSION,
                    'condition':facts.normalized, **({'asset':asset.upper()} if asset else {})}
    return None


class Classifier:
    def __init__(self, db, connection_ids):
        scope = encode(list(connection_ids))
        self.overrides = {tuple(row[k] for k in ('connection_id','account_id','transaction_id')):
                          (row['id'], json.loads(row['decision_json']) if row['decision_json'] else None)
                          for row in db.execute("""SELECT connection_id,account_id,transaction_id,id,decision_json
                            FROM of_classification_current WHERE connection_id IN (SELECT value FROM json_each(?))""",(scope,))}
        self.rules = defaultdict(lambda: defaultdict(list))
        self.disabled_natives = set()
        for row in db.execute("""SELECT rule_id,revision,after_run,definition_json FROM of_classification_rule_revisions
                                 ORDER BY rule_id,revision DESC"""):
            rule = json.loads(row['definition_json'])
            if 'native_id' in rule:
                continue
            cond = rule['conditions']
            if cond['connection_id'] in connection_ids:
                self.rules[cond['connection_id']][row['rule_id']].append(
                    (row['after_run'],row['revision'],rule,normalize(cond['description'])))
        for (definition,) in db.execute("""SELECT v.definition_json FROM of_classification_rules r
                JOIN of_classification_rule_revisions v ON v.rule_id=r.id AND v.revision=r.revision
                WHERE r.id LIKE 'native:%'"""):
            switch = json.loads(definition)
            if not switch['enabled']:
                self.disabled_natives.add(switch['native_id'])

    def classify(self, facts, provider_category):
        event, override = self.overrides.get(facts.key,(None,None))
        if override is not None:
            return {**override,'event':event}
        candidates = []
        for id, history in self.rules.get(facts.key[0],{}).items():
            version = next((v for v in history if facts.sequence > v[0]),None)
            if version:
                _, revision, rule, normalized = version
                if rule['enabled'] and rule.get('prospective',True) and matches(rule['conditions'],facts,normalized):
                    candidates.append((rule['priority'],id,revision,rule))
        inferred = None
        if candidates:
            ranked = sorted(candidates,key=lambda candidate:(-candidate[0],candidate[1]))
            priority,id,revision,winner = ranked[0]
            tied = [candidate for candidate in ranked if candidate[0]==priority]
            if len({encode(candidate[3]['result']) for candidate in tied}) > 1:
                inferred = {'category':None,'nature':'UNKNOWN','origin':'CUSTOM','review':'CONFLICT',
                            'conflicts':[candidate[1] for candidate in tied]}
            else:
                inferred = custom_decision(id,revision,winner)
        else:
            item = native(facts)
            if item and item['rule_id'] not in self.disabled_natives:
                inferred = item
        return {**(inferred or {'category':None,'nature':'UNKNOWN',
                               'origin':'PROVIDER' if provider_category!='missing' else 'UNCLASSIFIED',
                               'review':'UNCLASSIFIED'}), 'event':event}


def custom_decision(id, revision, rule):
    return {**rule['result'],'origin':'CUSTOM','rule_id':id,'rule_revision':revision,
            'condition':rule['conditions']['description'],
            'priority':rule['priority']}
