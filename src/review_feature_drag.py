"""Exercise actual WebView2 pointer input, without applying any game change."""
import json,sys,time,traceback
from pathlib import Path

def review_ui(window,bridge):
 from edition import VERSION,EDITION_NAME
 from System import Action
 from System.IO import MemoryStream
 from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
 out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent/'diagnostics'
 report=dict(version=VERSION,edition=EDITION_NAME,passed=False,frozen=bool(getattr(sys,'frozen',False)))
 def wait(fn):
  end=time.monotonic()+100
  while time.monotonic()<end:
   result=fn()
   if result:return result
   time.sleep(.1)
  raise TimeoutError('功能标签界面等待超时')
 def js(s):return window.evaluate_js(s)
 def cdp(method,params):
  holder={}
  def call():holder['task']=window.native.browser.webview.CoreWebView2.CallDevToolsProtocolMethodAsync(method,json.dumps(params))
  window.native.Invoke(Action(call));return holder['task'].GetAwaiter().GetResult()
 def mouse(kind,x,y,button=None,buttons=0):
  value=dict(type=kind,x=x,y=y,buttons=buttons)
  if button:value.update(button=button,clickCount=1)
  cdp('Input.dispatchMouseEvent',value)
 def bounds(selector):return js('(()=>{let e=document.querySelector('+json.dumps(selector)+');let r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()')
 def selected():return js("document.querySelector('.feature-tab[aria-selected=true]')?.textContent")
 def position():return js("document.querySelector('.feature-tab-scroll').scrollLeft")
 def drag(dx):
  rect=bounds('.feature-tab-scroll');x=rect['x']+rect['w']*(.7 if dx<0 else .3);y=rect['y']+18
  mouse('mouseMoved',x,y);mouse('mousePressed',x,y,'left',1)
  for step in range(1,13):mouse('mouseMoved',x+dx*step/12,y,buttons=1);time.sleep(.015)
  mouse('mouseReleased',x+dx,y,'left',0);time.sleep(.4)
 try:
  wait(lambda:not bridge.state().get('busy') and bridge.state().get('equipment',{}).get('saveOptions'))
  expected_root=Path(sys.argv[sys.argv.index('--game')+1]).resolve()
  assert Path(bridge.state()['gamePath']).resolve()==expected_root,'界面未读取指定验收目录'
  options=bridge.state()['equipment']['saveOptions']
  blank=next((i for i,label in enumerate(options) if label.startswith('blank_header')),None)
  if (expected_root/'SaveFile/blank_header/Save.sav').is_file():assert blank is not None,'未发现待验收存档'
  if blank is not None:
   bridge.command('save_slot',{'index':blank})
   wait(lambda:bridge.state()['equipment']['saveIndex']==blank and '583 件装备' in bridge.state()['status'])
   assert not bridge.state().get('dialogs') and not bridge.errors
   report['blank_header_save_loaded']=True
  js("window.__dragErrors=[];addEventListener('error',e=>window.__dragErrors.push(e.message));addEventListener('unhandledrejection',e=>window.__dragErrors.push(String(e.reason)))")
  bridge.command('page',{'page':'features'})
  wait(lambda:js("Boolean(document.querySelector('.feature-tab-scroll'))"))
  def walk(node):
   if not node:return
   yield node
   for child in node.get('children',[]):yield from walk(child)
   if node.get('body'):yield from walk(node['body'])
  expected=next(n for n in walk(bridge.state()['feature']) if n.get('kind')=='tabs')
  count=js("document.querySelectorAll('.feature-tab').length");assert count==len(expected['tabs']) and count>2,(count,len(expected['tabs']))
  js("(()=>{let e=[...document.querySelectorAll('.feature-tab')].find(e=>e.textContent==='空白秘籍低价购买');if(!e)throw Error('missing blank manual tab');e.scrollIntoView({inline:'center',block:'nearest'});})()")
  time.sleep(.3)
  r=js("(()=>{let e=[...document.querySelectorAll('.feature-tab')].find(e=>e.textContent==='空白秘籍低价购买');let r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
  mouse('mouseMoved',r['x'],r['y']);mouse('mousePressed',r['x'],r['y'],'left',1);mouse('mouseReleased',r['x'],r['y'],'left',0)
  wait(lambda:selected()=='空白秘籍低价购买' and '预览空白秘籍商店' in js('document.body.innerText'))
  r=js("(()=>{let e=[...document.querySelectorAll('button')].find(e=>e.textContent==='预览空白秘籍商店');let r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
  mouse('mouseMoved',r['x'],r['y']);mouse('mousePressed',r['x'],r['y'],'left',1);mouse('mouseReleased',r['x'],r['y'],'left',0)
  wait(lambda:not bridge.state().get('busy') and '预览完成：' in js('document.body.innerText'))
  text=js('document.body.innerText');assert '1铜币/本' in text and '20本' in text and '不写存档' in text
  assert not bridge.state().get('dialogs') and not bridge.errors
  (out/'空白秘籍商店界面验收.json').write_text(json.dumps(dict(version=VERSION,edition=EDITION_NAME,passed=True,frozen=bool(getattr(sys,'frozen',False)),actual_webview_pointer_input=True,game_path=str(expected_root),manual_tab=True,preview_clicked=True,no_apply=True,text=text),ensure_ascii=False,indent=2),'utf8')
  report['blank_manual_preview']=True
  # Restore the initial tab before the existing drag regression.
  first=expected['tabs'][0]['key'];bridge.command('tab',{'id':expected['id'],'key':first})
  wait(lambda:selected()==expected['tabs'][0]['label'])
  js("document.querySelector('.feature-tab-scroll').scrollLeft=0")
  assert js("(()=>{let e=document.querySelector('.feature-tab-scroll');return e.scrollWidth>e.clientWidth})()")
  original=selected();start=position();drag(-420);right=position();assert right>start+60,(start,right)
  assert selected()==original,'拖拽意外切换了标签'
  drag(360);left=position();assert left<right-60,(right,left)
  assert selected()==original
  # A regular click still changes the real Tk controller's selected tab.
  js("(()=>{let e=[...document.querySelectorAll('.feature-tab')].find(e=>e.textContent==='恢复角色突破');e.scrollIntoView({inline:'center',block:'nearest'});})()")
  time.sleep(.4)
  r=js("(()=>{let e=[...document.querySelectorAll('.feature-tab')].find(e=>e.textContent==='恢复角色突破');let r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
  mouse('mouseMoved',r['x'],r['y']);mouse('mousePressed',r['x'],r['y'],'left',1);mouse('mouseReleased',r['x'],r['y'],'left',0)
  wait(lambda:selected()=='恢复角色突破')
  wait(lambda:'预览角色突破' in js('document.body.innerText'))
  # Keyboard reaches both ends and selection remains visible after switching.
  js("document.querySelector('.feature-tab[aria-selected=true]').focus()")
  for kind in ('keyDown','keyUp'):cdp('Input.dispatchKeyEvent',dict(type=kind,key='End',code='End',windowsVirtualKeyCode=35))
  last=js("[...document.querySelectorAll('.feature-tab')].at(-1).textContent");wait(lambda:selected()==last)
  for kind in ('keyDown','keyUp'):cdp('Input.dispatchKeyEvent',dict(type=kind,key='Home',code='Home',windowsVirtualKeyCode=36))
  first=js("document.querySelector('.feature-tab').textContent");wait(lambda:selected()==first)
  window.resize(1280,800);time.sleep(.6);before=position();drag(-260);assert position()>before+50
  assert not bridge.errors,bridge.errors
  errors=js('window.__dragErrors');assert not errors,errors
  holder={}
  def capture():
   holder['stream']=MemoryStream();holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
  window.native.Invoke(Action(capture));holder['task'].GetAwaiter().GetResult()
  (out/'功能标签左右拖拽.png').write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose()
  report.update(passed=True,actual_webview_pointer_input=True,tabs=count,right_delta=right-start,left_delta=right-left,
   dragging_does_not_select=True,normal_click=True,keyboard_home_end=True,narrow_window=True,game_changes_applied=False,errors=errors)
 except Exception:report['error']=traceback.format_exc();raise
 finally:
  (out/'功能标签拖拽验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
  bridge.allow_close=True;window.destroy()
