"""Typed mobile dependencies. Unknown/missing native functionality is never stubbed."""
from object_bundle import references as common_references

# Literal IDs consumed by the named native operators, in addition to expression IDs.
LITERALS={
 380:{2:'SkillEffect'},
 384:{2:'Martial'},385:{2:'Buff'},386:{2:'Martial'},387:{2:'Buff'},390:{2:'Buff'},391:{2:'Clan'},
 398:{2:'Buff'},399:{2:'Buff'},421:{1:'Buff'},423:{2:'Martial',3:'Skill'},
 434:{2:'Buff'},448:{2:'Buff'},461:{1:'SkillEffect'},498:{},501:{},504:{1:'Buff'},
 526:{2:'Martial'},536:{2:'Martial'},558:{2:'Martial'},
}

def links(table,row,enums):
    result=list(common_references(table,row,enums))
    if table=='Condition':
        field,target={185:('CondArg2','Gift'),193:('CondArg1','Martial')}.get(row.get('CondType'),(None,None))
        if field and str(row.get(field,'')).isdecimal() and int(row[field])>0:
            result.append(([field],target,int(row[field])))
    if table=='SkillEffect':
        literals=dict(LITERALS.get(row['Name'],{}))
        if row['Name']==498 and row.get('EventArg1') in ([1,0],[2,0]):
            literals[3]='Skill' if row['EventArg1'][0]==1 else 'Martial'
        for n,target in literals.items():
            field='EventArg'+str(n);v=row.get(field,[])
            if len(v)==2 and v[0]>0 and v[1]==0:result.append(([field,0],target,v[0]))
    # Preserve order, and remove duplicate links from the ordinary packet rules.
    out=[];seen=set()
    for path,target,value in result:
        k=(tuple(path),target,value)
        if k not in seen:out.append((path,target,value));seen.add(k)
    return out

def expression_literal_links(row,lookup):
    """The same ID may be held in a constant-expression node instead of inline."""
    kinds=dict(LITERALS.get(row.get('Name'),{}))
    if row.get('Name')==498 and row.get('EventArg1') in ([1,0],[2,0]):
        kinds[3]='Skill' if row['EventArg1'][0]==1 else 'Martial'
    result=[]
    for n,target in kinds.items():
        arg=row.get('EventArg'+str(n),[])
        if len(arg)!=2 or not arg[1]:continue
        child=lookup(arg[1]);value=child.get('EventArg1',[])
        if child.get('Name')==0 and len(value)==2 and value[0]>0 and value[1]==0:
            result.append((arg[1],target,value[0]))
    return result



