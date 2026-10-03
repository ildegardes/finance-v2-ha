"""Public-client OAuthLib integration. All persistence uses schema 7.

This module owns protocol/login/grant lifecycle, not financial authorization.
Token resolution returns the existing client's identity and capabilities.
"""
from __future__ import annotations

import base64
from collections import deque
from hashlib import sha256
import hmac
from html import escape
from http.cookies import SimpleCookie, CookieError
import json
import logging
import re
import secrets
from threading import Lock
from urllib.parse import parse_qsl, urlencode, urlsplit

from oauthlib.oauth2 import AuthorizationCodeGrant, AuthorizationEndpoint, TokenEndpoint, BearerToken, RequestValidator
from oauthlib.oauth2.rfc6749.errors import OAuth2Error

from .authorization import FINANCE_SCOPES
from .db import connect, immediate_transaction
from .oauth import ISSUER, RESOURCE, OAuthClient, AuthorizationRequest, validate_resource, validate_scopes

CODE_TTL = 120
ACCESS_TOKEN_TTL = 900
CONSENT_TTL = 600
OWNER = "OWNER:local"
TOKEN_PREFIX = "fv2_oauth_"
CODE_PREFIX = "fv2_code_"
COOKIE_NAME = "finance_v2_oauth"
COOKIE_PATH = "/oauth/authorize"
AUTHORIZE_FIELDS = {"response_type", "client_id", "redirect_uri", "scope", "state", "resource", "code_challenge", "code_challenge_method"}
TOKEN_FIELDS = {"grant_type", "client_id", "code", "redirect_uri", "code_verifier", "resource"}


# OAuthLib's diagnostic request reprs can contain codes/verifiers/tokens.
# Silence those specific library loggers; our errors never serialize requests.
for name in tuple(logging.Logger.manager.loggerDict):
    if name == "oauthlib" or name.startswith("oauthlib."):
        logging.getLogger(name).disabled = True


class OAuthFailure(Exception):
    def __init__(self, error="invalid_request", status=400):
        self.error, self.status = error, status
        super().__init__(error)


def digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def parameters(raw: str, allowed: set[str], *, ignore_unknown: bool = False) -> dict[str, str]:
    if len(raw)>16384 or re.search(r"%(?![0-9a-fA-F]{2})", raw):raise OAuthFailure()
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, encoding="utf-8", errors="strict", max_num_fields=20)
    except (ValueError, UnicodeError):raise OAuthFailure() from None
    # OAuth clients may send registered extension/request metadata parameters.
    # Parse and validate all values for bounded input, but only expose fields
    # understood by this endpoint to security-sensitive code and HTML.
    if any(len(v)>4096 or any(ord(c)<32 or ord(c)==127 for c in v) for _, v in pairs):raise OAuthFailure()
    forbidden_unknown = {"code", "access_token", "refresh_token", "token", "client_secret", "ui_token"}
    if any(k in forbidden_unknown for k, _ in pairs if k not in allowed):raise OAuthFailure()
    if not ignore_unknown and any(k not in allowed for k, _ in pairs):raise OAuthFailure()
    known = [(k, v) for k, v in pairs if k in allowed]
    result = dict(known)
    if len(result)!=len(known):raise OAuthFailure()
    return result


def scopes_from_text(text: str) -> frozenset[str]:
    parts = text.split(" ")
    scopes = frozenset(parts)
    if not text or len(parts)!=len(scopes):raise OAuthFailure("invalid_scope")
    try:return validate_scopes(scopes)
    except ValueError:raise OAuthFailure("invalid_scope") from None


class RateLimit:
    """Bounded instance-wide throttles: never trust forwarded IP headers."""
    def __init__(self):
        self.lock = Lock()
        self.events = {"authorize":deque(), "login":deque(), "token":deque()}

    def check(self, kind, now):
        limit={"authorize":120,"login":10,"token":120}[kind]
        with self.lock:
            events=self.events[kind]
            while events and events[0]<=now-60:events.popleft()
            if len(events)>=limit:raise OAuthFailure("temporarily_unavailable",429)
            events.append(now)


