"""Character drafts, native variants and synchronized, backed-up table plans."""
import copy, hashlib, io, json, random, re, unicodedata
from contextlib import contextmanager
from pathlib import Path
from PIL import Image, ImageOps
from codec import decode
from client_config import Assets, enum_values, lua_rows, literal
from engine import SCHEMAS, clean
from martial_editor import indexed_rows, patch_table, patch_lua_rows, LANG_RE
from language_routing import next_id, resource_for
from role_locations import RoleLocations, install_placement

SLOTS={'Weapon':('武器',{9,10,11,12,27,28,29}),
       'Artifacts':('神器',{14}), 'Clothes':('衣服',{3}), 'Shoe':('鞋子',{4}),
       'Ornaments':('饰品',{5}), 'KungfuBook':('秘籍',{15}), 'Horse':('坐骑',{7})}
RANKS={1:'白',2:'绿',3:'蓝',4:'紫',5:'橙',6:'金',7:'暗金'}
EDIT_TABLES=('Role','RoleAttr','RoleModel','NpcEvolute','Language','Task','TaskEdge','TaskEvent','Behavior','Story','RoleTitle')
PORTRAIT_DIR=Path('ModProject/GameProject/Mod_MJH/Source/Other/role_editor')
ATTR_LABELS=dict(zip(
    ['Strength','Agility','Power','Constitution','Energy','Comprehension','FistMastery','KnifeMastery','LegMastery','SwordMastery','SoulMastery','HealingMastery','StickMastery','NeedleMastery','HP','MP','Speed','HittingPer','CritsPer','CritsFactor','MartialATK','Defense','QuanFaATK','DaoFaATK','TuiFaATK','JianFaATK','NeiGongATK','YiShuATK','QiMenATK','AnQiATK','HPRecover','MPRecover','MingZhongZhi','ShanBiZhi','BaoJiZhi','BaoJiDiKang','LianJiZhi','LianJiDiKang','FanJiZhi','PoZhaoZhi','BaoShangZhi','MissPer','CritsResistPer','ThornsPer','ComboPer','DoubleHitPer','AtkResistPer','HitBackPer','ReboundRate','BrokenDefPer','MultipleHit','MoveScope','KungfuLimit'],
    ['力道','灵巧','内劲','体质','精力','悟性','拳掌精通','刀法精通','腿法精通','剑法精通','内功精通','医术精通','奇门精通','暗器精通','生命','真气','速度','命中率','暴击率','暴伤倍率','武学攻击','防御','拳掌攻击','刀法攻击','腿法攻击','剑法攻击','内功攻击','医术攻击','奇门攻击','暗器攻击','生命恢复','真气恢复','命中值','闪避值','暴击值','暴击抵抗','连击值','连击抵抗','反击值','破招值','暴伤值','闪避率','暴击抵抗率','反伤率','连击率','双击率','攻击抵抗率','反击率','反弹率','破防率','多重攻击','移动范围','武学数量上限']))

def name_key(value):return unicodedata.normalize('NFKC',clean(value)).casefold()

def prepare_portrait(source,role_id,layout=None):
    source=Path(source)
    if source.stat().st_size>20*1024*1024:raise ValueError('立绘图片不能超过 20 MB')
    with Image.open(source) as im:
        if im.width*im.height>20000000:raise ValueError('立绘不能超过 2000 万像素')
        im=ImageOps.exif_transpose(im).convert('RGBA')
        if layout is None:im.thumbnail((4096,4096),Image.Resampling.LANCZOS)
        if layout is not None:
            from role_portrait import compose
            im=compose(im,layout)
        out=io.BytesIO();im.save(out,format='PNG');raw=out.getvalue()
    filename=f'{role_id}_{hashlib.sha256(raw).hexdigest()[:16]}.png'
    return '#role_editor/'+filename,PORTRAIT_DIR/filename,raw

