"""Reversible editor-owned support around installation of an external MOD.

Only the editor section and its recorded hooks are detached. Foreign bytes,
configuration and save progress are never restored from a vanilla snapshot.
"""
import hashlib, json, struct
from pathlib import Path

GUARDS = [(2345728,64,'fa1c2be9172947d3f4732d0476ab840f6dfeab6f1be2be8d0e9afdeb69c98c24'),
          (6003328,64,'a285818a7735570ed425dd861bda0e5db324975d4837ab9d32edbce68a2825f5'),
          (5142517,24,'a1707dc530f0332bf59893835e4bcae253ef2177f83a7b90adb52fcc71daf43d'),
          (5142934,24,'3c54867004a6b3a748eb41e6dcd91ea257625d0da89e8d2551842678d9ddb164')]
DLL = 'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
RECEIPT = '装备编辑器配置/外部MOD安装兼容.json'

def sha(b): return hashlib.sha256(b).hexdigest()

def certify_parent(raw):
    from bigmap_profile import race_parent
    if race_parent(raw):
        import pefile
        return pefile.PE(data=raw,fast_load=True)
    # The legacy guards below belong to the old PC build. A modified big-map
    # image must pass the full Shadow reverser, never these legacy addresses.
    import pefile
    probe=pefile.PE(data=raw,fast_load=True)
    if any(s.Name.rstrip(b'\0')==b'.rdata' and s.VirtualAddress in (0xf72000,0xf74000,0xf77000) for s in probe.sections):
        raise ValueError('大地图运行库含未认证的代码或暗影改动，未覆盖；请保留运行库及MOD版本供检查')
    import pefile
    from growth_runtime import HOOKS, SECTION
    pe=pefile.PE(data=raw,fast_load=True)
    if pe.FILE_HEADER.Machine!=0x8664 or pe.OPTIONAL_HEADER.Magic!=0x20b:
        raise ValueError('外部运行库架构不匹配，保留原文件')
    if any(s.Name.rstrip(b'\0')==SECTION for s in pe.sections):
        raise ValueError('外部运行库仍含编辑器支持段')
    for rva,size,want in GUARDS:
        off=pe.get_offset_from_rva(rva)
        if sha(raw[off:off+size])!=want:raise ValueError('外部 MOD 改变了编辑器所需计算入口：'+hex(rva))
    for rva,target,expected in HOOKS:
        off=pe.get_offset_from_rva(rva)
        if raw[off:off+5]!=expected:raise ValueError('成长入口被其他 MOD 占用：'+hex(rva))
    return pe

def inspect(raw):
    import pefile
    from growth_runtime import SECTION,SIGNATURE,META_MAGIC
    pe=pefile.PE(data=raw,fast_load=True)
    selected=[s for s in pe.sections if s.Name.rstrip(b'\0')==SECTION]
    if len(selected)!=1 or selected[0]!=pe.sections[-1]:raise ValueError('编辑器支持段不是独立的末尾段，暂不处理')
    section=selected[0];body=section.get_data();pos=body.find(META_MAGIC)
    if not body.startswith(SIGNATURE) or pos<0:raise ValueError('编辑器补丁标识或校验信息无效')
    size=struct.unpack_from('<I',body,pos+len(META_MAGIC))[0];start=pos+len(META_MAGIC)+4
    if size<=0 or start+size>len(body):raise ValueError('编辑器补丁校验长度无效')
    meta=json.loads(body[start:start+size].decode('ascii'))
    if any(body[start+size:]):raise ValueError('其他 MOD 在编辑器支持段内追加了数据，保留原文件')
    if section.PointerToRawData+section.SizeOfRawData!=len(raw):raise ValueError('编辑器支持段后还有外部数据')
    if section.Misc_VirtualSize!=start+size:raise ValueError('编辑器支持段长度与校验信息不同')
    return pe,section,body,pos,meta