class FinanceCodeGrant(AuthorizationCodeGrant):
    refresh_token = False

    def create_authorization_code(self, request):
        grant = {"code":CODE_PREFIX+secrets.token_urlsafe(32)}
        if request.state is not None:grant["state"]=request.state
        return grant

    def validate_code_challenge(self, challenge, challenge_method, verifier):
        if challenge_method!="S256" or not isinstance(verifier,str) or re.fullmatch(r"[A-Za-z0-9._~-]{43,128}",verifier) is None:
            return False
        return hmac.compare_digest(pkce_challenge(verifier),challenge)


class FinanceServer(AuthorizationEndpoint, TokenEndpoint):
    def __init__(self, validator):
        grant=FinanceCodeGrant(validator)
        bearer=BearerToken(validator,token_generator=lambda request:TOKEN_PREFIX+secrets.token_urlsafe(32),expires_in=ACCESS_TOKEN_TTL)
        AuthorizationEndpoint.__init__(self,default_response_type="code",response_types={"code":grant},default_token_type=bearer)
        TokenEndpoint.__init__(self,default_grant_type="authorization_code",grant_types={"authorization_code":grant},default_token_type=bearer)


class FinanceValidator(RequestValidator):
    def __init__(self, service, connection, client, now, pending=None):
        self.service, self.connection, self.client, self.now = service, connection, client, now
        self.pending=pending
        self.code_row=None

    def validate_client_id(self, client_id, request, *args, **kwargs):
        if client_id!=self.client.oauth_client_id:return False
        request.client=self.client
        return True

    def client_authentication_required(self, request, *args, **kwargs):return False
    def authenticate_client_id(self, client_id, request, *args, **kwargs):return self.validate_client_id(client_id,request)
    def validate_redirect_uri(self, client_id, redirect_uri, request, *args, **kwargs):return self.client.allows_redirect(redirect_uri)
    def get_default_redirect_uri(self, client_id, request, *args, **kwargs):return None
    def validate_response_type(self, client_id, response_type, client, request, *args, **kwargs):return response_type=="code"
    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):return grant_type=="authorization_code"
    def is_pkce_required(self, client_id, request):return True
    def get_default_scopes(self, client_id, request):return ["finance:read"]
    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):return bool(scopes) and frozenset(scopes)<=FINANCE_SCOPES

    def save_authorization_code(self, client_id, code, request, *args, **kwargs):
        row=self.pending
        if row is None or row["owner_subject"]!=OWNER or row["completed_at"] is not None:raise OAuthFailure("access_denied",403)
        granted=" ".join(sorted(request.scopes))
        if granted!=row["requested_scopes"]:raise OAuthFailure("invalid_scope")
        updated=self.connection.execute("UPDATE oauth_authorization_requests SET granted_scopes=?,completed_at=? WHERE request_id=? AND completed_at IS NULL AND revoked_at IS NULL AND expires_at>?",(granted,self.now,row["request_id"],self.now)).rowcount
        if updated!=1:raise OAuthFailure("access_denied",403)
        self.connection.execute("INSERT INTO oauth_authorization_codes(code_hash,request_id,created_at,expires_at) VALUES(?,?,?,?)",(digest(code["code"]),row["request_id"],self.now,self.now+CODE_TTL))

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        if re.fullmatch(re.escape(CODE_PREFIX)+r"[A-Za-z0-9_-]{43}",code or "") is None:return False
        row=self.connection.execute("SELECT r.*,c.code_hash,c.expires_at AS code_expires_at,c.consumed_at,c.revoked_at AS code_revoked_at FROM oauth_authorization_codes c JOIN oauth_authorization_requests r ON r.request_id=c.request_id WHERE c.code_hash=?",(digest(code),)).fetchone()
        if row is None:return False
        try:resource=validate_resource(request.resource)
        except (ValueError,TypeError):return False
        if row["oauth_client_id"]!=client_id or row["resource"]!=resource or row["redirect_uri"]!=request.redirect_uri or not client.allows_redirect(row["redirect_uri"]):return False
        if row["consumed_at"] is not None:
            # Only a replay proving the same PKCE possession can revoke a grant.
            if FinanceCodeGrant(self).validate_code_challenge(row["pkce_challenge"],row["pkce_method"],request.code_verifier):
                self.connection.execute("UPDATE oauth_access_tokens SET revoked_at=? WHERE request_id=? AND revoked_at IS NULL",(self.now,row["request_id"]))
            return False
        if row["code_expires_at"]<=self.now or row["code_revoked_at"] is not None or row["revoked_at"] is not None or row["completed_at"] is None or row["owner_subject"]!=OWNER:return False
        try:scopes=scopes_from_text(row["granted_scopes"])
        except OAuthFailure:return False
        if not scopes<=scopes_from_text(row["requested_scopes"]):return False
        self.code_row=row
        request.user=OWNER
        request.scopes=sorted(scopes)
        return True

    def get_code_challenge(self, code, request):return self.code_row["pkce_challenge"]
    def get_code_challenge_method(self, code, request):return self.code_row["pkce_method"]
    def confirm_redirect_uri(self, client_id, code, redirect_uri, client, request, *args, **kwargs):return self.code_row["redirect_uri"]==redirect_uri

    def save_bearer_token(self, token, request, *args, **kwargs):
        self.connection.execute("INSERT INTO oauth_access_tokens(token_hash,request_id,issuer,created_at,expires_at) VALUES(?,?,?,?,?)",(digest(token["access_token"]),self.code_row["request_id"],ISSUER,self.now,self.now+ACCESS_TOKEN_TTL))

    def invalidate_authorization_code(self, client_id, code, request, *args, **kwargs):
        count=self.connection.execute("UPDATE oauth_authorization_codes SET consumed_at=? WHERE code_hash=? AND consumed_at IS NULL",(self.now,digest(code))).rowcount
        if count!=1:raise OAuthFailure("invalid_grant")


