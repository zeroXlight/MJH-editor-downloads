"""Install verified, namespaced Windows particle resources per restored art."""
from pathlib import Path
import copy,hashlib,io,json,re,zipfile

STATE='装备编辑器配置/手游武学特效恢复.json'
def stage(store,payloads,installed,results):
    for mid,stem,title in (('10821','tianji','天玑五转'),('12916','wuxiang','无相剑诀')):
        if mid in installed:_stage_bundle(store,payloads,results,stem,title)

def _stage_bundle(store,payloads,results,stem,title):
    from engine import DATA_ROOT
    import UnityPy
    from bigmap_profile import race_image
    bigmap=race_image(store.read(store.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'))
    from bigmap_profile import november_parent,november15_parent
    from growth_runtime import _original
    november=bigmap and november_parent(_original(store.read(store.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll')))
    november15=bigmap and november15_parent(_original(store.read(store.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll')))
    filename=('nov15_' if november15 else 'nov5_' if november else 'bigmap_' if bigmap else 'mobile_')+stem+'_effects.zip'
    raw=(DATA_ROOT/'ui_assets'/filename).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        manifest=json.loads(z.read('manifest.json'));files={n:z.read(n) for n in manifest['files']}
    for name,data in files.items():
        if not re.fullmatch(r'mjh_'+re.escape(stem)+r'_[a-f0-9]{32}\.assets',name):raise ValueError('手游特效资源路径无效')
        if hashlib.sha256(data).hexdigest()!=manifest['files'][name]:raise ValueError('手游特效资源校验失败：'+name)
    assets=store.assets
    for native in manifest['native_shaders']:
        obj=next((o for o in assets.objects if o['id']==native['path_id'] and o['kind']==48),None)
        if not obj or hashlib.sha256(assets.data[assets.start+obj['off']:assets.start+obj['off']+obj['length']]).hexdigest()!=native['sha256']:
            raise ValueError('当前PC粒子着色器与验证版本不同，未安装手游特效；请保留当前资源以便核对。')
    manager=store.root/'DreamRivakes_Data/globalgamemanagers';original=store.read(manager)
    if not original:raise ValueError('游戏缺少globalgamemanagers，无法核对特效资源索引')
    current=payloads.get(manager,original);env=UnityPy.load(current);sf=env.file
    if sf.unity_version!='2018.4.12f1' or int(sf.target_platform)!=19:raise ValueError('当前Unity资源版本未通过手游特效兼容验证')
    resource=next(o for o in sf.objects.values() if o.type.name=='ResourceManager');tree=resource.read_typetree()
    before_entries=copy.deepcopy(tree['m_Container']);entries={n.lower():p for n,p in before_entries}
    before_objects={i:o.get_raw_data() for i,o in sf.objects.items() if i!=resource.path_id}
    before_externals=[e.path for e in sf.externals];changed=False
    for name,entry in manifest['roots'].items():
        old=entries.get(name.lower())
        if old:
            actual=sf.externals[old['m_FileID']-1].path if old['m_FileID'] else ''
            if actual!=entry['file'] or old['m_PathID']!=entry['path_id']:raise ValueError('手游特效独立资源名已被其他修改占用：'+name)
            continue
        index=next((i+1 for i,e in enumerate(sf.externals) if e.path==entry['file']),None)
        if index is None:
            ext=copy.copy(sf.externals[0]);ext.path=entry['file'];ext.guid=bytes(16);ext.type=0;ext.temp_empty=''
            sf.externals.append(ext);index=len(sf.externals)
        tree['m_Container'].append((name,{'m_FileID':index,'m_PathID':entry['path_id']}));changed=True
    if changed:
        resource.save_typetree(tree);updated=sf.save();check=UnityPy.load(updated).file
        if [e.path for e in check.externals][:len(before_externals)]!=before_externals:raise ValueError('特效资源索引保留校验失败')
        if any(o.get_raw_data()!=before_objects[i] for i,o in check.objects.items() if i!=resource.path_id):raise ValueError('特效安装改变了其他资源对象，已停止')
        after=check.objects[resource.path_id].read_typetree()['m_Container']
        if after[:len(before_entries)]!=before_entries:raise ValueError('特效安装改变了原有资源目录，已停止')
        payloads[manager]=updated
    added=0
    for name,data in files.items():
        path=store.root/'DreamRivakes_Data'/name;before=store.read(path);actual=payloads.get(path,before)
        if actual is not None and actual!=data:
            verified_old=False
            if bigmap:
                for prefix in (('mobile_','bigmap_','nov5_') if november15 else ('mobile_','bigmap_') if november else ('mobile_',)):
                    with zipfile.ZipFile(DATA_ROOT/'ui_assets'/(prefix+stem+'_effects.zip')) as old:
                        verified_old|=name in old.namelist() and old.read(name)==actual
            if not verified_old:raise ValueError('手游特效文件已被其他修改改变，未覆盖：'+name)
        if actual!=data:payloads[path]=data;added+=1
    state={'version':1,'source_apk_sha256':manifest['source_apk_sha256'],'roots':manifest['roots'],'files':manifest['files'],
        'material_adaptation':'FX/Particle → PC DB_SHADER/Particles/Particles_Unlit_DB；不是手游着色器的逐像素还原。'}
    path=store.root/(STATE if stem=='tianji' else '装备编辑器配置/手游无相剑诀特效恢复.json');before=store.read(path);data=json.dumps(state,ensure_ascii=False,indent=2).encode('utf8')
    if payloads.get(path,before)!=data:payloads[path]=data
    if changed or added:results.append('补入'+title+'的'+str(len(manifest['roots']))+'个手游特效与'+str(len(files))+'个独立资源文件；保留原资源目录。材质适配PC粒子着色器，动态溶解/扭曲与手游可能不同。')
