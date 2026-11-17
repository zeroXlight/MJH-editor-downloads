"""Bounded, content-keyed caches of immutable language records."""
from functools import lru_cache
import re,copy

@lru_cache(maxsize=2)
def _native_effects(data):
    from martial_editor import indexed_rows
    from engine import SCHEMAS
    from codec import decode
    rows,_=indexed_rows(data)
    return {i:decode(row,'SkillEffect',SCHEMAS) for i,row in rows.items()}

def _copy_effect_rows(rows):
    # SkillEffect arguments are flat numeric lists. Copy the editable lists
    # directly instead of recursively deepcopying every scalar and key.
    return {i:{k:v.copy() if isinstance(v,list) else copy.deepcopy(v) if isinstance(v,dict) else v
               for k,v in row.items()} for i,row in rows.items()}

def native_effects(data):return _copy_effect_rows(_native_effects(data))

@lru_cache(maxsize=8)
def _effect_script(text,enums):
    from client_config import lua_rows
    return lua_rows(text,'SkillEffect',dict(enums))

def effect_script(text,enums):return _copy_effect_rows(_effect_script(text,tuple(sorted(enums.items()))))

@lru_cache(maxsize=1)
def native_language(data):
    from martial_editor import indexed_rows
    from engine import SCHEMAS
    from codec import decode
    raw,_=indexed_rows(data)
    # Language has scalar string/integer fields. Consumers get fresh dicts;
    # neither a draft nor a mod overlay can mutate a cached record.
    return tuple((ident,tuple(decode(row,'Language',SCHEMAS).items())) for ident,row in raw.items())

# The current game has over 750 language partitions. A smaller per-script
# cache thrashes during a full read; cap this at one game's working set.
@lru_cache(maxsize=1024)
def language_script(text):
    def unquote(value):
        return re.sub(r'\\([\\"nrt])',lambda m:{'n':'\n','r':'\r','t':'\t'}.get(m[1],m[1]),value[1:-1])
    return tuple((int(ident),unquote(value)) for ident,value in re.findall(
        r'(?m)^\s*\[(\d+)\]\s*=\s*("(?:\\.|[^"\\])*"),?',text))
