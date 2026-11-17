"""Translate the matching mobile pet rows to the PC's retained four slots."""
import json
from codec import encoded,fields,numeric_list

def mobile_rows():
    from engine import DATA_ROOT
    source=json.loads((DATA_ROOT/'pet_mobile_data.json').read_text('utf8'))
    result={}
    for key,data in source.items():
        row={k:v for k,v in data.items() if k not in ('Attrs','IsHide','LimitTime')}
        row['Chain']=list(row.get('Chain',{}).values())
        for n,attr in data['Attrs'].items():
            kind=attr['PetAttrType'];n=int(n)
            if kind>10:raise ValueError('当前 PC 运行库不支持该手游宠物特性')
            if kind==1:v1,v2=attr['AttrType'],0
            elif kind==2:v1,v2=attr['Integer'],attr['AttrType']
            elif kind in (3,8):v1,v2=attr['Integer'],attr['PetBuffType']
            elif kind==4:v1,v2=attr['DepartEnumType'],attr['AttrType']
            else:v1,v2=attr['Integer'],0
            row.update({f'Attr{n}':kind,f'Attr{n}Value1':v1,f'Attr{n}Value2':v2,
                        f'Attr{n}Init':attr['BaseValue'],f'Attr{n}Grow':attr['GrowValue'],
                        f'Attr{n}Level':attr['UnlockLevel']})
            if n==1:row['Attr1Value2']=''
        result[int(key)]=row
    return result

def row_bytes(row):
    data=b''.join(encoded(i,row.get(k,0)) for i,k in ((1,'BaseID'),(2,'NameID'),(3,'Rank'),(4,'ArtID'),(6,'cardItem1'),(7,'cardItem2')))
    data+=numeric_list(5,row['Chain'])
    for n in range(1,5):
        start=8+(n-1)*5
        data+=encoded(start,row[f'Attr{n}'])+encoded(start+1,row[f'Attr{n}Value1'])
        # Only Attr1Value2 is a protobuf string. Slots 2--4 are enum integers;
        # writing length-delimited text silently leaves their native values at 0.
        data+=encoded(start+2,row['Attr1Value2'].encode('ascii'),2) if n==1 else encoded(start+2,row[f'Attr{n}Value2'])
        # Real combat consumes the flat damage bonus as an ordinary integer.
        # The separate martial power-preview formula divides by 10000 and must
        # not dictate the pet's stored combat unit.
        data+=encoded(start+3,row[f'Attr{n}Init'])+encoded(start+4,row[f'Attr{n}Grow'])
        data+=encoded(27+n,row[f'Attr{n}Level'])
    data+=b''.join(encoded(i,row.get(k,0)) for i,k in ((32,'DescID'),(33,'BuffID'),(34,'InitialNum'),(35,'growNum'),(36,'itemTypeID')))
    return data

def binary(raw):
    from martial_editor import indexed_rows
    rows,index=indexed_rows(raw);mobile=mobile_rows()
    if not set(mobile).issubset(rows):raise ValueError('当前游戏缺少预期的原生宠物记录')
    for ident,row in mobile.items():rows[ident]=row_bytes(row)
    return numeric_list(1,index)+b''.join(encoded(2,rows[i],2) for i in sorted(rows))+b''.join(f.raw for f in fields(raw) if f.number not in (1,2))

def lua_table():
    def lua(v):
        if isinstance(v,list):return '{'+','.join(lua(x) for x in v)+'}'
        if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
        return str(v)
    rows=mobile_rows()
    return 'return {\n'+''.join('['+str(i)+']={'+','.join(k+'='+lua(v) for k,v in r.items())+'},\n' for i,r in sorted(rows.items()))+'}\n'
