"""Independent titles and searchable existing battle talents."""
from engine import clean

ROLE_RANKS={1:'白',2:'绿',3:'蓝',4:'紫',5:'橙',6:'金',7:'暗金',8:'多彩',9:'三档暗金'}
COMMON_WISHES=(195,190)

def title_name(lib,ident):
    row=lib.tables.get('RoleTitle',{}).get(ident,{})
    if not row:return ''
    return clean(lib.text(row.get('TitleID',0)) or row.get('Name',''))

def battle_choices(lib,query=''):
    words=clean(query).casefold().split();result=[]
    for ident,row in lib.tables.get('Gift',{}).items():
        if row.get('GiftType')!=1:continue
        name=clean(lib.text(row.get('NameID',0)));desc=clean(lib.text(row.get('DescID',0)))
        search=f'{ident} {name} {desc}'.casefold()
        if all(word in search for word in words):result.append((ident,name,desc))
    return sorted(result,key=lambda x:(x[1],x[0]))

def defaults(lib,rid,settings):
    row=lib.row(rid)
    settings.setdefault('head',lib.tables.get('RoleModel',{}).get(row.get('ArtID'),{}).get('Head',''))
    settings.setdefault('head_layout',{})
    settings.setdefault('rank',row.get('Rank',4))
    settings.setdefault('title',title_name(lib,row.get('TitleID',0)))
    settings.setdefault('battle_gifts',[i for i in row.get('Gift',[]) if lib.tables.get('Gift',{}).get(i,{}).get('GiftType')==1])
    return settings

def validate(lib,settings):
    rank=settings.get('rank')
    if type(rank) is not int or rank not in ROLE_RANKS:raise ValueError('请选择有效的人物品质')
    title=settings.get('title','')
    if not isinstance(title,str) or len(title)>64 or any(c in title for c in '\n\r\t<>'):raise ValueError('称号最多 64 个字符，不能含换行或格式标签')
    gifts=settings.get('battle_gifts',[])
    if not isinstance(gifts,list) or len(set(gifts))!=len(gifts):raise ValueError('战斗天赋不能重复')
    for ident in gifts:
        if type(ident) is not int or lib.tables['Gift'].get(ident,{}).get('GiftType')!=1:raise ValueError('战斗天赋不存在或类型不符：'+str(ident))

def independent_title(lib,row,text):
    text=clean(text);previous=row.get('TitleID',0)
    if text==title_name(lib,previous):return previous
    if not text:return 0
    ident=lib.clone('RoleTitle',previous) if previous in lib.tables['RoleTitle'] else lib.new_id('RoleTitle')
    delta={'TitleID':lib.set_text(text),'Name':text}
    if previous not in lib.tables['RoleTitle']:delta.update(TitleAttr=0,Value=0,TitleRank=1,IsTakenIn=0,RankListID=0)
    lib.set('RoleTitle',ident,delta)
    return ident

def safe_wishes(lib):
    # Native generic chain: 4214 opens treasure quest 4342, then friendship 4193.
    expected={195:('寻物探宝',4214),190:('海内存知己',0)}
    for ident,(name,task) in expected.items():
        row=lib.tables['RoleWishQuest'].get(ident,{})
        if clean(lib.text(row.get('NameID',0)) or row.get('Name',''))!=name or row.get('TaskID',0)!=task:
            raise ValueError('通用情缘任务链不匹配，请刷新人物配置：'+name)
    if 4214 not in lib.tables['Task'] or lib.tables['Task'][4214].get('RootState')!=421401:
        raise ValueError('缺少原生通用情缘任务链，未修改人物')
    return list(COMMON_WISHES)
