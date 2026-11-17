# Generated for the exact certified big-map native build. See native mapping evidence.
"""Point accounting in existing native attribute records, without a save ABI change."""
from pathlib import Path
import base64,json,re,struct,sys
from engine import DATA_ROOT

MAGIC=b'MJHPOINTS2210\0'
BOOT_MAGIC=b'MJHPOINTBOOT2210\0'
SEAL=0x221001

def installed_bootstrap(raw,original):
    at=raw.find(BOOT_MAGIC,len(original))
    if at<0:return ()
    p=at+len(BOOT_MAGIC);n=struct.unpack_from('<I',raw,p)[0]
    if n>1024*1024:raise ValueError('加点迁移数据长度无效')
    return tuple(tuple(int(x) for x in row) for row in json.loads(raw[p+4:p+4+n]))

def append_support(original,pe,rva,body,overwrite,bootstrap=()):
    config=json.loads((DATA_ROOT/'bigmap_six_attrs_points_code.json').read_text('utf8'))
    body.extend(MAGIC);body.extend(bytes(-len(body)%16))
    entry=rva+len(body);code=bytearray(base64.b64decode(config['code']))
    for offset,target in config['relocations']:
        struct.pack_into('<i',code,offset,target-(entry+offset+4))
    data=[]
    for row in bootstrap:
        if len(row)!=16 or any(type(v) is not int or not 0<=v<=0x7fffffff for v in row):raise ValueError('旧版加点迁移记录无效')
        if any(row[10+i]>row[4+i] for i in range(6)):raise ValueError('旧版退点超过基础属性')
        data.append(struct.pack('<16I',*row))
    body.extend(code);body.extend(struct.pack('<I',len(data))+b''.join(data))
    serialized=json.dumps(bootstrap,separators=(',',':')).encode('ascii')
    body.extend(BOOT_MAGIC+struct.pack('<I',len(serialized))+serialized);body.extend(bytes(-len(body)%16))
    at=0x4755a6;offset=pe.get_offset_from_rva(at)
    expected=b'\xe8'+struct.pack('<i',0x72af20-at-5)
    if original[offset:offset+5]!=expected:raise ValueError('原生加点入口被其他修改覆盖')
    overwrite(offset,b'\xe8'+struct.pack('<i',entry-at-5))

def snapshot(raw):
    from feature_save import NativeSave,u32
    save=NativeSave(raw);result={};properties={}
    for r in save.tables[32]:
        if u32(r,36)!=2:continue
        attr=u32(r,32)&65535
        if attr not in (*range(3,9),*range(116,124)):continue
        owner=u32(r,20)
        if attr in properties.setdefault(owner,{}):raise ValueError('角色属性记录重复，停止迁移旧加点')
        properties[owner][attr]=struct.unpack_from('<i',r,24)[0]
    for row in save.tables[21]:
        ident=u32(row,16);attrs=properties.get(ident,{})
        if any(a not in attrs for a in range(3,9)):continue
        result[ident]={'type':u32(row,20),'level':u32(row,36),'points':u32(row,52),
                       'primary':[attrs[a] for a in range(3,9)],'seal':attrs.get(122,0)}
    return result

def migration_candidates(root,reads):
    """Import only an exact historical point/attribute delta; never infer drug gains."""
    root=Path(root);path=root/'Save.sav'
    if not path.is_file():return (),[]
    raw=path.read_bytes();reads[path]=raw
    try:current=snapshot(raw)
    except ValueError:return (),['旧存档布局无法核实；不导入历史加点，新分配点数仍由原生记录。']
    candidates=[]
    for old in [root/'Save.sav.check',root/'Save.sav.checksave',*(root/'SaveFile').rglob('Save.sav')]:
        if not old.is_file():continue
        data=old.read_bytes();reads[old]=data
        try:candidates.append(snapshot(data))
        except ValueError:continue
    # Previous shipped integration records are data-only historical snapshots.
    # Require the recorded full point budget and an exact six-property delta.
    base=Path(sys.executable).parent.parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]
    for old in base.glob('已有装备武学编辑器V2.2.9_*/实机验收记录.txt'):
        data=old.read_bytes();reads[old]=data;text=data.decode('utf8')
        who=re.search(r'OPEN_CHARACTER role=(\d+)',text);points=re.search(r'^POINTS (\d+)$',text,re.M)
        values={int(a):int(v) for a,v in re.findall(r'^ATTR (\d+) [^=\r\n]+=(\d+)$',text,re.M)}
        if not who or not points or any(a not in values for a in range(3,9)):continue
        uid=int(who[1]);now=current.get(uid)
        if now and int(points[1])==5*(now['level']-1):
            candidates.append({uid:{**now,'points':int(points[1]),'primary':[values[a] for a in range(3,9)]}})
    records=[]
    for uid,now in sorted(current.items()):
        if now['seal']==SEAL:continue
        matches=[]
        for previous in candidates:
            old=previous.get(uid)
            if not old or old['type']!=now['type'] or old['level']!=now['level']:continue
            counts=[b-a for a,b in zip(old['primary'],now['primary'])]
            if any(v<0 for v in counts) or sum(counts)<=0 or sum(counts)!=old['points']-now['points']:continue
            matches.append(counts)
        if matches:
            counts=max(matches,key=sum)
            records.append((uid,now['type'],now['level'],now['points'],*now['primary'],*counts))
    return tuple(records),([f'已核实 {len(records)} 名角色的旧版加点；读取后的第一次加点或重置会迁入原生分配记录。'] if records else [])
