# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files,collect_dynamic_libs
datas=[(name,'.') for name in ['schemas.json', 'metadata.json', 'caps_baseline.json', 'clause_baseline.json', 'app.ico', 'pet_mobile_data.json', 'six_attrs_data.json', 'six_attrs_schema.json', 'six_attrs_mobile_restore.json', 'six_attrs_points_code.json', 'six_attrs_character.lua', 'six_attrs_character_v227.lua', 'six_attrs_character_v228.lua', 'six_attrs_character_v229.lua', 'six_attrs_character_v2316.lua', 'six_attrs_mobile_layout.lua']]
datas += [('desktop_ui/dist','desktop_ui/dist'),('ui_assets','ui_assets')]
datas += [('bigmap_role_baseline.json','.'),('mobile_martial_pack.json','.'),('bigmap_data_profile.json','.'),('bigmap_six_attrs_points_code.json','.')]
datas += [('mobile_martial_repair_baseline.json','.'),('role_breakthrough_pack.json','.')]
datas += [('shadow_bigmap_v047d.zip','.')]
datas += [('nov15_six_attrs_points_code.json','.'),('nov15_role_baseline.json','.')]

datas += [('nov5_six_attrs_points_code.json','.'),('nov5_role_baseline.json','.')]

datas += collect_data_files('UnityPy')
datas += collect_data_files('archspec')
a=Analysis(['desktop_app.py'],pathex=[],binaries=collect_dynamic_libs('fmod_toolkit')+collect_dynamic_libs('keystone'),datas=datas,
 hiddenimports=['webview.platforms.winforms','webview.platforms.edgechromium','clr','pythonnet','UnityPy.resources'],
 hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['PyQt5','PyQt6','PySide2','PySide6','gtk'],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='MJH-editor',
 debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,
 disable_windowed_traceback=False,icon=['app.ico'])
