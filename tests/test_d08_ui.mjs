import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {openFinanceError,coverageFailureCode} from '../finance-v17/src/finance_v2/web/open-finance-errors.js';
const web=new URL('../finance-v17/src/finance_v2/web/',import.meta.url);
const app=fs.readFileSync(new URL('app.js',web),'utf8');
const apiSource=app.slice(app.indexOf('async function api('),app.indexOf('\nfunction busy('));
const buildApi=new Function('fetch','coverageFailureCode',`let context={},pendingSuccess=false;const errorText=()=> 'Erro genérico';const location={};${apiSource};return api;`);

test('coverage HTTP 502 preserves only a known run error without raw response',async()=>{
  let requests=0;
  const api=buildApi(async()=>{requests++;return {status:502,ok:false,json:async()=>({run:{state:'FAILED',error_code:'AUTH_FAILED',payload:'PRIVATE_CANARY'},secret:'PRIVATE_CANARY'})}},coverageFailureCode);
  await assert.rejects(api('/open-finance/coverage-sync',{method:'POST',body:{connection_id:'synthetic'}}),e=>{
    assert.equal(e.code,'AUTH_FAILED');assert.ok(!JSON.stringify(e).includes('PRIVATE_CANARY'));assert.ok(!e.message.includes('PRIVATE_CANARY'));return true;
  });
  assert.equal(requests,1);
});

test('messages distinguish auth scope consent network internal without guessing invalid credentials',()=>{
  assert.match(openFinanceError('AUTH_FAILED'),/motivo não foi confirmado/);
  assert.match(openFinanceError('ACCOUNT_SCOPE_MISMATCH'),/proteção de escopo/);
  assert.match(openFinanceError('CONSENT_EXPIRED'),/expirado/);
  assert.match(openFinanceError('CONSENT_NOT_ACTIVE'),/Nenhum consentimento ativo/);
  assert.match(openFinanceError('NETWORK_FAILURE'),/comunicação/);
  assert.match(openFinanceError('INTERNAL_ERROR'),/interna/);
  for(const value of ['PRIVATE_CANARY','<script>secret</script>','__proto__','constructor',null,{},[]]){
    assert.equal(coverageFailureCode({run:{state:'FAILED',error_code:value}}),undefined);
    assert.equal(openFinanceError(value),openFinanceError(undefined));
  }
  assert.equal(coverageFailureCode({run:{state:'SUCCEEDED',error_code:'AUTH_FAILED'}}),undefined);
});

test('unrelated API errors and success retain the existing contract',async()=>{
  const api=buildApi(async()=>({status:422,ok:false,json:async()=>({error:{code:'VALIDATION_ERROR'},run:{state:'FAILED',error_code:'AUTH_FAILED'}})}),coverageFailureCode);
  await assert.rejects(api('/expenses'),e=>e.code==='VALIDATION_ERROR');
  const value={run:{state:'SUCCEEDED'}};
  const success=buildApi(async()=>({status:200,ok:true,json:async()=>value}),coverageFailureCode);
  assert.equal(await success('/open-finance/coverage-sync',{method:'POST'}),value);
});

test('network failure does not repeat a non-idempotent coverage request',async()=>{
  let calls=0;const api=buildApi(async()=>{calls++;throw new Error('synthetic network failure')},coverageFailureCode);
  await assert.rejects(api('/open-finance/coverage-sync',{method:'POST'}));assert.equal(calls,1);
});

test('manual coverage handler renders the classified failure and always releases controls',async()=>{
  const source=fs.readFileSync(new URL('open-finance-coverage.js',web),'utf8');
  const start=source.indexOf("manual.querySelectorAll('[data-coverage-sync]')");
  const handlerSource=source.slice(start,source.lastIndexOf('\n}'));
  const button={dataset:{coverageSync:'synthetic'},disabled:false};
  const progress={textContent:''};let cleared=0,calls=0;
  const manual={querySelectorAll:()=>[button],querySelector:()=>progress,isConnected:true};
  new Function('manual','api','window','setInterval','clearInterval','openFinanceError',handlerSource)(
    manual,async()=>{calls++;throw Object.assign(new Error('PRIVATE_CANARY'),{code:'ACCOUNT_SCOPE_MISMATCH'})},
    {confirm:()=>true},()=>7,id=>{assert.equal(id,7);cleared++},openFinanceError);
  await button.onclick();
  assert.equal(progress.textContent,openFinanceError('ACCOUNT_SCOPE_MISMATCH'));
  assert.equal(button.disabled,false);assert.equal(cleared,1);assert.equal(calls,1);
  assert.ok(!progress.textContent.includes('PRIVATE_CANARY'));
});

test('history uses the same closed vocabulary; no sync is added to initial render',()=>{
  const source=fs.readFileSync(new URL('open-finance.js',web),'utf8');
  assert.ok(source.includes('esc(openFinanceError(r.error_code))'));
  assert.ok(!source.includes("method:'POST'"));
});

test('a late progress response cannot overwrite the final classified failure',async()=>{
  const source=fs.readFileSync(new URL('open-finance-coverage.js',web),'utf8');
  const handler=source.slice(source.indexOf("manual.querySelectorAll('[data-coverage-sync]')"),source.lastIndexOf('\n}'));
  const button={dataset:{coverageSync:'synthetic'}};const progress={textContent:''};let poll,failSync,finishPoll;
  const manual={querySelectorAll:()=>[button],querySelector:()=>progress,isConnected:true};
  const api=path=>path==='/open-finance/coverage'
    ?new Promise(resolve=>{finishPoll=resolve})
    :new Promise((_,reject)=>{failSync=reject});
  new Function('manual','api','window','setInterval','clearInterval','openFinanceError',handler)(manual,api,
    {confirm:()=>true},fn=>{poll=fn;return 1},()=>{},openFinanceError);
  const syncing=button.onclick();const polling=poll();
  failSync({code:'AUTH_FAILED'});await syncing;
  finishPoll({coverage:[{state:'RUNNING'}]});await polling;
  assert.equal(progress.textContent,openFinanceError('AUTH_FAILED'));
});
