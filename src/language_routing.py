"""Resolve names through the same ID partition used by ProcessLanguage."""
import re

def split_size(assets):
    match=re.search(r"\[['\"]splitByID['\"]\]\s*=\s*(\d+)",assets.script('Language.lua'))
    if not match or int(match[1])<=0:raise ValueError('语言表分片配置无效，停止写入')
    return int(match[1])

def resource_for(assets,ident):
    name=f'Language{ident//split_size(assets)}.lua'
    if name not in assets.scripts:raise ValueError(f'名称编号 {ident} 对应的游戏语言分表 {name} 不存在')
    return name

def next_id(lib,start=1600000000):
    size=split_size(lib.assets);used=lib.tables['Language']
    candidate=max(start,max((i for i in used if i>=start),default=start-1)+1)
    if candidate<=2100000000 and f'Language{candidate//size}.lua' in lib.assets.scripts:return candidate
    shards=sorted((int(re.fullmatch(r'Language(\d+)\.lua',name)[1]) for name in lib.resources['Language']),reverse=True)
    for shard in shards:
        low=max(shard*size,1);high=min((shard+1)*size,2100000001)
        for ident in range(low,high):
            if ident not in used:return ident
    raise ValueError('已有语言分表没有可用编号')

def misplaced(lib):
    size=split_size(lib.assets)
    return {i:resource for i,resource in lib.locations['Language'].items()
            if resource!=f'Language{i//size}.lua'}

def stage_repairs(lib):
    """Reuse IDs and text so saved martial instances keep all references."""
    repairs=misplaced(lib)
    with lib.edit():
        for ident in repairs:
            resource_for(lib.assets,ident)
            lib.set('Language',ident,{'Ch_Text':lib.text(ident)})
    return len(repairs)

def strip_rows(text,identifiers):
    from martial_editor import LANG_RE
    return re.sub(LANG_RE,lambda m:'' if int(m[2]) in identifiers else m[0],text)
