"""Materialize different owner-specific growth values without sharing a clone."""
import copy,json
from object_bundle import key

def contextualize(packet,reused):
    by_owner=packet['extras'].get('independent_growth_by_martial',{})
    if not by_owner:return
    nodes=packet['nodes'];edges=packet['edges'];variants={};next_id=1680000000
    legacy=packet['extras'].setdefault('independent_growth',{})
    # Unreferenced legacy values must not alter a reused/shared source clause.
    legacy.clear()
    for token,node in list(nodes.items()):
        if node['table']!='Martial' or token in reused:continue
        values=by_owner.get(str(node['id']),{})
        for index,cid in enumerate(node['row'].get('GrowProIDs',[])):
            selected={str(slot):values[f'{cid}:{slot}'] for slot in (1,2) if f'{cid}:{slot}' in values}
            if not selected:continue
            original=key('MartialItem',cid)
            shape=(cid,json.dumps(selected,sort_keys=True,separators=(',',':')))
            replacement=variants.get(shape)
            if replacement is None:
                prior=[v for (source,_),v in variants.items() if source==cid]
                if original not in reused and not prior:replacement=cid
                else:
                    while key('MartialItem',next_id) in nodes:next_id+=1
                    replacement=next_id;next_id+=1
                    new=key('MartialItem',replacement)
                    nodes[new]=copy.deepcopy(nodes[original]);nodes[new]['id']=replacement
                    nodes[new]['row']['BaseID']=replacement;edges[new]=copy.deepcopy(edges[original])
                variants[shape]=replacement
                for slot,value in selected.items():legacy[f'{replacement}:{slot}']=value
            node['row']['GrowProIDs'][index]=replacement
            for edge in edges[token]:
                if edge['path']==['GrowProIDs',index]:edge['target']=key('MartialItem',replacement)