def detach(raw,allow_parent_update=False):
    from growth_runtime import _build_runtime,installed_areas
    from range_runtime import LEGACY_AREA_MAGIC
    pe,section,body,pos,meta=inspect(raw)
    length=meta['length']
    if type(length)!=int or not 0<length<=section.PointerToRawData:raise ValueError('编辑器补丁原始长度无效')
    base=bytearray(raw[:length])
    for off,value in meta['undo']:
        if type(off)!=int:raise ValueError('补丁还原位置无效')
        value=bytes.fromhex(value)
        if off<0 or off+len(value)>length:raise ValueError('补丁还原位置越界')
        base[off:off+len(value)]=value
    from growth_runtime import _restore_parent
    base=_restore_parent(raw,meta);certify_parent(base)
    options={'area_only':b'MJHAREA208\0' in body,'areas':installed_areas(raw,base),
             'legacy':LEGACY_AREA_MAGIC in body}
    from recruitment_runtime import installed as installed_recruitment
    recruitment=installed_recruitment(raw,base)
    if recruitment:options['recruitment']=recruitment
    from interaction_unlock import MAGIC as INTERACTION_MAGIC
    if INTERACTION_MAGIC in raw[len(base):]:options['interactions']=True
    from pet_battle_runtime import MAGIC as PET_MAGIC
    if PET_MAGIC in body:options['pets']=True
    from six_attrs_runtime import MAGIC as SIX_MAGIC
    if SIX_MAGIC in raw[len(base):]:
        options['six_attrs']=True
        from six_attrs_points import installed_bootstrap,MAGIC as POINTS_MAGIC
        if POINTS_MAGIC in raw[len(base):]:options['six_bootstrap']=installed_bootstrap(raw,base)
        else:options['six_legacy']=True
    from attribute_uncap import MAGIC as UNCAP_MAGIC,DAMAGE_MAGIC
    if UNCAP_MAGIC in body:options['attribute_uncap']=True
    if DAMAGE_MAGIC in body:options['damage_uncap']=True
    from chest_autoloot import MAGIC as CHEST_MAGIC
    if CHEST_MAGIC in body:options['chest_autoloot']=True
    from role_breakthrough_runtime import MAGIC as BT_MAGIC,SUSPENDED_MAGIC as BT_OFF_MAGIC
    if BT_MAGIC in body:options['role_breakthrough']=True
    if BT_OFF_MAGIC in body:options['role_breakthrough']=2
    from role_breakthrough_runtime import SYNC_MAGIC,MOBILE_MAGIC
    legacy_bt=(True if SYNC_MAGIC not in body else '2315') if options.get('role_breakthrough') and MOBILE_MAGIC not in body else False
    expected=_build_runtime(base,**options,role_breakthrough_legacy=legacy_bt)
    _,expected_section,expected_body,expected_pos,expected_meta=inspect(expected)
    if body[:pos]!=expected_body[:expected_pos] or meta['undo']!=expected_meta['undo']:
        raise ValueError('编辑器补丁代码或还原记录被修改，保留原文件')
    if section.VirtualAddress!=expected_section.VirtualAddress or section.PointerToRawData!=expected_section.PointerToRawData:
        raise ValueError('编辑器支持段位置被修改')
    # Both normal detachment and MOD restoration must validate sizes against
    # the installed metadata. JSON spelling/length is not executable code and
    # can cross an alignment boundary even when all code and undo bytes match.
    align=lambda value,size:(value+size-1)//size*size
    raw_size=align(section.Misc_VirtualSize,pe.OPTIONAL_HEADER.FileAlignment)
    header=struct.pack('<8sIIIIIIHHI',b'.mjhgr',section.Misc_VirtualSize,
                       section.VirtualAddress,raw_size,section.PointerToRawData,0,0,0,0,0x60000020)
    if raw[section.get_file_offset():section.get_file_offset()+40]!=header:
        raise ValueError('编辑器支持段表头已被其他补丁修改，已保留原文件')
    import pefile
    parent_pe=pefile.PE(data=base,fast_load=True)
    opt=pe.OPTIONAL_HEADER.get_file_offset()
    derived_headers={opt+4:struct.pack('<I',parent_pe.OPTIONAL_HEADER.SizeOfCode+raw_size),
                     opt+56:struct.pack('<I',align(section.VirtualAddress+section.Misc_VirtualSize,pe.OPTIONAL_HEADER.SectionAlignment))}
    for off,value in meta['undo']:
        # Section virtual size depends on metadata size; it is checked above.
        if off==section.get_file_offset():continue
        size=len(bytes.fromhex(value))
        wanted=derived_headers.get(off,expected[off:off+size])
        if raw[off:off+size]!=wanted:
            kind='运行库表头校验不一致' if off in derived_headers or off==opt+64 else '编辑器补丁入口被覆盖'
            raise ValueError(kind+'：'+hex(off)+'；已保留原文件，请先用暗影兼容补丁 V1.0.1 检查已安装的暗影，退出游戏后重新读取目录')
    if not allow_parent_update and meta.get('external_parent_sha256') and meta['external_parent_sha256']!=sha(base):
        raise ValueError('外部基础运行库在安装支持后又发生变化')
    return base,options

