"""Per-character texture import and native-skeleton preview in both editor shells."""
import io
from pathlib import Path
from tkinter import ttk, filedialog
from PIL import Image, ImageTk

def build(page,notebook):
    import tkinter as tk
    page.texture_payload=None;page.texture_preview_cache={};page.texture_template_confirmed=False
    page.texture_note=tk.StringVar(value='先选择人物和模型模板，再导入按同一布局绘制的 PNG 或模板包。')
    frame=page.host.scroll_page(notebook,'模型贴图')
    bar=ttk.Frame(frame);bar.pack(fill='x',pady=8)
    ttk.Button(bar,text='1. 选择骨骼/贴图模板',command=lambda:choose_template(page)).pack(side='left')
    page.texture_import_button=ttk.Button(bar,text='2. 导入自定义贴图并绑定人物',command=lambda:import_file(page),state='disabled')
    page.texture_import_button.pack(side='left',padx=8)
    ttk.Button(bar,text='预览绑定模型',command=lambda:preview(page)).pack(side='left',padx=8)
    ttk.Button(bar,text='恢复模板原贴图',command=lambda:restore(page)).pack(side='left')
    ttk.Label(frame,textvariable=page.texture_note,wraplength=1000,style='Sub.TLabel').pack(anchor='w',pady=8)
    pictures=ttk.Frame(frame);pictures.pack(fill='x',pady=12)
    page.texture_model_label=ttk.Label(pictures,text='模型预览',anchor='center');page.texture_model_label.pack(side='left',padx=(0,18))
    page.texture_atlas_label=ttk.Label(pictures,text='贴图布局',anchor='center');page.texture_atlas_label.pack(side='left')
    ttk.Label(frame,text='先选模板，再导入对应 PNG 或模板包；模板包与已选骨骼/布局不一致会拒绝导入，不会自动切换模板。\n导入只建立当前人物的草稿；加入人物草稿后，点击“保存人物修改”才写入游戏。\n相同比例的单页 PNG 会高质量缩放至模板尺寸，保留透明通道；不裁切、不拉伸，原文件不变。缩小会减少像素细节，PNG 保存无损。\n新贴图沿用所选模板的骨骼与动画，并清空额外染色。原版人物模型不会被覆盖；点击“恢复模板原贴图”后保存即可解除绑定。预览是初始姿态，未播放完整动画。',wraplength=1000,style='Sub.TLabel').pack(anchor='w',pady=12)

def _photo(page,label,image,attribute,size):
    image=image.copy().convert('RGBA');image.thumbnail(size,Image.Resampling.LANCZOS)
    background=Image.new('RGBA',image.size,'#e4ebe5');background.alpha_composite(image)
    photo=ImageTk.PhotoImage(background.convert('RGB'));setattr(page,attribute,photo);label.configure(image=photo,text='')

def clear(page):
    page.texture_payload=None
    for attr,label in [('texture_model_photo',page.texture_model_label),('texture_atlas_photo',page.texture_atlas_label)]:
        label.configure(image='',text='模型预览' if attr=='texture_model_photo' else '贴图布局');setattr(page,attr,None)

def load(page,pending_raw=None):
    clear(page)
    if hasattr(page,'mobile_upload_button'):
        from mobile_models_ui import refresh
        refresh(page)
    state='normal' if page.texture_template_confirmed else 'disabled'
    page.texture_import_button.configure(state=state);page.texture_import_basic_button.configure(state=state)
    if not page.library or page.current is None:
        page.texture_note.set('请先读取并选择人物');return
    if page.settings.get('mobile_binding'):
        from edition import MOBILE_ENABLED
        spec=page.settings['mobile_binding'];page.texture_note.set('当前使用手游模型：'+spec['id']+' / '+spec['texture']+'。请在“手游模型与立绘”页预览；选择原版模板可切回。')
        if not MOBILE_ENABLED:page.texture_note.set('当前人物使用手游模型。请使用手游资源版编辑，或通过“选择模型”切回原版模型。')
        page.texture_import_button.configure(state='disabled');page.texture_import_basic_button.configure(state='disabled');return
    source=page.settings.get('model_source');row=page.library.tables['RoleModel'].get(source,{})
    spec=page.settings.get('texture_binding')
    if spec:page.texture_template_confirmed=True
    state='normal' if page.texture_template_confirmed else 'disabled'
    page.texture_import_button.configure(state=state);page.texture_import_basic_button.configure(state=state)
    if not spec:
        page.texture_note.set(f"模板：{row.get('Model','')} · 配置 {source}；使用模板原贴图。PNG 须为对应 atlas 的拆件贴图；模板包须与已选模板一致。")
        return
    from model_texture import TEXTURE_DIR,validate_binding
    try:validate_binding(page.library,page.settings)
    except ValueError as error:page.texture_note.set('绑定记录无效，请重新导入：'+str(error));return
    path=page.library.root/TEXTURE_DIR/spec['filename'];raw=pending_raw if pending_raw is not None else page.library.files.get(path)
    if raw is None and path.exists():raw=path.read_bytes()
    page.texture_note.set(f"已绑定：{spec.get('label','自定义贴图')} · {spec['model']} · {spec['width']}×{spec['height']}。配置 {source} 为源模板；保存时建立当前人物独立外观。")
    if spec.get('resize_filter')=='LANCZOS':
        page.texture_note.set(page.texture_note.get()+f" 已从 {spec['source_width']}×{spec['source_height']} 高质量缩放，透明通道保留。")
    if raw:
        page.texture_payload=raw
        with Image.open(io.BytesIO(raw)) as im:_photo(page,page.texture_atlas_label,im,'texture_atlas_photo',(340,340))
        cached=page.texture_preview_cache.get((spec['sha256'],spec['model']))
        if cached is not None:_photo(page,page.texture_model_label,cached,'texture_model_photo',(400,400))
        else:page.texture_model_label.configure(text='点击“预览绑定模型”读取骨骼')
    else:page.texture_note.set('绑定贴图文件已丢失，请重新导入')

