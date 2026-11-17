"""Read valid MOD rows independently; never rewrite a broken source document."""
import json, struct

def table_name(path):
    """Use the table prefix, independent of the name of the supplying MOD."""
    from pathlib import Path
    return Path(path).stem.split('_', 1)[0]

def validate_values(row, name, schemas):
    for key, value in row.items():
        spec = schemas.get(name, {}).get(key)
        if not spec: continue  # Keep extension fields verbatim.
        seq = value if spec['label'] == 3 else [value]
        if not isinstance(seq, list): raise ValueError(key + ' 必须是数组')
        for v in seq:
            typ = spec['type']
            if typ == 11:
                if not isinstance(v, dict): raise ValueError(key + ' 必须是结构化记录')
                validate_values(v, spec['type_name'].split('.')[-1], schemas)
            elif typ == 9:
                if not isinstance(v, str): raise ValueError(key + ' 必须是文字')
            elif typ in (1, 2):
                if not isinstance(v, (int, float)) or isinstance(v, bool): raise ValueError(key + ' 数值无效')
            elif typ not in (8, 12):
                if not isinstance(v, int) or isinstance(v, bool): raise ValueError(key + ' 整数无效')

def read_rows(raw, name, schemas, warnings, source):
    try:
        obj=json.loads(raw.decode('utf-8-sig'))
        if not isinstance(obj,dict) or not isinstance(obj.get('Items'),list):raise ValueError('Items 必须是数组')
    except (ValueError,UnicodeError) as error:
        warnings.append(f'{source}：已跳过异常配置（{error}）');return []
    rows=[]
    for index,row in enumerate(obj['Items']):
        try:
            if not isinstance(row,dict):raise ValueError('记录不是对象')
            ident=row['BaseID']
            if isinstance(ident,bool) or not isinstance(ident,int) or ident<=0:raise ValueError('BaseID 无效')
            validate_values(row, name, schemas)
            for key,value in row.items():
                spec=schemas.get(name,{}).get(key)
                if not spec:continue
                if spec['label']==3 and not isinstance(value,list):raise ValueError(key+' 必须是数组')
                if spec['label']==3 and spec['type'] not in (9,11,12):
                    if any(not isinstance(v,(int,float)) or isinstance(v,bool) for v in value):raise ValueError(key+' 数组内容无效')
                if spec['label']!=3 and spec['type']==9 and not isinstance(value,str):raise ValueError(key+' 必须是文字')
                if spec['type']==11:
                    seq=value if spec['label']==3 else [value]
                    if any(not isinstance(v,dict) for v in seq):raise ValueError(key+' 必须是结构化记录')
                if spec['label']!=3 and spec['type'] not in (8,9,11,12) and isinstance(value,bool):raise ValueError(key+' 不能使用布尔值代替数值')
            from martial_editor import encode_field
            for key,value in row.items():
                if key in schemas.get(name,{}):encode_field(key,value,name)
            rows.append(row)
        except (KeyError,ValueError,TypeError,OverflowError,struct.error) as error:
            warnings.append(f'{source} 第 {index+1} 条：已跳过（{error}）')
    return rows
