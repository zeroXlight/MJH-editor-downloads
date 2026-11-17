def review():
 from pathlib import Path
 from types import SimpleNamespace
 import sys,json,io,tempfile
 from PIL import Image
 from client_config import Assets,lua_rows,enum_values
 from model_texture import import_texture,stage_file
 root=Path(r'A:\steam\steamapps\common\xiake')
 package=Path(r'D:\mengjianghu\江灵露_role_zhouguniang贴图\清秀轻装版\江灵露_清秀轻装_高清导入包.zip')
 a=Assets((root/'DreamRivakes_Data/resources.assets').read_bytes());lib=SimpleNamespace(root=root,assets=a,tables={'RoleModel':lua_rows(a.script('RoleModel.lua'),'RoleModel',enum_values(a.script('common.lua')))})
 spec,raw,_=import_texture(lib,package,6)
 assert Image.open(io.BytesIO(raw)).size==(2048,2048)
 with tempfile.TemporaryDirectory() as tmp:
  staging=SimpleNamespace(root=Path(tmp),originals={},files={});stage_file(staging,spec,raw);assert next(iter(staging.files.values()))==raw
 out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
 (out/'高清导入验收.json').write_text(json.dumps(dict(passed=True,width=2048,height=2048,source_id=6,staging_validated=True,sha256=spec['sha256']),ensure_ascii=False,indent=2),encoding='utf8')
