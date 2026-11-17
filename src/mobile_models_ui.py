"""Mobile model and portrait selection inside the existing character editor."""
import io
import tkinter as tk
from tkinter import ttk,filedialog
from PIL import Image

def build(page,notebook):
    frame=page.host.scroll_page(notebook,'手游模型与立绘')
    ttk.Label(frame,text='手游模型与立绘',style='Title.TLabel').pack(anchor='w',pady=12)
    ttk.Label(frame,text='先选择手游模型与皮肤作为模板，再上传同拆件布局的 PNG 贴图。尺寸不同会按模板自动适配，保留透明度；图片比例须与模板一致。加入人物草稿并保存后生效。',wraplength=1000,style='Sub.TLabel').pack(anchor='w')
    row=ttk.Frame(frame);row.pack(fill='x',pady=12)
    ttk.Button(row,text='选择手游模型与皮肤',command=lambda:choose_model(page)).pack(side='left')
    ttk.Button(row,text='预览手游模型',command=lambda:preview(page)).pack(side='left',padx=10)
    ttk.Button(row,text='选择手游人物立绘',command=lambda:choose_portrait(page)).pack(side='left')
    uploads=ttk.Frame(frame);uploads.pack(fill='x',pady=(0,12))
    page.mobile_upload_button=ttk.Button(uploads,text='上传手游贴图',command=lambda:upload_texture(page),state='disabled');page.mobile_upload_button.pack(side='left')
    page.mobile_export_button=ttk.Button(uploads,text='导出手游贴图模板',command=lambda:export_texture(page),state='disabled');page.mobile_export_button.pack(side='left',padx=10)
    page.mobile_restore_button=ttk.Button(uploads,text='恢复模板贴图',command=lambda:restore_texture(page),state='disabled');page.mobile_restore_button.pack(side='left')
    page.mobile_note=tk.StringVar(value='请选择人物，再选择手游模型或立绘。')
    preview_row=ttk.Frame(frame);preview_row.pack(fill='x',pady=12)
    page.mobile_preview=ttk.Label(preview_row,text='选择模型后点击预览');page.mobile_preview.pack(side='left',anchor='n',padx=(0,18))
    ttk.Label(preview_row,textvariable=page.mobile_note,wraplength=440).pack(side='left',anchor='n',pady=10)

def refresh(page):
    spec=page.settings.get('mobile_binding')
    for button in (page.mobile_upload_button,page.mobile_export_button):button.configure(state='normal' if spec else 'disabled')
    page.mobile_restore_button.configure(state='normal' if spec and spec.get('custom_texture') else 'disabled')
    page.mobile_preview.configure(image='',text='选择模型后点击预览');page.mobile_photo=None
    if not spec:page.mobile_note.set('请先选择手游模型与皮肤作为模板，再上传 PNG 贴图。');return
    from mobile_models import selected
    try:
        _,texture=selected(spec);custom=spec.get('custom_texture')
        page.mobile_note.set('模板：'+spec['id']+' / '+spec['texture']+f"\n模板尺寸：{texture['width']}×{texture['height']} PNG，自动适配同等比例贴图。\n"+('当前自定义贴图：'+custom['label'] if custom else '当前使用模板原贴图。')+resize_note(custom))
    except Exception as error:page.mobile_note.set(str(error))

def upload_texture(page):
    if not page.available():return
    spec=page.settings.get('mobile_binding')
    if not spec:page.host.error(ValueError('请先选择手游模型与皮肤作为模板'));return
    path=filedialog.askopenfilename(title='上传对应手游模板的 PNG 贴图',parent=page,filetypes=[('PNG 贴图','*.png')])
    if not path:return
    from mobile_models import custom_texture
    try:
        page.settings['mobile_binding']=custom_texture(page.library,spec,path);page.dirty=True
        refresh(page);preview(page)
        page.host.status.set('自定义手游贴图已绑定草稿'+resize_note(page.settings['mobile_binding'].get('custom_texture'))+'；加入人物草稿后保存生效。')
    except Exception as error:page.host.error(error)

def restore_texture(page):
    if not page.available():return
    spec=page.settings.get('mobile_binding')
    if not spec:return
    from mobile_models import selected,binding
    try:
        model,texture=selected(spec);page.settings['mobile_binding']=binding(page.library,model,texture);page.dirty=True
        refresh(page);preview(page);page.host.status.set('已恢复手游模板原贴图；加入人物草稿后保存生效。')
    except Exception as error:page.host.error(error)

