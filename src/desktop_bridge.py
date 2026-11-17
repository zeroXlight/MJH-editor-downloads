"""Thread-confined adapter from the proven editor controllers to the desktop UI.

Tk owns the existing controllers and callbacks on its own thread. WebView never
touches a Tk object: commands enter a queue and snapshots contain plain JSON.
"""
import base64, json, queue, threading, time, traceback, uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from edition import DISPLAY_VERSION as VERSION,MOBILE_ENABLED,EDITION_NAME

class DesktopBridge:
    def __init__(self):
        self.requests=queue.Queue();self.ready=threading.Event();self.snapshot={}
        self.dialogs=[];self.images={};self.window=None;self.allow_close=False
        self.errors=[];self.widgets={};self.page='equipment'
        self.bindings={}
        self.close_lock=threading.Lock();self.close_pending=False
        self.stopping=False;self.stopped=threading.Event();self.thread=None
        self.invalidated=True;self.last_publish=0;self.revision=0;self.walk_cache={};self.scheduling_tick=False

    def start(self):
        self.thread=threading.Thread(target=self._run,name='EditorController',daemon=True)
        self.thread.start()
        if not self.ready.wait(45):raise RuntimeError('编辑器控制器未能启动')
        if self.errors:raise RuntimeError('编辑器控制器启动失败：'+self.errors[-1])

    def stop(self,timeout=5):
        if not self.stopped.is_set():self.requests.put(('shutdown',{}))
        if self.thread and threading.current_thread() is not self.thread:self.thread.join(timeout)
        return self.stopped.is_set()

    def _run(self):
        try:
            from app import Application
            original_register=tk.Misc._register
            def register(widget,func,subst=None,needcleanup=1):
                internal=self.scheduling_tick
                # New dialogs can enter a nested wait_window before the outer
                # callback returns. Invalidate when registering their callbacks,
                # not just when those callbacks eventually finish.
                if not internal:self.invalidated=True
                def callback(*args):
                    try:return func(*args)
                    finally:
                        if not internal:self.invalidated=True
                return original_register(widget,callback,subst,needcleanup)
            tk.Misc._register=register
            original_bind=tk.Misc.bind
            def bind(widget,sequence=None,func=None,add=None):
                if func is not None:
                    key=(str(widget),sequence)
                    self.bindings[key]=self.bindings.get(key,[])+[func] if add else [func]
                return original_bind(widget,sequence,func,add)
            tk.Misc.bind=bind
            # The old window is a controller host, never the displayed UI.
            self.app=Application();self.app.withdraw()
            self.app.title('梦江湖编辑器控制器 '+VERSION)
            self.app.report_callback_exception=self._error
            self._install_dialogs()
            self._tick();self.ready.set();self.app.mainloop()
        except Exception:
            self.errors.append(traceback.format_exc());self.ready.set()
        finally:
            # Release Tk objects on their owning thread before Python exits.
            self.widgets.clear();self.bindings.clear();self.images.clear();self.dialogs.clear()
            self.walk_cache.clear()
            tk.Misc.bind=original_bind;tk.Misc._register=original_register
            self.app=None
            import gc
            gc.collect();self.stopped.set()

    def _error(self,*args):
        self.errors.append(''.join(traceback.format_exception(*args)))
        self.notice('操作未完成',str(args[1]),'error')

    def _install_dialogs(self):
        # Message boxes share the Ant Design modal system. wait_variable runs a
        # nested Tk event loop, so incoming answers and cancel commands still run.
        for name,kind in [('showinfo','info'),('showwarning','warning'),('showerror','error'),('askyesno','confirm'),('askokcancel','confirm'),('askyesnocancel','confirm_cancel')]:
            setattr(messagebox,name,lambda title='',message='',_kind=kind,**kw:self.notice(title,message,_kind))
        self.app.bind_all('<Map>',self._hide_dialog,add='+')
        original=tk.Toplevel.wait_visibility
        def wait_visibility(widget,*args,**kwargs):
            if widget.winfo_toplevel() is not self.app:
                widget.withdraw();return
            return original(widget,*args,**kwargs)
        tk.Toplevel.wait_visibility=wait_visibility

    def _hide_dialog(self,event):
        if isinstance(event.widget,tk.Toplevel):event.widget.withdraw()

    def notice(self,title,message,kind='info'):
        ident=uuid.uuid4().hex;answer=tk.StringVar(self.app,value='pending')
        record={'id':ident,'title':str(title),'message':str(message),'kind':kind,'answer':answer}
        self.dialogs.append(record);self._publish()
        self.app.wait_variable(answer)
        value=answer.get();self.dialogs=[d for d in self.dialogs if d['id']!=ident]
        return None if value=='cancel' else value=='yes'

    def _tick(self):
        if self.stopping:return
        # Schedule first so nested legacy wait_window/wait_variable loops can
        # continue receiving commands while an edit dialog is open.
        self.scheduling_tick=True
        try:self.tick_job=self.app.after(50,self._tick)
        finally:self.scheduling_tick=False
        for _ in range(30):
            try:cmd,args=self.requests.get_nowait()
            except queue.Empty:break
            try:
                self.invalidated=True
                self._dispatch(cmd,args)
            except Exception as error:
                self.errors.append(traceback.format_exc())
                self.notice('操作未完成',str(error),'error')
            finally:
                # A nested wait_window / wait_variable may have published while
                # this command was suspended. Publish its final state as well.
                self.invalidated=True
            if self.stopping:return
        if self.invalidated and time.monotonic()-self.last_publish>=.12:self._publish()

    def state(self):
        return self.snapshot

    def command(self,name,args=None):
        if name=='close':
            with self.close_lock:
                if self.close_pending or self.allow_close:return {'accepted':True}
                self.close_pending=True
        self.requests.put((str(name),args or {}));return {'accepted':True}

    def _dispatch(self,name,p):
        app=self.app
        if name=='shutdown':
            self.stopping=True
            app.after_cancel(self.tick_job)
            for dialog in self.dialogs:dialog['answer'].set('no')
            for w in list(self._walk(app)):
                if isinstance(w,tk.Toplevel) and w.winfo_exists():w.destroy()
            app.after_idle(app.destroy)
            return
        if name=='answer':
            dialog=next((d for d in self.dialogs if d['id']==p['id']),None)
            if dialog:dialog['answer'].set(p.get('value','no'))
            return
        if name=='close_dialog':
            w=app.nametowidget(p['id']);w.event_generate('<<DesktopCancel>>')
            protocol=w.protocol('WM_DELETE_WINDOW')
            if protocol:app.tk.call(protocol)
            else:w.destroy()
            return
        if name=='close':
            try:
                if app.busy:self.notice('正在保存','请等待当前操作完成后关闭。');return
                if app.has_changes() and not self.notice('未保存的修改','关闭会丢弃尚未保存的草稿，确定关闭？','confirm'):return
                self.allow_close=True
                if self.window:threading.Thread(target=self.window.destroy,daemon=True).start()
            finally:
                with self.close_lock:self.close_pending=False
            return
        if name=='manage_features':
            from feature_manager_ui import open_manager
            open_manager(app);return
        if name=='bigmap_compat':
            from bigmap_compat_ui import show
            show(app);return
        if name=='page':
            self.page=p['page'];index={'equipment':0,'features':1,'martial':2,'role':3}[self.page];app.pages.select(index)
            if self.page=='martial' and not app.martial_page.library and not app.busy:app.martial_page.load()
            elif self.page=='role' and not app.role_page.library and not app.busy:app.role_page.load()
            elif self.page=='features':
                app.feature_panel.refresh()
            return
        if name=='set_main':
            variable={'gamePath':app.game_path,'search':app.search,'scope':app.scope,'grade':app.grade,'martialSearch':app.martial_page.query,'roleSearch':app.role_page.query}[p['key']]
            variable.set(str(p['value']));return
        if name=='save_slot':app.save_box.current(int(p['index']));app.load_save();return
        if name=='page_list':
            page=p['page'];cursor,render=(app.item_cursor,app.render_item_page) if page=='equipment' else (app.martial_page.list_cursor,app.martial_page.render_list_page) if page=='martial' else (app.role_page.cursor,app.role_page.render_page)
            if 'size' in p:cursor.resize(int(p['size']))
            elif 'number' in p:
                pos=max(0,min(len(cursor.keys)-1,(int(p['number'])-1)*cursor.limit));cursor.after=cursor.keys[pos-1] if pos else None
            else:getattr(cursor,p['direction'])()
            render();return
        if name=='select':
            w=app.nametowidget(p['id']);key=str(p['key'])
            # The WebView may send a click from the previous list snapshot
            # while a search or page change has already replaced its rows.
            if isinstance(w,ttk.Treeview) and not w.exists(key):return
            w.selection_set(key)
            if isinstance(w,ttk.Treeview):w.event_generate('<<TreeviewSelect>>')
            return
        if name=='activate':
            w=app.nametowidget(p['id']);event=tk.Event();event.widget=w
            for callback in self.bindings.get((str(w),'<Double-1>'),[]):callback(event)
            return
        if name=='canvas':
            w=app.nametowidget(p['id']);event=tk.Event();event.widget=w
            event.x=int(float(p['x'])*max(w.winfo_width(),8));event.y=int(float(p['y'])*max(w.winfo_height(),5))
            sequence={'down':'<ButtonPress-1>','move':'<B1-Motion>','up':'<ButtonRelease-1>'}[p['event']]
            for callback in self.bindings.get((str(w),sequence),[]):callback(event)
            return
        if name=='list_select':
            w=app.nametowidget(p['id']);w.selection_clear(0,'end');w.selection_set(int(p['index']));w.event_generate('<<ListboxSelect>>');return
        if name=='tab':app.nametowidget(p['id']).select(p['key']);return
        if name=='invoke':
            w=app.nametowidget(p['id'])
            if str(w.cget('state'))!='disabled':w.invoke()
            return
        if name=='value':
            w=app.nametowidget(p['id']);value=p['value']
            if isinstance(w,(tk.Scale,ttk.Scale)):w.set(float(value))
            elif isinstance(w,tk.Text):
                w.delete('1.0','end');w.insert('1.0',str(value));w.event_generate('<<Modified>>')
            else:
                variable=str(self._get(w,'textvariable'))
                if variable:app.setvar(variable,value)
                else:w.delete(0,'end');w.insert(0,str(value))
                if isinstance(w,ttk.Combobox):w.event_generate('<<ComboboxSelected>>')
                else:w.event_generate('<KeyRelease>')
            return
        if name=='check':
            w=app.nametowidget(p['id']);w.invoke();return
        if name=='attr':
            key=p['key'];mode=p['mode']
            if mode=='delete':app.delete_attr(key)
            else:app.edit_attr(key,mode)
            return
        raise ValueError('未知界面操作：'+name)

    def _get(self,w,key,default=''):
        try:return w.cget(key)
        except tk.TclError:return default

    def _text(self,w):
        var=self._get(w,'textvariable')
        try:return str(w.getvar(var)) if var else str(self._get(w,'text'))
        except tk.TclError:return str(self._get(w,'text'))

    def _children(self,w):
        managed=[c for c in w.winfo_children() if c.winfo_manager()]
        if managed and all(c.winfo_manager()=='grid' for c in managed):
            return sorted(managed,key=lambda c:(int(c.grid_info().get('row',0)),int(c.grid_info().get('column',0))))
        packed=w.pack_slaves()
        return packed or managed

    def _image(self,w):
        # Tk returns an image specification as a Tcl list, often a Python tuple.
        # str(('pyimage1',)) is not a valid Tk image name.
        names=w.tk.splitlist(self._get(w,'image'))
        return self._photo(w,str(names[0])) if names else None

    def _photo(self,w,name):
        if name in self.images:return self.images[name]
        try:
            data=w.tk.call(name,'data','-format','png')
            if isinstance(data,str):data=data.encode('latin1')
            uri='data:image/png;base64,'+base64.b64encode(data).decode()
            if len(self.images)>=64:self.images.pop(next(iter(self.images)))
            self.images[name]=uri;return uri
        except Exception:return None

    def tree(self,w):
        columns=list(w.cget('columns'))
        return {'kind':'table','id':str(w),'columns':[{'key':c,'title':str(w.heading(c,'text')),'width':int(w.column(c,'width'))} for c in columns],
                'rows':[{'key':str(i),**{c:str(v) for c,v in zip(columns,w.item(i,'values'))}} for i in w.get_children()],
                'selected':list(w.selection()),'doubleClick':(str(w),'<Double-1>') in self.bindings}

    def node(self,w,depth=0):
        if depth>18:return None
        self.widgets[str(w)]=w
        base={'id':str(w),'disabled':str(self._get(w,'state'))=='disabled'}
        if isinstance(w,ttk.Treeview):return self.tree(w)
        if isinstance(w,ttk.Scrollbar) or isinstance(w,ttk.Progressbar):return None
        if isinstance(w,ttk.Notebook):
            tabs=w.tabs();selected=w.select()
            return {**base,'kind':'tabs','tabs':[{'key':t,'label':str(w.tab(t,'text'))} for t in tabs],'selected':selected,'body':self.node(w.nametowidget(selected),depth+1) if selected else None}
        if isinstance(w,(ttk.Button,tk.Button)):return {**base,'kind':'button','text':self._text(w),'primary':'Primary' in str(self._get(w,'style'))}
        if isinstance(w,(ttk.Checkbutton,tk.Checkbutton,ttk.Radiobutton,tk.Radiobutton)):
            var=self._get(w,'variable');value=w.getvar(var) if var else False
            radio=isinstance(w,(ttk.Radiobutton,tk.Radiobutton))
            return {**base,'kind':'radio' if radio else 'check','text':self._text(w),'value':str(value)==str(self._get(w,'value')) if radio else str(value) not in ('0','False','false','')}
        if isinstance(w,(ttk.Entry,tk.Entry,ttk.Combobox,ttk.Spinbox,tk.Spinbox)):
            return {**base,'kind':'select' if isinstance(w,ttk.Combobox) else 'input','value':str(w.get()),'options':[str(v) for v in self._get(w,'values',())],
                    'readonly':str(self._get(w,'state'))=='readonly'}
        if isinstance(w,tk.Text):return {**base,'kind':'text','value':w.get('1.0','end-1c'),'readonly':base['disabled']}
        if isinstance(w,tk.Listbox):return {**base,'kind':'list','options':list(w.get(0,'end')),'selected':list(w.curselection())}
        if isinstance(w,(ttk.Label,tk.Label)):
            image=self._image(w)
            return {**base,'kind':'image','src':image,'text':self._text(w)} if image else {**base,'kind':'label','text':self._text(w),'muted':'Sub' in str(self._get(w,'style'))}
        if isinstance(w,(tk.Scale,ttk.Scale)):return {**base,'kind':'slider','value':w.get(),'min':float(w.cget('from')),'max':float(w.cget('to'))}
        children=self._children(w)
        if isinstance(w,tk.Canvas):
            children=[c for c in w.winfo_children() if isinstance(c,(ttk.Frame,tk.Frame))]
            if not children:
                items=[]
                for i in w.find_all():
                    kind=w.type(i)
                    if kind=='window':continue
                    item={'key':i,'kind':kind,'coords':w.coords(i)}
                    for option in ('fill','outline','width','text','anchor','image','font'):
                        try:item[option]=str(w.itemcget(i,option))
                        except tk.TclError:pass
                    if kind=='image' and item.get('image'):item['src']=self._photo(w,item['image'])
                    items.append(item)
                if not items:return None
                return {**base,'kind':'canvas','width':w.winfo_width() if w.winfo_width()>1 else int(w.cget('width')),
                        'height':w.winfo_height() if w.winfo_height()>1 else int(w.cget('height')),'items':items}
        nodes=[n for c in children if (n:=self.node(c,depth+1))]
        if not nodes:return None
        sides=[c.pack_info().get('side','top') for c in children if c.winfo_manager()=='pack']
        is_grid=bool(children) and all(c.winfo_manager()=='grid' for c in children)
        return {**base,'kind':'group','title':self._text(w) if isinstance(w,(ttk.LabelFrame,tk.LabelFrame)) else '',
                'layout':'grid' if is_grid else 'row' if sides and all(side in ('left','right') for side in sides) else 'column','children':nodes}

    def _walk(self,w):
        key=str(w)
        if key not in self.walk_cache:
            self.walk_cache[key]=[w]+[item for child in w.winfo_children() for item in self._walk(child)]
        yield from self.walk_cache[key]

    def buttons(self,w):
        return [{'id':str(c),'text':self._text(c),'primary':'Primary' in str(self._get(c,'style')),'disabled':str(self._get(c,'state'))=='disabled'} for c in self._walk(w) if isinstance(c,ttk.Button)]

    def pagination(self,cursor):
        return {'total':cursor.total,'size':cursor.limit,'current':cursor.start//cursor.limit+1}

    def module(self,page,key):
        notebook=next(c for c in self._walk(page) if isinstance(c,ttk.Notebook))
        tools=page.tools
        excluded=set(self._walk(notebook))|set(self._walk(page.list.master.master))|set(self._walk(tools))
        excluded|={c for dialog in self._walk(page) if isinstance(dialog,tk.Toplevel) for c in self._walk(dialog)}
        buttons=[b for b in self.buttons(page) if self.app.nametowidget(b['id']) not in excluded]
        return {'loaded':bool(page.library),'current':page.current,'title':page.note.get(),'summary':page.summary.get(),'query':page.query.get(),
                'list':self.tree(page.list),'pagination':self.pagination(page.list_cursor if key=='martial' else page.cursor),
                'buttons':buttons,'tools':self.node(tools.body),'form':self.node(notebook)}

    def _publish(self):
        app=self.app
        self.walk_cache.clear()
        try:
            equipment={'list':self.tree(app.items),'scope':app.scope.get(),'query':app.search.get(),'detail':app.detail.get(),'grade':app.grade.get(),
                       'pagination':self.pagination(app.item_cursor),'saveOptions':list(app.save_box.cget('values')),'saveIndex':app.save_box.current(),
                       'groups':{k:self.tree(t) for k,t in app.attr_trees.items()},'effectNote':app.effect_note.get(),
                       'effects':self.node(app.effect_attrs.master.master),'tools':self.node(app.equipment_tools.body)}
            modal_windows=[w for w in self._walk(app) if isinstance(w,tk.Toplevel) and w.winfo_exists()]
            dialogs=[{k:v for k,v in d.items() if k!='answer'} for d in self.dialogs]
            custom=[{'id':str(w),'title':w.title(),'body':self.node(w)} for w in modal_windows]
            snap={'version':VERSION,'edition':EDITION_NAME,'mobileEnabled':MOBILE_ENABLED,'page':self.page,'busy':app.busy,'status':app.status.get(),'gamePath':app.game_path.get(),
                  'dirty':len(app.drafts)+len(app.effects)+(1 if app.martial_page.has_changes() else 0)+(1 if app.role_page.has_changes() else 0),
                  'commands':self.buttons(app),'equipment':equipment,'dialogs':dialogs,'customDialogs':custom,'errors':self.errors[-8:]}
            if self.page=='martial':snap['module']=self.module(app.martial_page,'martial')
            if self.page=='role':snap['module']=self.module(app.role_page,'role')
            if self.page=='features':snap['feature']=self.node(app.nametowidget(app.pages.tabs()[1]))
            self.revision+=1;snap['revision']=self.revision
            self.snapshot=snap;self.last_publish=time.monotonic();self.invalidated=False
        except Exception:self.errors.append(traceback.format_exc())
        finally:self.walk_cache.clear()
