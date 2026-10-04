from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import hmac, json, logging, mimetypes, re, secrets
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qs

from .config import Settings
from .authorization import missing_capabilities
from .oauth import AUTHORIZATION_METADATA_PATH, RESOURCE_METADATA_PATH, RESOURCE_METADATA_URL, protected_resource_metadata, authorization_server_contract, bearer_challenge
from .oauth_server import OAuthService, TOKEN_PREFIX
from .db import connect, database_is_healthy
from .domain.catalog import add_card_calendar_version_idempotent, create_account, create_account_idempotent, create_card, create_card_idempotent, create_category, create_category_idempotent, create_tag, edit_card, set_active
from .domain.auto_debit import reactivate_auto_settlement_idempotent, reverse_auto_payment_idempotent
from .domain.clock import SystemClock
from .domain.errors import DomainError, InactiveAccount, InvalidState, NewDueDateRequired, NotFound, ValidationError
from .domain.expenses import cancel_expense, create_expense, create_expense_idempotent, edit_expense, effective_status, logical_delete_expense, pay_expense, reactivate_expense, replace_expense_payment, reverse_expense_payment
from .domain.revenues import cancel_revenue_idempotent, create_revenue_idempotent, edit_revenue, receive_revenue_idempotent, revenue_status, reverse_revenue_receipt_idempotent
from .domain.revenue_recurrence import create_revenue_series_idempotent, end_revenue_series_idempotent, materialize_revenue_series_idempotent, change_revenue_series_from_date
from .domain.support import require_row
from .domain.installments import cancel_remaining, create_installment_series, create_installments_idempotent
from .domain.invoices import cancel_invoice, close_invoice, effective_total, move_card_expense_idempotent, override_invoice_payment_config, paid_cents, pay_invoice_idempotent, reverse_invoice_payment_idempotent, revise_total_idempotent
from .domain.recurrence import cancel_occurrence_only, cancel_this_and_future, change_occurrence_payment_method, change_series_from_date, change_this_and_future, create_occurrence_override, create_series, end_series_idempotent, materialize, materialization_horizon, remove_occurrence_override
from .domain.recurrence_projection import expense_forecast, revenue_forecast
from .domain.reports import net_paid, overdue_total, pending_total, recognized_expenses, requires_attention, requires_manual_action, revenue_expected, revenue_received, revenue_realized
from .idempotency import IdempotencyConflict, InvalidIdempotencyKey
from .migrations import migration_status
from .mcp_recurring import OPERATIONS as RECURRING_MCP_OPERATIONS, tools as recurring_mcp_tools, validate_arguments as validate_recurring_arguments, PAYMENT_METHODS as RECURRING_PAYMENT_METHODS, FREQUENCIES as RECURRING_FREQUENCIES, DUE_RULES as RECURRING_DUE_RULES

LOGGER=logging.getLogger(__name__)

@dataclass(frozen=True)
class Identity:
    client_id:str
    role:str
    csrf:str|None=None
    capabilities:frozenset[str]=frozenset()

@dataclass(frozen=True)
class Route:
    method:str; path:str; operation:str; write:bool=False; idem:bool=False
    def match(self,path):
        return re.match("^"+re.sub(r"\{([a-z_]+)\}",r"(?P<\1>[0-9]+)",self.path)+"$",path)

ROUTES=(
 Route("GET","/api/v2/health","health"),Route("GET","/api/v2/openapi.json","openapi"),
 Route("GET","/api/v2/assistant/context","assistant_context"),Route("GET","/api/v2/assistant/dashboard","assistant_dashboard"),Route("GET","/api/v2/assistant/expenses","assistant_expense_list"),Route("POST","/api/v2/assistant/expenses","assistant_expense_create",True,True),Route("GET","/api/v2/assistant/openapi.json","assistant_openapi"),
 Route("GET","/api/v2/context","context"),Route("GET","/api/v2/catalogs","catalogs"),Route("GET","/api/v2/recurring-series","series_list"),Route("GET","/api/v2/recurring-series/{id}","series_detail"),Route("GET","/api/v2/installment-series","installments_list"),Route("GET","/api/v2/installment-series/{id}","installments_detail"),
 Route("POST","/api/v2/accounts","catalog_create",True),Route("POST","/api/v2/categories","catalog_create",True),Route("POST","/api/v2/tags","catalog_create",True),
 Route("PATCH","/api/v2/accounts/{id}","catalog_active",True),Route("PATCH","/api/v2/categories/{id}","catalog_active",True),Route("PATCH","/api/v2/tags/{id}","catalog_active",True),Route("PATCH","/api/v2/cards/{id}","catalog_active",True),Route("PATCH","/api/v2/cards/{id}/edit","card_edit",True),
 Route("GET","/api/v2/cards","card_list"),Route("GET","/api/v2/cards/{id}","card_detail"),Route("POST","/api/v2/cards","card_create",True),Route("POST","/api/v2/cards/{id}/calendar-versions","card_calendar_create",True,True),Route("POST","/api/v2/expenses","expense_create",True),Route("GET","/api/v2/expenses","expense_list"),Route("GET","/api/v2/expenses/{id}","expense_detail"),Route("PATCH","/api/v2/expenses/{id}","expense_edit",True),
 Route("POST","/api/v2/expenses/{id}/pay","expense_pay",True,True),Route("POST","/api/v2/expenses/{id}/cancel","expense_cancel",True),Route("POST","/api/v2/expenses/{id}/reactivate","expense_reactivate",True),Route("POST","/api/v2/expenses/{id}/delete","expense_delete",True,True),
 Route("POST","/api/v2/revenues","revenue_create",True,True),Route("GET","/api/v2/revenues","revenue_list"),Route("GET","/api/v2/revenues/{id}","revenue_detail"),Route("PATCH","/api/v2/revenues/{id}","revenue_edit",True),Route("POST","/api/v2/revenues/{id}/receive","revenue_receive",True,True),Route("POST","/api/v2/revenues/{id}/cancel","revenue_cancel",True,True),Route("GET","/api/v2/revenues/{id}/audit","revenue_audit"),Route("POST","/api/v2/revenue-receipts/{id}/reverse","revenue_reverse",True,True),
 Route("GET","/api/v2/revenue-recurring-series","revenue_series_list"),Route("GET","/api/v2/revenue-recurring-series/{id}","revenue_series_detail"),Route("POST","/api/v2/revenue-recurring-series","revenue_series_create",True,True),Route("POST","/api/v2/revenue-recurring-series/{id}/materialize","revenue_series_materialize",True,True),Route("POST","/api/v2/revenue-recurring-series/{id}/end","revenue_series_end",True,True),Route("POST","/api/v2/revenue-recurring-series/{id}/change-from","revenue_series_change_from",True,True),
 Route("POST","/api/v2/expense-payments/{id}/reverse","expense_reverse",True,True),Route("POST","/api/v2/expense-payments/{id}/replace","expense_replace",True,True),Route("POST","/api/v2/expenses/{id}/move-invoice","expense_move_invoice",True,True),Route("GET","/api/v2/expenses/{id}/audit","expense_audit"),
 Route("POST","/api/v2/recurring-series","series_create",True),Route("POST","/api/v2/recurring-series/{id}/materialize","series_materialize",True),Route("POST","/api/v2/recurring-series/{id}/end","series_end",True,True),
 Route("POST","/api/v2/recurring-occurrences/{id}/override","occurrence_override",True),Route("POST","/api/v2/recurring-occurrences/{id}/cancel","occurrence_cancel",True),Route("POST","/api/v2/recurring-occurrences/{id}/cancel-this-and-future","occurrence_cancel_future",True,True),
 Route("POST","/api/v2/recurring-occurrences/{id}/this-and-future","occurrence_change_future",True,True),Route("POST","/api/v2/recurring-series/{id}/change-from","series_change_from",True,True),
 Route("POST","/api/v2/recurring-overrides/{id}/remove","occurrence_override_remove",True),
 Route("POST","/api/v2/recurring-occurrences/{id}/payment-method","occurrence_payment_method",True,True),
 Route("POST","/api/v2/installment-series","installments_create",True),Route("POST","/api/v2/installment-series/{id}/cancel-remaining","installments_cancel",True),
 Route("GET","/api/v2/invoices","invoice_list"),Route("GET","/api/v2/invoices/{id}","invoice_detail"),Route("POST","/api/v2/invoices/{id}/close","invoice_close",True),Route("POST","/api/v2/invoices/{id}/cancel","invoice_cancel",True),
 Route("POST","/api/v2/invoices/{id}/pay","invoice_pay",True,True),Route("POST","/api/v2/invoice-payments/{id}/reverse","invoice_reverse",True,True),Route("POST","/api/v2/invoices/{id}/correct-total","invoice_correct",True,True),Route("POST","/api/v2/invoices/{id}/payment-config","invoice_payment_config",True,True),Route("GET","/api/v2/invoices/{id}/audit","invoice_audit"),
 Route("POST","/api/v2/settlements/{id}/reactivate","settlement_reactivate",True,True),Route("POST","/api/v2/auto-payments/{id}/reverse","auto_payment_reverse",True,True),
 Route("GET","/api/v2/aggregates","aggregates"),Route("GET","/api/v2/dashboard","dashboard"),
)

class HttpError(RuntimeError):
    def __init__(self,status,code,message): self.status,self.code,self.message=status,code,message

def civil(value,field,default=None):
    if value is None and default is not None:return default
    if not isinstance(value,str):raise HttpError(422,"VALIDATION_ERROR",f"{field} must be an ISO date")
    try: result=date.fromisoformat(value)
    except ValueError:raise HttpError(422,"VALIDATION_ERROR",f"{field} must be a valid ISO date")
    if result.isoformat()!=value:raise HttpError(422,"VALIDATION_ERROR",f"{field} must be canonical")
    return result

def integer(value,field,positive=False):
    if isinstance(value,bool) or not isinstance(value,int) or positive and value<=0:raise HttpError(422,"VALIDATION_ERROR",f"{field} must be an integer")
    return value

def query_positive_int(value,field):
    if not isinstance(value,str) or len(value)>19 or re.fullmatch(r"[0-9]+",value) is None or not 0<int(value)<=9223372036854775807:raise HttpError(422,"VALIDATION_ERROR",f"{field} must be a positive integer")
    return int(value)

