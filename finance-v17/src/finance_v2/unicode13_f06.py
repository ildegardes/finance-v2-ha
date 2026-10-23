"""Canonical U31-A13 F06 using pinned Unicode13 primitives only.

Adapted from the separately validated OF-L3-03 backend. No native Unicode
property/normalization/casefold decision, no runtime-version fallback.
"""
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from functools import lru_cache
import json
import stat

DATA_SHA256='DE81088662045384D1F0B07FDF53A40BEE297843782FE80BF1AAEA94383BAAA4'
BACKEND_ID='FINANCE-F06-U13/1'
EXPECTED_KEYS={'contract','ucd','generator','canonical_decomposition',
               'combining_class','full_casefold','mn'}


class ProfileUnavailable(Exception):
    code='QUERY_PROFILE_UNAVAILABLE'
    status=503


class QueryRejected(Exception):
    def __init__(self,code,status=422):
        super().__init__(code)
        self.code,self.status=code,status


def _require(ok):
    if not ok:raise ProfileUnavailable('PINNED_UNICODE_PROFILE_INVALID')


def _scalar(n):
    return type(n) is int and 0<=n<=0x10FFFF and not 0xD800<=n<=0xDFFF


def _unique(pairs):
    result={}
    for k,v in pairs:
        _require(k not in result);result[k]=v
    return result


def _decode(raw,expected):
    # Private decoder used by adversarial fixtures with their own test pins.
    # The real constructor has NO path or expected-hash override.
    _require(isinstance(raw,bytes) and 0<len(raw)<=200000)
    _require(sha256(raw).hexdigest().upper()==expected)
    try:
        data=json.loads(raw,object_pairs_hook=_unique,
                        parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
    except (ValueError,UnicodeError,RecursionError):
        raise ProfileUnavailable('PINNED_UNICODE_PROFILE_INVALID') from None
    _require(type(data) is dict and set(data)==EXPECTED_KEYS)
    _require(data['contract']=='OF-L3-03-U13-PRIMITIVES/1' and data['ucd']=='13.0.0'
             and data['generator']=='CPython 3.10.0 installed reference')
    for key,count in (('canonical_decomposition',2061),('combining_class',872),('full_casefold',1490)):
        _require(type(data[key]) is dict and len(data[key])==count)
        for k,v in data[key].items():
            _require(isinstance(k,str) and k.isascii() and k.isdecimal() and len(k)<=7)
            cp=int(k);_require(_scalar(cp) and str(cp)==k)
            if key=='combining_class':
                _require(type(v) is int and 1<=v<=255)
            else:
                _require(type(v) is list and 1<=len(v)<=3 and all(_scalar(c) for c in v))
    _require(type(data['mn']) is list and len(data['mn'])==1839
             and all(_scalar(cp) for cp in data['mn'])
             and data['mn']==sorted(set(data['mn'])))
    return data


def _read_profile():
    try:
        path=Path(__file__).with_name('unicode13_primitives.json')
        info=path.lstat()
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<info.st_size<=200000
                 and not getattr(info,'st_file_attributes',0)&0x400)
        return _decode(path.read_bytes(),DATA_SHA256)
    except OSError:
        raise ProfileUnavailable('PINNED_UNICODE_PROFILE_UNAVAILABLE') from None


class Fixed13:
    def __init__(self):
        data=_read_profile()
        decomposition={int(k):tuple(v) for k,v in data['canonical_decomposition'].items()}
        expanded={}
        def expand(cp,trail=()):
            _require(cp not in trail and len(trail)<32)
            if cp in expanded:return expanded[cp]
            if 0xAC00<=cp<=0xD7A3:return self.hangul(cp)
            if cp not in decomposition:return (cp,)
            value=tuple(c for child in decomposition[cp] for c in expand(child,trail+(cp,)))
            _require(len(value)<=32)
            expanded[cp]=value
            return value
        for cp in decomposition:expand(cp)
        self.decomposition=MappingProxyType(expanded)
        self.combining=MappingProxyType({int(k):v for k,v in data['combining_class'].items()})
        self.fold=MappingProxyType({int(k):tuple(v) for k,v in data['full_casefold'].items()})
        self.mn=frozenset(data['mn'])

    @staticmethod
    def hangul(cp):
        index=cp-0xAC00
        lead=0x1100+index//588
        vowel=0x1161+(index%588)//28
        tail=index%28
        return (lead,vowel,0x11A7+tail) if tail else (lead,vowel)

    def nfd(self,value):
        out=[];marks=[]
        for ch in value:
            cp=ord(ch)
            parts=self.hangul(cp) if 0xAC00<=cp<=0xD7A3 else self.decomposition.get(cp,(cp,))
            for part in parts:
                if self.combining.get(part,0)==0:
                    if marks:
                        out.extend(sorted(marks,key=self.combining.__getitem__));marks=[]
                    out.append(part)
                else:marks.append(part)
        if marks:out.extend(sorted(marks,key=self.combining.__getitem__))
        return ''.join(map(chr,out))

    def full_casefold(self,value):
        return ''.join(chr(v) for ch in value for v in self.fold.get(ord(ch),(ord(ch),)))

    def key(self,value,*,term=False):
        if not isinstance(value,str) or len(value)>(256 if term else 4096) or any(
                0xD800<=ord(ch)<=0xDFFF or (ord(ch)<32 and ch not in '\t\n\r')
                or ord(ch)==127 for ch in value):
            if term:raise QueryRejected('INVALID_QUERY')
            return None
        value=value.replace('\r\n','\n').replace('\r','\n')
        key=self.nfd(self.full_casefold(self.nfd(value)))
        key=''.join(ch for ch in key if ord(ch) not in self.mn
                    or 0xFE00<=ord(ch)<=0xFE0F or 0xE0100<=ord(ch)<=0xE01EF)
        if len(key)>(2048 if term else 32768):
            raise QueryRejected('QUERY_LIMIT_EXCEEDED',422 if term else 503)
        if term and (not key or not key.strip(' ')):
            raise QueryRejected('EMPTY_SEARCH')
        return key


@lru_cache(maxsize=1)
def backend():
    return Fixed13()


def search_key(value,*,term=False):
    return backend().key(value,term=term)




def verify_profile():
    """Recheck physical bytes/schema at startup and once per search request.

    Query rows use the immutable in-memory snapshot, never partially reloaded
    tables. A cached backend does not bypass this physical integrity check.
    """
    _read_profile()
    return backend()

