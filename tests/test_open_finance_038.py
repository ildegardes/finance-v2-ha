"""Synthetic reconciliation for the unified Open Finance presentation."""
from contextlib import closing
from dataclasses import replace
from datetime import date
from decimal import Decimal
import hashlib
import json
import unittest

from finance_v2.db import connect
from finance_v2.open_finance_analytics import analytics
from finance_v2.open_finance_wealth import report
from finance_v2.pluggy_coverage import project
from finance_v2.open_finance_relations import record_batch
from finance_v2.portfolio_fx import refresh
from finance_v2.snaptrade_sync import connection_policy
import test_snaptrade_036 as fixture

SECOND='bank-santander'
DATE=fixture.TODAY
BEFORE='2026-10-19'
DUE='2026-10-28'
REIT='73000000-0000-4000-8000-000000000038'
ETF='73000000-0000-4000-8000-000000000039'
UNKNOWN='73000000-0000-4000-8000-000000000040'


def seed(test):
    test.broker.second=False
    base=test.broker.read
    reference=fixture.STAMP
    test.broker.reference=BEFORE+'T17:00:00Z'
    assert test.run_sync()['state']=='AVAILABLE'
    test.broker.reference=reference

    def read(op,**kwargs):
        body=base(op,**kwargs)
        if op=='positions':
            for id,kind,name,price in [(REIT,'stock','REAL',2000),(ETF,'etf','INDEX',1000),(UNKNOWN,'other','UNK',400)]:
                body['results'].append({'instrument':{'id':id,'kind':kind,'symbol':name,'exchange':'XNYS'},
                                        'currency':'USD','units':'1','price':str(price)})
        return body

    test.broker.read=read
    for n,(kind,amount,id,ticker,security) in enumerate([
        ('DIVIDEND','4',REIT,'REAL',{'description':'Real Estate Investment Trust'}),
        ('DIVIDEND','2',ETF,'INDEX',{'code':'et'}),('WITHHOLDING','-2',REIT,'REAL',{}),
    ]):
        test.broker.activities.append({'id':f'new-038-{n}','type':kind,'trade_date':DATE,'amount':amount,
            'currency':{'code':'USD'},'description':'Evento sintético','symbol':{'id':id,'symbol':ticker,'type':security}})
    assert test.run_sync()['state']=='AVAILABLE'
    test.settings=replace(test.settings,pluggy_connections=test.settings.pluggy_connections+
                          (replace(test.settings.pluggy_connections[0],id=SECOND,institution='Santander'),))
    db_path=test.case.db
    with closing(connect(db_path)) as db:
        db.execute("BEGIN")
        db.execute("INSERT INTO of_connections(id,institution,enabled,binding_hash,updated_at) VALUES (?,'Santander',1,?,?)",
                   (SECOND,'a'*64,fixture.STAMP))
        db.execute("INSERT INTO of_connection_registry(connection_id,source,lifecycle,label,updated_at) VALUES (?,'LEGACY','ACTIVE','Santander',?)",
                   (SECOND,fixture.STAMP))
        current=db.execute("SELECT id FROM of_sync_runs WHERE connection_id='bank-test' AND state='SUCCEEDED' LIMIT 1").fetchone()[0]
        new_run='e'*32
        for run,cid in [(new_run,SECOND),('a'*32,'bank-test'),('b'*32,'bank-test'),('c'*32,SECOND)]:
            db.execute("""INSERT INTO of_sync_runs(id,connection_id,actor,started_at,finished_at,state)
                      VALUES (?,?,'UI:local',?,?,'SUCCEEDED')""",(run,cid,fixture.STAMP,fixture.STAMP))

        def add(cid,resource,parent,external,body,run=current):
            payload=json.dumps(body,ensure_ascii=False,sort_keys=True)
            db.execute("""INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,
                payload_hash,state,first_run_id,last_run_id,observed_at) VALUES (?,?,?,?,?,?,'PRESENT',?,?,?)
                ON CONFLICT(connection_id,resource,parent_id,external_id) DO UPDATE SET payload_json=excluded.payload_json,
                payload_hash=excluded.payload_hash,last_run_id=excluded.last_run_id,observed_at=excluded.observed_at""",
                (cid,resource,parent,external,payload,hashlib.sha256(payload.encode()).hexdigest(),run,run,fixture.STAMP))

        db.execute("UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.date','2026-09-01') WHERE resource='transactions'")
        db.execute("UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.balance',1000,'$.date',?) WHERE external_id='account-BANK'",(DATE,))
        add(SECOND,'accounts','','bank-038',{'type':'BANK','name':'Conta Santander','currencyCode':'BRL','balance':2000,'date':DATE},new_run)
        add(SECOND,'investments','','fund-038',{'type':'EQUITY','subtype':'REAL_ESTATE_FUND','name':'FII sintético',
            'market':'B3','currencyCode':'BRL','balance':50000,'date':DATE},new_run)
        for run,cid,key,point,value in [('a'*32,'bank-test','tesouro',BEFORE,'99000'),
            ('b'*32,'bank-test','tesouro',DATE,'100000'),('c'*32,SECOND,'fund',BEFORE,'49000'),(new_run,SECOND,'fund',DATE,'50000')]:
            db.execute("""INSERT INTO of_portfolio_snapshots(run_id,connection_id,external_id,currency,value,reference_date,observed_at)
                          VALUES (?,?,?,'BRL',?,?,?)""",(run,cid,key,value,point,fixture.STAMP))
        for ext,amount,description,direction,currency,when in [
            ('div-br-038',12,'Entrada COR JSCP MACA3','CREDIT','BRL',DATE),
            ('salary-038',100,'Salário confirmado','CREDIT','BRL',DATE),
            ('expense-038',20,'Energia elétrica','DEBIT','USD',BEFORE),
            ('internal-038',300,'Aplicação automática','DEBIT','BRL',DATE),
        ]:
            add('bank-test','transactions','account-BANK',ext,{'id':ext,'type':direction,'status':'POSTED',
                'date':when,'description':description,'currencyCode':currency,'amount':amount})
            recognition={
                'div-br-038':{'category':'Rendimentos','nature':'INVESTMENT_INCOME','provent':'interest_equity','asset':'MACA3'},
                'salary-038':{'category':'Salário','nature':'SALARY'},
                'expense-038':{'category':'Energia','nature':'EXPENSE'},
                'internal-038':{'category':'Aplicação','nature':'APPLICATION'},
            }[ext]
            db.execute("""INSERT INTO of_classification_events(connection_id,account_id,transaction_id,action,decision_json,recorded_at,actor)
                          VALUES ('bank-test','account-BANK',?,'MANUAL',?,?,'UI:local')""",
                       (ext,json.dumps({**recognition,'origin':'MANUAL','review':'CONFIRMED'}),fixture.STAMP))
        item=test.settings.pluggy_connections[0].item_id
        item_payload={'id':item,'status':'UPDATED','connector':{'id':601,'isOpenFinance':True}}
        consent={'id':'consent-039','itemId':item,'products':['CREDIT_CARDS'],
                 'openFinancePermissionsGranted':['CREDIT_CARDS_ALL'],'revokedAt':None}
        for resource,payload in [('item',item_payload),('consents',consent)]:
            add('bank-test',resource,'',payload['id'],project(resource,payload)[0])
        for resource,payloads in [('consents',[consent]),('accounts',[None]*4)]:
            record_batch(db,'bank-test',{'resource':resource,'parent':'','state':'AVAILABLE','last':True,'rows':payloads},
                         current,fixture.STAMP)
        for index,ext in enumerate(['account-CREDIT','card-extra','card-repeat','card-missing']):
            suffix=('T' if index==0 else str(index))
            balance=[320,180,0,0][index]
            tail=str(9400+index)
            card={'id':ext,'itemId':item,'type':'CREDIT','subtype':'CREDIT_CARD','currencyCode':'BRL',
                  'name':'Cartão sintético '+suffix,'number':'xxxx'+tail,'balance':balance,'updatedAt':fixture.STAMP,
                  'creditData':{'status':'ACTIVE','brand':'VISA','holderType':'MAIN','creditLimit':1000,'balanceDueDate':DUE,
                                'disaggregatedCreditLimits':[{'creditLineLimitType':'LIMITE_CREDITO_TOTAL',
                                     'consolidationType':'INDIVIDUAL','identificationNumber':tail,
                                     'usedAmount':balance,'usedAmountCurrencyCode':'BRL','limitAmount':1000,
                                     'limitAmountCurrencyCode':'BRL','isLimitFlexible':False}]}}
            add('bank-test','accounts','',ext,project('accounts',card)[0])
            if index!=3:
                total=50 if index==1 else 100
                add('bank-test','bills',ext,'bill-second' if index==1 else 'bill-test',
                    {'dueDate':DUE,'totalAmount':total,'totalAmountCurrencyCode':'BRL','billClosingDate':BEFORE,
                     'payments':[{'amount':80,'currencyCode':'BRL'}]})
            if index in (1,2):
                db.execute("""INSERT INTO of_resource_coverage(connection_id,resource,parent_id,state,run_id,observed_at,record_count)
                              VALUES ('bank-test','bills',?,'AVAILABLE',?,?,1)""",(ext,current,fixture.STAMP))
        db.commit()
    refresh(test.service,date.fromisoformat(BEFORE),date.fromisoformat(DATE),
            transport=lambda *_:[{'dataHoraCotacao':day+' 13:00:00','cotacaoVenda':rate}
                                  for day,rate in [(BEFORE,4),(DATE,5)]])