def choose_template(page):
    if not page.available():return
    from model_texture import template_choices
    def finish(choices):
        result=page.picker('选择骨骼/贴图模板（按模型资源归类）',choices,page.settings['model_source'])
        if not result:return
        page.settings['model_source']=result['id'];page.settings.pop('texture_binding',None);page.settings.pop('mobile_binding',None)
        page.texture_template_confirmed=True;page.dirty=True;load(page);page.render_portrait()
        page.host.status.set('已选择骨骼/贴图模板，请继续导入同布局贴图。')
    page.host.martial_page.worker('正在读取全部可绑定人物的骨骼/贴图模板…',lambda:template_choices(page.library),finish)

def import_file(page):
    if not page.available():return
    if not page.texture_template_confirmed:page.host.error(ValueError('请先点击“1. 选择骨骼/贴图模板”，再导入贴图'));return
    path=filedialog.askopenfilename(title='导入模型贴图或模板包',parent=page,filetypes=[('模型贴图或模板包','*.png *.zip'),('PNG 贴图','*.png'),('模板包','*.zip')])
    if not path:return
    from model_texture import import_texture
    from model_texture_preview import runtime_data,render
    def work():
        spec,raw,info=import_texture(page.library,path,page.settings['model_source'])
        error='';preview_image=None
        try:
            with Image.open(io.BytesIO(raw)) as im:preview_image=render(runtime_data(page.library.root,info),im)
        except Exception as e:error=str(e)
        return spec,raw,preview_image,error
    def finish(result):
        spec,raw,image,error=result
        page.settings['model_source']=spec['source_id'];page.settings['texture_binding']=spec;page.dirty=True
        if image is not None:page.texture_preview_cache[spec['sha256'],spec['model']]=image
        load(page,raw);page.render_portrait()
        if error:page.texture_note.set(page.texture_note.get()+' 骨骼预览暂不可用：'+error)
        page.host.status.set('自定义贴图已绑定当前人物草稿；加入人物草稿后保存生效。')
    page.host.martial_page.worker('正在检查模板、读取贴图并生成骨骼预览…',work,finish)

def preview(page):
    if not page.available():return
    spec=page.settings.get('texture_binding')
    if not spec:page.host.error(ValueError('请先导入自定义贴图'));return
    from model_texture import TEXTURE_DIR,template_info
    from model_texture_preview import runtime_data,render
    path=page.library.root/TEXTURE_DIR/spec['filename']
    raw=page.texture_payload or page.library.files.get(path)
    if raw is None:
        if not path.exists():page.host.error(ValueError('贴图丢失，请重新导入'));return
        raw=path.read_bytes()
    def work():
        info=template_info(page.library,page.settings['model_source'])
        with Image.open(io.BytesIO(raw)) as im:return render(runtime_data(page.library.root,info),im)
    def finish(image):
        page.texture_preview_cache[spec['sha256'],spec['model']]=image
        _photo(page,page.texture_model_label,image,'texture_model_photo',(400,400))
        page.host.status.set('已按实际骨骼生成初始姿态预览；保存人物修改后重启游戏读取。')
    page.host.martial_page.worker('正在生成模型预览…',work,finish)

def restore(page):
    if not page.available():return
    from model_texture import PREFIX
    spec=page.settings.get('texture_binding')
    current=page.library.tables['RoleModel'].get(page.settings['model_source'],{})
    if spec and current.get('Texture','').startswith(PREFIX):
        choices=[i for i,r in page.library.tables['RoleModel'].items() if r.get('Model')==spec['model'] and not r.get('Texture','').startswith(PREFIX)]
        exact=[i for i in choices if page.library.tables['RoleModel'][i].get('Texture')==spec.get('original_texture')]
        choices=exact or choices
        if not choices:page.host.error(ValueError('未找到原贴图模板，请先选择原版模型'));return
        page.settings['model_source']=spec.get('original_source_id') if spec.get('original_source_id') in choices else min(choices)
    page.settings.pop('texture_binding',None);page.settings.pop('mobile_binding',None);page.dirty=True;load(page);page.render_portrait()
    page.host.status.set('已恢复模板原贴图，加入人物草稿后保存生效。')
