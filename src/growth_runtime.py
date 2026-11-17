"""Version-checked native support for independent per-clause growth values.

The two existing growth dispatch calls are redirected only for a two-value
clause carrying our marker. All native clauses retain their original calls.
No files are written here; the editor's ordinary backup transaction installs it.
"""
import hashlib
import json
import struct

MARKER=-2147482007
ORIGINAL_SHA='55f3bca229e971431b27731e4bdc91d7879e2252ba48d763cb0b64f192dbc0aa'
SECTION=b'.mjhgr'
SIGNATURE=b'MJHGROW202\0'
META_MAGIC=b'MJHGRMETA'
HOOKS=((0x4e780d,0x4e8750,bytes.fromhex('e83e0f0000')),
       (0x4e79ae,0x4e8840,bytes.fromhex('e88d0e0000')))

def _expand_headers(raw):
    """Create room for one PE header without moving virtual addresses."""
    import pefile
    pe=pefile.PE(data=raw,fast_load=True)
    header=pe.sections[-1].get_file_offset()+40
    if header+40<=pe.OPTIONAL_HEADER.SizeOfHeaders and not any(raw[header:header+40]):return raw,None
    first=min(s.PointerToRawData for s in pe.sections if s.SizeOfRawData)
    if first!=pe.OPTIONAL_HEADER.SizeOfHeaders or header>first or any(raw[header:first]):
        raise ValueError('运行库表头包含未知数据，不能扩展')
    if pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size or pe.FILE_HEADER.PointerToSymbolTable:
        raise ValueError('运行库含签名或符号文件偏移，暂不扩展表头')
    amount=((header+40-first+pe.OPTIONAL_HEADER.FileAlignment-1)//pe.OPTIONAL_HEADER.FileAlignment)*pe.OPTIONAL_HEADER.FileAlignment
    out=bytearray(raw[:first]+bytes(amount)+raw[first:])
    for section in pe.sections:
        off=section.get_file_offset()
        for rel in (20,24,28):
            value=struct.unpack_from('<I',raw,off+rel)[0]
            if value:
                if value<first:raise ValueError('运行库节文件偏移无效')
                struct.pack_into('<I',out,off+rel,value+amount)
    struct.pack_into('<I',out,pe.OPTIONAL_HEADER.get_file_offset()+60,first+amount)
    debug=pe.OPTIONAL_HEADER.DATA_DIRECTORY[6]
    if debug.Size:
        if debug.Size%28:raise ValueError('调试目录结构无效')
        off=pe.get_offset_from_rva(debug.VirtualAddress)
        if off<first:raise ValueError('调试目录位于未知表头数据中')
        for pos in range(off,off+debug.Size,28):
            value=struct.unpack_from('<I',raw,pos+24)[0]
            if value:
                if value<first:raise ValueError('调试数据文件偏移无效')
                struct.pack_into('<I',out,pos+amount+24,value+amount)
    return bytes(out),{'offset':first,'amount':amount,'headers':raw[:first].hex(),
                       'debug':[[pos+24,raw[pos+24:pos+28].hex()] for pos in range(off,off+debug.Size,28)] if debug.Size else []}

def _restore_parent(raw,metadata):
    before=bytearray(raw[:metadata['length']])
    for offset,value in metadata['undo']:
        value=bytes.fromhex(value)
        if offset<0 or offset+len(value)>len(before):raise ValueError('独立成长校验范围错误')
        before[offset:offset+len(value)]=value
    shift=metadata.get('header_shift')
    if shift:
        offset=shift['offset'];amount=shift['amount'];headers=bytes.fromhex(shift['headers'])
        if offset!=len(headers) or amount<=0 or offset+amount>len(before):raise ValueError('表头恢复记录无效')
        del before[offset:offset+amount]
        before[:offset]=headers
        for pos,value in shift.get('debug',[]):before[pos:pos+4]=bytes.fromhex(value)
    return bytes(before)

def custom_values(row,slot):
    vals=row.get(f'Effect{slot}Value',[])
    return vals if row.get(f'EffectEnum{slot}') in (7,9) and len(vals)==2 and vals[1]==MARKER else None

def _helper(rva,hook,target):
    code=bytearray();fixups=[];labels={}
    def emit(data):code.extend(data)
    def relative(op,target):
        emit(op);emit(struct.pack('<i',target-(rva+len(code)+4)))
    def label_jump(name):
        emit(b'\x0f\x85');fixups.append((len(code),name));emit(bytes(4))
    # Preserve incoming arguments and provide the Windows x64 shadow space.
    emit(bytes.fromhex('51 52 41 50 41 51 48 83 ec 20'))
    emit(bytes.fromhex('48 8b 8c 24 b0 01 00 00'))
    relative(b'\xe8',0x23cb00) # repeated-field count
    emit(bytes.fromhex('83 f8 02'));label_jump('fallback')
    emit(bytes.fromhex('48 8b 8c 24 b0 01 00 00 ba 01 00 00 00'))
    relative(b'\xe8',0x5b9a80) # repeated-field element 1
    emit(b'\x81\x38'+struct.pack('<i',MARKER));label_jump('fallback')
    emit(bytes.fromhex('8b 84 24 90 00 00 00')) # already loaded element 0
    unwind=bytes.fromhex('48 83 c4 20 41 59 41 58 5a 59')
    emit(unwind);relative(b'\xe9',hook+5)
    labels['fallback']=len(code)
    emit(unwind);relative(b'\xe8',target);relative(b'\xe9',hook+5)
    for offset,name in fixups:struct.pack_into('<i',code,offset,labels[name]-(offset+4))
    return bytes(code)

def _original(raw):
    from bigmap_profile import race_parent
    if race_parent(raw):return raw
    if hashlib.sha256(raw).hexdigest()==ORIGINAL_SHA:return raw
    import pefile
    pe=pefile.PE(data=raw,fast_load=True)
    sections=[s for s in pe.sections if s.Name.rstrip(b'\0')==SECTION]
    if len(sections)!=1:raise ValueError('当前游戏版本未校验独立每级成长，请使用现有成长引用或恢复原版运行库')
    body=sections[0].get_data()
    if not body.startswith(SIGNATURE):raise ValueError('独立成长运行库标识不正确')
    pos=body.find(META_MAGIC)
    if pos<0:raise ValueError('独立成长运行库校验信息缺失')
    size=struct.unpack_from('<I',body,pos+len(META_MAGIC))[0]
    start=pos+len(META_MAGIC)+4
    metadata=json.loads(body[start:start+size].decode('ascii'))
    before=_restore_parent(raw,metadata)
    digest=hashlib.sha256(before).hexdigest()
    if digest!=ORIGINAL_SHA and not race_parent(before):
        if metadata.get('external_parent_sha256')!=digest:raise ValueError('运行库存在其他修改，停止安装独立成长支持')
        from external_runtime import certify_parent
        certify_parent(bytes(before))
    return bytes(before)

def _build_runtime(original,area_only=False,areas=(),legacy=False,recruitment=(),interactions=False,six_attrs=False,six_legacy=False,six_bootstrap=(),pets=False,attribute_uncap=False,damage_uncap=False,chest_autoloot=False,role_breakthrough=False,role_breakthrough_legacy=False):
    from bigmap_profile import race_parent
    if race_parent(original):
        from bigmap_growth_runtime import _build_runtime as build
        return build(original,area_only,areas,legacy,recruitment,interactions,six_attrs,six_legacy,six_bootstrap,pets,attribute_uncap,damage_uncap,chest_autoloot,role_breakthrough,role_breakthrough_legacy)
    if role_breakthrough:raise ValueError("角色突破目前只认证大地图运行库")
    import pefile
    parent=original
    original,header_shift=_expand_headers(original)
    pe=pefile.PE(data=original,fast_load=True)
    if hashlib.sha256(parent).hexdigest()!=ORIGINAL_SHA:
        from shadow_runtime import certify_features
        certify_features(original,pe,six_attrs)
    align=lambda n,a:(n+a-1)//a*a
    header=pe.sections[-1].get_file_offset()+40
    if header+40>pe.OPTIONAL_HEADER.SizeOfHeaders or any(original[header:header+40]):raise ValueError('运行库没有可用扩展表头')
    if pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size:raise ValueError('运行库包含签名，无法安装独立成长支持')
    rva=pe.OPTIONAL_HEADER.SizeOfImage
    raw_offset=align(len(original),pe.OPTIONAL_HEADER.FileAlignment)
    body=bytearray(SIGNATURE);body.extend(bytes((-len(body))%16))
    undo=[];output=bytearray(original)
    def overwrite(offset,value):
        undo.append((offset,original[offset:offset+len(value)].hex()))
        output[offset:offset+len(value)]=value
    for hook,target,expected in HOOKS:
        offset=pe.get_offset_from_rva(hook)
        if original[offset:offset+5]!=expected:raise ValueError('游戏成长计算入口版本不一致')
        entry=rva+len(body);body.extend(_helper(entry,hook,target))
        overwrite(offset,b'\xe9'+struct.pack('<i',entry-(hook+5)))
        body.extend(bytes((-len(body))%16))
    if area_only:
        from martial_ranges import AREA_START,AREA_END
        hook=0x7ef5b7;target=0x7bd680
        offset=pe.get_offset_from_rva(hook)
        expected=b'\xe8'+struct.pack('<i',target-(hook+5))
        if original[offset:offset+5]!=expected:raise ValueError('技能范围计算入口版本不一致')
        body.extend(b'MJHAREA208\0');body.extend(bytes((-len(body))%16))
        entry=rva+len(body)
        # Arguments are untouched. Native ranges tail-call the original cast setter;
        # editor area-only ranges return without clearing either cast vector.
        code=b'\x81\xfa'+struct.pack('<i',AREA_START)+b'\x7c\x09'
        code+=b'\x81\xfa'+struct.pack('<i',AREA_END)+b'\x7d\x01\xc3'
        code+=b'\xe9'+struct.pack('<i',target-(entry+len(code)+5))
        body.extend(code);body.extend(bytes((-len(body))%16))
        overwrite(offset,b'\xe8'+struct.pack('<i',entry-(hook+5)))
    if areas:
        from range_runtime import AREA_MAGIC,LEGACY_AREA_MAGIC,HIT_GRID_RVA,HIT_GRID_PREFIX,hit_grid_helper,legacy_hit_grid_helper,validate_areas
        magic=LEGACY_AREA_MAGIC if legacy else AREA_MAGIC
        helper=legacy_hit_grid_helper if legacy else hit_grid_helper
        areas=validate_areas(areas)
        if not area_only:raise ValueError('命名技能范围需要独立作用范围支持')
        offset=pe.get_offset_from_rva(HIT_GRID_RVA)
        if original[offset:offset+5]!=HIT_GRID_PREFIX:raise ValueError('实际技能寻敌入口版本不一致')
        data=json.dumps(areas,separators=(',',':')).encode('ascii')
        body.extend(magic+struct.pack('<I',len(data))+data);body.extend(bytes((-len(body))%16))
        trampoline=rva+len(body)
        body.extend(HIT_GRID_PREFIX+b'\xe9'+struct.pack('<i',HIT_GRID_RVA+5-(trampoline+10)))
        body.extend(bytes((-len(body))%16));entry=rva+len(body)
        body.extend(helper(entry,trampoline,areas));body.extend(bytes((-len(body))%16))
        overwrite(offset,b'\xe9'+struct.pack('<i',entry-(HIT_GRID_RVA+5)))
    from recruitment_runtime import append_support
    append_support(original,pe,rva,body,overwrite,recruitment)
    from interaction_unlock import append_support as append_interactions
    append_interactions(original,pe,rva,body,overwrite,interactions)
    if six_legacy:from six_attrs_runtime_v229 import append_support as append_six_attrs
    else:from six_attrs_runtime import append_support as append_six_attrs
    if six_legacy:append_six_attrs(original,pe,rva,body,overwrite,six_attrs)
    else:append_six_attrs(original,pe,rva,body,overwrite,six_attrs,six_bootstrap)
    from pet_battle_runtime import append_support as append_pets
    append_pets(original,pe,rva,body,overwrite,pets)
    from attribute_uncap import append_support as append_uncap
    append_uncap(original,pe,rva,body,overwrite,attribute_uncap,damage_uncap)
    from chest_autoloot import append_support as append_chest
    append_chest(original,pe,rva,body,overwrite,chest_autoloot)
    from role_breakthrough_runtime import append_support as append_role_breakthrough
    append_role_breakthrough(original,pe,rva,body,overwrite,role_breakthrough,role_breakthrough_legacy)
    optional=pe.OPTIONAL_HEADER.get_file_offset()
    overwrite(pe.FILE_HEADER.get_file_offset()+2,struct.pack('<H',pe.FILE_HEADER.NumberOfSections+1))
    # Metadata length does not depend on the numeric header values.
    for off,width in ((header,40),(optional+4,4),(optional+56,4),(optional+64,4)):
        undo.append((off,original[off:off+width].hex()))
    metadata={'length':len(original),'undo':undo}
    if header_shift:metadata['header_shift']=header_shift
    if hashlib.sha256(parent).hexdigest()!=ORIGINAL_SHA:
        from external_runtime import certify_parent
        certify_parent(parent)
        metadata['external_parent_sha256']=hashlib.sha256(parent).hexdigest()
    metadata=json.dumps(metadata,separators=(',',':')).encode('ascii')
    body.extend(META_MAGIC+struct.pack('<I',len(metadata))+metadata)
    raw_size=align(len(body),pe.OPTIONAL_HEADER.FileAlignment)
    section=struct.pack('<8sIIIIIIHHI',SECTION,len(body),rva,raw_size,raw_offset,0,0,0,0,0x60000020)
    output[header:header+40]=section
    struct.pack_into('<I',output,optional+4,pe.OPTIONAL_HEADER.SizeOfCode+raw_size)
    struct.pack_into('<I',output,optional+56,align(rva+len(body),pe.OPTIONAL_HEADER.SectionAlignment))
    struct.pack_into('<I',output,optional+64,0)
    output.extend(bytes(raw_offset-len(output)));output.extend(body);output.extend(bytes(raw_size-len(body)))
    result=bytes(output)
    return result

def installed_areas(raw,original=None):
    from range_runtime import AREA_MAGIC,LEGACY_AREA_MAGIC,validate_areas
    original=_original(raw) if original is None else original
    pos=raw.find(AREA_MAGIC,len(original))
    if pos<0:pos=raw.find(LEGACY_AREA_MAGIC,len(original))
    if pos<0:return []
    start=pos+len(AREA_MAGIC)
    size=struct.unpack_from('<I',raw,start)[0]
    return validate_areas(json.loads(raw[start+4:start+4+size].decode('ascii')))

def patch_runtime(raw,area_only=None,areas=None,recruitment=None,interactions=None,six_attrs=None,six_bootstrap=None,pets=None,attribute_uncap=None,damage_uncap=None,chest_autoloot=None,role_breakthrough=None):
    original=_original(raw)
    installed=b'MJHAREA208\0' in raw[len(original):]
    previous=installed_areas(raw,original)
    from range_runtime import LEGACY_AREA_MAGIC
    legacy=LEGACY_AREA_MAGIC in raw[len(original):]
    from recruitment_runtime import installed as installed_recruitment
    prior_recruitment=installed_recruitment(raw,original)
    from interaction_unlock import MAGIC as INTERACTION_MAGIC
    prior_interactions=INTERACTION_MAGIC in raw[len(original):]
    from six_attrs_runtime import MAGIC as SIX_MAGIC
    prior_six=SIX_MAGIC in raw[len(original):]
    from six_attrs_points import installed_bootstrap
    prior_bootstrap=installed_bootstrap(raw,original)
    from pet_battle_runtime import MAGIC as PET_MAGIC
    prior_pets=PET_MAGIC in raw[len(original):]
    from attribute_uncap import MAGIC as UNCAP_MAGIC,DAMAGE_MAGIC
    prior_uncap=UNCAP_MAGIC in raw[len(original):]
    prior_damage=DAMAGE_MAGIC in raw[len(original):]
    from chest_autoloot import MAGIC as CHEST_MAGIC
    prior_chest=CHEST_MAGIC in raw[len(original):]
    from role_breakthrough_runtime import MAGIC as BT_MAGIC,SUSPENDED_MAGIC as BT_OFF_MAGIC
    prior_breakthrough=2 if BT_OFF_MAGIC in raw[len(original):] else BT_MAGIC in raw[len(original):]
    if raw!=original and raw!=_build_runtime(original,installed,previous,legacy=legacy,recruitment=prior_recruitment,interactions=prior_interactions,six_attrs=prior_six,six_bootstrap=prior_bootstrap,pets=prior_pets,attribute_uncap=prior_uncap,damage_uncap=prior_damage,chest_autoloot=prior_chest,role_breakthrough=prior_breakthrough):
        if not prior_six or raw!=_build_runtime(original,installed,previous,legacy=legacy,recruitment=prior_recruitment,interactions=prior_interactions,six_attrs=prior_six,six_legacy=True,pets=prior_pets,attribute_uncap=prior_uncap,damage_uncap=prior_damage,chest_autoloot=prior_chest,role_breakthrough=prior_breakthrough):
            # Older valid metadata may have a different serialized length.
            # detach checks exact owned code, hooks, undo records, parent hash
            # and body-derived PE sizes before allowing canonical regeneration.
            from external_runtime import detach
            verified,_=detach(raw)
            if verified!=original:raise ValueError('已安装的运行库支持被修改，请先恢复运行库')
    use_area=installed if area_only is None else area_only
    return _build_runtime(original,use_area,(previous if areas is None else areas) if use_area else (),recruitment=prior_recruitment if recruitment is None else recruitment,interactions=prior_interactions if interactions is None else interactions,six_attrs=prior_six if six_attrs is None else six_attrs,six_bootstrap=prior_bootstrap if six_bootstrap is None else six_bootstrap,pets=prior_pets if pets is None else pets,attribute_uncap=prior_uncap if attribute_uncap is None else attribute_uncap,damage_uncap=prior_damage if damage_uncap is None else damage_uncap,chest_autoloot=prior_chest if chest_autoloot is None else chest_autoloot,role_breakthrough=prior_breakthrough if role_breakthrough is None else role_breakthrough)

def supported_patch(raw):
    try:
        original=_original(raw)
        if raw==original:return False
        patch_runtime(raw) # Validate legacy images too, allowing an upgrade.
        return True
    except Exception:return False

def patch_client(text):
    """Display and static power preview use the same stored per-level value."""
    if '-- MJH independent growth V2.0.2' in text:return text
    anchor='        local ret = sAttr'
    if text.count(anchor)!=1:raise ValueError('客户端成长说明入口不一致')
    insert=f'''        -- MJH independent growth V2.0.2
        if (effectEnum == MartialItemEffect.MTT_JUESECHENGZHANG or effectEnum == MartialItemEffect.MTT_WUXUECHENGZHANG) and args and #args == 2 and args[2] == {MARKER} then
            iValue = args[1]
            if effectEnum == MartialItemEffect.MTT_WUXUECHENGZHANG and attrEnum == AttrType.MP_WEILIXISHU then iValue = iValue * SKILL_SHOW_NUM_RATE end
        end
'''
    text=text.replace(anchor,insert+anchor)
    anchor='local iValue = math.floor(gradeGrowFactor * rankGrowFactor * BATTLE_CONFIG / 10 + 0.5) * 10'
    if text.count(anchor)!=1:raise ValueError('客户端每级威力计算入口不一致')
    addition=f'''
    for _, cid in ipairs(staticMartialData.GrowProIDs or {{}}) do
        local clause = GetTableData("MartialItem", cid)
        if clause then
            for slot = 1, 2 do
                local values = clause["Effect" .. slot .. "Value"]
                if clause["EffectEnum" .. slot] == MartialItemEffect.MTT_WUXUECHENGZHANG and clause["AttrEnum" .. slot] == AttrType.MP_WEILIXISHU and values and #values == 2 and values[2] == {MARKER} then iValue = values[1] end
            end
        end
    end'''
    return text.replace(anchor,anchor+addition)