class OAuthService:
    def __init__(self, settings, clock):
        self.settings,self.clock=settings,clock
        self.limiter=RateLimit()
        # Callback query components must not already contain response fields.
        for client in settings.oauth_clients:
            for uri in client.redirect_uris:
                if {k for k,v in parse_qsl(urlsplit(uri).query)} & {"code","state","error","access_token"}:
                    raise ValueError("redirect URI contains reserved response parameters")

    def now(self):return int(self.clock.now_utc().timestamp())
    def db(self):return connect(self.settings.database_path,self.settings.busy_timeout_ms)

    def client(self, client_id):
        for client in self.settings.oauth_clients:
            if client.oauth_client_id==client_id:return client
        raise OAuthFailure("invalid_client")

    def client_row(self, connection, client, now, *, create=False):
        row=connection.execute("SELECT * FROM oauth_clients WHERE oauth_client_id=?",(client.oauth_client_id,)).fetchone()
        if row is None and create:
            connection.execute("INSERT INTO oauth_clients(oauth_client_id,identity_client_id,redirect_uris_json,created_at) VALUES(?,?,?,?)",(client.oauth_client_id,client.identity_client_id,json.dumps(client.redirect_uris),now))
        elif row is None or row["disabled_at"] is not None or row["identity_client_id"]!=client.identity_client_id:
            raise OAuthFailure("invalid_client")
        elif create:
            connection.execute("UPDATE oauth_clients SET redirect_uris_json=? WHERE oauth_client_id=?",(json.dumps(client.redirect_uris),client.oauth_client_id))

    def begin(self, params):
        now=self.now()
        self.limiter.check("authorize",now)
        client=self.client(params.get("client_id"))
        if not client.allows_redirect(params.get("redirect_uri")):raise OAuthFailure()
        if params.get("response_type")!="code":raise OAuthFailure("unsupported_response_type")
        scopes=scopes_from_text(params.get("scope","finance:read"))
        state=params.get("state")
        if state is not None and (not state or any(ord(c)<32 for c in state)):raise OAuthFailure()
        try:resource=validate_resource(params.get("resource"))
        except (ValueError,TypeError):raise OAuthFailure("invalid_target") from None
        try:
            binding=secrets.token_urlsafe(32)
            pending=AuthorizationRequest(secrets.token_urlsafe(24),client,params["redirect_uri"],scopes,resource,state,digest(binding),params.get("code_challenge",""),now,now+CONSENT_TTL,params.get("code_challenge_method",""))
        except (ValueError,TypeError,KeyError):raise OAuthFailure() from None
        if not self.settings.ui_token:raise OAuthFailure("temporarily_unavailable",503)
        connection=self.db()
        try:
            with immediate_transaction(connection):
                self.client_row(connection,client,now,create=True)
                connection.execute("DELETE FROM oauth_authorization_requests WHERE completed_at IS NULL AND expires_at<=? AND request_id NOT IN (SELECT request_id FROM oauth_authorization_codes)",(now,))
                if connection.execute("SELECT count(*) FROM oauth_authorization_requests WHERE completed_at IS NULL AND expires_at>?",(now,)).fetchone()[0]>=256:raise OAuthFailure("temporarily_unavailable",429)
                connection.execute("INSERT INTO oauth_authorization_requests(request_id,oauth_client_id,redirect_uri,state,browser_binding_hash,requested_scopes,resource,pkce_challenge,pkce_method,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(pending.request_id,client.oauth_client_id,pending.redirect_uri,json.dumps(state),pending.browser_binding_hash," ".join(sorted(scopes)),resource,pending.pkce_challenge,"S256",now,now+CONSENT_TTL))
                row=connection.execute("SELECT * FROM oauth_authorization_requests WHERE request_id=?",(pending.request_id,)).fetchone()
            return row,binding
        finally:connection.close()

    def csrf(self, row, binding, action):
        if not self.settings.ui_token:raise OAuthFailure("access_denied",403)
        message="oauth-csrf:"+row["request_id"]+":"+binding+":"+action
        return hmac.new(self.settings.ui_token.encode(),message.encode(),sha256).hexdigest()

    def browser_binding(self, environ):
        cookie=SimpleCookie()
        try:cookie.load(environ.get("HTTP_COOKIE",""))
        except CookieError:raise OAuthFailure("access_denied",403) from None
        value=cookie.get(COOKIE_NAME)
        if value is None or re.fullmatch(r"[A-Za-z0-9_-]{43}",value.value) is None:raise OAuthFailure("access_denied",403)
        return value.value

    def act(self, params, binding):
        now=self.now()
        connection=self.db()
        try:
            with immediate_transaction(connection):
                row=connection.execute("SELECT * FROM oauth_authorization_requests WHERE request_id=?",(params.get("request_id",""),)).fetchone()
                if row is None or row["completed_at"] is not None or row["revoked_at"] is not None or row["expires_at"]<=now or not hmac.compare_digest(digest(binding),row["browser_binding_hash"]):raise OAuthFailure("access_denied",403)
                client=self.client(row["oauth_client_id"])
                self.client_row(connection,client,now)
                if not client.allows_redirect(row["redirect_uri"]):raise OAuthFailure("access_denied",403)
                action=params.get("action")
                purpose="login" if action=="login" else "consent"
                if not hmac.compare_digest(params.get("csrf","").encode(),self.csrf(row,binding,purpose).encode()):raise OAuthFailure("access_denied",403)
                if action=="login":
                    self.limiter.check("login",now)
                    supplied=params.get("ui_token","")
                    if not self.settings.ui_token or not hmac.compare_digest(supplied.encode(),self.settings.ui_token.encode()):raise OAuthFailure("access_denied",401)
                    connection.execute("UPDATE oauth_authorization_requests SET owner_subject=? WHERE request_id=? AND completed_at IS NULL",(OWNER,row["request_id"]))
                    row=connection.execute("SELECT * FROM oauth_authorization_requests WHERE request_id=?",(row["request_id"],)).fetchone()
                    return "consent",row
                if row["owner_subject"]!=OWNER or action not in {"allow","deny"}:raise OAuthFailure("access_denied",403)
                if action=="deny":
                    connection.execute("UPDATE oauth_authorization_requests SET completed_at=?,revoked_at=? WHERE request_id=?",(now,now,row["request_id"]))
                    response={"error":"access_denied"}
                    state=json.loads(row["state"])
                    if state is not None:response["state"]=state
                    return "redirect",row["redirect_uri"]+("&" if "?" in row["redirect_uri"] else "?")+urlencode(response)
                validator=FinanceValidator(self,connection,client,now,pending=row)
                params={"response_type":"code","client_id":client.oauth_client_id,"redirect_uri":row["redirect_uri"],"scope":row["requested_scopes"],"resource":row["resource"],"code_challenge":row["pkce_challenge"],"code_challenge_method":"S256"}
                state=json.loads(row["state"])
                if state is not None:params["state"]=state
                headers,body,status=FinanceServer(validator).create_authorization_response(ISSUER+"/oauth/authorize?"+urlencode(params),scopes=row["requested_scopes"].split(" "),credentials={"user":OWNER})
                if status!=302 or "Location" not in headers:raise OAuthFailure("server_error",500)
                return "redirect",headers["Location"]
        finally:connection.close()

    def exchange(self, params):
        now=self.now()
        self.limiter.check("token",now)
        if params.get("grant_type")!="authorization_code":raise OAuthFailure("unsupported_grant_type")
        if any(not params.get(key) for key in TOKEN_FIELDS):raise OAuthFailure()
        if re.fullmatch(r"[A-Za-z0-9._~-]{43,128}",params["code_verifier"]) is None:raise OAuthFailure("invalid_grant")
        try:params={**params,"resource":validate_resource(params["resource"])}
        except (TypeError,ValueError):raise OAuthFailure("invalid_target") from None
        client=self.client(params["client_id"])
        connection=self.db()
        try:
            with immediate_transaction(connection):
                self.client_row(connection,client,now)
                validator=FinanceValidator(self,connection,client,now)
                headers,body,status=FinanceServer(validator).create_token_response(ISSUER+"/oauth/token",body=urlencode(params),headers={"Content-Type":"application/x-www-form-urlencoded"})
                payload=json.loads(body)
                if status!=200:
                    # Do not return library descriptions/request contents.
                    return status,{"error":payload.get("error","invalid_grant")}
                return status,payload
        finally:connection.close()

    def resolve(self, token):
        if re.fullmatch(re.escape(TOKEN_PREFIX)+r"[A-Za-z0-9_-]{43}",token) is None:return None
        connection=self.db()
        try:
            row=connection.execute("SELECT r.*,t.issuer,t.created_at AS token_created_at,t.expires_at AS token_expires_at,t.revoked_at AS token_revoked_at,c.identity_client_id,c.disabled_at,code.consumed_at,code.revoked_at AS code_revoked_at FROM oauth_access_tokens t JOIN oauth_authorization_requests r ON r.request_id=t.request_id JOIN oauth_clients c ON c.oauth_client_id=r.oauth_client_id JOIN oauth_authorization_codes code ON code.request_id=r.request_id WHERE t.token_hash=?",(digest(token),)).fetchone()
            if row is None or row["issuer"]!=ISSUER or row["resource"]!=RESOURCE or row["token_created_at"]>self.now() or row["token_expires_at"]<=self.now() or row["token_revoked_at"] is not None or row["revoked_at"] is not None or row["disabled_at"] is not None or row["code_revoked_at"] is not None or row["consumed_at"] is None or row["owner_subject"]!=OWNER:return None
            try:
                client=self.client(row["oauth_client_id"])
                scopes=scopes_from_text(row["granted_scopes"])
                if not scopes<=scopes_from_text(row["requested_scopes"]):return None
            except OAuthFailure:return None
            if client.identity_client_id!=row["identity_client_id"] or not client.allows_redirect(row["redirect_uri"]):return None
            return client.identity_client_id,scopes
        finally:connection.close()

    def page(self, row, binding, *, consent=False):
        purpose="consent" if consent else "login"
        hidden=f'<input type="hidden" name="request_id" value="{escape(row["request_id"],quote=True)}"><input type="hidden" name="csrf" value="{self.csrf(row,binding,purpose)}">'
        client=escape(row["oauth_client_id"])
        if consent:
            labels={"finance:read":"consultar seus dados financeiros","finance:write":"criar/alterar registros permitidos pelas tools autorizadas"}
            scopes="".join("<li>"+labels[scope]+"</li>" for scope in row["requested_scopes"].split(" "))
            fields=f'<p>O aplicativo {client} solicita acesso ao Finance V2:</p><ul>{scopes}</ul><button name="action" value="allow">AUTORIZAR</button> <button name="action" value="deny">CANCELAR</button>'
            title="Autorizar acesso"
        else:
            fields=f'<p>Identifique-se como proprietário da Finance V2 para continuar com {client}.</p><label>Credencial do proprietário <input type="password" name="ui_token" required autocomplete="current-password"></label><button name="action" value="login">Entrar</button>'
            title="Entrar na Finance V2"
        return f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><main><h1>{title}</h1><form method="post" action="/oauth/authorize">{hidden}{fields}</form></main></html>'

    def http(self, environ, start):
        path=environ.get("PATH_INFO","")
        method=environ.get("REQUEST_METHOD","")
        try:
            if path=="/oauth/authorize" and method=="GET":
                params=parameters(environ.get("QUERY_STRING",""),AUTHORIZE_FIELDS,ignore_unknown=True)
                try:row,binding=self.begin(params)
                except OAuthFailure as failure:
                    # Redirect protocol errors only after exact client/callback
                    # validation. Unknown clients/redirects remain local errors.
                    client=self.client(params.get("client_id"))
                    if not client.allows_redirect(params.get("redirect_uri")) or failure.status!=400:raise failure
                    state=params.get("state")
                    response={"error":failure.error}
                    if state:response["state"]=state
                    uri=params["redirect_uri"]
                    return http_response(start,302,None,location=uri+("&" if "?" in uri else "?")+urlencode(response))
                return http_response(start,200,self.page(row,binding),html=True,cookie=f"{COOKIE_NAME}={binding}; Path={COOKIE_PATH}; Secure; HttpOnly; SameSite=Lax; Max-Age={CONSENT_TTL}")
            if method!="POST" or path not in {"/oauth/authorize","/oauth/token"}:return http_response(start,405,{"error":"invalid_request"},allow="POST" if path=="/oauth/token" else "GET, POST")
            if environ.get("QUERY_STRING") or environ.get("HTTP_AUTHORIZATION"):raise OAuthFailure()
            if environ.get("CONTENT_TYPE","").split(";",1)[0].lower()!="application/x-www-form-urlencoded":raise OAuthFailure()
            try:length=int(environ.get("CONTENT_LENGTH") or "0")
            except ValueError:raise OAuthFailure() from None
            if not 0<length<=16384:raise OAuthFailure()
            raw=environ["wsgi.input"].read(length)
            if len(raw)!=length:raise OAuthFailure()
            try:raw=raw.decode("utf-8",errors="strict")
            except UnicodeError:raise OAuthFailure() from None
            if path=="/oauth/token":
                status,payload=self.exchange(parameters(raw,TOKEN_FIELDS))
                return http_response(start,status,payload)
            if environ.get("HTTP_ORIGIN") not in (None,ISSUER):raise OAuthFailure("access_denied",403)
            binding=self.browser_binding(environ)
            result,payload=self.act(parameters(raw,{"request_id","csrf","action","ui_token"}),binding)
            if result=="consent":return http_response(start,200,self.page(payload,binding,consent=True),html=True)
            return http_response(start,302,None,location=payload,cookie=f"{COOKIE_NAME}=; Path={COOKIE_PATH}; Secure; HttpOnly; SameSite=Lax; Max-Age=0")
        except OAuthFailure as error:return http_response(start,error.status,{"error":error.error})
        except OAuth2Error:return http_response(start,400,{"error":"invalid_request"})
        except Exception:
            # Exception reprs/SQLite integrity errors may contain secrets. Fail
            # closed with a fixed error; never log the exception or request.
            return http_response(start,500,{"error":"server_error"})


def http_response(start, status, payload, *, html=False, location=None, cookie=None, allow="GET, POST"):
    body=b"" if payload is None else payload.encode("utf-8") if html else json.dumps(payload,separators=(",",":")).encode("utf-8")
    headers=[("Content-Type","text/html; charset=utf-8" if html else "application/json; charset=utf-8"),("Content-Length",str(len(body))),("Cache-Control","no-store"),("Pragma","no-cache"),("Referrer-Policy","no-referrer"),("X-Content-Type-Options","nosniff"),("Content-Security-Policy","default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")]
    if location:headers.append(("Location",location))
    if cookie:headers.append(("Set-Cookie",cookie))
    if status==405:headers.append(("Allow",allow))
    phrases={200:"OK",302:"Found",400:"Bad Request",401:"Unauthorized",403:"Forbidden",405:"Method Not Allowed",429:"Too Many Requests",500:"Internal Server Error",503:"Service Unavailable"}
    start(str(status)+" "+phrases.get(status,"Error"),headers)
    return [body]
