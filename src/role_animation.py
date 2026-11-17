"""Bind RoleModel IDs to complete Spine animation timing and event data.

RoleModel.BaseID (not the resource ModelID) indexes SpineAnimaitionTime.
Cloned appearance records must receive their own timing entry. Keeping the
whole source record preserves attack/switch/jump event frames for future
model import support; a matching idle animation alone is insufficient.
"""
import re
import json

def skeleton_body(data):
    """Use the model's actual Spine event timeline, never an unrelated numeric ID."""
    animations=data.get('animations')
    if not isinstance(animations,list) or not animations:raise ValueError('骨骼文件没有可读取的动作')
    lines=[];seen=set()
    for animation in animations:
        name=animation.get('Name');duration=animation.get('Milliseconds')
        if not isinstance(name,str) or not name or name in seen or type(duration) is not int or not 0<=duration<2147483648:
            raise ValueError('骨骼动作名称或时长无效')
        seen.add(name);events={}
        for event in animation.get('Events',[]):
            key=event.get('Name');time=event.get('Milliseconds')
            if not isinstance(key,str) or not key or type(time) is not int or not 0<=time<=duration:
                raise ValueError('骨骼动作事件帧无效：'+name)
            events.setdefault(key,[]).append(time)
        body=str(duration)+','
        for key,times in events.items():body+=' ['+json.dumps(key,ensure_ascii=False)+'] = {'+','.join(map(str,times))+'},'
        lines.append('  ['+json.dumps(name,ensure_ascii=False)+'] = {'+body+'},')
    return '{\n'+'\n'.join(lines)+'\n}'

def ensure_sources(lib,text,bindings):
    rows=animation_rows(text);missing={};visiting=set()
    def resolve(ident):
        if ident in visiting:raise ValueError('模型动作绑定存在循环：'+str(ident))
        if ident in bindings and bindings[ident]!=ident:
            visiting.add(ident);resolve(bindings[ident]);visiting.remove(ident);return
        if ident in rows or ident in missing:return
        if ident not in lib.tables['RoleModel']:raise ValueError('动作来源模型不存在：'+str(ident))
        from model_texture import template_info
        from model_texture_preview import runtime_data
        cache=getattr(lib,'_skeleton_animation_cache',None)
        if cache is None:cache={};lib._skeleton_animation_cache=cache
        info=template_info(lib,ident);key=info['skeleton_sha']
        if key not in cache:cache[key]=skeleton_body(runtime_data(lib.root,info))
        missing[ident]=cache[key]
    for ident in bindings:resolve(ident)
    if missing:
        anchor=re.search(r'\}\s*return\s+spineAnimaition\b',text)
        if not anchor:raise ValueError('模型动作表结构不兼容，未修改文件')
        addition=''.join('['+str(i)+'] = '+body+',\n' for i,body in sorted(missing.items()))
        text=text[:anchor.start()]+addition+text[anchor.start():]
    return text

def resolved_timings(lib,text,bindings):
    return bind_animations(ensure_sources(lib,text,bindings),bindings)

def pending(lib):
    bindings=model_bindings(lib)
    if not bindings:return False
    cached=getattr(lib,'_animation_pending_index',None)
    if cached is None or cached[0] is not lib.assets:
        cached=(lib.assets,animation_rows(lib.assets.script('SpineAnimaitionTime.lua')))
        lib._animation_pending_index=cached
    rows=cached[1]
    return any(target not in rows or source not in rows for target,source in bindings.items())

def animation_rows(text):
    rows={}
    for match in re.finditer(r'^\s*\[(\d+)\]\s*=\s*\{',text,re.M):
        start=match.end()-1;depth=0;quote=None;escaped=False
        for end in range(start,len(text)):
            char=text[end]
            if quote:
                if escaped:escaped=False
                elif char=='\\':escaped=True
                elif char==quote:quote=None
            elif char in ('"',"'"):quote=char
            elif char=='{':depth+=1
            elif char=='}':
                depth-=1
                if depth==0:
                    rows[int(match[1])]=(start,end+1,text[start:end+1]);break
        else:raise ValueError('模型动作数据不完整：'+match[1])
    return rows

def bind_animations(text,bindings):
    """Copy complete timing records, resolve chained donors, fail atomically on cycles."""
    rows=animation_rows(text);resolved={};visiting=set()
    def body(ident):
        if ident in resolved:return resolved[ident]
        if ident in visiting:raise ValueError('模型动作绑定存在循环：'+str(ident))
        visiting.add(ident)
        if ident in bindings and bindings[ident]!=ident:result=body(bindings[ident])
        elif ident in rows:result=rows[ident][2]
        else:raise ValueError('模型缺少动作时间与事件数据：'+str(ident))
        visiting.remove(ident);resolved[ident]=result;return result
    replacements=[];missing=[]
    for target in sorted(bindings):
        value=body(target)
        if target in rows:
            start,end,old=rows[target]
            if old!=value:replacements.append((start,end,value))
        else:missing.append(f'[{target}] = {value},\n')
    if missing:
        match=re.search(r'\}\s*return\s+spineAnimaition\b',text)
        if not match:raise ValueError('模型动作表结构不兼容，未修改文件')
        replacements.append((match.start(),match.start(),''.join(missing)))
    for start,end,value in sorted(replacements,reverse=True):text=text[:start]+value+text[end:]
    return text

def model_bindings(lib):
    bindings={}
    for rid,record in lib.meta.items():
        if not record.get('owned_art') or record.get('settings',{}).get('mobile_binding'):continue
        target=lib.row(int(rid))['ArtID']
        donor=record.get('animation_source',record['settings'].get('model_source',record.get('base_art')))
        if target==donor:donor=record.get('base_art',donor)
        if target!=donor:bindings[target]=donor
    return bindings

def plan_bindings(lib,assetdata):
    from client_config import Assets
    from edition import MOBILE_ENABLED
    bindings=model_bindings(lib)
    mobile=MOBILE_ENABLED and any(r.get('settings',{}).get('mobile_binding') for r in lib.meta.values())
    if not bindings and not mobile:return assetdata
    assets=Assets(assetdata)
    if 'SpineAnimaitionTime.lua' not in assets.scripts:raise ValueError('游戏缺少模型动作表，未修改文件')
    text=assets.script('SpineAnimaitionTime.lua');new=resolved_timings(lib,text,bindings)
    if mobile:
        from mobile_models import animation_patch
        new=animation_patch(lib,new)
    return assets.replace_script('SpineAnimaitionTime.lua',new) if new!=text else assetdata