def mixed_history(test):
    with closing(connect(test.case.db)) as db:
        for run,observed,reference,value in (
                ('a'*32,BEFORE,'2026-10-18','300'),('b'*32,DATE,BEFORE,'350')):
            stamp=observed+'T17:00:00Z'
            db.execute('UPDATE of_sync_runs SET started_at=?,finished_at=? WHERE id=?',(stamp,stamp,run))
            db.execute('UPDATE of_portfolio_snapshots SET observed_at=? WHERE run_id=?',(stamp,run))
            db.execute("""INSERT INTO of_portfolio_snapshots(run_id,connection_id,external_id,currency,value,reference_date,observed_at)
                          VALUES (?,'bank-test','second-holding','BRL',?,?,?)""",(run,value,reference,stamp))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.SnapTradeTests('test_discovery_currency_and_cash_once')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        seed(self.fixture)

    def view(self,target='BRL',**kwargs):
        q={**{'presentation':target,'start':'2026-10-01','end':DATE,'product':'ALL'},**kwargs}
        with closing(connect(self.fixture.case.db)) as db:
            return analytics(db,self.fixture.settings,{k:[v] for k,v in q.items()},DATE)['presentation_view']

    @staticmethod
    def value(scope,key):
        return Decimal(scope['amounts'][key])

    def test_original_and_converted_kpis_card_dedup_and_economic_income(self):
        br=self.view()
        self.assertEqual(self.value(br['accounts'],'BRL'),3000)
        self.assertEqual(self.value(br['investments'],'BRL'),267000)
        self.assertEqual(self.value(br['cash'],'BRL'),2500)
        self.assertEqual(self.value(br['incoming'],'BRL'),112)
        self.assertEqual(self.value(br['outgoing'],'BRL'),80)
        self.assertEqual(self.value(br['cards']['metric'],'BRL'),500)
        self.assertEqual((br['cards']['included_count'],br['cards']['count']),(4,4))
        self.assertEqual(br['cards']['utilization_by_currency'],{'BRL':'0.125'})
        self.assertEqual(self.value(br['income']['credits'],'BRL'),92)
        self.assertEqual(self.value(br['income']['tax'],'BRL'),Decimal('16.25'))
        self.assertIsNone(br['income']['net'])
        self.assertEqual({row['class'] for row in br['composition']},{'PLUGGY:TREASURY','PLUGGY:EQUITY','STOCK','REIT','ETF','UNKNOWN'})
        self.assertIn('foreign_withholding',{row['kind'] for row in br['income']['by_kind']})
        us=self.view('USD')
        self.assertEqual(self.value(us['investments'],'USD'),53400)
        self.assertEqual(self.value(us['cards']['metric'],'USD'),100)
        self.assertEqual(self.value(us['outgoing'],'USD'),20)
        original=self.view('original')
        self.assertEqual({k:Decimal(v) for k,v in original['investments']['amounts'].items()},{'BRL':150000,'USD':23400})
        self.assertEqual({row['institution'] for row in original['institutions']},{'Itaú','Santander','Charles Schwab'})

    def test_history_values_use_each_date_and_ignore_period(self):
        value=self.view(end=BEFORE)
        self.assertEqual(value['history']['state'],'AVAILABLE')
        self.assertEqual([(p['date'],Decimal(p['value'])) for p in value['history']['points']],[(BEFORE,228000),(DATE,267000)])
        self.assertEqual([p['fx']['rate'] for p in value['history']['points']],['4','5'])
        snap=next(row['id'] for row in value['history']['connections'] if row['label']=='Charles Schwab')
        individual=self.view('USD',connection_id=snap,portfolio_connection=snap)
        self.assertEqual({row['institution'] for row in individual['institutions']},{'Charles Schwab'})
        self.assertEqual(self.value(individual['investments'],'USD'),23400)
        self.assertEqual([Decimal(row['value']) for row in individual['history']['points']],[20000,23400])
        self.assertEqual(individual['accounts']['amounts'],{})

    def test_institution_history_can_use_collection_day_for_mixed_references(self):
        mixed_history(self.fixture)
        view=self.view(portfolio_connection='bank-test')['history']
        self.assertEqual((view['state'],view['basis']),('AVAILABLE','COLLECTION_DATE'))
        self.assertEqual([(row['date'],Decimal(row['value'])) for row in view['points']],
                         [(BEFORE,99300),(DATE,100350)])
        self.assertEqual(view['points'][1]['references'],[BEFORE,DATE])
        self.assertEqual(Decimal(view['change']),1050)
        self.assertEqual(self.view()['history']['points'],[])
        with closing(connect(self.fixture.case.db)) as db:
            historical=report(db,self.fixture.settings,{'view':['history'],'connection_id':['bank-test'],
                              'start':[BEFORE],'end':[DATE]},DATE)
        self.assertEqual(historical['basis'],'COLLECTION_DATE')
        self.assertEqual(historical['points'][-1]['original'],{'BRL':'100350'})

    def test_class_and_income_record_filters_match_overview(self):
        with closing(connect(self.fixture.case.db)) as db:
            stocks=report(db,self.fixture.settings,{'asset_class':['STOCK']},DATE)
            domestic=report(db,self.fixture.settings,{'asset_class':['PLUGGY:EQUITY'],'currency':['BRL']},DATE)
        self.assertTrue(stocks['items'])
        self.assertTrue(all(row['asset_class']=='STOCK' and row['provider']=='SNAPTRADE' for row in stocks['items']))
        self.assertEqual([row['label'] for row in domestic['items']],['FII sintético'])
        data=self.view(income_kind='reit_distribution',income_currency='BRL')['income']
        detail=data['detail']
        self.assertEqual(detail['total'],1)
        self.assertEqual(detail['items'][0]['asset'],'REAL')
        self.assertEqual(detail['items'][0]['description'],'Evento sintético')
        group=next(row for row in data['by_kind'] if row['kind']=='reit_distribution')
        self.assertEqual(sum(Decimal(row['presented']) for row in detail['items']),Decimal(group['value']))
        domestic=self.view('original',income_kind='interest_equity',income_currency='BRL')['income']['detail']
        self.assertEqual([row['description'] for row in domestic['items']],['Entrada COR JSCP MACA3'])
        empty=self.view('original',income_kind='interest_equity',income_currency='USD')['income']['detail']
        self.assertEqual(empty['total'],0)

    def test_missing_stale_and_future_rate_and_different_references(self):
        case=self.fixture.case
        case.write("DELETE FROM portfolio_fx_rates")
        case.write("INSERT INTO portfolio_fx_rates VALUES ('2026-10-03','4',?,'BCB_PTAX_SELL'),('2026-10-21','6',?,'BCB_PTAX_SELL')",
                   (fixture.STAMP,fixture.STAMP))
        case.write("UPDATE st_balances SET reference_at=?",(BEFORE+'T12:00:00Z',))
        case.write("UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.date','2026-10-17') WHERE resource='investments' AND connection_id=?",(SECOND,))
        case.write("UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.date','2026-10-16') WHERE external_id='account-BANK'")
        value=self.view()
        self.assertEqual(self.value(value['investments'],'BRL'),150000)
        self.assertTrue(value['investments']['partial'])
        self.assertGreaterEqual(len(value['quality']['dates']),4)
        self.assertTrue(value['quality']['mixed_dates'])
        self.assertFalse(value['quality']['rates'])
        self.assertEqual(value['history']['points'],[])

    def test_bill_dates_and_amounts_do_not_change_used_balance(self):
        case=self.fixture.case
        before=self.view()['cards']['metric']
        case.write("UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.dueDate','2026-10-10','$.totalAmount',9999) WHERE resource='bills'")
        self.assertEqual(self.view()['cards']['metric'],before)
        self.assertEqual(case.sql("SELECT count(*) FROM of_resource_records WHERE resource='bills' AND parent_id='account-CREDIT'"),[(1,)])

    def test_cross_provider_duplicate_credit_and_explicit_zero(self):
        case=self.fixture
        case.broker.activities.append({'id':'same-credit-038','type':'DIVIDEND','trade_date':DATE,'amount':'12',
            'currency':{'code':'BRL'},'description':'Mesmo crédito sintético','symbol':{'id':fixture.STOCK,'symbol':'MACA3'}})
        self.assertEqual(case.run_sync()['state'],'AVAILABLE')
        view=self.view()
        self.assertEqual(self.value(view['income']['credits'],'BRL'),92)
        self.assertEqual(sum(row['overlap'] for row in view['income']['events']),1)
        self.assertTrue(view['income']['credits']['partial'])
        case.case.write("UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.balance',0) WHERE resource='accounts' AND json_extract(payload_json,'$.type')='BANK'")
        self.assertEqual(self.value(self.view()['accounts'],'BRL'),0)

    def test_archived_and_excluded_connections(self):
        case=self.fixture
        cid=next(row['connection_id'] for row in self.view()['institutions'] if row['provider']=='SNAPTRADE')
        for archived,excluded in ((False,True),(True,False)):
            connection_policy(case.service,{'connection_id':cid,'archived':archived,'excluded':excluded,'paused':False})
            current=self.view()
            self.assertEqual(self.value(current['investments'],'BRL'),150000)
            self.assertTrue(all(row['id']!=cid for row in current['history']['connections']))
            self.assertFalse(any(row['provider']=='SNAPTRADE' for row in current['income']['events']))
        self.assertEqual(self.fixture.case.sql("SELECT count(*) FROM st_positions"),[(5,)])


if __name__=='__main__':
    unittest.main()
