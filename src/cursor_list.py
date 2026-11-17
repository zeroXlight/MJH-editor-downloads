"""In-memory keyset pagination. Search always covers the complete snapshot."""
from bisect import bisect_left,bisect_right
from dataclasses import dataclass
from tkinter import ttk,StringVar

@dataclass(frozen=True)
class Entry:
    key:int
    value:object
    search:str
    scope:str=''

class CursorList:
    def __init__(self,limit=100):
        self.limit=limit;self.entries=();self.lookup={};self.keys=()
        self.criteria=None;self.after=None;self.start=0
    def update(self,entries):
        entries=tuple(sorted(entries,key=lambda row:row.key))
        if entries==self.entries:return False
        if len({row.key for row in entries})!=len(entries):raise ValueError('列表游标编号重复')
        old=self.criteria;cursor=self.after
        self.entries=entries;self.lookup={row.key:row for row in entries};self.criteria=None
        if old is not None:self.filter(*old);self.after=cursor
        return True
    def filter(self,query='',scope=''):
        criteria=(query.strip().casefold(),scope)
        if criteria==self.criteria:return False
        self.criteria=criteria;q,s=criteria
        self.keys=tuple(row.key for row in self.entries if (not s or row.scope==s) and (not q or q in row.search))
        self.after=None;self.start=0
        return True
    def page(self):
        self.start=bisect_right(self.keys,self.after) if self.after is not None else 0
        if self.start>=len(self.keys):self.after=None;self.start=0
        return [self.lookup[key] for key in self.keys[self.start:self.start+self.limit]]
    def first(self):self.after=None
    def next(self):
        rows=self.page()
        if rows and self.has_next:self.after=rows[-1].key
    def previous(self):
        self.page();pos=max(0,self.start-self.limit)
        self.after=self.keys[pos-1] if pos else None
    def seek(self,key):
        pos=bisect_left(self.keys,key)
        if pos>=len(self.keys) or self.keys[pos]!=key:return False
        pos=(pos//self.limit)*self.limit
        self.after=self.keys[pos-1] if pos else None
        return True
    def resize(self,limit):
        if limit not in (50,100,200):raise ValueError('每页条数无效')
        self.limit=limit;self.first()
    @property
    def total(self):return len(self.keys)
    @property
    def has_next(self):return self.start+self.limit<len(self.keys)
    @property
    def has_previous(self):return self.start>0

class PageBar(ttk.Frame):
    def __init__(self,parent,model,change):
        super().__init__(parent);self.model=model;self.change=change
        self.note=StringVar(value='尚未读取');ttk.Label(self,textvariable=self.note,style='Sub.TLabel').pack(anchor='w')
        row=ttk.Frame(self);row.pack(fill='x',pady=(4,0))
        self.first_button=ttk.Button(row,text='首页',width=4,command=lambda:self.move('first'));self.first_button.pack(side='left')
        self.previous_button=ttk.Button(row,text='上一页',width=6,command=lambda:self.move('previous'));self.previous_button.pack(side='left',padx=3)
        self.next_button=ttk.Button(row,text='下一页',width=6,command=lambda:self.move('next'));self.next_button.pack(side='left')
        self.size=StringVar(value=str(model.limit));box=ttk.Combobox(row,textvariable=self.size,values=['50','100','200'],state='readonly',width=4)
        box.pack(side='right');ttk.Label(row,text='每页',style='Sub.TLabel').pack(side='right',padx=3)
        box.bind('<<ComboboxSelected>>',self.resize);self.sync()
    def move(self,direction):
        getattr(self.model,direction)();self.change()
    def resize(self,event=None):self.model.resize(int(self.size.get()));self.change()
    def sync(self):
        self.model.page();total=self.model.total
        self.note.set(f'{self.model.start+1}–{min(total,self.model.start+self.model.limit)} / 共 {total} 条（全量筛选）' if total else '共 0 条（全量筛选）')
        self.first_button.configure(state='normal' if self.model.has_previous else 'disabled')
        self.previous_button.configure(state='normal' if self.model.has_previous else 'disabled')
        self.next_button.configure(state='normal' if self.model.has_next else 'disabled')
