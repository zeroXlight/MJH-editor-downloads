"""Bounded, data-only Lua table parser for native animation tables."""
import re,json,math
TOKEN=re.compile(r'\s*(?:(--[^\n]*(?:\n|$))|("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|(-?(?:0x[0-9a-fA-F]+|\d+(?:\.\d*)?(?:[eE][+-]?\d+)?))|([A-Za-z_]\w*)|([{}\[\],;=]))')

def parse(text):
    tokens=[];pos=0
    while pos<len(text):
        if not text[pos:].strip():break
        m=TOKEN.match(text,pos)
        if not m:raise ValueError('动画包含非数据 Lua 语法，不能导出')
        pos=m.end()
        if m[1]:continue
        tokens.append(next(v for v in m.groups()[1:] if v is not None))
        if len(tokens)>200000:raise ValueError('动画数据过大')
    cursor=0
    def value(depth=0):
        nonlocal cursor
        if depth>60 or cursor>=len(tokens):raise ValueError('动画数据层级／长度异常')
        t=tokens[cursor];cursor+=1
        if t=='{':
            out={};index=1
            while cursor<len(tokens) and tokens[cursor]!='}':
                if tokens[cursor]=='[':
                    cursor+=1;k=value(depth+1)
                    if tokens[cursor:cursor+2]!=[']','=']:raise ValueError('动画表键无效')
                    cursor+=2;v=value(depth+1)
                elif cursor+1<len(tokens) and tokens[cursor+1]=='=':
                    k=tokens[cursor];cursor+=2;v=value(depth+1)
                else:k=index;index+=1;v=value(depth+1)
                if not isinstance(k,(str,int)) or isinstance(k,bool) or str(k) in out:raise ValueError('动画表键重复或无效')
                out[str(k)]=v
                if cursor<len(tokens) and tokens[cursor] in (',',';'):cursor+=1
            if cursor>=len(tokens):raise ValueError('动画表未闭合')
            cursor+=1;return out
        if t.startswith(('"',"'")):
            if t.startswith('"'):return json.loads(t)
            return re.sub(r'\\([\\\'nrt])',lambda m:{'n':'\n','r':'\r','t':'\t'}.get(m[1],m[1]),t[1:-1])
        if t=='nil':return None
        if t in ('true','false'):return t=='true'
        if re.fullmatch(r'-?0x[0-9a-fA-F]+',t):return int(t,16)
        if re.fullmatch(r'-?\d+',t):return int(t)
        try:v=float(t)
        except ValueError:raise ValueError('动画含函数或标识符，不能作为数据导入')
        if not math.isfinite(v):raise ValueError('动画数值异常')
        return v
    out=value()
    if cursor!=len(tokens):raise ValueError('动画表后有额外代码')
    return out

def dump(value,depth=0):
    if depth>60:raise ValueError('动画层级过深')
    if isinstance(value,dict):
        return '{'+','.join('['+(str(int(k)) if re.fullmatch(r'-?\d+',k) else json.dumps(k,ensure_ascii=False))+']='+dump(v,depth+1) for k,v in value.items())+'}'
    if isinstance(value,list):return '{'+','.join(dump(v,depth+1) for v in value)+'}'
    if value is None:return 'nil'
    if isinstance(value,str):return json.dumps(value,ensure_ascii=False)
    if isinstance(value,bool):return 'true' if value else 'false'
    if type(value) in (int,float) and math.isfinite(value):return str(value)
    raise ValueError('动画只能包含数据')
