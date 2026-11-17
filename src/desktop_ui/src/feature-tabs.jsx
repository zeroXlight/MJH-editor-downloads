import React,{useEffect,useRef,useState} from 'react';

// Native scrolling keeps drag, keyboard focus and the scrollbar on one path.
export function FeatureTabs({node,children,onChange}){
 const viewport=useRef(null),gesture=useRef(null),suppressUntil=useRef(0);
 const [dragging,setDragging]=useState(false),[edges,setEdges]=useState({left:false,right:false});
 const measure=()=>{const el=viewport.current;if(el){const value={left:el.scrollLeft>1,right:el.scrollLeft+el.clientWidth<el.scrollWidth-1};setEdges(old=>old.left===value.left&&old.right===value.right?old:value);}};
 const stop=()=>{gesture.current=null;setDragging(false);};
 useEffect(()=>{
  const el=viewport.current,observer=new ResizeObserver(measure);observer.observe(el);measure();
  window.addEventListener('pointerup',stop);window.addEventListener('pointercancel',stop);
  return()=>{observer.disconnect();window.removeEventListener('pointerup',stop);window.removeEventListener('pointercancel',stop);};
 },[node.id,node.tabs.length]);
 useEffect(()=>{
  const el=viewport.current,selected=el?.querySelector('[aria-selected="true"]');if(!selected)return;
  const view=el.getBoundingClientRect(),item=selected.getBoundingClientRect();
  if(item.left<view.left)el.scrollLeft-=view.left-item.left;
  else if(item.right>view.right)el.scrollLeft+=item.right-view.right;
  measure();
 },[node.selected]);
 const down=e=>{if(e.button!==0||!e.isPrimary)return;gesture.current={id:e.pointerId,x:e.clientX,y:e.clientY,left:e.currentTarget.scrollLeft,moved:false};};
 const move=e=>{
  const g=gesture.current,el=viewport.current;if(!g||g.id!==e.pointerId)return;
  const dx=e.clientX-g.x,dy=e.clientY-g.y;
  if(!g.moved){if(Math.abs(dx)<6)return;if(Math.abs(dy)>Math.abs(dx)){stop();return;}g.moved=true;el.setPointerCapture(e.pointerId);setDragging(true);}
  e.preventDefault();el.scrollLeft=g.left-dx;suppressUntil.current=performance.now()+300;measure();
 };
 const click=e=>{if(e.detail!==0&&performance.now()<suppressUntil.current){e.preventDefault();e.stopPropagation();}};
 const key=(e,index)=>{
  let next;if(e.key==='ArrowRight')next=(index+1)%node.tabs.length;else if(e.key==='ArrowLeft')next=(index+node.tabs.length-1)%node.tabs.length;
  else if(e.key==='Home')next=0;else if(e.key==='End')next=node.tabs.length-1;else return;
  e.preventDefault();viewport.current.querySelectorAll('[role="tab"]')[next]?.focus();onChange(node.tabs[next].key);
 };
 const scroll=direction=>viewport.current?.scrollBy({left:direction*Math.max(180,viewport.current.clientWidth*.7),behavior:'smooth'});
 return <div className="editor-tabs feature-tabs" data-feature-tabs={node.id}>
  <div className="feature-tab-toolbar">
   <button className="feature-tab-arrow" aria-label="向左滚动功能标签" disabled={!edges.left} onClick={()=>scroll(-1)}>‹</button>
   <div className={'feature-tab-scroll'+(dragging?' dragging':'')} ref={viewport} role="tablist" aria-label="功能修改" onScroll={measure}
    onPointerDown={down} onPointerMove={move} onPointerUp={stop} onPointerCancel={stop} onClickCapture={click}>
    {node.tabs.map((tab,index)=><button type="button" role="tab" aria-selected={tab.key===node.selected} tabIndex={tab.key===node.selected?0:-1}
     className="feature-tab" key={tab.key} onClick={()=>onChange(tab.key)} onKeyDown={e=>key(e,index)}>{tab.label}</button>)}
   </div>
   <button className="feature-tab-arrow" aria-label="向右滚动功能标签" disabled={!edges.right} onClick={()=>scroll(1)}>›</button>
  </div>
  <div className="feature-tab-body" role="tabpanel">{children}</div>
 </div>;
}
