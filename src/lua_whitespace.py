"""Ignore Lua formatting only; preserve literal bytes and editor marker comments."""
import re
from functools import lru_cache
WORD=re.compile(rb'[A-Za-z_][A-Za-z_0-9]*|(?:0[xX][0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?(?:[pP][+-]?[0-9]+)?|[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)')
LONG=re.compile(rb'\[(=*)\[')
OPS=(b'...',b'..',b'//',b'<<',b'>>',b'<=',b'>=',b'==',b'~=',b'::')

def tokens(raw):
    out=[];pos=0
    while pos<len(raw):
        if raw[pos] in b' \t\r\n\v\f':pos+=1;continue
        start=pos;comment=raw.startswith(b'--',pos)
        if comment:pos+=2
        long=LONG.match(raw,pos)
        if long:
            end=raw.find(b']'+long[1]+b']',long.end())
            if end<0:raise ValueError('Unterminated Lua long literal')
            pos=end+len(long[1])+2
        elif comment:
            end=raw.find(b'\n',pos);pos=len(raw) if end<0 else end
            out.append(raw[start:pos].rstrip(b'\r'));continue
        elif raw[pos] in (34,39):
            quote=raw[pos];pos+=1
            while pos<len(raw):
                if raw[pos]==92:pos+=2
                elif raw[pos]==quote:pos+=1;break
                else:pos+=1
            else:raise ValueError('Unterminated Lua quoted literal')
        else:
            word=WORD.match(raw,pos)
            if word:pos=word.end()
            else:pos+=len(next((op for op in OPS if raw.startswith(op,pos)),raw[pos:pos+1]))
        out.append(raw[start:pos])
    return out

@lru_cache(maxsize=1)
def compiler():
    from lupa.lua53 import LuaRuntime
    return LuaRuntime(encoding=None).eval(b'function(s) return load(s) ~= nil end')

def equivalent(a,b):
    try:return tokens(a)==tokens(b) and compiler()(a) and compiler()(b)
    except ValueError:return False

def equivalent_table(a,b,name,enums):
    """Pure data-row key order can change during a composed field update."""
    from engine import SCHEMAS
    from client_config import lua_rows
    from martial_editor import ROW_RE
    match=re.fullmatch(r'([A-Za-z]+)\d*\.lua',name)
    if not match or match[1] not in SCHEMAS:return False
    try:
        x=a.decode('utf-8-sig');y=b.decode('utf-8-sig')
        if lua_rows(x,match[1],enums)!=lua_rows(y,match[1],enums):return False
        strip=lambda text:re.sub(ROW_RE,lambda m:m[1]+'{},',text).encode('utf8')
        return equivalent(strip(x),strip(y))
    except (ValueError,KeyError,UnicodeError):return False
