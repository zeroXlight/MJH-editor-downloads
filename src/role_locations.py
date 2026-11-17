"""Full map paths and one-shot native NPC placement, without save-file edits."""
from engine import clean

AUTO='仅指定城市（由游戏安排具体落点）'

class RoleLocations:
    def __init__(self,library):
        self.lib=library;self.by_city={};self.paths={}
        maps=library.tables['Map']
        for city,row in library.tables['City'].items():
            root=row.get('EnterMapID',0);roots=[root]
            # The original city entry stays 60; the village story switches it to 140.
            if root==60 and 140 in maps:roots.append(140)
            choices={AUTO:()}
            def walk(ident,path):
                if ident not in maps or ident in path:return
                path=(*path,ident);r=maps[ident]
                if len(path)>1 and r.get('BuildingImg'):
                    label=self.describe(city,path);choices[label]=path
                    self.paths[(city,path)]=label
                for child in r.get('ChildIDList',[]):walk(child,path)
            for root in roots:walk(root,())
            self.by_city[city]=choices
    def describe(self,city,path):
        name=clean(self.lib.text(self.lib.tables['City'][city].get('NameID')))
        names=[]
        for index,ident in enumerate(path):
            r=self.lib.tables['Map'][ident]
            title=clean(self.lib.text(r.get('BuildingNameID')) or self.lib.text(r.get('NameID'))) or str(ident)
            if index==0:
                title=name
                if ident==60:title+='（正常）'
                elif ident==140:title+='（摧毁后）'
            elif r.get('BuildingType')==self.lib.enums.get('MapBuildingType.BT_DOOR'):title='[通道] '+title
            names.append(f'{title} [地图 {ident}]')
        return ' › '.join(names)
    def validate(self,city,path):
        path=tuple(path or ())
        if path and (city,path) not in self.paths:raise ValueError('具体位置已失效或不属于所选城市，请重新选择完整场景路径')
        return path
    def note(self,city,path):
        if not path:return '只设置城市不会保证出现在某个建筑。要固定落点，请选择下面的具体场景。'
        conditions=[f'地图 {i}：条件 {self.lib.tables["Map"][i]["ShowCondition"]}' for i in path if self.lib.tables['Map'][i].get('ShowCondition')]
        roots={p[0] for c,p in self.paths if c==city and p[-1]==path[-1]}
        shared=' 此建筑地图由多个状态共用；所选状态决定首次放置时机，此后人物仍属于同一建筑地图。' if len(roots)>1 else ''
        return (self.describe(city,path)+'\n人物固定在最后一级建筑卡片，非像素坐标。新周目首次进入所选根场景时放置一次；未开放的剧情场景不会被强行解锁。'+
                (' 场景显示限制：'+'；'.join(conditions)+'。' if conditions else '')+shared)

def install_placement(lib,rid,path,previous):
    """Register standard task callbacks after the requested city scene is entered.

    BET 385 resolves/creates the NPC by template and moves it; BET 386 records
    the unique position. A successful task ends, so revisits don't pull a
    recruited NPC out of the party or re-create a killed NPC.
    """
    owned=previous.get('position_task')
    if not path and not owned:return None
    if not owned:
        owned={name:lib.new_id(name) for name in ('Task','TaskEdge','TaskEvent')}
        first=lib.new_id('Behavior');owned['move']=first;owned['unique']=first+1
    task,edge,event=(owned[n] for n in ('Task','TaskEdge','TaskEvent'))
    lib.set('Task',task,{'RootState':task,'Type':0,'NameID':0})
    callbacks=[]
    if path:
        for key,kind in [('move',385),('unique',386)]:
            lib.set('Behavior',owned[key],{'Type':kind,'Arg1':str(rid),'Arg2':str(path[-1])})
            callbacks.append(owned[key])
        lib.set('TaskEvent',event,{'Event':lib.enums['Event.Event_MapEnter'],'EventArg1':str(path[0])})
    lib.set('TaskEdge',edge,{'StateID':task,'Type':lib.enums['TaskEdgeType.TET_Succeed'],
                           'TaskEventID':event if path else 0,'ConditonSatisfyCallbackIDs':callbacks})
    for ident,row in list(lib.tables['Story'].items()):
        starts=row.get('StartTask',[])
        if task not in starts:lib.set('Story',ident,{'StartTask':[*starts,task]})
    return owned
