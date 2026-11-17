"""The native per-level formulas are shared KungfuBase rows, not EffectValue."""
import copy, json, re
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from codec import fields, read_varint, decode
from client_config import Assets, literal
from engine import SCHEMAS
from growth_runtime import MARKER, custom_values

def growth_native(data):
    ids=[];rows=[]
    for f in fields(data):
        if f.number==1:
            if f.wire==2:
                pos=0
                while pos<len(f.value):
                    i,pos=read_varint(f.value,pos);ids.append(i)
            else:ids.append(f.value)
        elif f.number==2:rows.append(f.value)
    if len(ids)!=len(rows) or len(ids)!=len(set(ids)):raise ValueError('成长表索引与记录不一致')
    return dict(zip(ids,rows))

def growth_lua(text,enums):
    default=re.search(r'local KungfuBaseDefault\s*=\s*(\{[^\r\n]+)',text)
    base=literal(default[1],enums)
    return {int(i):{**base,**literal(body.rstrip().rstrip(','),enums)} for i,body in re.findall(r'(?m)^\s*\[(\d+)\]\s*=\s*(\{[^\r\n]+)',text)}

class GrowthDraft:
    def __init__(self,lib):
        mod=lib.root/'ModProject/GameProject'
        if mod.exists() and any(mod.rglob('KungfuBase_*.json')):raise ValueError('检测到其他模组的成长表覆盖，暂不改写共享成长公式')
        self.path=lib.root/'TableData/KungfuBase.bytes';raw=self.path.read_bytes();lib.originals[self.path]=raw
        self.raw=raw;self.native=growth_native(raw);self.rows=growth_lua(lib.assets.script('KungfuBase.lua'),lib.enums);self.changes={}
        self.runtime_path=lib.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
        lib.originals[self.runtime_path]=self.runtime_path.read_bytes()
        for i,r in self.native.items():
            if decode(r,'KungfuBase',SCHEMAS)!=self.rows[i]:raise ValueError('成长表客户端与逻辑表不同，请先同步模组配置')
    def available(self,lib,mid):
        """Only native formula combinations whose role/skill paths are understood."""
        m=lib.tables['Martial'][mid];depart=m['DepartEnum']
        return {i:r for i,r in self.rows.items() if r['IsGrowup']==1 and
                ((r['IsRoleAttr']==1 and r['KfType']==(depart if r['AttrType']==65 else 0)) or
                 (r['IsRoleAttr']==0 and ((r['AttrType']==359 and r['KfType']==depart) or (r['AttrType']==335 and r['KfType']==0))))}
    def actual(self,lib,profile):
        raw=Decimal(profile['raw']);attr=profile['attr']
        if attr==359:
            # GetStaticMartialWeiLiXiShuGrow rounds native values to multiples of ten,
            # then the game's skill UI multiplies by SKILL_SHOW_NUM_RATE=100.
            raw=(raw*Decimal(profile['factor'])/10000/10+Decimal('.5')).to_integral_value(rounding=ROUND_FLOOR)*10
            return raw/100
        percent=lib.percent.get(attr,{})
        if percent.get('PerMyriad')==1:raw/=10000
        if percent.get('ShowAsPercent')==1:raw*=100
        return raw
    def display(self,lib,profile):
        value=self.actual(lib,profile)
        text=f'{value:.1f}' if value==value.quantize(Decimal('.1')) else f'{value.normalize():f}'
        if lib.percent.get(profile['attr'],{}).get('ShowAsPercent')==1:text+='%'
        return ('+' if value>=0 else '')+text
    def encode_actual(self,lib,profile,text):
        desired=Decimal(str(text).strip().rstrip('%'))
        if not desired.is_finite():raise ValueError('请输入有限数值')
        attr=profile['attr']
        if attr==359:
            if desired!=desired.quantize(Decimal('.1')):raise ValueError('游戏威力系数的显示与结算精度为 0.1，请填写例如 6.7')
            if profile['factor']<=0:raise ValueError('当前成长公式不能产生威力系数，请选择有效成长表')
            raw=(desired*100*10000/profile['factor']).to_integral_value(rounding=ROUND_HALF_UP)
        else:
            raw=desired;p=lib.percent.get(attr,{})
            if p.get('ShowAsPercent')==1:raw/=100
            if p.get('PerMyriad')==1:raw*=10000
            if raw!=raw.to_integral_value():raise ValueError('该游戏属性只能使用整数编码；精通请填写整数，百分比最多两位小数')
        raw=int(raw)
        if not -(1<<31)<=raw<(1<<31):raise ValueError('每级成长超出游戏整数范围')
        if self.actual(lib,{**profile,'raw':raw})!=desired:raise ValueError('该数值无法按现有游戏公式精确表示，请调整数值')
        return raw
    def option_profile(self,lib,mid,ident,grade=2):
        if ident not in self.available(lib,mid):raise ValueError('所选成长表不适用于当前武学类别')
        r=self.rows[ident];m=lib.tables['Martial'][mid];rank=m['Rank']
        factor=next((x['GrowFactor'] for x in lib.tables['MatGrowUPAttrGrade'].values() if x['Grade']==grade),None) if r['AttrType']==359 else 10000
        if factor is None:raise ValueError('没有对应的游戏成长公式')
        affected=[]
        kind=7 if r['IsRoleAttr'] else 9
        for i,x in lib.tables['Martial'].items():
            if x['Rank']!=rank or (r['KfType'] and x['DepartEnum']!=r['KfType']):continue
            if any(lib.tables['MartialItem'].get(c,{}).get(f'EffectEnum{s}')==kind and lib.tables['MartialItem'].get(c,{}).get(f'AttrEnum{s}')==r['AttrType'] for c in x.get('GrowProIDs',[]) for s in (1,2)):affected.append(i)
        return {'id':ident,'rank':rank,'attr':r['AttrType'],'factor':factor,'raw':r['RankDatas'][rank],'affected':affected,'grade':grade,'kind':kind}
    def profile(self,lib,mid,key,index,slot):
        m=lib.tables['Martial'][mid];c=lib.tables['MartialItem'][m[key][index]]
        kind=c.get('EffectEnum'+str(slot));attr=c.get('AttrEnum'+str(slot),0)
        if kind not in (7,9):raise ValueError('请选择“每级”成长属性阶段')
        depart=m['DepartEnum'];rank=m['Rank'];role=int(kind==7)
        # Native KungfuBase keys: attr | depart<<10 | role<<14 | grow<<15.
        candidates=[(i,r) for i,r in self.rows.items() if r['AttrType']==attr and r['IsRoleAttr']==role and r['IsGrowup']==1 and r['KfType'] in (0,depart)]
        exact=[x for x in candidates if x[1]['KfType']==depart]
        if len(exact or candidates)!=1:raise ValueError('没有唯一的原生成长公式，不能仅凭说明修改')
        ident,r=(exact or candidates)[0];grade=c.get('Grade'+str(slot),0) or 2
        fixed=custom_values(c,slot)
        if fixed:
            return {'id':ident,'rank':rank,'attr':attr,'factor':10000,'raw':fixed[0],'affected':[mid],
                    'grade':grade,'kind':kind,'independent':True}
        factor=next((r['GrowFactor'] for r in lib.tables['MatGrowUPAttrGrade'].values() if r['Grade']==grade),10000) if kind==9 else 10000
        affected=[i for i,x in lib.tables['Martial'].items() if x['Rank']==rank and (r['KfType']==0 or x['DepartEnum']==depart)]
        return {'id':ident,'rank':rank,'attr':attr,'factor':factor,'raw':r['RankDatas'][rank],'affected':affected,'grade':grade}
    def change(self,profile,value):
        if not isinstance(value,int) or not -(1<<31)<=value<(1<<31):raise ValueError('成长值超出游戏整数范围')
        ident=profile['id'];row=copy.deepcopy(self.rows[ident]);row['RankDatas'][profile['rank']]=value
        self.rows={**self.rows,ident:row};self.changes={**self.changes,ident:row}
    def apply(self,lib,mid,ident,value,reuse_existing=False,selected=None,slot=1):
        """Clone a clause; default values are independent of the shared template."""
        if not reuse_existing:
            from mod_compatibility import require_native
            require_native(lib,'独立每级成长')
        existing=lib.tables['Martial'][mid].get('GrowProIDs',[])
        grade=2
        if selected is not None:
            old=lib.tables['MartialItem'][existing[selected]]
            if old.get('CondID') or old.get(f'MartialFilter{slot}'):raise ValueError('带条件或筛选的成长阶段请沿用原模板')
            grade=old.get(f'Grade{slot}') or 2
        profile=self.option_profile(lib,mid,ident,grade)
        attr=profile['attr'];kind=profile['kind'];n=str(slot)
        for index,cid in enumerate(existing):
            row=lib.tables['MartialItem'][cid]
            for s in (1,2):
                if index==selected and s==slot:continue
                if row.get(f'EffectEnum{s}') in (7,9) and row.get(f'AttrEnum{s}')==attr:raise ValueError('该属性已有每级成长，请选中对应成长阶段修改，避免重复结算')
        if reuse_existing:
            if Decimal(str(value).rstrip('%'))!=self.actual(lib,profile):raise ValueError('引用现有成长时使用模板原值；如需改值，请选择新建独立成长')
            vals=[] if kind==9 else [profile['raw'],0]
        else:
            isolated={**profile,'factor':10000}
            raw=self.encode_actual(lib,isolated,value)
            vals=[raw,MARKER]
            if kind==9 and attr==359 and slot!=1:raise ValueError('每级威力系数请使用第 1 项效果，以兼容游戏武学威力预览')
        delta={f'EffectEnum{n}':kind,f'AttrEnum{n}':attr,f'SkillID{n}':0,f'MartialFilter{n}':0,
               f'Effect{n}Value':vals,f'Grade{n}':grade if kind==9 else 0,'DesID':0}
        if selected is None:
            source=next((i for i,r in lib.tables['MartialItem'].items() if r.get('EffectEnum1')==kind and r.get('AttrEnum1')==attr and not r.get('CondID')),next(iter(lib.tables['MartialItem'])))
            delta.update({'CondID':0,'EffectEnum2':0,'AttrEnum2':0,'SkillID2':0,'MartialFilter2':0,'Effect2Value':[],'Grade2':0})
            index=lib.add_stage(mid,'GrowProIDs',source,delta=delta)
        else:
            index=selected;lib.update_stage(mid,'GrowProIDs',index,delta)
        return index
    def plan(self,lib,assets,payloads,originals):
        from mod_compatibility import native_supported,changed_native_growth,note
        marked=any(custom_values(row,s) for row in lib.changes['MartialItem'].values() for s in (1,2))
        if marked and not native_supported(lib.root):
            if changed_native_growth(lib):
                from mod_compatibility import require_native
                require_native(lib,'独立成长数值修改')
            note(lib,'未改值的已有独立成长词条保持原样，未替换MOD运行库')
            marked=False
        if marked:
            from mod_compatibility import require_native
            require_native(lib,'独立每级成长')
            from growth_runtime import patch_runtime,patch_client
            original=originals[self.runtime_path]
            if self.runtime_path.read_bytes()!=original:raise ValueError('运行库在读取后发生变化，请重新读取')
            payloads[self.runtime_path]=patch_runtime(original)
            a=Assets(assets);assets=a.replace_script('MartialDataManager.lua',patch_client(a.script('MartialDataManager.lua')))
        if not self.changes:return assets
        from martial_editor import encode_field,patch_lua_rows
        mod=lib.root/'ModProject/GameProject'
        if mod.exists() and any(mod.rglob('KungfuBase_*.json')):raise ValueError('成长表被其他模组覆盖，请重新读取并检查模组')
        from codec import encoded
        def patch_native(raw):
            rows=growth_native(raw);ids=list(rows);out=[];pos=0
            for f in fields(raw):
                if f.number!=2:out.append(f.raw);continue
                ident=ids[pos];pos+=1
                if ident not in self.changes:out.append(f.raw);continue
                delta=self.changes[ident];keep=b''.join(x.raw for x in fields(f.value) if x.number!=5)
                new=keep+encode_field('RankDatas',delta['RankDatas'],'KungfuBase')
                if decode(new,'KungfuBase',SCHEMAS)!=delta:raise ValueError('成长表回读校验失败')
                out.append(encoded(2,new,2))
            return b''.join(out)
        for folder in ('TableData','DreamRivakes_Data/StreamingAssets'):
            p=lib.root/folder/'KungfuBase.bytes'
            if p.exists():
                raw=originals.get(p,p.read_bytes());originals[p]=raw;payloads[p]=patch_native(raw)
        a=Assets(assets)
        if 'KungfuBase' in a.scripts:
            _,q,n=a.scripts['KungfuBase'];assets=a.replace_blob('KungfuBase',patch_native(a.data[q+4:q+4+n]))
        a=Assets(assets);text=patch_lua_rows(a.script('KungfuBase.lua'),self.changes)
        parsed=growth_lua(text,lib.enums)
        if any(parsed[i]!=r for i,r in self.changes.items()):raise ValueError('客户端成长公式回读校验失败')
        return a.replace_script('KungfuBase.lua',text)