class RoleLibrary:
    def __init__(self,root):
        self.root=Path(root).resolve();self.assets_path=self.root/'DreamRivakes_Data/resources.assets'
        raw=self.assets_path.read_bytes();self.assets=Assets(raw);self.originals={self.assets_path:raw}
        self.enums=enum_values(self.assets.script('common.lua'))|enum_values(self.assets.script('Enum.lua'))
        self.tables={};self.changes={n:{} for n in EDIT_TABLES};self.sources={n:{} for n in EDIT_TABLES}
        self.mod_warnings=[]
        from client_shards import prepare,merge
        prepare(self)
        self.resources={};self.locations={};self.overrides={};self.own_jsons={};self.files={}
        for name in (*EDIT_TABLES,'Item','Martial','City','Map','Gift','RoleWishQuest'):
            path=self.root/'TableData'/(name+'.bytes');raw=path.read_bytes();self.originals[path]=raw
            if name=='Language':
                from read_cache import native_language
                self.tables[name]={i:dict(row) for i,row in native_language(raw)}
            else:self.tables[name]={i:decode(r,name,SCHEMAS) for i,r in indexed_rows(raw)[0].items()}
            native_rows=copy.deepcopy(self.tables[name])
            pattern=r'Language\d+\.lua' if name=='Language' else re.escape(name)+r'\d*\.lua'
            resources=sorted(n for n in self.assets.scripts if re.fullmatch(pattern,n))
            if not resources:raise ValueError('客户端缺少 '+name+' 表')
            self.resources[name]=resources;self.locations[name]={};self.overrides[name]={}
            for resource in resources:
                text=self.assets.script(resource);self.enums.update(enum_values(text))
                if name=='Language':
                    from read_cache import language_script
                    rows={i:{'BaseID':i,'Ch_Text':v} for i,v in language_script(text)}
                else:rows=lua_rows(text,name,self.enums)
                merge(self,name,resource,rows)
            client_rows=copy.deepcopy(self.tables[name])
            directory=self.root/'ModProject/GameProject/Mod_MJH/Json';own=directory/(name+'_role_editor.json');self.own_jsons[name]=own
            for path in sorted(directory.glob(name+'_*.json')):
                raw=path.read_bytes();self.originals[path]=raw
                from mod_rows import read_rows
                rows=read_rows(raw,name,SCHEMAS,self.mod_warnings,path.name)
                from editor_data_repair import role_rows,remember
                if name=='Role':rows=role_rows(self,path,rows,native_rows)
                if path==own:remember(self,name,rows,native_rows,client_rows)
                for row in rows:
                    row=copy.deepcopy(row);ident=int(row['BaseID'])
                    if name=='Language' and 'Text' in row:row['Ch_Text']=row.pop('Text')
                    self.tables[name].setdefault(ident,{}).update(row)
                    if path!=own:self.overrides[name].setdefault(ident,[]).append(path.name)
        self.meta_path=self.root/'装备编辑器配置/人物编辑.json'
        raw=self.meta_path.read_bytes() if self.meta_path.exists() else None;self.originals[self.meta_path]=raw
        self.meta=json.loads(raw.decode('utf8')) if raw else {};self.meta_before=copy.deepcopy(self.meta)
        runtime=self.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
        if runtime.exists():self.originals[runtime]=runtime.read_bytes()
        retired=self.root/'装备编辑器配置/武学安全编号迁移.json'
        retired_raw=retired.read_bytes() if retired.exists() else None;self.originals[retired]=retired_raw
        self.retired_martials=set(map(int,json.loads(retired_raw.decode('utf8')))) if retired_raw else set()
        self.compat_notes=[]
        from editor_data_repair import finish
        finish(self)
        from shadow_compat import prepare_routes
        prepare_routes(self)
        self.baseline=copy.deepcopy({n:self.tables[n] for n in EDIT_TABLES})
        self.group_roles()
        self.places=RoleLocations(self)
        self.load_clans()
        from role_placement_repair import pending
        self.placement_repair_pending=pending(self)
        from role_dependency_repair import inspect
        self.dependency_repairs,dependency_reads=inspect(self)
        self.dependency_paths=set(dependency_reads)
        for path,before in dependency_reads.items():self.originals.setdefault(path,before)

    def load_clans(self):
        self.clans={0:'无所属门派'}
        # Only names are needed from Clan; membership is Role.Clan.
        if 'Clan.lua' in self.assets.scripts:
            for ident,name in re.findall(r'\[(\d+)\]\s*=\s*\{[^\r\n]*?\bNameID\s*=\s*(\d+)',self.assets.script('Clan.lua')):
                if int(ident):self.clans[int(ident)]=clean(self.text(int(name))) or f'门派 {ident}'
        directory=self.root/'ModProject/GameProject/Mod_MJH/Json'
        from mod_rows import read_rows
        for path in sorted(directory.glob('Clan_*.json')):
            try:raw=path.read_bytes()
            except OSError as error:
                self.mod_warnings.append(f'{path.name}：已跳过无法读取的门派配置（{error}）');continue
            self.originals[path]=raw
            for row in read_rows(raw,'Clan',SCHEMAS,self.mod_warnings,path.name):
                name=row.get('NameID')
                if isinstance(name,bool) or not isinstance(name,int) or name<0:
                    self.mod_warnings.append(f'{path.name} 门派 {row["BaseID"]}：已跳过无效 NameID');continue
                self.clans[row['BaseID']]=clean(self.text(name)) or f'门派 {row["BaseID"]}'
        for row in self.tables['Role'].values():
            clan=row.get('Clan',0)
            if isinstance(clan,int) and not isinstance(clan,bool):
                self.clans.setdefault(clan,f'未知门派 {clan}（原配置编号）')

    def text(self,ident):return self.tables['Language'].get(ident,{}).get('Ch_Text','')
    def group_roles(self):
        self.roles={}
        for ident,row in self.tables['Role'].items():self.roles.setdefault(row['RoleID'],[]).append(ident)
        for ids in self.roles.values():ids.sort(key=lambda i:self.tables['Role'][i].get('Index',0))
    def row(self,rid):return self.tables['Role'][self.roles[rid][0]]
    def name(self,rid):
        r=self.row(rid)
        return clean(self.text(r.get('NameID',0)) or self.text(r.get('SurnameID',0))+self.text(r.get('GivennameID',0))) or f'未命名人物 {rid}'
    def city(self,rid):
        rows=[r for r in self.tables['NpcEvolute'].values() if r.get('RoleID')==rid]
        return rows[0].get('CityID',0) if rows else self.row(rid).get('EvoInitCity',0)
    def modified(self):
        from model_texture import binding_runtime_pending
        from recruitment_runtime import pending
        from role_animation import pending as animation_pending
        from mobile_models import runtime_pending
        return bool(getattr(self,'dependency_repairs',{})) or bool(getattr(self,'placement_repair_pending',False)) or bool(getattr(self,'client_repairs',{})) or any(self.changes.values()) or self.meta!=self.meta_before or bool(self.files) or binding_runtime_pending(self) or pending(self) or animation_pending(self) or runtime_pending(self)
    @contextmanager
    def edit(self):
        before=copy.deepcopy((self.tables,self.changes,self.sources,self.meta,self.files))
        try:yield
        except Exception:
            self.tables,self.changes,self.sources,self.meta,self.files=before;self.group_roles();raise
    def new_id(self,name,start=1600000000):
        if name=='RoleModel':
            from role_model_ids import new_id
            return new_id(self)
        if name=='Language':return next_id(self,start)
        return max(start,max((i for i in self.tables[name] if i>=start),default=start-1)+1)
    def set(self,name,ident,delta):
        if self.overrides[name].get(ident):raise ValueError(f'{name} {ident} 被其他模组覆盖：'+','.join(self.overrides[name][ident]))
        row={**self.tables[name].get(ident,decode(b'',name,SCHEMAS)),**copy.deepcopy(delta),'BaseID':ident}
        if row==self.tables[name].get(ident):return
        self.tables[name][ident]=row;self.changes[name].setdefault(ident,{}).update(copy.deepcopy(delta));self.changes[name][ident]['BaseID']=ident
    def clone(self,name,source):
        ident=self.new_id(name);self.sources[name][ident]=source;self.set(name,ident,self.tables[name][source]);return ident
    def set_text(self,text):
        ident=self.new_id('Language');self.set('Language',ident,{'Ch_Text':text});return ident
    def candidates(self,slot,rank):
        return [i for i,r in self.tables['Item'].items() if r.get('ItemType') in SLOTS[slot][1] and r.get('Rank')==rank and (slot=='KungfuBook' or 1 in r.get('Feature',[]))]
    def options(self,rid):
        if str(rid) in self.meta:
            s=copy.deepcopy(self.meta[str(rid)]['settings']);s.setdefault('location_path',[])
            s.setdefault('clan',self.row(rid).get('Clan',0));s.setdefault('chat','')
            from role_traits import defaults
            return defaults(self,rid,s)
        r=self.row(rid);art=self.tables['RoleModel'].get(r.get('ArtID'),{})
        from role_traits import defaults
        return defaults(self,rid,dict(name=self.name(rid),city=self.city(rid),clan=r.get('Clan',0),location_path=[],level=r.get('Level',1),
                    kungfu=list(zip(r.get('Kungfu',[]),r.get('KungfuLevel',[]))),
                    equipment={k:{'mode':'item','id':r.get(k,0)} for k in SLOTS},
                    attrs={k:v for k,v in self.tables['RoleAttr'].get(r.get('AttributeID'),{}).items() if k!='BaseID'},
                    chat='',mute=True,empty_bag=True,portrait=art.get('Drawing',''),model_source=r.get('ArtID')))
    def validate(self,rid,settings):
        from role_chat import validate_chat
        from role_portrait import validate_layout
        validate_chat(settings.get('chat',''));validate_layout(settings.get('portrait_layout',{}))
        from role_head import validate as validate_head
        validate_head(settings.get('head_layout',{}))
        if not isinstance(settings.get('head',''),str) or len(settings.get('head',''))>512 or '\x00' in settings.get('head',''):raise ValueError('头像资源配置无效')
        from role_traits import validate
        validate(self,settings)
        name=clean(settings['name'])
        if not name or len(name)>64:raise ValueError('人物名字须为 1～64 个字符')
        if any(c in settings['name'] for c in ('\n','\r','\t','<','>')):raise ValueError('人物名字不能包含换行、制表符或格式标签')
        clan=settings.get('clan',self.row(rid).get('Clan',0) if rid in self.roles else 0)
        if isinstance(clan,bool) or not isinstance(clan,int) or clan not in self.clans:raise ValueError('请选择有效的所属门派')
        if settings.get('model_source') not in self.tables['RoleModel']:raise ValueError('请选择有效的人物模型')
        from model_texture import validate_binding
        validate_binding(self,settings)
        from mobile_models import validate as validate_mobile
        validate_mobile(self,settings)
        if not 1<=settings['level']<=1000:raise ValueError('人物等级范围为 1～1000')
        ids=[]
        for mid,level in settings['kungfu']:
            if mid not in self.tables['Martial']:raise ValueError('武学不存在：'+str(mid))
            if mid in ids:raise ValueError('同一人物的武学不能重复')
            if type(level) is not int or not 1<=level<2147483648:raise ValueError('武学等级须为正整数（不超过存储范围 2147483647）')
            ids.append(mid)
        for slot,spec in settings['equipment'].items():
            if slot not in SLOTS:raise ValueError('装备部位无效')
            if spec['mode']=='random':
                if spec.get('rank') not in RANKS or not self.candidates(slot,spec['rank']):raise ValueError(SLOTS[slot][0]+'没有所选品质的装备')
            elif spec['mode']=='item':
                ident=spec.get('id',0)
                if ident and (ident not in self.tables['Item'] or self.tables['Item'][ident].get('ItemType') not in SLOTS[slot][1]):raise ValueError('所选装备不属于 '+SLOTS[slot][0])
            else:raise ValueError('装备选择方式无效')
        for key,value in settings['attrs'].items():
            if key not in SCHEMAS['RoleAttr'] or key=='BaseID' or not isinstance(value,int) or not 0<=value<2147483648:raise ValueError('属性数值无效：'+key)
        return name
    def create(self,template,settings,portrait_source=None,head_source=None):
        from role_traits import defaults,safe_wishes
        settings=defaults(self,template,copy.deepcopy(settings));settings['preserve_location']=False;self.validate(None,settings)
        wishes=safe_wishes(self)
        source=self.roles[template][0];ident=self.clone('Role',source)
        used=set(self.roles);rid=max(1700000000,max((i for i in used if i>=1700000000),default=1699999999)+1)
        self.set('Role',ident,{'RoleID':rid,'Index':0,'IndexNum':1,'GenNum':1,'NoRandom':1,
                             'WishQuestID':wishes,'RelationID':[],'RelationDisposition':[],'RelationDescID':[],
                             'MarryRole':0,'BroAndSisRole':[],'Father':0,'Mother':0,'Children':[],
                             'BabyTemplate':0,'IsWishline':0,'EvoCondi':0,'EvoType':0,'KillCond':0,
                             'ForbbidLeaveTag':0,'TeamCondition':0,'ExtraGiftPool':0})
        self.group_roles();self.update(rid,settings,portrait_source,template=template,head_source=head_source);return rid
    def update(self,rid,settings,portrait_source=None,template=None,head_source=None,texture_source=None):
        from role_traits import defaults,independent_title
        settings=defaults(self,rid,copy.deepcopy(settings));settings.setdefault('clan',self.row(rid).get('Clan',0))
        settings['name']=self.validate(rid,settings)
        settings['title']=clean(settings['title'])
        original_settings=self.options(rid);r=copy.deepcopy(self.row(rid));original_name=self.name(rid)
        previous=self.meta.get(str(rid),{});actual=copy.deepcopy(original_settings)
        original_art=self.tables['RoleModel'].get(r.get('ArtID'),{})
        actual['mute']=not any(r.get(k) for k in ('hurtSound','helloSound','dieSound','BattleAudio')) and not any(original_art.get(k) for k in ('HelloSound','OpenAudio','BattleAudio'))
        actual['empty_bag']=not r.get('Bag')
        before=previous.get('before',self.snapshot(rid,actual))
        if portrait_source:
            portrait,path,raw=prepare_portrait(portrait_source,rid,settings.get('portrait_layout'));path=self.root/path
            self.originals.setdefault(path,path.read_bytes() if path.exists() else None);self.files[path]=raw;settings['portrait']=portrait
        if head_source:
            from role_head import prepare as prepare_head
            head,path,raw=prepare_head(head_source,rid,settings.get('head_layout',{}));path=self.root/path
            self.originals.setdefault(path,path.read_bytes() if path.exists() else None);self.files[path]=raw;settings['head']=head
        attr=r.get('AttributeID');art=r.get('ArtID')
        if attr not in self.tables['RoleAttr'] or art not in self.tables['RoleModel']:raise ValueError('模板缺少有效的属性或模型配置，请选择其他模板')
        if settings['attrs']!={k:v for k,v in self.tables['RoleAttr'][attr].items() if k!='BaseID'}:
            if not previous.get('owned_attr'):attr=self.clone('RoleAttr',attr)
            self.set('RoleAttr',attr,settings['attrs'])
        art_delta={}
        donor=self.tables['RoleModel'][settings['model_source']]
        for key in ('ModelID','Model','Texture','Hue','ModelScale','WeaponPos','WeaponScale','InitWeapom'):
            if key in donor:art_delta[key]=copy.deepcopy(donor[key])
        mobile=settings.get('mobile_binding')
        if mobile:
            from mobile_models import stage,PREFIX as MOBILE_PREFIX
            stage(self,mobile)
            art_delta.update(Model=MOBILE_PREFIX+mobile['key'],Texture=MOBILE_PREFIX+mobile['key']+'_texture',Hue='')
        binding=settings.get('texture_binding')
        if binding:
            from model_texture import PREFIX,stage_file
            stage_file(self,binding,texture_source)
            art_delta.update(Texture=PREFIX+binding['filename'],Hue='')
        if settings.get('portrait')!=self.tables['RoleModel'][art].get('Drawing'):art_delta.update(Drawing=settings['portrait'],PictureID=0)
        if settings.get('head')!=self.tables['RoleModel'][art].get('Head',''):art_delta.update(Head=settings['head'],PictureID=0)
        if settings['mute']:art_delta.update(HelloSound=0,OpenAudio=0,BattleAudio=0)
        if any(self.tables['RoleModel'][art].get(k)!=v for k,v in art_delta.items()):
            shared=any(row.get('ArtID')==art and row.get('RoleID')!=rid for row in self.tables['Role'].values())
            from role_model_ids import safe as safe_model_id
            if not previous.get('owned_art') or shared or not safe_model_id(art):art=self.clone('RoleModel',art)
            self.set('RoleModel',art,art_delta)
        title_id=independent_title(self,r,settings['title'])
        name_id=r.get('NameID') if settings['name']==original_name and template is None else self.set_text(settings['name'])
        random_slots=[k for k,v in settings['equipment'].items() if v['mode']=='random']
        count=max(len(self.roles[rid]),20 if random_slots else 1)
        while len(self.roles[rid])<count:
            self.clone('Role',self.roles[rid][0]);self.group_roles()
        ids=self.roles[rid];pools={k:self.candidates(k,settings['equipment'][k]['rank']) for k in random_slots}
        for index,ident in enumerate(ids):
            gifts=[i for i in self.tables['Role'][ident].get('Gift',[]) if self.tables['Gift'].get(i,{}).get('GiftType')!=1]+settings['battle_gifts']
            delta=dict(Rank=settings['rank'],TitleID=title_id,Gift=gifts,NameID=name_id,SurnameID=0,GivennameID=0,Prefix='',Postfix='',Level=settings['level'],Clan=settings['clan'],
                       AttributeID=attr,ArtID=art,Kungfu=[i for i,l in settings['kungfu']],KungfuLevel=[l for i,l in settings['kungfu']],
                       EvoInitCity=settings['city'],Index=index,IndexNum=count)
            if settings.get('preserve_location'):delta.pop('EvoInitCity',None)
            if random_slots:delta['NoRandom']=0
            if settings['mute']:delta.update(hurtSound=0,helloSound=0,dieSound=0,BattleAudio=0)
            if settings['empty_bag']:delta['Bag']=[]
            for slot,spec in settings['equipment'].items():
                # Each native Index is a generation candidate, not an extra NPC.
                # Reuse candidates on unrelated edits; save itself never rerolls.
                if spec['mode']=='random':
                    value=self.tables['Role'][ident].get(slot,0)
                    if settings['equipment'].get(slot)!=original_settings['equipment'].get(slot) or value not in pools[slot]:value=random.choice(pools[slot])
                    delta[slot]=value
                else:delta[slot]=spec.get('id',0)
            self.set('Role',ident,delta)
        evos=[i for i,e in self.tables['NpcEvolute'].items() if e.get('RoleID')==rid]
        if settings.get('preserve_location'):pass
        elif not evos:
            evo=self.new_id('NpcEvolute');self.set('NpcEvolute',evo,{'RoleID':rid,'CityID':settings['city'],'IsMove':0,'IsEvolute':1,'IsAllowKilled':1,'IsAllowBigmapMove':0,'EvoluteConditionID':0})
        else:
            for ident in evos:self.set('NpcEvolute',ident,{'CityID':settings['city']})
        position_task=previous.get('position_task') if settings.get('preserve_location') else install_placement(self,rid,settings.get('location_path',[]),previous)
        animation_source=settings['model_source']
        if animation_source==art:
            animation_source=previous.get('animation_source',previous.get('base_art',r['ArtID']))
        fields=previous.get('recruitment_fields',0)
        if settings['kungfu']!=original_settings['kungfu']:fields|=1
        if settings['attrs']!=original_settings['attrs']:fields|=2
        self.meta[str(rid)]=dict(recruitment_fields=fields,art_id=art,animation_source=animation_source,settings=settings,before=before,template=previous.get('template',template),position_task=position_task,
                                base_art=previous.get('base_art',r['ArtID']),
                                owned_attr=previous.get('owned_attr',False) or attr!=r['AttributeID'],
                                owned_art=previous.get('owned_art',False) or art!=r['ArtID'])
    def snapshot(self,rid,settings=None):
        s=settings or self.options(rid);r=self.row(rid);art=self.tables['RoleModel'].get(r.get('ArtID'),{})
        equipment={}
        for slot,spec in s['equipment'].items():
            equipment[SLOTS[slot][0]]=('按品质随机：'+RANKS[spec['rank']] if spec['mode']=='random' else clean(self.tables['Item'].get(spec.get('id'),{}).get('ItemName','')) or '不佩戴')
        try:position=self.places.describe(s['city'],s['location_path']) if s.get('location_path') else (self.text(self.tables['City'].get(s['city'],{}).get('NameID',0)) or str(s['city']))+'（沿用原位置）'
        except (KeyError,ValueError):position='沿用原位置 '+str(s.get('city',0))+' / '+str(s.get('location_path',[]))
        clan=s.get('clan',r.get('Clan',0))
        from role_traits import ROLE_RANKS
        return dict(称号=s.get('title',self.text(r.get('TitleID',0))),品质=ROLE_RANKS.get(s.get('rank',r.get('Rank')),str(r.get('Rank'))),战斗天赋=[clean(self.text(self.tables['Gift'][i].get('NameID',0)))+f' · {i}' for i in s.get('battle_gifts',[])],心愿=list(r.get('WishQuestID',[])),名字=s['name'],位置=position,门派=self.clans.get(clan,f'未知门派 {clan}')+f' · {clan}',
                    闲聊=s.get('chat','') or '使用游戏原有闲聊',等级=s['level'],武学=[self.text(self.tables['Martial'][i]['NameID'])+f' {l}级' for i,l in s['kungfu']],
                    装备=equipment,属性={ATTR_LABELS.get(k,k):v for k,v in s['attrs'].items()},
                    动作绑定=str(r.get('ArtID',0))+' ← '+str(self.meta.get(str(rid),{}).get('animation_source',s.get('model_source',0))),立绘=s.get('portrait',''),队伍头像=s.get('head',art.get('Head','')),模型=self.tables['RoleModel'].get(s.get('model_source'),art).get('Model',''),模型贴图=(s.get('texture_binding') or {}).get('label','模板原贴图'),语音='已去掉' if s['mute'] else '保留原配置',背包='空' if s['empty_bag'] else '保留原配置')
    def logs(self):
        return role_logs(self.meta_before,self.meta,self)
    def plan(self):
        from role_placement_repair import stage as repair_placement
        repair_placement(self)
        from mobile_models import repair_saved_bindings
        repair_saved_bindings(self)
        from role_common_wishes import backfill
        backfill(self)
        from role_model_ids import migrate
        migrate(self)
        payloads={};originals=dict(self.originals)
        directory=self.root/'ModProject/GameProject/Mod_MJH/Json'
        if set(directory.glob('Clan_*.json'))!={p for p in originals if p.parent==directory and p.name.startswith('Clan_')}:
            raise ValueError('门派 MOD 文件列表已变化，请刷新人物缓存后重新编辑')
        for path,raw in originals.items():
            if (path.read_bytes() if path.exists() else None)!=raw:raise ValueError('配置已变化，请重新读取：'+str(path))
        for name in self.tables:
            directory=self.own_jsons[name].parent
            expected={p for p in originals if p.parent==directory and p.name.startswith(name+'_')}
            if set(directory.glob(name+'_*.json'))!=expected:raise ValueError('模组文件列表已变化，请重新读取')
        if not self.modified():return {},originals
        from client_shards import staged
        assetdata=staged(self,originals[self.assets_path])
        for name,changes in self.changes.items():
            if not changes:continue
            for directory in ('TableData','DreamRivakes_Data/StreamingAssets'):
                path=self.root/directory/(name+'.bytes')
                if not path.exists():continue
                originals.setdefault(path,path.read_bytes());payloads[path]=patch_table(originals[path],name,changes,self.sources[name])
            assets=Assets(assetdata)
            if name in assets.scripts:
                _,q,n=assets.scripts[name];assetdata=assets.replace_blob(name,patch_table(assetdata[q+4:q+4+n],name,changes,self.sources[name]))
            grouped={}
            for ident in changes:
                resource=resource_for(self.assets,ident) if name=='Language' else self.locations[name].get(ident,self.resources[name][0])
                from client_shards import targets
                for target in targets(self,name,ident,resource):
                    grouped.setdefault(target,{})[ident]=self.tables[name][ident]['Ch_Text'] if name=='Language' else {k:v for k,v in self.tables[name][ident].items() if v!={}}
            for resource,rows in grouped.items():
                assets=Assets(assetdata);text=patch_lua_rows(assets.script(resource),rows,name=='Language')
                parsed={int(i):literal(v,self.enums) for _,i,v in re.findall(LANG_RE,text)} if name=='Language' else lua_rows(text,name,self.enums)
                if any(parsed.get(i)!=row for i,row in rows.items()):raise ValueError('客户端回读校验失败：'+name)
                assetdata=assets.replace_script(resource,text)
            path=self.own_jsons[name];old=originals.get(path);originals[path]=old
            obj=json.loads(old.decode('utf-8-sig')) if old else {'Items':[]};records={int(r['BaseID']):r for r in __import__('editor_data_repair').json_rows(self,name,obj.get('Items',[]))}
            for ident in changes:
                row=copy.deepcopy({k:v for k,v in self.tables[name][ident].items() if v!={}})
                if name=='Language':row['Text']=row.pop('Ch_Text')
                from editor_data_repair import keep_owned
                if keep_owned(self,name,ident):records[ident]=row
            obj['Items']=list(records.values());payloads[path]=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf8')
        from role_animation import plan_bindings
        from mod_compatibility import attempt
        # An edited appearance without matching hit/switch timings must not be
        # saved as a successful model replacement with this required step skipped.
        assetdata=plan_bindings(self,assetdata)
        if any(r.get('settings',{}).get('head','').startswith('#role_editor/head_mobile_') for r in self.meta.values()):
            from disguise_portraits import patch_loader
            portrait_assets=Assets(assetdata)
            assetdata=attempt(self,'手游头像加载',lambda:portrait_assets.replace_script('ResourcesMgr.lua',patch_loader(portrait_assets.script('ResourcesMgr.lua'))),assetdata)
        from role_roll_portrait import patch_roll
        roll_assets=Assets(assetdata)
        assetdata=attempt(self,'转盘立绘修复',lambda:roll_assets.replace_script('RandomRollUI.lua',patch_roll(roll_assets.script('RandomRollUI.lua'))),assetdata)
        from role_chat import patch_chat
        if any(r.get('settings',{}).get('chat') for r in self.meta.values()) or any(r.get('settings',{}).get('chat') for r in self.meta_before.values()):
            assets=Assets(assetdata)
            assetdata=attempt(self,'闲聊界面同步',lambda:assets.replace_script('SelectUI.lua',patch_chat(assets.script('SelectUI.lua'),self.meta)),assetdata)
        from client_runtime_repair import repair
        # These earlier views retain obsolete whole-resource byte buffers.
        # Their script edits are already reflected in assetdata.
        assets=None;roll_assets=None
        assetdata=repair(assetdata,self.compat_notes if hasattr(self,'compat_notes') else None)
        from model_texture import PREFIX,plan_loader
        if any(row.get('Texture','').startswith(PREFIX) for row in self.tables['RoleModel'].values()):
            assetdata=plan_loader(assetdata)
        from mobile_models import plan_loader as plan_mobile_loader
        assetdata=plan_mobile_loader(self,assetdata)
        payloads[self.assets_path]=assetdata;payloads.update(self.files)
        for rid,record in self.meta.items():
            if int(rid) in self.roles:record['snapshot']=self.snapshot(int(rid),record['settings'])
            else:
                from mod_compatibility import note
                note(self,'当前没有有效人物配置，已跳过旧缓存快照：'+rid)
        payloads[self.meta_path]=json.dumps(self.meta,ensure_ascii=False,indent=2).encode('utf8')
        from recruitment_runtime import plan as plan_recruitment
        plan_recruitment(self,payloads,originals)
        from shadow_compat import route_payloads
        from role_dependency_repair import stage as restore_dependencies
        restore_dependencies(self,payloads,originals)
        return route_payloads(self,payloads,originals)

def role_logs(old,new,lib=None):
    from change_log import entry
    logs=[]
    for rid in old.keys()|new.keys():
        a=old.get(rid);b=new.get(rid)
        if a==b:continue
        prior=(a or {}).get('snapshot') or (b or {}).get('before',{})
        current=lib.snapshot(int(rid),b['settings']) if b and lib else (b or {}).get('snapshot',{})
        name=current.get('名字',prior.get('名字',rid))
        created=b and b.get('template') is not None and a is None
        if created:logs.append(entry('人物',name,'新增人物','以现有人物为模板；'+str(current)))
        elif b is None:logs.append(entry('人物',name,'还原人物配置','撤销人物编辑记录'))
        for key in prior.keys()|current.keys():
            if prior.get(key)==current.get(key) and not created:continue
            av=prior.get(key);bv=current.get(key)
            if isinstance(av,dict) and isinstance(bv,dict):
                for field in av.keys()|bv.keys():
                    if av.get(field)!=bv.get(field) or created:logs.append(entry('人物',name,'修改'+key+'·'+field,f'{av.get(field)} → {bv.get(field)}'))
            else:logs.append(entry('人物',name,'修改'+key,f'{av} → {bv}'))
    return logs