def export_texture(page):
    if not page.available():return
    spec=page.settings.get('mobile_binding')
    if not spec:return
    from mobile_models import selected,read
    try:
        _,texture=selected(spec)
        path=filedialog.asksaveasfilename(title='导出手游模板原贴图',parent=page,initialfile=texture['name']+'.png',defaultextension='.png',filetypes=[('PNG 贴图','*.png')])
        if not path:return
        from pathlib import Path
        path=Path(path).resolve()
        from mobile_models import asset_root
        if path.is_relative_to(asset_root().resolve()) or path.is_relative_to(page.library.root):raise ValueError('请导出到游戏目录及 mobile_assets 资源目录之外')
        path.write_bytes(read(texture));page.host.status.set('已导出模板原贴图。修改颜色和细节后，可上传到当前模板。')
    except Exception as error:page.host.error(error)

def choose_model(page):
    if not page.available():return
    from mobile_models import catalog,binding,missing_actions,AUXILIARY_TEXTURES
    try:
        choices=[];entries=[]
        for model in catalog()['models']:
            if not model.get('compatible') or not model['id'].startswith('role_'):continue
            if missing_actions(model):continue
            for texture in model['textures']:
                if texture['name'] in AUXILIARY_TEXTURES:continue
                entries.append((model,texture));choices.append((len(entries),model['id']+' / '+texture['name']+f" · {model['animation_count']} 动作"))
        result=page.picker('选择手游模型与皮肤（可搜索模型名）',choices)
        if result is None:return
        model,texture=entries[result['id']-1];spec=binding(page.library,model,texture)
        page.settings['model_source']=spec['source'];page.settings['mobile_binding']=spec;page.settings.pop('texture_binding',None)
        page.texture_payload=None;page.dirty=True
        from model_texture_ui import load
        load(page);refresh(page);page.render_portrait();preview(page)
        page.host.status.set('已绑定手游模型草稿；加入人物草稿后保存生效。')
    except Exception as error:page.host.error(error)

def preview(page):
    if not page.available():return
    spec=page.settings.get('mobile_binding')
    if not spec:page.host.error(ValueError('请先选择手游模型与皮肤'));return
    from mobile_models import selected,runtime,texture_bytes
    from model_texture_preview import render
    def work():
        model,texture=selected(spec);data=runtime(spec)
        with Image.open(io.BytesIO(texture_bytes(page.library,spec))) as im:image=render(data,im)
        return image,data
    def finish(result):
        image,data=result
        from model_texture_ui import _photo
        _photo(page,page.mobile_preview,image,'mobile_photo',(320,320))
        names=[a['Name'] for a in data['animations']]
        events=sum(len(a.get('Events',[])) for a in data['animations'])
        custom=spec.get('custom_texture');_,texture=selected(spec)
        label=('自定义贴图：'+custom['label']+resize_note(custom)) if custom else '使用模板原贴图'
        page.mobile_note.set(f"{spec['id']} / {spec['texture']}\n{label}\n贴图尺寸：{texture['width']}×{texture['height']} PNG\nSpine {data['version']} · {len(names)} 个动作 · {events} 个事件帧\n\n当前为初始姿态预览。\n保存将安装对应骨骼、贴图及完整动作时序。\n完整动作可在“模型动作绑定检查”中查看。")
    page.host.martial_page.worker('正在生成手游骨骼预览…',work,finish)

def resize_note(custom):
    if not custom or not custom.get('resize_filter'):return ''
    return f"\n已自动适配：{custom['source_width']}×{custom['source_height']} → {custom['width']}×{custom['height']}，透明度保留。"

def choose_portrait(page):
    if not page.available():return
    from mobile_models import catalog,read,asset_root
    try:
        entries=catalog()['portraits'];choices=[(i+1,f"{e['id']} · {e['width']}×{e['height']} · "+('同步头像' if e.get('head') else '保留原头像')) for i,e in enumerate(entries)]
        result=page.picker('选择手游人物立绘',choices)
        if result is None:return
        entry=entries[result['id']-1];read(entry)
        from disguise_portraits import stage_head
        head=stage_head(page.library,entry)
        page.portrait_source=asset_root()/entry['file'];page.settings.pop('portrait_layout',None);page.dirty=True;page.render_portrait()
        if head:
            page.settings['head']=head;page.settings.pop('head_layout',None);page.head_source=None
            from role_head_ui import render
            render(page)
        page.host.status.set('已选择手游人物立绘'+('并同步对应头像' if head else '；此立绘无唯一对应头像，保留原头像')+'；加入人物草稿后保存生效。')
    except Exception as error:page.host.error(error)