def reattach(raw,options):
    from growth_runtime import _build_runtime
    certify_parent(raw)
    out=_build_runtime(raw,**options)
    restored,_=detach(out)
    if restored!=raw:raise ValueError('恢复编辑器支持的回读验证失败')
    return out

def plan(root,restore=False):
    root=Path(root).resolve();path=root/DLL;receipt=root/RECEIPT
    before=path.read_bytes();old=receipt.read_bytes() if receipt.exists() else None
    if restore:
        from shadow_runtime import ready,detected
        existing=None
        try:parent,existing=detach(before,allow_parent_update=True)
        except ValueError:parent=before
        if old is None or json.loads(old).get('state')=='restored':
            if not detected(root) or not ready(root):raise ValueError('没有待完成的安装准备；已安装暗影请退出游戏后重新读取目录，由独立补丁恢复支持，无需先还原所有修改')
            doc={'version':1,'root':str(root),'options':existing or {},'state':'restored'}
            # A certified big-map MOD no longer needs the legacy standalone
            # installer. Attach only missing editor support in this transaction.
            from bigmap_profile import race_parent
            after=reattach(parent,existing or {}) if race_parent(parent) else before
        else:
            doc=json.loads(old)
            if doc.get('state')!='prepared' or Path(doc.get('root','')).resolve()!=root:raise ValueError('准备记录不属于本次安装')
            options=dict(doc['options'])
            if existing is not None:
                # Reading resources can already have installed the standalone
                # bridge. Merge its active features instead of appending twice.
                for key,value in existing.items():
                    if isinstance(value,bool):
                        options[key]=(bool(options.get(key)) and value) if key=='area_only' else bool(options.get(key)) or value
                    elif key=='role_breakthrough' and type(value)is int and value in (1,2):
                        options[key]=value
                    elif isinstance(value,(list,tuple)):
                        merged=list(options.get(key,()))
                        for item in value:
                            if item not in merged:merged.append(item)
                        options[key]=merged
                    else:raise ValueError('未知运行库功能选项：'+key)
            after=reattach(parent,options);doc['options']=options
        doc.update(state='restored',external_sha256=sha(parent),supported_sha256=sha(after))
        label='恢复编辑器计算支持'
    else:
        if old and json.loads(old).get('state')=='prepared':raise ValueError('已有待完成的安装准备，请安装 MOD 后恢复支持')
        after,options=detach(before)
        doc={'version':1,'root':str(root),'state':'prepared','options':options,
             'before_sha256':sha(before),'prepared_sha256':sha(after)}
        label='准备安装外部MOD'
    payloads={path:after};originals={path:before,receipt:old}
    # The role transaction has its own outer client section. Detach only that
    # section for an external install; keep pet and martial-limit options.
    client=root/'DreamRivakes_Data/Plugins/ClientDll.dll'
    if client.is_file():
        from role_breakthrough_client import detach as detach_role,patch as patch_role
        current=client.read_bytes();parent,active=detach_role(current)
        if restore:
            from shadow_bigmap import repair_legacy_client
            repaired=repair_legacy_client(parent)
            if repaired!=parent:payloads[client]=repaired;originals[client]=current;parent=repaired
        if not restore and active:
            payloads[client]=parent;originals[client]=current;doc['role_breakthrough_client']=True
        elif restore and doc.get('role_breakthrough_client'):
            payloads[client]=patch_role(parent,True);originals[client]=current
    from shadow_loader_repair import plan as loader_plan
    lp,lo,lr,ln,reads=loader_plan(root,restore)
    payloads.update(lp);originals.update(reads);originals.update(lo)
    payloads[receipt]=json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8')
    return payloads,originals,label

def certified_transition(before,after):
    try:
        base,_=detach(before)
        if base==after:return True
    except Exception:pass
    try:
        base,_=detach(after)
        return base==before
    except Exception:return False
