"""Read local Unity resources for disguise portraits and default model thumbnails."""
import io,hashlib
from pathlib import Path
from PIL import Image

class _ReadingFiles:
    def __init__(self,filesystem):self.filesystem=filesystem;self.streams=[]
    def __getattr__(self,name):return getattr(self.filesystem,name)
    def open(self,*args,**kwargs):
        stream=self.filesystem.open(*args,**kwargs);self.streams.append(stream);return stream
    def close(self):
        for stream in reversed(self.streams):stream.close()
        self.streams.clear()

class NativeImages:
    def __init__(self,root):
        import UnityPy
        from fsspec.implementations.local import LocalFileSystem
        self.root=Path(root);self.data=self.root/'DreamRivakes_Data'
        self._files=_ReadingFiles(LocalFileSystem());self._closed=False;self.index={}
        self.env=UnityPy.Environment(fs=self._files,path=str(self.data))
        try:self._load()
        except BaseException:self.close();raise
    def _load(self):
        self.env.load_file(str(self.data/'globalgamemanagers'))
        original=self.env.find_file
        loaded={}
        def find(name,*args,**kwargs):
            key=str(name).replace('\\','/').rsplit('/',1)[-1]
            if key.lower() in loaded:return loaded[key.lower()]
            for k,v in self.env.files.items():
                if str(k).replace('\\','/').rsplit('/',1)[-1].lower()==key.lower():
                    loaded[key.lower()]=v;return v
            path=self.data/key
            if path.is_file():
                result=self.env.load_file(str(path),name=key);loaded[key.lower()]=result
                return result
            return original(name,*args,**kwargs)
        self.env.find_file=find
        resources=next(o.read() for o in self.env.objects if o.type.name=='ResourceManager')
        self.index={}
        for name,pointer in resources.m_Container:self.index.setdefault(name.lower(),[]).append(pointer)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        if self._closed:return
        self._closed=True
        self._files.close();self.index.clear()
        if 'find_file' in self.env.__dict__:del self.env.find_file
        self.env.files.clear();self.env.cabs.clear()
    def image(self,path):
        if path.startswith('#'):
            folder,name=path[1:].split('/',1)
            if folder not in ('role_editor','martial_editor','model_editor') or Path(name).name!=name:raise ValueError('图片路径无效')
            local=self.root/('mod/editor_model_textures' if folder=='model_editor' else 'ModProject/GameProject/Mod_MJH/Source/Other/'+folder)/name
            with Image.open(local) as image:return image.convert('RGBA')
        key=path.lower()
        if not key.startswith(('ui/','actor/')):key='ui/uisprite/'+key
        for pointer in self.index.get(key,[]):
            obj=pointer.deref()
            if obj.type.name in ('Sprite','Texture2D'):return obj.read().image.convert('RGBA')
        raise ValueError('图片资源不存在：'+path)
    def portraits(self):
        return sorted(k[len('ui/uisprite/'):] for k in self.index if k.startswith('ui/uisprite/charactercg/'))
    def has_sprite(self,path):
        if path.startswith('#'):return False
        key=path.lower()
        if not key.startswith(('ui/','actor/')):key='ui/uisprite/'+key
        return any(p.deref().type.name=='Sprite' for p in self.index.get(key,[]))
    def models(self):
        return {k.split('/')[1] for k in self.index if k.startswith('actor/') and k.endswith('_prefab')}

def icon_bytes(image):
    image=image.copy();image.thumbnail((240,240),Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(256,256));canvas.alpha_composite(image,((256-image.width)//2,(256-image.height)//2))
    out=io.BytesIO();canvas.save(out,format='PNG');return out.getvalue()