class Application:
 def __init__(self,settings,clock=None):self.settings=settings;self.clock=clock or SystemClock(settings.timezone);self.oauth=OAuthService(settings,self.clock)
 def __call__(self,environ,start_response)->Iterable[bytes]:
  rid=environ.get("HTTP_X_REQUEST_ID","local");origin=environ.get("HTTP_ORIGIN")
  try:
   path=environ.get("PATH_INFO","");method=environ.get("REQUEST_METHOD","GET")
   if method=="GET" and path in {RESOURCE_METADATA_PATH,"/.well-known/oauth-protected-resource"}:
    return self.json_document_response(start_response,200,protected_resource_metadata())
   if method=="GET" and path==AUTHORIZATION_METADATA_PATH:
    return self.json_document_response(start_response,200,authorization_server_contract())
   if path in {"/oauth/authorize","/oauth/token"}:
    return self.oauth.http(environ,start_response)
   if path=="/" and method=="GET":
    start_response("303 See Other",[("Location","/app/"),("Cache-Control","no-store")]);return [b""]
   if path.startswith("/app"):
    return self.app_request(environ,start_response,rid)
   if path=="/mcp" and method in {"POST","GET"}:
    return self.mcp_request(environ,start_response,rid)
   if environ.get("REQUEST_METHOD")=="OPTIONS":
    if origin not in self.settings.cors_origins:raise HttpError(403,"CORS_FORBIDDEN","origin is not allowed")
    return self.respond(start_response,204,{},rid,origin)
   route,params=self.route(method,path);identity=self.identity(environ,route)
   assistant_operation=route.operation.startswith("assistant_")
   body=self.body(environ);key=environ.get("HTTP_IDEMPOTENCY_KEY")
   if route.idem and key is None:raise HttpError(400,"IDEMPOTENCY_KEY_REQUIRED","Idempotency-Key is required")
   if identity.role=="EXTERNAL_CLIENT":self.require_capabilities(identity,write=assistant_operation and route.write)
   if assistant_operation and identity.role!="EXTERNAL_CLIENT":raise HttpError(403,"FORBIDDEN","assistant routes require an external client")
   if route.write and environ.get("finance_v2.cookie_auth") and environ.get("HTTP_X_CSRF_TOKEN")!=environ.get("finance_v2.csrf"):raise HttpError(403,"CSRF_INVALID","CSRF token is missing or invalid")
   if route.write and not (assistant_operation and identity.role=="EXTERNAL_CLIENT") and identity.role!="UI":raise HttpError(403,"FORBIDDEN","identity cannot execute this operation")
   payload,status=self.dispatch(route,params,identity,body,parse_qs(environ.get("QUERY_STRING","")),key)
   return self.respond(start_response,status,payload,rid,origin)
  except HttpError as e:return self.respond(start_response,e.status,{"error":{"code":e.code,"message":e.message}},rid,origin)
  except InvalidIdempotencyKey as e:return self.respond(start_response,400,{"error":{"code":"IDEMPOTENCY_KEY_INVALID","message":str(e)}},rid,origin)
  except IdempotencyConflict as e:return self.respond(start_response,409,{"error":{"code":"IDEMPOTENCY_CONFLICT","message":str(e)}},rid,origin)
  except NewDueDateRequired as e:return self.respond(start_response,400,{"error":{"code":e.code,"message":str(e)}},rid,origin)
  except NotFound as e:return self.respond(start_response,404,{"error":{"code":"NOT_FOUND","message":str(e)}},rid,origin)
  except (InactiveAccount,InvalidState,DomainError) as e:return self.respond(start_response,422 if isinstance(e,ValidationError) else 409,{"error":{"code":e.code,"message":str(e)}},rid,origin)
  except json.JSONDecodeError:return self.respond(start_response,400,{"error":{"code":"INVALID_JSON","message":"request body is not valid JSON"}},rid,origin)
  except FileNotFoundError as e:return self.respond(start_response,503,{"status":"degraded","database":"error","error":{"code":"DATABASE_UNAVAILABLE","message":str(e)}},rid,origin)
  except Exception:LOGGER.exception("request failed request_id=%s",rid);return self.respond(start_response,500,{"error":{"code":"INTERNAL_ERROR","message":"internal server error"}},rid,origin)
 def route(self,method,path):
  for r in ROUTES:
   m=r.match(path)
   if r.method==method and m:return r,{k:int(v) for k,v in m.groupdict().items()}
  raise HttpError(404,"NOT_FOUND","resource not found")
 def identity(self,e,r):
  if r.operation in {"health","openapi"}:return Identity("PUBLIC","PUBLIC")
  h=e.get("HTTP_AUTHORIZATION","")
  if not h.startswith("Bearer "):
   if h:raise HttpError(401,"UNAUTHENTICATED","invalid authorization header")
   session=self.session(e)
   if session:
    e["finance_v2.cookie_auth"]=True;e["finance_v2.csrf"]=session;return Identity("UI:local","UI",session)
   raise HttpError(401,"UNAUTHENTICATED","valid session or Bearer token required")
  token=h[7:]
  if not token or len(token)>4096 or any(ord(c)<=32 or ord(c)>=127 for c in token):raise HttpError(401,"UNAUTHENTICATED","invalid Bearer token")
  if token.startswith(TOKEN_PREFIX):
   resolved=self.oauth.resolve(token) if r.operation=="mcp" else None
   if resolved is None:raise HttpError(401,"UNAUTHENTICATED","invalid OAuth token")
   client_id,scopes=resolved
   return Identity(client_id,"EXTERNAL_CLIENT",capabilities=scopes)
  for client in self.settings.external_clients:
   if not client.enabled:continue
   if hmac.compare_digest(token,client.token) or client.previous_token is not None and hmac.compare_digest(token,client.previous_token):
    return Identity(f"CLIENT:{client.client_id}","EXTERNAL_CLIENT",capabilities=client.capabilities)
  for configured,ident in ((self.settings.ui_token,Identity("UI:local","UI")),(self.settings.scheduler_token,Identity("SCHEDULER:internal","SCHEDULER")),(self.settings.hermes_token,Identity("CLIENT:hermes","EXTERNAL_CLIENT",capabilities=frozenset({"finance:read"})))):
   if configured and hmac.compare_digest(token,configured):return ident
  raise HttpError(401,"UNAUTHENTICATED","valid Bearer token required")
 def mcp_request(self,e,start,rid):
  try:
   identity=self.identity(e,Route("POST","/mcp","mcp"))
   if identity.role!="EXTERNAL_CLIENT":raise HttpError(403,"FORBIDDEN","MCP requires an external client")
   if e.get("REQUEST_METHOD")=="GET":
    # No standalone SSE listener in the existing transport. Authentication
    # still runs first so GET probes can discover the protected resource.
    return self.mcp_response(start,405,{"error":"GET transport not supported"},rid,e)
   request=self.body(e);method=request.get("method");request_id=request.get("id")
   if not isinstance(method,str):raise HttpError(400,"INVALID_JSON","MCP method is required")
   if method=="initialize":
    result={"protocolVersion":"2025-03-26","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"Finance V2","version":"0.1.18"}}
   elif method=="notifications/initialized":
    return self.mcp_response(start,202,None,rid,e)
   elif method=="tools/list":
    result={"tools":self.mcp_tools()}
   elif method=="tools/call":
    params=request.get("params") or {};name=params.get("name");arguments=params.get("arguments") or {}
    e["finance_v2.required_scopes"]="finance:read finance:write" if any(t["name"]==name and not t["annotations"]["readOnlyHint"] for t in self.mcp_tools()) else "finance:read"
    result=self.mcp_call(name,arguments,identity)
   else:
    raise HttpError(400,"MCP_METHOD_NOT_FOUND",f"unsupported MCP method: {method}")
   return self.mcp_response(start,200,{"jsonrpc":"2.0","id":request_id,"result":result},rid,e)
  except HttpError as exc:
   return self.mcp_response(start,exc.status,{"jsonrpc":"2.0","id":request_id if 'request_id' in locals() else None,"error":{"code":exc.code,"message":exc.message}},rid,e)
  except (IdempotencyConflict,InvalidIdempotencyKey,DomainError,NotFound) as exc:
   code=getattr(exc,"code","DOMAIN_ERROR")
   if "same scoped key" in str(exc) or "permanent key payload conflict" in str(exc):code="IDEMPOTENCY_CONFLICT"
   return self.mcp_response(start,409,{"jsonrpc":"2.0","id":request_id if 'request_id' in locals() else None,"error":{"code":code,"message":str(exc)}},rid,e)
  except Exception:
   LOGGER.exception("MCP request failed request_id=%s",rid)
   return self.mcp_response(start,500,{"jsonrpc":"2.0","id":request_id if 'request_id' in locals() else None,"error":{"code":"INTERNAL_ERROR","message":"internal server error"}},rid,e)
 def mcp_tools(self):
  read={"type":"object","additionalProperties":False}
  expenses={"type":"object","additionalProperties":False,"properties":{"page":{"type":"integer","minimum":1},"page_size":{"type":"integer","enum":[25,50,100]},"search":{"type":"string"},"start":{"type":"string","format":"date","description":"Inclusive lower bound on expense_date (competence), YYYY-MM-DD; may be used alone."},"end":{"type":"string","format":"date","description":"Inclusive upper bound on expense_date (competence), YYYY-MM-DD; may be used alone. start > end returns an empty list, matching the canonical API."}}}
  summary={"type":"object","additionalProperties":False,"properties":{"month":{"type":"string","pattern":"^[0-9]{4}-[0-9]{2}$","description":"Dashboard competence YYYY-MM. Omitted: current month of the configured Finance clock/timezone."}}}
  create={"type":"object","additionalProperties":False,"required":["idempotency_key","description","amount_cents","planned_payment_method","category_id"],"properties":{"idempotency_key":{"type":"string","minLength":16,"maxLength":128},"description":{"type":"string","minLength":1},"amount_cents":{"type":"integer","minimum":1},"expense_date":{"type":"string","format":"date"},"due_date":{"type":["string","null"],"format":"date"},"planned_payment_method":{"type":"string","enum":["CREDIT_CARD","AUTO_DEBIT","PIX","BANK_TRANSFER","CASH","BANK_SLIP","DEBIT"]},"category_id":{"type":"integer","minimum":1},"account_id":{"type":["integer","null"],"minimum":1},"card_id":{"type":["integer","null"],"minimum":1},"notes":{"type":["string","null"]},"tag_ids":{"type":"array","items":{"type":"integer","minimum":1}}}}
  return recurring_mcp_tools()+[
   {"name":"finance_get_context","description":"Return Finance V2 context and authorized capabilities.","inputSchema":read,"annotations":{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True}},
   {"name":"finance_get_summary","description":"Return the canonical Dashboard for month YYYY-MM; omitted month uses the current Finance clock/timezone month. Recognized expenses use expense_date competence; pending obligations use due dates, and realized totals use financial event dates. These are distinct measures.","inputSchema":summary,"annotations":{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True}},
   {"name":"finance_list_categories","description":"List registered categories.","inputSchema":read,"annotations":{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True}},
   {"name":"finance_list_accounts","description":"List registered accounts.","inputSchema":read,"annotations":{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True}},
   {"name":"finance_list_cards","description":"List registered cards.","inputSchema":read,"annotations":{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True}},
   {"name":"finance_list_expenses","description":"List canonical API expense records. For expenses of a requested competence month, send its first/last dates as start/end: inclusive expense_date bounds, NOT due_date or invoice due dates. Card/invoice-linked records remain included. Omitted bounds retain the existing all-period listing; cancelled/superseded history remains included, deleted records excluded. Combine search/page/page_size; follow has_more to retrieve all pages. start > end returns empty. Never interpret an unfiltered page as a monthly total.","inputSchema":expenses,"annotations":{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True}},
   {"name":"finance_create_expense","description":"Create an expense using permanent idempotency.","inputSchema":create,"annotations":{"readOnlyHint":False,"destructiveHint":False,"idempotentHint":True}},
   {"name":"finance_create_category","description":"Create a category with permanent replay protection.","inputSchema":{"type":"object","additionalProperties":False,"required":["idempotency_key","name"],"properties":{"idempotency_key":{"type":"string","minLength":16,"maxLength":128},"name":{"type":"string","minLength":1}}},"annotations":{"readOnlyHint":False,"destructiveHint":False,"idempotentHint":True}},
   {"name":"finance_create_account","description":"Create an account with permanent replay protection.","inputSchema":{"type":"object","additionalProperties":False,"required":["idempotency_key","name"],"properties":{"idempotency_key":{"type":"string","minLength":16,"maxLength":128},"name":{"type":"string","minLength":1}}},"annotations":{"readOnlyHint":False,"destructiveHint":False,"idempotentHint":True}},
   {"name":"finance_create_card","description":"Create a card and its initial calendar with permanent replay protection.","inputSchema":{"type":"object","additionalProperties":False,"required":["idempotency_key","name","payment_mode","closing_day","due_day"],"properties":{"idempotency_key":{"type":"string","minLength":16,"maxLength":128},"name":{"type":"string","minLength":1},"payment_mode":{"type":"string","enum":["MANUAL","AUTO_DEBIT"]},"payment_account_id":{"type":["integer","null"],"minimum":1},"effective_from":{"type":"string","format":"date"},"closing_day":{"type":"integer","minimum":1,"maximum":31},"due_day":{"type":"integer","minimum":1,"maximum":31}}},"annotations":{"readOnlyHint":False,"destructiveHint":False,"idempotentHint":True}}
  ]
 def mcp_call(self,name,arguments,identity):
  if not isinstance(name,str):raise HttpError(400,"VALIDATION_ERROR","tool name is required")
  names={item["name"] for item in self.mcp_tools()}
  if name not in names:raise HttpError(404,"NOT_FOUND","tool not found")
  write=next(t for t in self.mcp_tools() if t["name"]==name)["annotations"]["readOnlyHint"] is False
  self.require_capabilities(identity,write=write)
  if name in {"finance_list_expenses","finance_get_summary"}:
   allowed={"page","page_size","search","start","end"} if name=="finance_list_expenses" else {"month"}
   if not isinstance(arguments,dict) or set(arguments)-allowed:raise HttpError(422,"VALIDATION_ERROR","unsupported read tool arguments")
   for field,value in arguments.items():
    if field in {"page","page_size"}:integer(value,field,True)
    elif not isinstance(value,str):raise HttpError(422,"VALIDATION_ERROR",f"{field} must be a string")
    if field=="month" and not re.fullmatch(r"[0-9]{4}-[0-9]{2}",value):raise HttpError(422,"VALIDATION_ERROR","month must be YYYY-MM")
  if name in RECURRING_MCP_OPERATIONS:
   validate_recurring_arguments(name,arguments)
   method,path,operation,identifier=RECURRING_MCP_OPERATIONS[name]
   p={"id":arguments[identifier]} if identifier else {}
   body={k:v for k,v in arguments.items() if k not in {identifier,"idempotency_key"}}
   q={"month":[body.pop("month")]} if operation=="series_list" and "month" in body else {}
   payload,status=self.dispatch(Route(method,path,operation,write,write),p,identity,body,q,arguments.get("idempotency_key"))
  elif name=="finance_get_context":
   payload,status=self.dispatch(Route("GET","/api/v2/assistant/context","assistant_context"),{},identity,{}, {},None)
   payload["recurring_expense_contract"]={"payment_methods":RECURRING_PAYMENT_METHODS,"frequencies":RECURRING_FREQUENCIES,"due_rules":RECURRING_DUE_RULES,"calendar":"Monthly base_day 1..31 clamps to month end; 31 represents last day. Resolve IDs from catalog tools; materialization belongs to domain/scheduler."}
  elif name=="finance_get_summary":payload,status=self.dispatch(Route("GET","/api/v2/assistant/dashboard","assistant_dashboard"),{},identity,{}, {"month":[arguments["month"]]} if "month" in arguments else {},None)
  elif name.startswith("finance_list_") and name!="finance_list_expenses":
   payload,status=self.dispatch(Route("GET","/api/v2/catalogs","catalogs"),{},identity,{}, {},None);payload={name.removeprefix("finance_list_"):payload.get(name.removeprefix("finance_list_"),[])}
  elif name=="finance_list_expenses":
   q={k:[str(v)] for k,v in arguments.items() if k in {"page","page_size","search","start","end"}}
   payload,status=self.dispatch(Route("GET","/api/v2/assistant/expenses","assistant_expense_list"),{},identity,{},q,None)
  elif name=="finance_create_expense":
   key=arguments.get("idempotency_key");body={k:v for k,v in arguments.items() if k!="idempotency_key"}
   payload,status=self.dispatch(Route("POST","/api/v2/assistant/expenses","assistant_expense_create",True,True),{},identity,body,{},key)
  else:
   key=arguments.get("idempotency_key");body={k:v for k,v in arguments.items() if k!="idempotency_key"}
   c=self.db()
   try:
    if name=="finance_create_category":resource_id,replayed=create_category_idempotent(c,name=str(body.get("name","")),client_id=identity.client_id,idempotency_key=key,clock=self.clock)
    elif name=="finance_create_account":resource_id,replayed=create_account_idempotent(c,name=str(body.get("name","")),client_id=identity.client_id,idempotency_key=key,clock=self.clock)
    else:resource_id,replayed=create_card_idempotent(c,name=str(body.get("name","")),payment_mode=body.get("payment_mode"),payment_account_id=body.get("payment_account_id"),effective_from=civil(body.get("effective_from"),"effective_from",self.clock.today()),closing_day=integer(body.get("closing_day"),"closing_day",True),due_day=integer(body.get("due_day"),"due_day",True),client_id=identity.client_id,idempotency_key=key,clock=self.clock)
    payload={"id":resource_id,"replayed":replayed};status=200 if replayed else 201
   finally:c.close()
   if status>=400:
    error=payload.get("error",{})
    code=error.get("code","MCP_ERROR")
    if code=="DOMAIN_ERROR" and "same scoped key" in error.get("message",""):code="IDEMPOTENCY_CONFLICT"
    raise HttpError(status,code,error.get("message","tool failed"))
  return {"content":[{"type":"text","text":json.dumps(payload,ensure_ascii=False,separators=(",",":"),default=str)}],"structuredContent":payload,"isError":False}
 def require_capabilities(self,identity,*,write=False):
  missing=missing_capabilities(identity.capabilities,write=write)
  if missing:raise HttpError(403,"FORBIDDEN","identity lacks "+" and ".join(sorted(missing))+" capability")
 def mcp_response(self,start,status,payload,rid,e):
  if status==202:return self.respond(start,202,{},rid)
  raw=json.dumps(payload,ensure_ascii=False,separators=(",",":"),default=str).encode()
  if "text/event-stream" in e.get("HTTP_ACCEPT",""):
   body=b"event: message\ndata: "+raw+b"\n\n";headers=[("Content-Type","text/event-stream"),("Content-Length",str(len(body))),("Cache-Control","no-cache")]
  else: body=raw;headers=[("Content-Type","application/json"),("Content-Length",str(len(body))),("Cache-Control","no-store")]
  if status==401:headers.append(("WWW-Authenticate",bearer_challenge(invalid_token=bool(e.get("HTTP_AUTHORIZATION")))))
  if status==403 and e.get("HTTP_AUTHORIZATION","").startswith("Bearer "+TOKEN_PREFIX):headers.append(("WWW-Authenticate",f'Bearer error="insufficient_scope", resource_metadata="{RESOURCE_METADATA_URL}", scope="{e.get("finance_v2.required_scopes","finance:read")}"'))
  if status==405:headers.append(("Allow","POST"))
  headers.append(("Mcp-Session-Id",e.get("HTTP_MCP_SESSION_ID") or secrets.token_urlsafe(18)))
  phrase={200:"OK",400:"Bad Request",401:"Unauthorized",403:"Forbidden",405:"Method Not Allowed",409:"Conflict",500:"Internal Server Error"}.get(status,"Error")
  start(f"{status} {phrase}",headers);return [body]
 def session(self,e):
  if not self.settings.ui_token:return None
  cookie=SimpleCookie();cookie.load(e.get("HTTP_COOKIE",""));m=cookie.get("finance_v2_session")
  if not m:return None
  try:csrf,signature=m.value.split(".",1)
  except ValueError:return None
  expected=hmac.new(self.settings.ui_token.encode(),csrf.encode(),sha256).hexdigest()
  return csrf if hmac.compare_digest(signature,expected) else None
 def app_request(self,e,start,rid):
  path=e.get("PATH_INFO","");method=e.get("REQUEST_METHOD","GET")
  if path=="/app/session" and method=="POST":
   n=int(e.get("CONTENT_LENGTH") or 0);raw=e["wsgi.input"].read(n).decode();data=parse_qs(raw);token=data.get("token",[""])[0]
   if not self.settings.ui_token or not hmac.compare_digest(token,self.settings.ui_token):return self.html(start,401,"<h1>Credencial inválida</h1><a href='/app/unlock'>Voltar</a>")
   csrf=secrets.token_urlsafe(24);sig=hmac.new(self.settings.ui_token.encode(),csrf.encode(),sha256).hexdigest();secure="; Secure" if e.get("wsgi.url_scheme")=="https" else ""
   start("303 See Other",[("Location","/app/"),("Set-Cookie",f"finance_v2_session={csrf}.{sig}; Path=/; HttpOnly; SameSite=Strict{secure}"),("Cache-Control","no-store")]);return [b""]
  if path=="/app/logout" and method=="POST":
   start("303 See Other",[("Location","/app/unlock"),("Set-Cookie","finance_v2_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"),("Cache-Control","no-store")]);return [b""]
  root=Path(__file__).with_name("web")
  if path=="/app/unlock":return self.file(start,root/"unlock.html")
  relative="index.html" if path in {"/app","/app/"} or not path.startswith("/app/assets/") else path.removeprefix("/app/assets/")
  target=(root/relative).resolve()
  if root.resolve() not in target.parents and target!=root.resolve():raise HttpError(404,"NOT_FOUND","asset not found")
  return self.file(start,target)
 def file(self,start,path):
  if not path.is_file():raise HttpError(404,"NOT_FOUND","asset not found")
  raw=path.read_bytes();mime=mimetypes.guess_type(path.name)[0] or "application/octet-stream";start("200 OK",[("Content-Type",mime+(("; charset=utf-8") if mime.startswith("text/") or mime=="application/javascript" else "")),("Content-Length",str(len(raw))),("Cache-Control","no-store"),("X-Content-Type-Options","nosniff")]);return [raw]
 def html(self,start,status,body):
  raw=("<!doctype html><meta charset=utf-8>"+body).encode();start(f"{status} Error",[("Content-Type","text/html; charset=utf-8"),("Content-Length",str(len(raw))),("Cache-Control","no-store")]);return [raw]
 def body(self,e):
  n=int(e.get("CONTENT_LENGTH") or 0)
  if n>1_000_000:raise HttpError(413,"PAYLOAD_TOO_LARGE","payload exceeds limit")
  data=json.loads(e["wsgi.input"].read(n).decode()) if n else {}
  if not isinstance(data,dict):raise HttpError(422,"VALIDATION_ERROR","body must be an object")
  if "client_id" in data or "authenticated_client_id" in data:raise HttpError(422,"IDENTITY_FIELD_FORBIDDEN","identity cannot be supplied in payload")
  return data
 def db(self):return connect(self.settings.database_path,self.settings.busy_timeout_ms)
 def dispatch(self,r,p,i,b,q,key):
  if r.operation=="openapi":return self.openapi(),200
  if r.operation=="assistant_openapi":return self.assistant_openapi(),200
  c=self.db()
  try:
   if r.operation=="health":
    ok=database_is_healthy(c);m=migration_status(c);return {"status":"ok" if ok and m["up_to_date"] else "degraded","database":"ok" if ok else "error","migrations":m},200 if ok and m["up_to_date"] else 503
   if r.operation=="context":return {"system_date":self.clock.today(),"timezone":self.settings.timezone,"csrf_token":i.csrf},200
   if r.operation=="assistant_context":return {"system_date":self.clock.today(),"timezone":self.settings.timezone,"capabilities":sorted(i.capabilities)},200
   if r.operation=="assistant_dashboard":r=Route("GET","/api/v2/dashboard","dashboard")
   if r.operation=="assistant_expense_list":return self.list_expenses(c,q),200
   if r.operation=="assistant_expense_create":
    allowed={"description","amount_cents","expense_date","due_date","planned_payment_method","category_id","account_id","card_id","notes","tag_ids"}
    if set(b)-allowed:raise HttpError(422,"VALIDATION_ERROR","assistant expense contains unsupported fields")
    kwargs={"description":str(b.get("description","")),"amount_cents":integer(b.get("amount_cents"),"amount_cents",True),"expense_date":civil(b.get("expense_date"),"expense_date",self.clock.today()),"due_date":civil(b["due_date"],"due_date") if b.get("due_date") else None,"planned_payment_method":b.get("planned_payment_method"),"category_id":integer(b.get("category_id"),"category_id",True),"account_id":b.get("account_id"),"card_id":b.get("card_id"),"notes":b.get("notes"),"tags":tuple(b.get("tag_ids",())),"actor":i.client_id,"correlation_id":"assistant-expense-create","clock":self.clock}
    expense_id,replay=create_expense_idempotent(c,client_id=i.client_id,idempotency_key=key,**kwargs)
    return {"id":expense_id,"replayed":replay},200 if replay else 201
   if r.operation=="catalogs":return {name:[dict(x) for x in c.execute(f"SELECT * FROM {name} ORDER BY id")] for name in ("accounts","categories","tags","cards")},200
   if r.operation=="series_list":
    items=[dict(x) for x in c.execute("SELECT s.*,v.description,v.frequency,v.amount_cents,v.planned_payment_method FROM recurring_series s JOIN recurring_series_versions v ON v.id=(SELECT id FROM recurring_series_versions WHERE recurring_series_id=s.id ORDER BY effective_from DESC,id DESC LIMIT 1) ORDER BY s.id DESC")]
    forecast_day=self.clock.today()
    if q.get("month",[None])[0]:
     raw=q["month"][0]
     try:
      y,m=map(int,raw.split("-"));forecast_day=date(y,m,1)
     except (ValueError,TypeError):raise HttpError(422,"VALIDATION_ERROR","month must be a valid calendar month")
    for item in items:
     item.update(expense_forecast(c,item["id"],forecast_day) or {"next_occurrence":None,"next_due_date":None,"association_name":None})
    return {"items":items},200
   if r.operation=="series_detail":
    s=c.execute("SELECT * FROM recurring_series WHERE id=?",(p["id"],)).fetchone()
    if not s:raise NotFound("recurring series not found")
    versions=[dict(x) for x in c.execute("SELECT * FROM recurring_series_versions WHERE recurring_series_id=? ORDER BY effective_from,id",(p["id"],))]
    for version in versions:
     version["tag_ids"]=[row[0] for row in c.execute("SELECT tag_id FROM recurring_version_tags WHERE recurring_version_id=? ORDER BY tag_id",(version["id"],))]
    occurrences=[dict(x) for x in c.execute("SELECT * FROM expenses WHERE recurring_series_id=? ORDER BY expense_date,id",(p["id"],))]
    for x in occurrences:
     x["effective_status"]=effective_status(c,x["id"],self.clock.today());x["override"]=(dict(o) if (o:=c.execute("SELECT * FROM occurrence_overrides WHERE expense_id=? ORDER BY id DESC LIMIT 1",(x["id"],)).fetchone()) else None)
    events=[dict(x) for x in c.execute("SELECT * FROM lifecycle_events WHERE (entity_type='RECURRING_SERIES' AND entity_id=?) OR (entity_type='RECURRING_VERSION' AND entity_id IN (SELECT id FROM recurring_series_versions WHERE recurring_series_id=?)) OR (entity_type='EXPENSE' AND entity_id IN (SELECT id FROM expenses WHERE recurring_series_id=?)) ORDER BY id",(p["id"],p["id"],p["id"]))]
    return {"series":dict(s),"versions":versions,"occurrences":occurrences,"events":events},200
   if r.operation=="installments_list":
    items=[dict(x) for x in c.execute("SELECT s.*,s.original_total_cents AS total_cents,(SELECT description FROM expenses e WHERE e.installment_series_id=s.id ORDER BY installment_number LIMIT 1) AS description FROM installment_series s ORDER BY id DESC")]
    month=q.get("month",[None])[0]
    if month:
     if not re.fullmatch(r"\d{4}-\d{2}",month): raise HttpError(422,"VALIDATION_ERROR","month must be YYYY-MM")
     try:
      y,m=map(int,month.split("-")); import calendar
      start=date(y,m,1).isoformat(); end=date(y,m,calendar.monthrange(y,m)[1]).isoformat()
     except ValueError as exc:
      raise HttpError(422,"VALIDATION_ERROR","month must be a valid calendar month") from exc
     items=[item for item in items if c.execute("SELECT 1 FROM expenses WHERE installment_series_id=? AND expense_date BETWEEN ? AND ? AND lifecycle_state<>'DELETED' LIMIT 1",(item["id"],start,end)).fetchone()]
    for item in items:
     month_filter=""
     month_args=[item["id"]]
     if month:
      month_filter=" AND e.expense_date BETWEEN ? AND ?";month_args.extend([start,end])
     next_item=c.execute("SELECT e.installment_number,e.expense_date,e.amount_cents FROM expenses e LEFT JOIN invoices i ON i.id=e.invoice_id WHERE e.installment_series_id=?"+month_filter+" AND e.lifecycle_state='ACTIVE' AND (e.invoice_id IS NULL OR i.state NOT IN ('PAID','CANCELLED')) AND NOT EXISTS(SELECT 1 FROM expense_payments p WHERE p.expense_id=e.id AND p.reversed_at IS NULL) ORDER BY e.installment_number LIMIT 1",tuple(month_args)).fetchone() if not item["ended_at"] else None
     item["next_installment"]=dict(next_item) if next_item else None
    return {"items":items},200
   if r.operation=="installments_detail":
    s=c.execute("SELECT * FROM installment_series WHERE id=?",(p["id"],)).fetchone()
    if not s:raise NotFound("installment series not found")
    series=dict(s);series["total_cents"]=series["original_total_cents"];series["description"]=(c.execute("SELECT description FROM expenses WHERE installment_series_id=? ORDER BY installment_number LIMIT 1",(p["id"],)).fetchone() or [""])[0]
    installments=[{**dict(x),"effective_status":effective_status(c,x["id"],self.clock.today())} for x in c.execute("SELECT * FROM expenses WHERE installment_series_id=? ORDER BY installment_number",(p["id"],))]
    return {"series":series,"installments":installments,"events":[dict(x) for x in c.execute("SELECT * FROM lifecycle_events WHERE (entity_type='EXPENSE' AND entity_id IN (SELECT id FROM expenses WHERE installment_series_id=?)) OR (entity_type='INSTALLMENT_SERIES' AND entity_id=?) ORDER BY id",(p["id"],p["id"]))]},200
   if r.operation=="catalog_create":
    resource=r.path.split("/")[3];fn={"accounts":create_account,"categories":create_category,"tags":create_tag}[resource];return {"id":fn(c,str(b.get("name","")))},201
   if r.operation=="catalog_active":
    if not isinstance(b.get("active"),bool):raise HttpError(422,"VALIDATION_ERROR","active must be boolean")
    set_active(c,r.path.split("/")[3],p["id"],b["active"]);return {"id":p["id"],"active":b["active"]},200
   if r.operation=="card_edit":
    edit_card(c,p["id"],name=b.get("name"),payment_mode=b.get("payment_mode"),payment_account_id=b.get("payment_account_id"),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-card-edit")),clock=self.clock);return {"id":p["id"]},200
   if r.operation=="card_create":return {"id":create_card(c,str(b.get("name","")),b.get("payment_mode"),b.get("payment_account_id"),civil(b.get("effective_from"),"effective_from",self.clock.today()),integer(b.get("closing_day"),"closing_day",True),integer(b.get("due_day"),"due_day",True))},201
   if r.operation=="card_list":return {"items":[dict(x) for x in c.execute("SELECT * FROM cards ORDER BY id DESC")]},200
   if r.operation=="card_detail":
    card=c.execute("SELECT * FROM cards WHERE id=?",(p["id"],)).fetchone()
    if not card:raise NotFound("card not found")
    return {"card":dict(card),"calendar_versions":[dict(x) for x in c.execute("SELECT * FROM card_calendar_versions WHERE card_id=? ORDER BY effective_from,id",(p["id"],))],"invoices":[dict(x) for x in c.execute("SELECT * FROM invoices WHERE card_id=? ORDER BY due_date DESC,id DESC",(p["id"],))]},200
   if r.operation=="card_calendar_create":version,replay=add_card_calendar_version_idempotent(c,card_id=p["id"],effective_from=civil(b.get("effective_from"),"effective_from",self.clock.today()),closing_day=integer(b.get("closing_day"),"closing_day",True),due_day=integer(b.get("due_day"),"due_day",True),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-calendar")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"version_id":version,"replayed":replay},201 if not replay else 200
   if r.operation=="expense_create":return {"id":create_expense(c,description=str(b.get("description","")),amount_cents=integer(b.get("amount_cents"),"amount_cents",True),expense_date=civil(b.get("expense_date"),"expense_date",self.clock.today()),due_date=civil(b["due_date"],"due_date") if b.get("due_date") else None,planned_payment_method=b.get("planned_payment_method"),category_id=integer(b.get("category_id"),"category_id",True),account_id=b.get("account_id"),card_id=b.get("card_id"),notes=b.get("notes"),tags=tuple(b.get("tag_ids",())),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-create")),clock=self.clock)},201
   if r.operation=="expense_list":return self.list_expenses(c,q),200
   if r.operation=="expense_detail":
    x=c.execute("SELECT * FROM expenses WHERE id=?",(p["id"],)).fetchone()
    if not x:raise NotFound("expense not found")
    item=dict(x);item["effective_status"]=effective_status(c,p["id"],self.clock.today());item["requires_manual_action"]=requires_manual_action(c,"EXPENSE",p["id"]);item["requires_attention"]=requires_attention(c,"EXPENSE",p["id"])
    item["tags"]=[dict(row) for row in c.execute("SELECT t.* FROM tags t JOIN expense_tags et ON et.tag_id=t.id WHERE et.expense_id=? ORDER BY t.id",(p["id"],))]
    item["payments"]=[dict(row) for row in c.execute("SELECT * FROM expense_payments WHERE expense_id=? ORDER BY id",(p["id"],))]
    return item,200
   if r.operation=="expense_edit":edit_expense(c,p["id"],description=b.get("description"),amount_cents=b.get("amount_cents"),due_date=civil(b["due_date"],"due_date") if b.get("due_date") else None,category_id=b.get("category_id"),notes=b.get("notes"),tags=tuple(b["tag_ids"]) if "tag_ids" in b else None,actor=i.client_id,correlation_id=str(b.get("correlation_id","api-edit")),clock=self.clock);return {"id":p["id"]},200
   if r.operation=="expense_delete":
    logical_delete_expense(c,p["id"],i.client_id,str(b.get("correlation_id","api-delete")),self.clock);return {"id":p["id"],"deleted":True},200
   if r.operation=="expense_pay":payment,replay=pay_expense(c,expense_id=p["id"],paid_on=civil(b.get("paid_on"),"paid_on",self.clock.today()),payment_method=b.get("payment_method"),account_id=b.get("account_id"),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-pay")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"payment_id":payment,"replayed":replay},200
   if r.operation in {"expense_cancel","expense_reactivate"}:(cancel_expense if r.operation.endswith("cancel") else reactivate_expense)(c,p["id"],i.client_id,str(b.get("correlation_id",r.operation)),self.clock);return {"id":p["id"]},200
   if r.operation=="expense_reverse":payment,replay=reverse_expense_payment(c,payment_id=p["id"],reversed_on=civil(b.get("reversed_on"),"reversed_on",self.clock.today()),reason=str(b.get("reason","")),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-reverse")),clock=self.clock,client_id=i.client_id,idempotency_key=key,new_due_date=civil(b.get("new_due_date"),"new_due_date") if b.get("new_due_date") is not None else None);return {"payment_id":payment,"replayed":replay},200
   if r.operation=="expense_replace":payment,replay=replace_expense_payment(c,payment_id=p["id"],reversed_on=civil(b.get("reversed_on"),"reversed_on",self.clock.today()),reason=str(b.get("reason","")),new_paid_on=civil(b.get("new_paid_on"),"new_paid_on",self.clock.today()),new_method=b.get("payment_method"),new_account_id=b.get("account_id"),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-replace")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"payment_id":payment,"replayed":replay},200
   if r.operation=="expense_move_invoice":expense,replay=move_card_expense_idempotent(c,expense_id=p["id"],target_invoice_id=integer(b.get("target_invoice_id"),"target_invoice_id",True),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-move")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"expense_id":expense,"replayed":replay},200
   if r.operation=="expense_audit":return {"payments":[dict(x) for x in c.execute("SELECT * FROM expense_payments WHERE expense_id=? ORDER BY id",(p["id"],))],"events":[dict(x) for x in c.execute("SELECT * FROM lifecycle_events WHERE entity_type='EXPENSE' AND entity_id=? ORDER BY id",(p["id"],))]},200
   if r.operation=="revenue_create":rid,replay=create_revenue_idempotent(c,description=str(b.get("description","")),amount_cents=integer(b.get("amount_cents"),"amount_cents",True),competence_date=civil(b.get("competence_date"),"competence_date",self.clock.today()),expected_on=civil(b.get("expected_on"),"expected_on",self.clock.today()),category_id=integer(b.get("category_id"),"category_id",True),account_id=b.get("account_id"),notes=b.get("notes"),tags=tuple(b.get("tag_ids",())),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-revenue-create")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"id":rid,"replayed":replay},201 if not replay else 200
   if r.operation=="revenue_list":return self.list_revenues(c,q),200
   if r.operation=="revenue_detail":
    x=c.execute("SELECT * FROM revenues WHERE id=?",(p["id"],)).fetchone()
    if not x:raise NotFound("revenue not found")
    item=dict(x);item["financial_status"]=revenue_status(c,x,self.clock.today());item["tags"]=[dict(z) for z in c.execute("SELECT t.* FROM tags t JOIN revenue_tags rt ON rt.tag_id=t.id WHERE rt.revenue_id=?",(p["id"],))];item["receipts"]=[dict(z) for z in c.execute("SELECT * FROM revenue_receipts WHERE revenue_id=? ORDER BY id",(p["id"],))];return item,200
   if r.operation=="revenue_edit":edit_revenue(c,p["id"],description=b.get("description"),amount_cents=b.get("amount_cents"),competence_date=civil(b["competence_date"],"competence_date") if b.get("competence_date") else None,expected_on=civil(b["expected_on"],"expected_on") if b.get("expected_on") else None,category_id=b.get("category_id"),account_id=b.get("account_id"),notes=b.get("notes"),tags=tuple(b["tag_ids"]) if "tag_ids" in b else None,actor=i.client_id,correlation_id=str(b.get("correlation_id","api-revenue-edit")),clock=self.clock);return {"id":p["id"]},200
   if r.operation=="revenue_receive":receipt,replay=receive_revenue_idempotent(c,p["id"],received_on=civil(b.get("received_on"),"received_on",self.clock.today()),account_id=integer(b.get("account_id"),"account_id",True),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-revenue-receive")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"receipt_id":receipt,"replayed":replay},200
   if r.operation=="revenue_cancel":rid,replay=cancel_revenue_idempotent(c,p["id"],actor=i.client_id,correlation_id=str(b.get("correlation_id","api-revenue-cancel")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"id":rid,"replayed":replay},200
   if r.operation=="revenue_reverse":receipt,replay=reverse_revenue_receipt_idempotent(c,p["id"],reversed_on=civil(b.get("reversed_on"),"reversed_on",self.clock.today()),reason=str(b.get("reason","")),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-revenue-reverse")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"receipt_id":receipt,"replayed":replay},200
   if r.operation=="revenue_audit":return {"receipts":[dict(x) for x in c.execute("SELECT * FROM revenue_receipts WHERE revenue_id=? ORDER BY id",(p["id"],))],"events":[dict(x) for x in c.execute("SELECT * FROM lifecycle_events WHERE entity_type='REVENUE' AND entity_id=? ORDER BY id",(p["id"],))]},200
   if r.operation=="revenue_series_list":
    items=[dict(x) for x in c.execute("SELECT * FROM revenue_recurring_series ORDER BY id DESC")]
    forecast_day=self.clock.today()
    if q.get("month",[None])[0]:
     raw=q["month"][0]
     try:
      y,m=map(int,raw.split("-"));forecast_day=date(y,m,1)
     except (ValueError,TypeError):raise HttpError(422,"VALIDATION_ERROR","month must be a valid calendar month")
    for item in items:
     item.update(revenue_forecast(c,item,forecast_day) or {"next_occurrence":None,"next_due_date":None,"association_name":None})
    return {"items":items},200
   if r.operation=="revenue_series_detail":
    s=require_row(c,"SELECT * FROM revenue_recurring_series WHERE id=?",(p["id"],),"revenue series");return {"series":dict(s),"occurrences":[dict(x) for x in c.execute("SELECT r.* FROM revenues r JOIN revenue_recurring_occurrences o ON o.revenue_id=r.id WHERE o.series_id=? ORDER BY o.occurrence_date",(p["id"],))]},200
   if r.operation=="revenue_series_create":sid,replay=create_revenue_series_idempotent(c,description=str(b.get("description","")),amount_cents=integer(b.get("amount_cents"),"amount_cents",True),start_date=civil(b.get("start_date"),"start_date",self.clock.today()),end_date=civil(b["end_date"],"end_date") if b.get("end_date") else None,frequency=b.get("frequency"),expected_day=integer(b.get("expected_day"),"expected_day",True),category_id=integer(b.get("category_id"),"category_id",True),account_id=b.get("account_id"),tags=tuple(b.get("tag_ids",())),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-revenue-series")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"id":sid,"replayed":replay},201 if not replay else 200
   if r.operation=="revenue_series_materialize":ids,replay=materialize_revenue_series_idempotent(c,series_id=p["id"],through=civil(b.get("through"),"through",self.clock.today()),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-revenue-materialize")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"series_id":p["id"],"revenue_ids":ids,"replayed":replay},200
   if r.operation=="revenue_series_end":sid,replay=end_revenue_series_idempotent(c,series_id=p["id"],actor=i.client_id,correlation_id=str(b.get("correlation_id","api-revenue-end")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"id":sid,"replayed":replay},200
   if r.operation=="revenue_series_change_from":vid,replay=change_revenue_series_from_date(c,series_id=p["id"],effective_from=civil(b.get("effective_from"),"effective_from",self.clock.today()),description=str(b.get("description","")),amount_cents=integer(b.get("amount_cents"),"amount_cents",True),frequency=b.get("frequency"),expected_day=integer(b.get("expected_day"),"expected_day",True),category_id=integer(b.get("category_id"),"category_id",True),account_id=b.get("account_id"),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-revenue-series-change")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"version_id":vid,"replayed":replay},200
   if r.operation=="series_create":sid,vid=create_series(c,start_date=civil(b.get("start_date"),"start_date",self.clock.today()),description=str(b.get("description","")),category_id=integer(b.get("category_id"),"category_id",True),frequency=b.get("frequency"),base_day=b.get("base_day"),amount_cents=integer(b.get("amount_cents"),"amount_cents",True),payment_method=b.get("payment_method"),account_id=b.get("account_id"),card_id=b.get("card_id"),due_rule=b.get("due_rule"),due_offset_days=b.get("due_offset_days"),due_day=b.get("due_day"),tags=tuple(b.get("tag_ids",())),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-series")),clock=self.clock,end_date=civil(b["end_date"],"end_date") if b.get("end_date") else None,materialize_through=materialization_horizon(self.clock),**({"client_id":i.client_id,"idempotency_key":key} if key is not None else {}));return {"id":sid,"version_id":vid},201
   if r.operation=="series_materialize":return {"expense_ids":materialize(c,series_id=p["id"],through=civil(b.get("through"),"through",date(self.clock.today().year,12,31)),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-materialize")),clock=self.clock)},200
   if r.operation=="series_end":sid,replay=end_series_idempotent(c,series_id=p["id"],cut_date=civil(b.get("cut_date"),"cut_date",self.clock.today()),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-end")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"series_id":sid,"replayed":replay},200
   if r.operation=="occurrence_payment_method":
    eid,replay=change_occurrence_payment_method(c,expense_id=p["id"],payment_method=b.get("payment_method"),account_id=integer(b["account_id"],"account_id",True) if b.get("account_id") is not None else None,card_id=integer(b["card_id"],"card_id",True) if b.get("card_id") is not None else None,due_date=civil(b["due_date"],"due_date") if b.get("due_date") else None,actor=i.client_id,correlation_id=str(b.get("correlation_id","api-occurrence-method")),clock=self.clock,client_id=i.client_id,idempotency_key=key)
    return {"expense_id":eid,"replayed":replay},200
   if r.operation=="occurrence_override":return {"override_id":create_occurrence_override(c,expense_id=p["id"],reason=str(b.get("reason","")),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-override")),clock=self.clock)},201
   if r.operation=="occurrence_override_remove":
    if not str(b.get("reason","")).strip():raise ValidationError("override removal requires reason")
    remove_occurrence_override(c,override_id=p["id"],reason=b["reason"],actor=i.client_id,correlation_id=str(b.get("correlation_id","api-remove-override")),clock=self.clock);return {"override_id":p["id"]},200
   if r.operation=="occurrence_cancel":cancel_occurrence_only(c,expense_id=p["id"],actor=i.client_id,correlation_id=str(b.get("correlation_id","api-only")),clock=self.clock);return {"id":p["id"]},200
   if r.operation=="occurrence_cancel_future":sid,replay=cancel_this_and_future(c,anchor_expense_id=p["id"],actor=i.client_id,correlation_id=str(b.get("correlation_id","api-cut")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"series_id":sid,"replayed":replay},200
   if r.operation=="occurrence_change_future":vid,replay=change_this_and_future(c,anchor_expense_id=p["id"],description=str(b.get("description","")),amount_cents=integer(b.get("amount_cents"),"amount_cents",True),frequency=b.get("frequency"),base_day=b.get("base_day"),payment_method=b.get("payment_method"),account_id=b.get("account_id"),card_id=b.get("card_id"),due_rule=b.get("due_rule"),due_offset_days=b.get("due_offset_days"),due_day=b.get("due_day"),tags=tuple(b.get("tag_ids",())),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-tf")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"version_id":vid,"replayed":replay},200
   if r.operation=="series_change_from":
    vid,replay=change_series_from_date(c,series_id=p["id"],effective_from=civil(b.get("effective_from"),"effective_from",self.clock.today()),description=str(b.get("description","")),amount_cents=integer(b.get("amount_cents"),"amount_cents",True),category_id=integer(b.get("category_id"),"category_id",True),frequency=b.get("frequency"),base_day=b.get("base_day"),payment_method=b.get("payment_method"),account_id=b.get("account_id"),card_id=b.get("card_id"),due_rule=b.get("due_rule"),due_offset_days=b.get("due_offset_days"),due_day=b.get("due_day"),tags=tuple(b.get("tag_ids",())),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-series-change")),clock=self.clock,client_id=i.client_id,idempotency_key=key,bind_category_identity=i.role=="EXTERNAL_CLIENT");return {"version_id":vid,"replayed":replay},200
   if r.operation=="installments_create":
    method=b.get("payment_method","CREDIT_CARD")
    if not isinstance(method,str):raise ValidationError("payment_method must be a string")
    if not isinstance(b.get("tag_ids",[]),list):raise ValidationError("tag_ids must be an array")
    if method!="CREDIT_CARD" and key is None:raise HttpError(400,"IDEMPOTENCY_KEY_REQUIRED","Idempotency-Key is required for V17 multimethod installments")
    values=dict(purchase_date=civil(b.get("purchase_date"),"purchase_date",self.clock.today()),card_id=integer(b["card_id"],"card_id",True) if b.get("card_id") is not None else None,total_cents=integer(b.get("total_cents"),"total_cents",True),count=integer(b.get("count"),"count",True),category_id=integer(b.get("category_id"),"category_id",True),description=str(b.get("description","")),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-installments")),clock=self.clock,payment_method=method,account_id=integer(b["account_id"],"account_id",True) if b.get("account_id") is not None else None,first_due_date=civil(b["first_due_date"],"first_due_date") if b.get("first_due_date") else None,tags=tuple(b.get("tag_ids",())))
    if key:
     result,replay=create_installments_idempotent(c,client_id=i.client_id,idempotency_key=key,**values);return {**result,"replayed":replay},200 if replay else 201
    sid,ids=create_installment_series(c,**values);return {"id":sid,"expense_ids":ids,"replayed":False},201
   if r.operation=="installments_cancel":cancel_remaining(c,series_id=p["id"],from_installment=integer(b.get("from_installment"),"from_installment",True),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-cancel")),clock=self.clock);return {"id":p["id"]},200
   if r.operation=="invoice_list":return self.list_invoices(c,q),200
   if r.operation=="invoice_detail":
    x=c.execute("SELECT * FROM invoices WHERE id=?",(p["id"],)).fetchone()
    if not x:raise NotFound("invoice not found")
    item=dict(x);item["effective_total_cents"]=effective_total(c,p["id"]);item["paid_cents"]=paid_cents(c,p["id"]);item["balance_cents"]=max(0,item["effective_total_cents"]-item["paid_cents"]);item["requires_manual_action"]=requires_manual_action(c,"INVOICE",p["id"]);item["requires_attention"]=requires_attention(c,"INVOICE",p["id"])
    item["items"]=[dict(row) for row in c.execute("SELECT * FROM expenses WHERE invoice_id=? ORDER BY expense_date,id",(p["id"],))];item["payments"]=[dict(row) for row in c.execute("SELECT * FROM invoice_payments WHERE invoice_id=? ORDER BY id",(p["id"],))];item["revisions"]=[dict(row) for row in c.execute("SELECT * FROM invoice_total_revisions WHERE invoice_id=? ORDER BY id",(p["id"],))]
    item["automations"]=[dict(row) for row in c.execute("SELECT ae.* FROM settlements s JOIN automation_executions ae ON ae.settlement_id=s.id WHERE s.obligation_type='INVOICE' AND s.obligation_id=? ORDER BY ae.id",(p["id"],))];return item,200
   if r.operation=="invoice_close":return {"id":p["id"],"state":close_invoice(c,p["id"],i.client_id,str(b.get("correlation_id","api-close")),self.clock)},200
   if r.operation=="invoice_cancel":cancel_invoice(c,p["id"],i.client_id,str(b.get("correlation_id","api-cancel")),self.clock);return {"id":p["id"],"state":"CANCELLED"},200
   if r.operation=="invoice_pay":payment,replay=pay_invoice_idempotent(c,invoice_id=p["id"],amount_cents=integer(b.get("amount_cents"),"amount_cents",True),paid_on=civil(b.get("paid_on"),"paid_on",self.clock.today()),method=b.get("payment_method"),account_id=integer(b.get("account_id"),"account_id",True),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-pay")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"payment_id":payment,"replayed":replay},200
   if r.operation=="invoice_reverse":payment,replay=reverse_invoice_payment_idempotent(c,payment_id=p["id"],reversed_on=civil(b.get("reversed_on"),"reversed_on",self.clock.today()),actor=i.client_id,reason=str(b.get("reason","")),correlation_id=str(b.get("correlation_id","api-reverse")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"payment_id":payment,"replayed":replay},200
   if r.operation=="invoice_correct":revision,replay=revise_total_idempotent(c,invoice_id=p["id"],new_total_cents=integer(b.get("new_total_cents"),"new_total_cents"),reason=str(b.get("reason","")),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-correct")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"revision_id":revision,"replayed":replay},200
   if r.operation=="invoice_payment_config":invoice,replay=override_invoice_payment_config(c,invoice_id=p["id"],payment_mode=b.get("payment_mode"),payment_account_id=b.get("payment_account_id"),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-config")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"invoice_id":invoice,"replayed":replay},200
   if r.operation=="invoice_audit":return {"payments":[dict(x) for x in c.execute("SELECT * FROM invoice_payments WHERE invoice_id=? ORDER BY id",(p["id"],))],"revisions":[dict(x) for x in c.execute("SELECT * FROM invoice_total_revisions WHERE invoice_id=? ORDER BY id",(p["id"],))]},200
   if r.operation=="settlement_reactivate":settlement,replay=reactivate_auto_settlement_idempotent(c,previous_settlement_id=p["id"],new_settlement_key=str(b.get("new_settlement_key","")),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-reactivate")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"settlement_id":settlement,"replayed":replay},200
   if r.operation=="auto_payment_reverse":payment,replay=reverse_auto_payment_idempotent(c,obligation_type=str(b.get("obligation_type","")),payment_id=p["id"],reason=str(b.get("reason","")),actor=i.client_id,correlation_id=str(b.get("correlation_id","api-auto-reverse")),clock=self.clock,client_id=i.client_id,idempotency_key=key);return {"payment_id":payment,"replayed":replay},200
   if r.operation=="aggregates":start=civil(q.get("start",[None])[0],"start",date(self.clock.today().year,self.clock.today().month,1));end=civil(q.get("end",[None])[0],"end",self.clock.today());return {"start":start,"end":end,"recognized_cents":recognized_expenses(c,start,end),"pending_cents":pending_total(c,start,end),"overdue_cents":overdue_total(c,self.clock.today()),"net_paid_cents":net_paid(c,start,end),"revenue_expected_cents":revenue_expected(c,start,end),"revenue_received_cents":revenue_received(c,start,end)},200
   if r.operation=="dashboard":return self.dashboard_data(c,q),200
   raise HttpError(404,"NOT_FOUND","operation not found")
  finally:c.close()
 def dashboard_data(self,c,q=None):
  import calendar
  today=self.clock.today();raw=(q or {}).get("month",[None])[0]
  if raw:
   if not re.fullmatch(r"\d{4}-\d{2}",raw):raise HttpError(422,"VALIDATION_ERROR","month must be YYYY-MM")
   try:year,month=map(int,raw.split("-"));start=date(year,month,1)
   except ValueError as error:raise HttpError(422,"VALIDATION_ERROR","invalid month") from error
  else:start=date(today.year,today.month,1)
  end=date(start.year,start.month,calendar.monthrange(start.year,start.month)[1])
  summary={"revenue_expected_cents":revenue_expected(c,start,end),"revenue_received_cents":revenue_realized(c,start,end),"expense_recognized_cents":recognized_expenses(c,start,end),"expense_pending_cents":pending_total(c,start,end),"expense_overdue_cents":c.execute("SELECT COALESCE(SUM(e.amount_cents),0) FROM expenses e WHERE e.lifecycle_state='ACTIVE' AND e.expense_date BETWEEN ? AND ? AND e.due_date<? AND NOT EXISTS(SELECT 1 FROM expense_payments p WHERE p.expense_id=e.id AND p.reversed_at IS NULL)",(start.isoformat(),end.isoformat(),today.isoformat())).fetchone()[0],"net_paid_cents":net_paid(c,start,end)}
  summary["invoice_open_cents"]=c.execute("SELECT COALESCE(SUM(e.amount_cents),0) FROM invoices i JOIN expenses e ON e.invoice_id=i.id AND e.lifecycle_state='ACTIVE' WHERE i.state IN('OPEN','CLOSED') AND i.due_date BETWEEN ? AND ?",(start.isoformat(),end.isoformat())).fetchone()[0]
  upcoming=[dict(x) for x in c.execute("SELECT e.id,e.description,e.amount_cents,e.due_date,c.name category_name FROM expenses e JOIN categories c ON c.id=e.category_id WHERE e.lifecycle_state='ACTIVE' AND e.due_date BETWEEN ? AND ? AND NOT EXISTS(SELECT 1 FROM expense_payments p WHERE p.expense_id=e.id AND p.reversed_at IS NULL) ORDER BY e.due_date,e.id LIMIT 6",(start.isoformat(),end.isoformat()))]
  invoices=[dict(x) for x in c.execute("SELECT i.id,i.card_id,c.name card_name,i.closing_date,i.due_date,i.state,COALESCE((SELECT SUM(e.amount_cents) FROM expenses e WHERE e.invoice_id=i.id AND e.lifecycle_state='ACTIVE'),0) amount_cents FROM invoices i JOIN cards c ON c.id=i.card_id WHERE i.state IN('OPEN','CLOSED') AND i.due_date BETWEEN ? AND ? ORDER BY i.due_date,i.id LIMIT 4",(start.isoformat(),end.isoformat()))]
  recurring=[{"kind":"EXPENSE","id":s["id"],"ended_at":s["ended_at"],**forecast} for s in c.execute("SELECT * FROM recurring_series WHERE ended_at IS NULL ORDER BY id DESC") if (forecast:=expense_forecast(c,s["id"],today))]
  recurring += [{"kind":"REVENUE","id":s["id"],"description":s["description"],"frequency":s["frequency"],"amount_cents":s["amount_cents"],"ended_at":s["ended_at"],**forecast} for s in c.execute("SELECT * FROM revenue_recurring_series WHERE active=1 ORDER BY id DESC") if (forecast:=revenue_forecast(c,s,today))]
  recurring=sorted(recurring,key=lambda x:(x["next_due_date"] or x["next_occurrence"],x["kind"],x["id"]))[:6]
  categories=[dict(x) for x in c.execute("SELECT c.name,SUM(e.amount_cents) amount_cents FROM expenses e JOIN categories c ON c.id=e.category_id WHERE e.lifecycle_state='ACTIVE' AND e.expense_date BETWEEN ? AND ? GROUP BY c.id,c.name ORDER BY amount_cents DESC LIMIT 6",(start.isoformat(),end.isoformat()))]
  recent=[dict(x) for x in c.execute("SELECT * FROM (SELECT 'EXPENSE' kind,e.id,e.description,e.amount_cents,e.expense_date event_date,c.name category_name,e.lifecycle_state state,(e.recurring_series_id IS NOT NULL) is_recurring FROM expenses e JOIN categories c ON c.id=e.category_id WHERE e.lifecycle_state='ACTIVE' AND e.expense_date BETWEEN ? AND ? UNION ALL SELECT 'REVENUE',r.id,r.description,r.amount_cents,r.competence_date,c.name,r.lifecycle_state,EXISTS(SELECT 1 FROM revenue_recurring_occurrences o WHERE o.revenue_id=r.id) FROM revenues r JOIN categories c ON c.id=r.category_id WHERE r.lifecycle_state='ACTIVE' AND r.competence_date BETWEEN ? AND ?) ORDER BY event_date DESC,id DESC LIMIT 8",(start.isoformat(),end.isoformat(),start.isoformat(),end.isoformat()))]
  trend=[]
  for offset in range(5,-1,-1):
   absolute=start.year*12+start.month-1-offset;year,month=divmod(absolute,12);month+=1
   month_start=date(year,month,1);month_end=date(year,month,calendar.monthrange(year,month)[1])
   trend.append({"month":month_start.isoformat(),"revenue_cents":revenue_realized(c,month_start,month_end),"expense_cents":net_paid(c,month_start,month_end)})
  return {"month":start.strftime("%Y-%m"),"summary":summary,"upcoming":upcoming,"invoices":invoices,"recurring":recurring,"categories":categories,"recent":recent,"trend":trend}
 def list_revenues(self,c,q):
  page=query_positive_int(q.get("page",["1"])[0],"page");size=query_positive_int(q.get("page_size",["50"])[0],"page_size")
  if size not in {25,50,100}:raise HttpError(422,"VALIDATION_ERROR","page_size must be 25, 50 or 100")
  clauses=[];args=[]
  if q.get("start",[None])[0]:clauses.append("r.competence_date>=?");args.append(civil(q["start"][0],"start").isoformat())
  if q.get("end",[None])[0]:clauses.append("r.competence_date<=?");args.append(civil(q["end"][0],"end").isoformat())
  if q.get("category_id",[None])[0]:clauses.append("r.category_id=?");args.append(query_positive_int(q["category_id"][0],"category_id"))
  if q.get("account_id",[None])[0]:clauses.append("r.account_id=?");args.append(query_positive_int(q["account_id"][0],"account_id"))
  if q.get("tag",[None])[0]:clauses.append("EXISTS(SELECT 1 FROM revenue_tags rt WHERE rt.revenue_id=r.id AND rt.tag_id=?)");args.append(query_positive_int(q["tag"][0],"tag"))
  if q.get("search",[None])[0]:clauses.append("lower(r.description) LIKE ?");args.append("%"+q["search"][0].strip().lower()+"%")
  rows=c.execute("SELECT r.* FROM revenues r"+(" WHERE "+" AND ".join(clauses) if clauses else "")+" ORDER BY r.expected_on,r.id",args).fetchall()
  status_filter=q.get("status",[None])[0]
  if status_filter and status_filter not in {"PENDING","OVERDUE","RECEIVED","CANCELLED"}:raise HttpError(422,"VALIDATION_ERROR","invalid revenue status")
  items=[]
  for row in rows:
   item=dict(row);item["financial_status"]=revenue_status(c,row,self.clock.today())
   if not status_filter or item["financial_status"]==status_filter:items.append(item)
  offset=(page-1)*size
  return {"items":items[offset:offset+size],"page":page,"page_size":size,"has_more":len(items)>offset+size}
 def list_expenses(self,c,q):
  size=query_positive_int(q.get("page_size",["50"])[0],"page_size");page=query_positive_int(q.get("page",["1"])[0],"page")
  if size not in {25,50,100} or (page-1)*size>9223372036854775807:raise HttpError(422,"VALIDATION_ERROR","invalid pagination")
  where=["e.lifecycle_state<>'DELETED'"];v=[]
  for key,col in (("category_id","category_id"),("account_id","account_id"),("card_id","card_id")):
   if key in q:where.append(f"e.{col}=?");v.append(query_positive_int(q[key][0],key))
  if "start" in q:where.append("e.expense_date>=?");v.append(civil(q["start"][0],"start").isoformat())
  if "end" in q:where.append("e.expense_date<=?");v.append(civil(q["end"][0],"end").isoformat())
  if q.get("search",[None])[0]:where.append("lower(e.description) LIKE ?");v.append("%"+q["search"][0].strip().lower()+"%")
  preset=q.get("preset",[None])[0]
  if preset:
   from datetime import timedelta
   today=self.clock.today()
   if preset=="today":start=end=today
   elif preset=="next_7_days":start,end=today,today+timedelta(days=7)
   elif preset=="next_30_days":start,end=today,today+timedelta(days=30)
   elif preset=="current_month":
    import calendar
    start=date(today.year,today.month,1);end=date(today.year,today.month,calendar.monthrange(today.year,today.month)[1])
   else:raise HttpError(422,"VALIDATION_ERROR","invalid preset")
   where.extend(["e.due_date>=?","e.due_date<=?"]);v.extend([start.isoformat(),end.isoformat()])
  flag=q.get("financial_status",[None])[0]
  if flag=="overdue":where.extend(["e.lifecycle_state='ACTIVE'","e.due_date<?","NOT EXISTS(SELECT 1 FROM expense_payments p WHERE p.expense_id=e.id AND p.reversed_at IS NULL)"]);v.append(self.clock.today().isoformat())
  elif flag=="paid":where.append("EXISTS(SELECT 1 FROM expense_payments p WHERE p.expense_id=e.id AND p.reversed_at IS NULL)")
  elif flag=="cancelled":where.append("e.lifecycle_state='CANCELLED'")
  elif flag=="need_pay":where.extend(["e.lifecycle_state='ACTIVE'","e.planned_payment_method<>'CREDIT_CARD'","NOT EXISTS(SELECT 1 FROM expense_payments p WHERE p.expense_id=e.id AND p.reversed_at IS NULL)"])
  elif flag=="auto_debit":where.append("e.planned_payment_method='AUTO_DEBIT'")
  elif flag is not None:raise HttpError(422,"VALIDATION_ERROR","invalid financial_status")
  if "tag" in q:marks=",".join("?" for _ in q["tag"]);where.append(f"EXISTS(SELECT 1 FROM expense_tags et WHERE et.expense_id=e.id AND et.tag_id IN ({marks}))");v.extend(query_positive_int(value,"tag") for value in q["tag"])
  attention=q.get("requires_attention",[None])[0]
  if attention not in {None,"true","false"}:raise HttpError(422,"VALIDATION_ERROR","invalid requires_attention")
  rows=c.execute(f"SELECT e.*,cat.name category_name,a.name account_name,card.name card_name FROM expenses e JOIN categories cat ON cat.id=e.category_id LEFT JOIN accounts a ON a.id=e.account_id LEFT JOIN cards card ON card.id=e.card_id WHERE {' AND '.join(where)} ORDER BY e.expense_date DESC,e.id DESC",v).fetchall()
  if attention is not None:rows=[x for x in rows if requires_attention(c,"EXPENSE",x["id"]) is (attention=="true")]
  start=(page-1)*size;rows=rows[start:start+size+1];has_more=len(rows)>size;rows=rows[:size]
  items=[]
  for x in rows:
   item=dict(x);item["effective_status"]=effective_status(c,x["id"],self.clock.today());item["requires_manual_action"]=requires_manual_action(c,"EXPENSE",x["id"]);item["requires_attention"]=requires_attention(c,"EXPENSE",x["id"]);items.append(item)
  return {"items":items,"page":page,"page_size":size,"has_more":has_more}
 def list_invoices(self,c,q):
  size=query_positive_int(q.get("page_size",["50"])[0],"page_size");page=query_positive_int(q.get("page",["1"])[0],"page")
  if size not in {25,50,100} or (page-1)*size>9223372036854775807:raise HttpError(422,"VALIDATION_ERROR","invalid pagination")
  where=["1=1"];values=[]
  for key in ("card_id",):
   if key in q:where.append(f"{key}=?");values.append(query_positive_int(q[key][0],key))
  if "state" in q:
   if q["state"][0] not in {"OPEN","CLOSED","PAID","CANCELLED"}:raise HttpError(422,"VALIDATION_ERROR","invalid invoice state")
   where.append("state=?");values.append(q["state"][0])
  if "start" in q:where.append("due_date>=?");values.append(civil(q["start"][0],"start").isoformat())
  if "end" in q:where.append("due_date<=?");values.append(civil(q["end"][0],"end").isoformat())
  attention=q.get("requires_attention",[None])[0]
  if attention not in {None,"true","false"}:raise HttpError(422,"VALIDATION_ERROR","invalid requires_attention")
  if attention is None:
   rows=c.execute(f"SELECT * FROM invoices WHERE {' AND '.join(where)} ORDER BY due_date DESC,id DESC LIMIT ? OFFSET ?",(*values,size+1,(page-1)*size)).fetchall()
  else:
   matching=[x for x in c.execute(f"SELECT * FROM invoices WHERE {' AND '.join(where)} ORDER BY due_date DESC,id DESC",values).fetchall() if requires_attention(c,"INVOICE",x["id"]) is (attention=="true")]
   rows=matching[(page-1)*size:(page-1)*size+size+1]
  has_more=len(rows)>size;rows=rows[:size]
  items=[]
  for x in rows:
   item=dict(x);item["effective_total_cents"]=effective_total(c,x["id"]);item["paid_cents"]=paid_cents(c,x["id"]);item["balance_cents"]=max(0,item["effective_total_cents"]-item["paid_cents"]);item["requires_manual_action"]=requires_manual_action(c,"INVOICE",x["id"]);item["requires_attention"]=requires_attention(c,"INVOICE",x["id"]);items.append(item)
  return {"items":items,"page":page,"page_size":size,"has_more":has_more}
 def openapi(self):
  date_schema={"type":"string","format":"date","description":"Financial civil date (YYYY-MM-DD)"}
  money={"type":"integer","minimum":0,"description":"Amount in integer cents"}
  signed_money={"type":"integer","description":"Net realized flow in integer cents; reversals may make it negative"}
  positive_money={"type":"integer","minimum":1,"description":"Positive amount in integer cents"}
  integer_id={"type":"integer","minimum":1,"maximum":9223372036854775807}
  enums={"payment_method":["PIX","DEBIT","BANK_TRANSFER","CASH","AUTO_DEBIT"],"planned_payment_method":["PIX","DEBIT","CASH","BANK_SLIP","AUTO_DEBIT","CREDIT_CARD"],"payment_mode":["MANUAL","AUTO_DEBIT"],"frequency":["WEEKLY","BIWEEKLY","MONTHLY","BIMONTHLY","QUARTERLY","SEMIANNUAL","ANNUAL"],"due_rule":["SAME_DAY","OFFSET","DAY_OF_MONTH","INVOICE"],"obligation_type":["EXPENSE","INVOICE"]}
  date_fields={"effective_from","expense_date","competence_date","expected_on","received_on","due_date","paid_on","reversed_on","new_paid_on","new_due_date","start_date","end_date","through","cut_date","purchase_date"};money_fields={"amount_cents","total_cents","new_total_cents"};id_fields={"category_id","account_id","card_id","target_invoice_id","payment_account_id"}
  body_fields={"assistant_expense_create":(["description","amount_cents","expense_date","due_date","planned_payment_method","category_id","account_id","card_id","notes","tag_ids"],["description","amount_cents","planned_payment_method","category_id"]),
   "revenue_series_create":(["description","amount_cents","start_date","end_date","frequency","expected_day","category_id","account_id","tag_ids","correlation_id"],["description","amount_cents","start_date","frequency","expected_day","category_id"]),"revenue_series_materialize":(["through","correlation_id"],[]),"revenue_series_end":(["correlation_id"],[]),"revenue_series_change_from":(["effective_from","description","amount_cents","frequency","expected_day","category_id","account_id","correlation_id"],["effective_from","description","amount_cents","frequency","expected_day","category_id"]),
   "revenue_create":(["description","amount_cents","competence_date","expected_on","category_id","account_id","notes","tag_ids","correlation_id"],["description","amount_cents","category_id"]),"revenue_edit":(["description","amount_cents","competence_date","expected_on","category_id","account_id","notes","tag_ids","correlation_id"],[]),"revenue_receive":(["received_on","account_id","correlation_id"],["account_id"]),"revenue_cancel":(["correlation_id"],[]),"revenue_reverse":(["reversed_on","reason","correlation_id"],["reason"]),
   "catalog_create":(["name"],["name"]),"catalog_active":(["active"],["active"]),"card_edit":(["name","payment_mode","payment_account_id","correlation_id"],[]),"card_create":(["name","payment_mode","payment_account_id","effective_from","closing_day","due_day"],["name","payment_mode","closing_day","due_day"]),"card_calendar_create":(["effective_from","closing_day","due_day","correlation_id"],["effective_from","closing_day","due_day"]),
   "expense_create":(["description","amount_cents","expense_date","due_date","planned_payment_method","category_id","account_id","card_id","notes","tag_ids","correlation_id"],["description","amount_cents","planned_payment_method","category_id"]),"expense_edit":(["description","amount_cents","due_date","category_id","notes","tag_ids","correlation_id"],[]),"expense_pay":(["paid_on","payment_method","account_id","correlation_id"],["payment_method"]),"expense_cancel":(["correlation_id"],[]),"expense_reactivate":(["correlation_id"],[]),"expense_delete":(["correlation_id"],[]),"expense_reverse":(["reversed_on","new_due_date","reason","correlation_id"],["reason"]),"expense_replace":(["reversed_on","reason","new_paid_on","payment_method","account_id","correlation_id"],["reason","payment_method"]),"expense_move_invoice":(["target_invoice_id","correlation_id"],["target_invoice_id"]),
   "series_create":(["start_date","end_date","description","category_id","frequency","base_day","amount_cents","payment_method","account_id","card_id","due_rule","due_offset_days","due_day","tag_ids","correlation_id"],["description","category_id","frequency","amount_cents","payment_method","due_rule"]),"series_materialize":(["through","correlation_id"],[]),"series_end":(["cut_date","correlation_id"],["cut_date"]),"series_change_from":(["effective_from","description","amount_cents","category_id","frequency","base_day","payment_method","account_id","card_id","due_rule","due_offset_days","due_day","tag_ids","correlation_id"],["effective_from","description","amount_cents","category_id","frequency","payment_method","due_rule"]),"occurrence_override":(["reason","correlation_id"],["reason"]),"occurrence_cancel":(["correlation_id"],[]),"occurrence_cancel_future":(["correlation_id"],[]),"occurrence_change_future":(["description","amount_cents","frequency","base_day","payment_method","account_id","card_id","due_rule","due_offset_days","due_day","tag_ids","correlation_id"],["description","amount_cents","frequency","payment_method","due_rule"]),
   "installments_create":(["purchase_date","card_id","payment_method","account_id","first_due_date","tag_ids","total_cents","count","category_id","description","correlation_id"],["total_cents","count","category_id","description"]),"installments_cancel":(["from_installment","correlation_id"],["from_installment"]),"invoice_close":(["correlation_id"],[]),"invoice_cancel":(["correlation_id"],[]),"invoice_pay":(["amount_cents","paid_on","payment_method","account_id","correlation_id"],["amount_cents","payment_method","account_id"]),"invoice_reverse":(["reversed_on","reason","correlation_id"],["reason"]),"invoice_correct":(["new_total_cents","reason","correlation_id"],["new_total_cents","reason"]),"invoice_payment_config":(["payment_mode","payment_account_id","correlation_id"],["payment_mode"]),"settlement_reactivate":(["new_settlement_key","correlation_id"],["new_settlement_key"]),"auto_payment_reverse":(["obligation_type","reason","correlation_id"],["obligation_type","reason"])}
  body_fields["occurrence_override_remove"] = (["reason","correlation_id"],["reason"])
  body_fields["occurrence_payment_method"] = (["payment_method","account_id","card_id","due_date","correlation_id"],["payment_method"])
  def property_schema(name):
   if name in date_fields:return {**date_schema,"type":["string","null"]} if name in {"due_date","new_due_date","end_date"} else date_schema
   if name in money_fields:return money if name=="new_total_cents" else positive_money
   if name in id_fields:return {**integer_id,"type":["integer","null"]} if name in {"account_id","card_id","payment_account_id"} else integer_id
   if name=="expected_day":return {"type":"integer","minimum":1,"maximum":31}
   if name in {"closing_day","due_day","base_day"}:return {"type":["integer","null"] if name in {"base_day","due_day"} else "integer","minimum":1,"maximum":31}
   if name in {"due_offset_days","count","from_installment"}:return {"type":["integer","null"] if name=="due_offset_days" else "integer","minimum":0 if name=="due_offset_days" else 1,**({"maximum":60} if name=="count" else {})}
   if name=="tag_ids":return {"type":"array","items":integer_id,"uniqueItems":True}
   if name=="active":return {"type":"boolean"}
   if name in enums:return {"type":"string","enum":enums[name]}
   if name in {"name","description","reason","new_settlement_key"}:return {"type":"string","pattern":r"\S"}
   return {"type":["string","null"] if name in {"notes","correlation_id"} else "string"}
  def when(field,values,then):return {"if":{"properties":{field:{"enum":values}},"required":[field]},"then":then}
  response_fields={
   "revenue_series_create":{"id":integer_id,"replayed":{"type":"boolean"}},"revenue_series_materialize":{"series_id":integer_id,"revenue_ids":{"type":"array","items":integer_id},"replayed":{"type":"boolean"}},"revenue_series_end":{"id":integer_id,"replayed":{"type":"boolean"}},
   "revenue_create":{"id":integer_id,"replayed":{"type":"boolean"}},"revenue_edit":{"id":integer_id},"revenue_receive":{"receipt_id":integer_id,"replayed":{"type":"boolean"}},"revenue_cancel":{"id":integer_id,"replayed":{"type":"boolean"}},"revenue_reverse":{"receipt_id":integer_id,"replayed":{"type":"boolean"}},
   "health":{"status":{"type":"string","enum":["ok","degraded"]},"database":{"type":"string","enum":["ok","error"]},"migrations":{"type":"object","required":["current_version","expected_version","applied_count","expected_count","up_to_date"],"properties":{"current_version":{"type":"integer","minimum":0},"expected_version":{"type":"integer","minimum":0},"applied_count":{"type":"integer","minimum":0},"expected_count":{"type":"integer","minimum":0},"up_to_date":{"type":"boolean"}}}},"catalog_create":{"id":integer_id},"catalog_active":{"id":integer_id,"active":{"type":"boolean"}},"card_create":{"id":integer_id},"card_calendar_create":{"version_id":integer_id,"replayed":{"type":"boolean"}},"expense_create":{"id":integer_id},"expense_edit":{"id":integer_id},"expense_pay":{"payment_id":integer_id,"replayed":{"type":"boolean"}},"expense_cancel":{"id":integer_id},"expense_reactivate":{"id":integer_id},"expense_reverse":{"payment_id":integer_id,"replayed":{"type":"boolean"}},"expense_replace":{"payment_id":integer_id,"replayed":{"type":"boolean"}},"expense_move_invoice":{"expense_id":integer_id,"replayed":{"type":"boolean"}},
   "occurrence_payment_method":{"expense_id":integer_id,"replayed":{"type":"boolean"}},"series_create":{"id":integer_id,"version_id":integer_id},"series_materialize":{"expense_ids":{"type":"array","items":integer_id}},"series_end":{"series_id":integer_id,"replayed":{"type":"boolean"}},"occurrence_override":{"override_id":integer_id},"occurrence_cancel":{"id":integer_id},"occurrence_cancel_future":{"series_id":integer_id,"replayed":{"type":"boolean"}},"occurrence_change_future":{"version_id":integer_id,"replayed":{"type":"boolean"}},"installments_create":{"id":integer_id,"expense_ids":{"type":"array","items":integer_id},"replayed":{"type":"boolean"}},"installments_cancel":{"id":integer_id},
   "invoice_close":{"id":integer_id,"state":{"type":"string","enum":["CLOSED","CANCELLED"]}},"invoice_cancel":{"id":integer_id,"state":{"const":"CANCELLED"}},"invoice_pay":{"payment_id":integer_id,"replayed":{"type":"boolean"}},"invoice_reverse":{"payment_id":integer_id,"replayed":{"type":"boolean"}},"invoice_correct":{"revision_id":integer_id,"replayed":{"type":"boolean"}},"invoice_payment_config":{"invoice_id":integer_id,"replayed":{"type":"boolean"}},"settlement_reactivate":{"settlement_id":integer_id,"replayed":{"type":"boolean"}},"auto_payment_reverse":{"payment_id":integer_id,"replayed":{"type":"boolean"}},
   "aggregates":{"start":date_schema,"end":date_schema,"recognized_cents":money,"pending_cents":money,"overdue_cents":money,"net_paid_cents":money,"revenue_expected_cents":money,"revenue_received_cents":money}}
  response_fields["card_edit"]={"id":integer_id};response_fields["expense_delete"]={"id":integer_id,"deleted":{"type":"boolean"}};response_fields["series_change_from"]={"version_id":integer_id,"replayed":{"type":"boolean"}}
  def table_row_schema(required_int,nullable_int,required_text,nullable_text,extra=None):
   properties={name:{"type":"integer"} for name in required_int.split()}
   properties.update({name:{"type":["integer","null"]} for name in nullable_int.split()})
   properties.update({name:{"type":"string"} for name in required_text.split()})
   properties.update({name:{"type":["string","null"]} for name in nullable_text.split()})
   properties.update(extra or {})
   return {"type":"object","required":list(properties),"properties":properties}
  expense_db_row=table_row_schema("id amount_cents category_id","account_id card_id invoice_id recurring_series_id recurring_version_id installment_series_id installment_number superseded_by_expense_id","description expense_date planned_payment_method lifecycle_state created_at updated_at","due_date recurrence_occurrence_key logical_slot_lineage_key materialization_slot_key superseded_at supersession_reason_code supersession_correlation_id notes")
  expense_db_row["properties"].update({"id":integer_id,"category_id":integer_id,"amount_cents":positive_money,"expense_date":date_schema,"due_date":{**date_schema,"type":["string","null"]},"planned_payment_method":{"type":"string","enum":enums["planned_payment_method"]+["BANK_TRANSFER"]},"effective_status":{"type":"string","enum":["PENDING","OVERDUE","PAID","CANCELLED","SUPERSEDED","DELETED"]},"lifecycle_state":{"type":"string","enum":["ACTIVE","CANCELLED","SUPERSEDED","DELETED"]}})
  expense_row={"type":"object","required":expense_db_row["required"]+["effective_status","requires_manual_action","requires_attention"],"properties":{**expense_db_row["properties"],"effective_status":{"type":"string"},"requires_manual_action":{"type":"boolean"},"requires_attention":{"type":"boolean"}}}
  expense_list_row={"type":"object","required":expense_row["required"]+["category_name","account_name","card_name"],"properties":{**expense_row["properties"],"category_name":{"type":"string"},"account_name":{"type":["string","null"]},"card_name":{"type":["string","null"]}}}
  invoice_db_row=table_row_schema("id card_id","closed_total_cents payment_account_id","closing_date due_date period_start period_end state payment_mode created_at","closed_at paid_at cancelled_at")
  invoice_db_row["properties"].update({"id":integer_id,"card_id":integer_id,"state":{"type":"string","enum":["OPEN","CLOSED","PAID","CANCELLED"]},"payment_mode":{"type":"string","enum":enums["payment_mode"]},"closing_date":date_schema,"due_date":date_schema,"period_start":date_schema,"period_end":date_schema})
  invoice_row={"type":"object","required":invoice_db_row["required"]+["effective_total_cents","paid_cents","balance_cents","requires_manual_action","requires_attention"],"properties":{**invoice_db_row["properties"],"effective_total_cents":money,"paid_cents":money,"balance_cents":money,"requires_manual_action":{"type":"boolean"},"requires_attention":{"type":"boolean"}}}
  expense_payment_row=table_row_schema("id expense_id amount_cents","account_id settlement_id replacement_payment_id","paid_on payment_method source correlation_id","reversed_at reversed_on reversed_by_actor reversal_reason")
  invoice_payment_row=table_row_schema("id invoice_id amount_cents account_id","settlement_id replacement_payment_id","paid_on payment_method source correlation_id","reversed_at reversed_on reversed_by_actor reversal_reason")
  event_row=table_row_schema("id entity_id metadata_schema_version","","entity_type event_type actor correlation_id created_at","metadata_json")
  revision_row=table_row_schema("id invoice_id previous_total_cents new_total_cents","","reason_code correlation_id actor created_at","")
  automation_row=table_row_schema("id settlement_id attempt_number","","attempt_group_key result started_at finished_at","error_code")
  override_row=table_row_schema("id expense_id originating_recurring_version_id","","reason_code correlation_id created_at created_by_actor","removed_at removed_by_actor removal_reason_code removal_correlation_id")
  account_row=table_row_schema("id active","","name","")
  category_row=table_row_schema("id active","","name normalized_name","")
  card_row=table_row_schema("id active","invoice_payment_account_id","name invoice_payment_mode","")
  calendar_row=table_row_schema("id card_id closing_day due_day","","effective_from","effective_to")
  series_row=table_row_schema("id","","lineage_epoch_uuid start_date","end_date ended_at reconciled_through")
  series_version_row=table_row_schema("id recurring_series_id category_id anchor_logical_ordinal amount_cents","superseded_by_version_id base_day account_id card_id due_offset_days due_day","lifecycle_state description created_at effective_from anchor_occurrence_key anchor_logical_date frequency planned_payment_method due_rule","superseded_at supersession_reason_code supersession_correlation_id effective_to")
  series_version_row["properties"].update({"frequency":{"type":"string","enum":enums["frequency"]},"planned_payment_method":{"type":"string","enum":enums["planned_payment_method"]},"due_rule":{"type":"string","enum":enums["due_rule"]},"amount_cents":positive_money})
  series_version_row["properties"]["tag_ids"]={"type":"array","items":integer_id}
  series_version_row["required"].append("tag_ids")
  installment_row=table_row_schema("id original_total_cents installment_count","card_id account_id ended_from_installment","purchase_date payment_method","ended_at first_due_date")
  installment_row["properties"].update({"payment_method":{"type":"string","enum":["CREDIT_CARD","AUTO_DEBIT","PIX","BANK_TRANSFER","BANK_SLIP","DEBIT","CASH"]},"purchase_date":date_schema,"first_due_date":{**date_schema,"type":["string","null"]}})
  revenue_db_row=table_row_schema("id amount_cents category_id","account_id","description competence_date expected_on lifecycle_state created_at updated_at","notes")
  revenue_db_row["properties"].update({"id":integer_id,"amount_cents":positive_money,"category_id":integer_id,"competence_date":date_schema,"expected_on":date_schema,"lifecycle_state":{"type":"string","enum":["ACTIVE","CANCELLED"]}})
  revenue_row={"type":"object","required":revenue_db_row["required"]+["financial_status"],"properties":{**revenue_db_row["properties"],"financial_status":{"type":"string","enum":["PENDING","OVERDUE","RECEIVED","CANCELLED"]}}}
  revenue_receipt_row=table_row_schema("id revenue_id amount_cents account_id","","received_on created_at correlation_id","reversed_at reversed_on reversed_by_actor reversal_reason")
  revenue_receipt_row["properties"].update({"id":integer_id,"revenue_id":integer_id,"amount_cents":positive_money,"account_id":integer_id,"received_on":date_schema,"reversed_on":{**date_schema,"type":["string","null"]}})
  revenue_series_row=table_row_schema("id amount_cents category_id expected_day active","account_id","description start_date frequency created_at","end_date ended_at")
  revenue_series_row["properties"].update({"id":integer_id,"amount_cents":positive_money,"category_id":integer_id,"expected_day":{"type":"integer","minimum":1,"maximum":31},"active":{"type":"integer","enum":[0,1]},"start_date":date_schema,"end_date":{**date_schema,"type":["string","null"]},"frequency":{"type":"string","enum":enums["frequency"]}})
  def success_schema(operation):
   if operation=="occurrence_override_remove":return {"type":"object","required":["override_id","request_id"],"properties":{"override_id":integer_id,"request_id":{"type":"string"}}}
   if operation=="openapi":return {"type":"object","required":["openapi","paths"],"properties":{"openapi":{"type":"string"},"paths":{"type":"object"}}}
   if operation=="context":return {"type":"object","required":["system_date","timezone","csrf_token","request_id"],"properties":{"system_date":date_schema,"timezone":{"type":"string"},"csrf_token":{"type":["string","null"]},"request_id":{"type":"string"}}}
   if operation=="catalogs":return {"type":"object","required":["accounts","categories","tags","cards","request_id"],"properties":{"accounts":{"type":"array","items":account_row},"categories":{"type":"array","items":category_row},"tags":{"type":"array","items":category_row},"cards":{"type":"array","items":card_row},"request_id":{"type":"string"}}}
   if operation=="dashboard":
    dashboard_money={"type":"integer","minimum":0}
    return {"type":"object","required":["summary","upcoming","invoices","recurring","categories","recent","trend","request_id"],"properties":{"summary":{"type":"object","required":["revenue_expected_cents","revenue_received_cents","expense_recognized_cents","expense_pending_cents","expense_overdue_cents","net_paid_cents","invoice_open_cents"],"properties":{name:(signed_money if name in {"revenue_received_cents","net_paid_cents"} else dashboard_money) for name in ("revenue_expected_cents","revenue_received_cents","expense_recognized_cents","expense_pending_cents","expense_overdue_cents","net_paid_cents","invoice_open_cents")}},"upcoming":{"type":"array","items":{"type":"object","required":["id","description","amount_cents","due_date","category_name"],"properties":{"id":integer_id,"description":{"type":"string"},"amount_cents":money,"due_date":date_schema,"category_name":{"type":"string"}}}},"invoices":{"type":"array","items":{"type":"object","required":["id","card_id","card_name","closing_date","due_date","state","amount_cents"],"properties":{"id":integer_id,"card_id":integer_id,"card_name":{"type":"string"},"closing_date":date_schema,"due_date":date_schema,"state":{"type":"string","enum":["OPEN","CLOSED"]},"amount_cents":money}}},"recurring":{"type":"array","items":{"type":"object","required":["kind","id","description","frequency","amount_cents"],"properties":{"kind":{"type":"string","enum":["EXPENSE","REVENUE"]},"id":integer_id,"description":{"type":"string"},"frequency":{"type":"string","enum":enums["frequency"]},"amount_cents":money,"ended_at":{"type":["string","null"]},"next_occurrence":{**date_schema,"type":["string","null"]},"next_due_date":{**date_schema,"type":["string","null"]},"association_name":{"type":["string","null"]}}}},"categories":{"type":"array","items":{"type":"object","required":["name","amount_cents"],"properties":{"name":{"type":"string"},"amount_cents":money}}},"recent":{"type":"array","items":{"type":"object","required":["kind","id","description","amount_cents","event_date","category_name","state","is_recurring"],"properties":{"kind":{"type":"string","enum":["EXPENSE","REVENUE"]},"id":integer_id,"description":{"type":"string"},"amount_cents":money,"event_date":date_schema,"category_name":{"type":"string"},"state":{"type":"string"},"is_recurring":{"type":"integer","enum":[0,1]}}}},"trend":{"type":"array","items":{"type":"object","required":["month","revenue_cents","expense_cents"],"properties":{"month":date_schema,"revenue_cents":signed_money,"expense_cents":signed_money}}},"request_id":{"type":"string"}}}
   if operation=="card_list":return {"type":"object","required":["items","request_id"],"properties":{"items":{"type":"array","items":card_row},"request_id":{"type":"string"}}}
   if operation=="card_detail":return {"type":"object","required":["card","calendar_versions","invoices","request_id"],"properties":{"card":card_row,"calendar_versions":{"type":"array","items":calendar_row},"invoices":{"type":"array","items":invoice_db_row},"request_id":{"type":"string"}}}
   if operation=="series_list":return {"type":"object","required":["items","request_id"],"properties":{"items":{"type":"array","items":{"type":"object","required":series_row["required"]+["description","frequency","amount_cents","planned_payment_method","next_occurrence","next_due_date","association_name"],"properties":{**series_row["properties"],"description":{"type":"string"},"frequency":{"type":"string"},"amount_cents":money,"planned_payment_method":{"type":"string"},"next_occurrence":{**date_schema,"type":["string","null"]},"next_due_date":{**date_schema,"type":["string","null"]},"association_name":{"type":["string","null"]}}}},"request_id":{"type":"string"}}}
   if operation=="series_detail":return {"type":"object","required":["series","versions","occurrences","events","request_id"],"properties":{"series":series_row,"versions":{"type":"array","items":series_version_row},"occurrences":{"type":"array","items":{"type":"object","required":expense_db_row["required"]+["effective_status","override"],"properties":{**expense_db_row["properties"],"effective_status":{"type":"string"},"override":{"anyOf":[override_row,{"type":"null"}]}}}},"events":{"type":"array","items":event_row},"request_id":{"type":"string"}}}
   if operation=="installments_list":return {"type":"object","required":["items","request_id"],"properties":{"items":{"type":"array","items":{"type":"object","required":installment_row["required"]+["total_cents","description","next_installment"],"properties":{**installment_row["properties"],"total_cents":money,"description":{"type":["string","null"]},"next_installment":{"anyOf":[{"type":"object","required":["installment_number","expense_date","amount_cents"],"properties":{"installment_number":{"type":"integer","minimum":1},"expense_date":date_schema,"amount_cents":money}},{"type":"null"}]}}}},"request_id":{"type":"string"}}}
   if operation=="installments_detail":return {"type":"object","required":["series","installments","events","request_id"],"properties":{"series":{"type":"object","required":installment_row["required"]+["total_cents","description"],"properties":{**installment_row["properties"],"total_cents":money,"description":{"type":"string"}}},"installments":{"type":"array","items":expense_db_row},"events":{"type":"array","items":event_row},"request_id":{"type":"string"}}}
   if operation=="revenue_list":return {"type":"object","required":["items","page","page_size","has_more","request_id"],"properties":{"items":{"type":"array","items":revenue_row},"page":{"type":"integer","minimum":1},"page_size":{"type":"integer","enum":[25,50,100]},"has_more":{"type":"boolean"},"request_id":{"type":"string"}}}
   if operation=="revenue_detail":return {"type":"object","required":revenue_row["required"]+["tags","receipts","request_id"],"properties":{**revenue_row["properties"],"tags":{"type":"array","items":category_row},"receipts":{"type":"array","items":revenue_receipt_row},"request_id":{"type":"string"}}}
   if operation=="revenue_audit":return {"type":"object","required":["receipts","events","request_id"],"properties":{"receipts":{"type":"array","items":revenue_receipt_row},"events":{"type":"array","items":event_row},"request_id":{"type":"string"}}}
   if operation=="revenue_series_list":return {"type":"object","required":["items","request_id"],"properties":{"items":{"type":"array","items":{"type":"object","required":revenue_series_row["required"]+["next_occurrence","next_due_date","association_name"],"properties":{**revenue_series_row["properties"],"next_occurrence":{**date_schema,"type":["string","null"]},"next_due_date":{**date_schema,"type":["string","null"]},"association_name":{"type":["string","null"]}}}},"request_id":{"type":"string"}}}
   if operation=="revenue_series_detail":return {"type":"object","required":["series","occurrences","request_id"],"properties":{"series":revenue_series_row,"occurrences":{"type":"array","items":revenue_db_row},"request_id":{"type":"string"}}}
   if operation in {"expense_list","invoice_list"}:return {"type":"object","required":["items","page","page_size","has_more","request_id"],"properties":{"items":{"type":"array","items":expense_list_row if operation=="expense_list" else invoice_row},"page":{"type":"integer"},"page_size":{"type":"integer","enum":[25,50,100]},"has_more":{"type":"boolean"},"request_id":{"type":"string"}}}
   if operation=="expense_detail":return {"type":"object","required":expense_row["required"]+["tags","payments","request_id"],"properties":{**expense_row["properties"],"tags":{"type":"array","items":{"type":"object","required":["id","name","normalized_name","active"],"properties":{"id":integer_id,"name":{"type":"string"},"normalized_name":{"type":"string"},"active":{"type":"integer","enum":[0,1]}}}},"payments":{"type":"array","items":expense_payment_row},"request_id":{"type":"string"}}}
   if operation=="invoice_detail":return {"type":"object","required":invoice_row["required"]+["items","payments","revisions","automations","request_id"],"properties":{**invoice_row["properties"],"items":{"type":"array","items":expense_db_row},"payments":{"type":"array","items":invoice_payment_row},"revisions":{"type":"array","items":revision_row},"automations":{"type":"array","items":automation_row},"request_id":{"type":"string"}}}
   if operation=="expense_audit":return {"type":"object","required":["payments","events","request_id"],"properties":{"payments":{"type":"array","items":expense_payment_row},"events":{"type":"array","items":event_row},"request_id":{"type":"string"}}}
   if operation=="invoice_audit":return {"type":"object","required":["payments","revisions","request_id"],"properties":{"payments":{"type":"array","items":invoice_payment_row},"revisions":{"type":"array","items":revision_row},"request_id":{"type":"string"}}}
   fields={**response_fields.get(operation,{}),"request_id":{"type":"string"}}
   return {"type":"object","required":list(fields),"properties":fields}
  paths={}
  for r in ROUTES:
   success="201" if r.operation in {"catalog_create","card_create","card_calendar_create","expense_create","revenue_create","revenue_series_create","series_create","occurrence_override","installments_create"} else "200"
   op={"operationId":r.operation,"responses":{success:{"description":"Success","content":{"application/json":{"schema":success_schema(r.operation)}}},"400":{"$ref":"#/components/responses/BadRequest"},"401":{"$ref":"#/components/responses/Unauthenticated"},"403":{"$ref":"#/components/responses/Forbidden"},"404":{"$ref":"#/components/responses/NotFound"},"409":{"$ref":"#/components/responses/Conflict"},"413":{"$ref":"#/components/responses/PayloadTooLarge"},"422":{"$ref":"#/components/responses/ValidationError"},"500":{"$ref":"#/components/responses/InternalError"},"503":{"$ref":"#/components/responses/DatabaseUnavailable"}},"security":[] if r.operation in {"health","openapi"} else [{"bearerAuth":[]}]}
   if r.operation in {"card_calendar_create","revenue_create","revenue_series_create","installments_create"}:op["responses"]["200"]={"description":"Idempotent replay","content":{"application/json":{"schema":success_schema(r.operation)}}}
   if r.operation=="health":op["responses"]["503"]={"description":"Database or migrations degraded","content":{"application/json":{"schema":{"oneOf":[success_schema(r.operation),{"$ref":"#/components/schemas/Error"}]}}}}
   if r.operation not in {"health","openapi"}:op["x-external-capability"]="not-available" if r.write else "finance:read"
   parameters=[]
   if "{id}" in r.path:parameters.append({"name":"id","in":"path","required":True,"schema":integer_id})
   if r.idem:parameters.append({"name":"Idempotency-Key","in":"header","required":True,"description":"Case-sensitive permanent operation identity","schema":{"type":"string","pattern":"^[!-~]{16,128}$","minLength":16,"maxLength":128}})
   if r.operation=="installments_create":parameters.append({"name":"Idempotency-Key","in":"header","required":False,"description":"Required for non-card installments; optional for the legacy card request. Permanent replay and conflict protection when supplied.","schema":{"type":"string","pattern":"^[!-~]{16,128}$","minLength":16,"maxLength":128}})
   if r.operation=="expense_list":
    parameters += [{"name":"page","in":"query","description":"Offset pagination over a mutable collection may shift between requests.","schema":{**integer_id,"default":1}},{"name":"page_size","in":"query","schema":{"type":"integer","enum":[25,50,100],"default":50}},{"name":"search","in":"query","schema":{"type":"string"}},{"name":"preset","in":"query","schema":{"type":"string","enum":["today","next_7_days","next_30_days","current_month"]}},{"name":"financial_status","in":"query","schema":{"type":"string","enum":["overdue","need_pay","auto_debit","paid","cancelled"]}},{"name":"requires_attention","in":"query","schema":{"type":"boolean"}}]+[{"name":x,"in":"query","schema":date_schema if x in {"start","end"} else integer_id} for x in ("start","end","category_id","account_id","card_id","tag")]
   if r.operation=="invoice_list":parameters += [{"name":"page","in":"query","description":"Offset pagination over a mutable collection may shift between requests.","schema":{**integer_id,"default":1}},{"name":"page_size","in":"query","schema":{"type":"integer","enum":[25,50,100],"default":50}},{"name":"state","in":"query","schema":{"type":"string","enum":["OPEN","CLOSED","PAID","CANCELLED"]}},{"name":"requires_attention","in":"query","schema":{"type":"boolean"}},{"name":"card_id","in":"query","schema":integer_id},{"name":"start","in":"query","schema":date_schema},{"name":"end","in":"query","schema":date_schema}]
   if r.operation=="revenue_list":parameters += [{"name":"page","in":"query","description":"Offset pagination over a mutable collection may shift between requests.","schema":{**integer_id,"default":1}},{"name":"page_size","in":"query","schema":{"type":"integer","enum":[25,50,100],"default":50}},{"name":"status","in":"query","schema":{"type":"string","enum":["PENDING","OVERDUE","RECEIVED","CANCELLED"]}},{"name":"search","in":"query","schema":{"type":"string"}}]+[{"name":x,"in":"query","schema":date_schema if x in {"start","end"} else integer_id} for x in ("start","end","category_id","account_id","tag")]
   if r.operation=="aggregates":parameters += [{"name":"start","in":"query","schema":date_schema},{"name":"end","in":"query","schema":date_schema}]
   if parameters:op["parameters"]=parameters
   if r.write:
    fields,required=body_fields[r.operation];schema={"type":"object","properties":{name:property_schema(name) for name in fields}}
    if "payment_method" in schema["properties"]:
     allowed=(["CREDIT_CARD","AUTO_DEBIT","PIX","BANK_TRANSFER","BANK_SLIP","DEBIT","CASH"] if r.operation=="installments_create" else enums["planned_payment_method"] if r.operation in {"series_create","occurrence_change_future","occurrence_payment_method","series_change_from"} else ["PIX","DEBIT","BANK_TRANSFER"] if r.operation=="invoice_pay" else ["PIX","DEBIT","BANK_TRANSFER","CASH"])
     schema["properties"]["payment_method"]={"type":"string","enum":allowed}
    for name in required:
     field=schema["properties"][name]
     if isinstance(field.get("type"),list):schema["properties"][name]={**field,"type":field["type"][0]}
    constraints=[]
    if r.operation=="installments_create":
     schema["properties"]["payment_method"]["default"]="CREDIT_CARD"
     schema["properties"]["first_due_date"]={**date_schema,"type":["string","null"]}
     constraints=[{"if":{"properties":{"payment_method":{"const":"CREDIT_CARD"}}},"then":{"required":["card_id"],"properties":{"card_id":integer_id,"account_id":{"type":"null"},"first_due_date":{"type":"null"}}}},when("payment_method",["AUTO_DEBIT","PIX","BANK_TRANSFER","DEBIT"],{"required":["account_id","first_due_date"],"properties":{"account_id":integer_id,"card_id":{"type":"null"},"first_due_date":date_schema}}),when("payment_method",["CASH","BANK_SLIP"],{"required":["first_due_date"],"properties":{"card_id":{"type":"null"},"first_due_date":date_schema}}),when("payment_method",["CASH"],{"properties":{"account_id":{"type":"null"}}})]
    if r.operation in {"card_create","invoice_payment_config"}:
     mode="payment_mode";account="payment_account_id"
     constraints=[when(mode,["AUTO_DEBIT"],{"required":[account],"properties":{account:integer_id}}),when(mode,["MANUAL"],{"properties":{account:{"type":"null"}}})]
    if r.operation in {"expense_pay","expense_replace"}:
     constraints=[when("payment_method",["CASH"],{"properties":{"account_id":{"type":"null"}}}),when("payment_method",["PIX","DEBIT","BANK_TRANSFER"],{"required":["account_id"],"properties":{"account_id":integer_id}})]
    if r.operation=="expense_create":
     schema["properties"]["planned_payment_method"]["enum"]=enums["planned_payment_method"]+["BANK_TRANSFER"]
     constraints=[when("planned_payment_method",["CREDIT_CARD"],{"required":["card_id"],"properties":{"card_id":integer_id,"account_id":{"type":"null"},"due_date":{"type":"null"}}}),when("planned_payment_method",["PIX","DEBIT","BANK_TRANSFER","AUTO_DEBIT"],{"required":["account_id","due_date"],"properties":{"account_id":integer_id,"card_id":{"type":"null"},"due_date":date_schema}}),when("planned_payment_method",["CASH","BANK_SLIP"],{"required":["due_date"],"properties":{"card_id":{"type":"null"},"due_date":date_schema}})]
     constraints.append(when("planned_payment_method",["CASH"],{"properties":{"account_id":{"type":"null"}}}))
    if r.operation in {"series_create","occurrence_change_future"}:
     constraints=[when("payment_method",["CREDIT_CARD"],{"required":["card_id"],"properties":{"card_id":integer_id,"account_id":{"type":"null"},"due_rule":{"const":"INVOICE"}}}),when("payment_method",["PIX","DEBIT","AUTO_DEBIT"],{"required":["account_id"],"properties":{"account_id":integer_id,"card_id":{"type":"null"},"due_rule":{"not":{"const":"INVOICE"}}}}),when("payment_method",["CASH","BANK_SLIP"],{"properties":{"card_id":{"type":"null"},"due_rule":{"not":{"const":"INVOICE"}}}}),when("frequency",["WEEKLY","BIWEEKLY"],{"properties":{"base_day":{"type":"null"}}}),when("frequency",["MONTHLY","BIMONTHLY","QUARTERLY","SEMIANNUAL","ANNUAL"],{"required":["base_day"],"properties":{"base_day":{"type":"integer","minimum":1,"maximum":31}}}),when("due_rule",["OFFSET"],{"required":["due_offset_days"],"properties":{"due_offset_days":{"type":"integer","minimum":0},"due_day":{"type":"null"}}}),when("due_rule",["DAY_OF_MONTH"],{"required":["due_day"],"properties":{"due_day":{"type":"integer","minimum":1,"maximum":31},"due_offset_days":{"type":"null"}}}),when("due_rule",["SAME_DAY","INVOICE"],{"properties":{"due_offset_days":{"type":"null"},"due_day":{"type":"null"}}})]
     constraints.append(when("payment_method",["CASH"],{"properties":{"account_id":{"type":"null"}}}))
    if constraints:schema["allOf"]=constraints
    if required:schema["required"]=required
    op["requestBody"]={"required":bool(required),"content":{"application/json":{"schema":schema}}}
   paths.setdefault(r.path,{})[r.method.lower()]=op
  known_error_codes=["INVALID_JSON","IDEMPOTENCY_KEY_REQUIRED","IDEMPOTENCY_KEY_INVALID","NEW_DUE_DATE_REQUIRED","UNAUTHENTICATED","FORBIDDEN","CSRF_INVALID","CORS_FORBIDDEN","NOT_FOUND","CONFLICT","INVALID_STATE_TRANSITION","ACTIVE_PAYMENT_EXISTS","INACTIVE_ACCOUNT","OVERPAYMENT","INVOICE_PAID","AUTO_DEBIT_REQUIRES_ATTENTION","IDEMPOTENCY_CONFLICT","DOMAIN_ERROR","PAYLOAD_TOO_LARGE","VALIDATION_ERROR","IDENTITY_FIELD_FORBIDDEN","INTERNAL_ERROR","DATABASE_UNAVAILABLE"]
  error_schema={"type":"object","required":["error","request_id"],"properties":{"error":{"type":"object","required":["code","message"],"properties":{"code":{"type":"string","enum":known_error_codes},"message":{"type":"string"}}},"request_id":{"type":"string"}}}
  def response(description,codes):
   schema={"type":"object","required":["error","request_id"],"properties":{"error":{"type":"object","required":["code","message"],"properties":{"code":{"type":"string","enum":codes},"message":{"type":"string"}}},"request_id":{"type":"string"}}}
   return {"description":description,"content":{"application/json":{"schema":schema}}}
  return {"openapi":"3.1.0","info":{"title":"Finance V2 API","version":"2.0.0"},"paths":paths,"components":{"securitySchemes":{"bearerAuth":{"type":"http","scheme":"bearer"}},"schemas":{"MoneyCents":money,"CivilDate":date_schema,"UtcTimestamp":{"type":"string","format":"date-time","pattern":"Z$"},"Error":error_schema},"responses":{"BadRequest":response("Malformed request or idempotency key",["INVALID_JSON","IDEMPOTENCY_KEY_REQUIRED","IDEMPOTENCY_KEY_INVALID","NEW_DUE_DATE_REQUIRED"]),"Unauthenticated":response("Missing or invalid Bearer token",["UNAUTHENTICATED"]),"Forbidden":response("Authenticated identity is not authorized",["FORBIDDEN","CSRF_INVALID","CORS_FORBIDDEN"]),"NotFound":response("Resource not found",["NOT_FOUND"]),"Conflict":response("Domain or idempotency conflict",["CONFLICT","INVALID_STATE_TRANSITION","ACTIVE_PAYMENT_EXISTS","INACTIVE_ACCOUNT","OVERPAYMENT","INVOICE_PAID","AUTO_DEBIT_REQUIRES_ATTENTION","IDEMPOTENCY_CONFLICT","DOMAIN_ERROR"]),"PayloadTooLarge":response("Request body exceeds limit",["PAYLOAD_TOO_LARGE"]),"ValidationError":response("Domain validation failed",["VALIDATION_ERROR","IDENTITY_FIELD_FORBIDDEN"]),"InternalError":response("Unexpected internal failure",["INTERNAL_ERROR"]),"DatabaseUnavailable":response("Database unavailable",["DATABASE_UNAVAILABLE"])}}}
 def assistant_openapi(self):
  integer_id={"type":"integer","minimum":1}; date_schema={"type":"string","format":"date"}; error={"type":"object","required":["error","request_id"],"properties":{"error":{"type":"object","required":["code","message"],"properties":{"code":{"type":"string"},"message":{"type":"string"}}},"request_id":{"type":"string"}}}
  expense={"type":"object","properties":{"description":{"type":"string"},"amount_cents":{"type":"integer","minimum":1},"expense_date":date_schema,"due_date":{"anyOf":[date_schema,{"type":"null"}]},"planned_payment_method":{"type":"string"},"category_id":integer_id,"account_id":{"anyOf":[integer_id,{"type":"null"}]},"card_id":{"anyOf":[integer_id,{"type":"null"}]},"notes":{"type":["string","null"]}}}
  write={"type":"object","required":["description","amount_cents","planned_payment_method","category_id"],"properties":expense["properties"]}
  paths={}
  for method,path,operation in (("get","/api/v2/assistant/context","assistant_context"),("get","/api/v2/assistant/dashboard","assistant_dashboard"),("get","/api/v2/assistant/expenses","assistant_expense_list"),("post","/api/v2/assistant/expenses","assistant_expense_create")):
   op={"operationId":operation,"security":[{"bearerAuth":["finance:read"]}],"responses":{"200":{"description":"Success","content":{"application/json":{"schema":{"type":"object"}}}},"401":{"description":"Unauthenticated","content":{"application/json":{"schema":{"$ref":"#/components/schemas/Error"}}}},"403":{"description":"Forbidden"}},}
   if method=="post":
    op["security"]=[{"bearerAuth":["finance:read","finance:write"]}];op["parameters"]=[{"name":"Idempotency-Key","in":"header","required":True,"schema":{"type":"string","minLength":16,"maxLength":128}}];op["requestBody"]={"required":True,"content":{"application/json":{"schema":write}}};op["responses"]["201"]={"description":"Created"};op["responses"]["409"]={"description":"Idempotency conflict"};op["responses"]["422"]={"description":"Validation error"}
   paths[path]={method:op}
  return {"openapi":"3.1.0","info":{"title":"Finance V2 Assistant API","version":"1.0.0"},"paths":paths,"components":{"securitySchemes":{"bearerAuth":{"type":"http","scheme":"bearer","bearerFormat":"token"}},"schemas":{"Error":error}}}
 def respond(self,start,status,payload,rid,origin=None):
  if isinstance(payload,dict):payload={**payload,"request_id":rid}
  return self.json_document_response(start,status,payload,origin)
 def json_document_response(self,start,status,payload,origin=None):
  """Serialize a protocol document without the Finance API envelope."""
  raw=b"" if status==204 else json.dumps(payload,ensure_ascii=False,separators=(",",":"),default=str).encode();headers=[("Content-Type","application/json; charset=utf-8"),("Content-Length",str(len(raw))),("Cache-Control","no-store"),("X-Content-Type-Options","nosniff")]
  if origin in self.settings.cors_origins:headers += [("Access-Control-Allow-Origin",origin),("Vary","Origin"),("Access-Control-Allow-Headers","Authorization, Content-Type, Idempotency-Key, X-Request-ID"),("Access-Control-Allow-Methods","GET, POST, PATCH, OPTIONS")]
  phrase={200:"OK",201:"Created",202:"Accepted",204:"No Content",400:"Bad Request",401:"Unauthorized",403:"Forbidden",404:"Not Found",409:"Conflict",413:"Payload Too Large",422:"Unprocessable Entity",500:"Internal Server Error",503:"Service Unavailable"}.get(status,"Error");start(f"{status} {phrase}",headers);return [raw]

def create_app(settings=None,clock=None):return Application(settings or Settings.from_env(),clock)
