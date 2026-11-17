"""Public desktop theme entry point."""
from ink_theme import apply_theme,DataTree,InkHeader,PAPER,FIELD,INK,RED,BLUE

from tkinter import ttk

class ToolShelf(ttk.Frame):
    """Disclosure for secondary commands, preserving all native button callbacks."""
    def __init__(self,parent,label):
        super().__init__(parent)
        self.label=label;self.open=False
        self.heading=ttk.Frame(self);self.heading.pack(fill='x')
        self.toggle=ttk.Button(self.heading,text='▸  '+label,command=self.flip)
        self.toggle.pack(anchor='w',pady=(6,4))
        self.body=ttk.Frame(self,padding=(2,4,2,6))
    def flip(self):
        self.open=not self.open
        self.toggle.configure(text=('▾  ' if self.open else '▸  ')+self.label)
        if self.open:self.body.pack(fill='x')
        else:self.body.pack_forget()
