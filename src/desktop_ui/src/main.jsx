import React,{useState,useEffect,useRef,useCallback} from 'react';
import {createRoot} from 'react-dom/client';
import {FluentProvider,webLightTheme,TabList,Tab,Toolbar,ToolbarDivider} from '@fluentui/react-components';
import {ConfigProvider,Button,Input,InputNumber,Select,Table,Tabs,Pagination,Checkbox,Modal,Drawer,Dropdown,Tooltip,Spin,Empty,Tag,Slider,AutoComplete,Radio} from 'antd';
import zhCN from 'antd/locale/zh_CN';
import {FolderOpenOutlined,ReloadOutlined,UndoOutlined,SettingOutlined,SaveOutlined,DatabaseOutlined,FileTextOutlined,DownloadOutlined,UploadOutlined,PlusOutlined,EditOutlined,CopyOutlined,DeleteOutlined,HeartFilled,SafetyCertificateFilled,SearchOutlined,InfoCircleFilled,MoreOutlined,ReadOutlined,UserOutlined,ToolOutlined,AppstoreOutlined,CheckCircleFilled,SkinOutlined,LinkOutlined} from '@ant-design/icons';
import {Landscape} from './landscape';
import './theme.css';
import {FeatureTabs} from './feature-tabs';
import {Updates} from './updates';
import './feature-tabs.css';
const FeatureTabsContext=React.createContext(false);

const inkTheme={...webLightTheme,colorBrandBackground:'#a74236',colorBrandForeground1:'#9b382f',colorBrandStroke1:'#a74236',colorNeutralBackground1:'#faf8f3',fontFamilyBase:'"Microsoft YaHei UI", "Microsoft YaHei", sans-serif',borderRadiusMedium:'8px'};
const antTheme={token:{colorPrimary:'#287eaa',colorText:'#262927',colorTextSecondary:'#8c8981',colorBorder:'#d8d1c5',colorBgContainer:'#fcfaf6',colorBgElevated:'#fffcf7',colorFillAlter:'#f0ece3',borderRadius:7,controlHeight:38,fontSize:14,fontFamily:'"Microsoft YaHei UI", "Microsoft YaHei", sans-serif',boxShadowSecondary:'0 10px 36px rgba(67,52,33,.10)'},components:{Button:{defaultShadow:'0 1px 2px rgba(63,48,32,.04)',primaryShadow:'0 2px 5px rgba(37,111,154,.20)'},Table:{headerBg:'#eeeae1',headerColor:'#373934',headerSplitColor:'#e3ddd2',rowHoverBg:'#f3ece2',rowSelectedBg:'#f1dad3',rowSelectedHoverBg:'#eed3ca',cellPaddingBlock:9,cellPaddingInline:16,borderColor:'#e9e2d8'},Tabs:{inkBarColor:'#a64236',itemSelectedColor:'#a13f34',itemHoverColor:'#a13f34'},Input:{activeBorderColor:'#57899d',hoverBorderColor:'#b7aa95'},Select:{optionSelectedBg:'#f0dfd6',optionSelectedColor:'#9a3c31'}}};

let refresh=()=>{};
async function api(name,args={}){if(typeof window.pywebview?.api?.command==='function'){const result=await window.pywebview.api.command(name,args);setTimeout(refresh,120);return result;}throw new Error('桌面控制器尚未就绪');}
function iconFor(text){if(/保存|加入.*草稿/.test(text))return <SaveOutlined/>;if(/读取|刷新/.test(text))return <ReloadOutlined/>;if(/导出/.test(text))return <DownloadOutlined/>;if(/导入/.test(text))return <UploadOutlined/>;if(/撤销|还原|恢复/.test(text))return <UndoOutlined/>;if(/删除|移除/.test(text))return <DeleteOutlined/>;if(/添加|新增/.test(text))return <PlusOutlined/>;if(/修改|编辑/.test(text))return <EditOutlined/>;if(/复制/.test(text))return <CopyOutlined/>;if(/修复/.test(text))return <ToolOutlined/>;return null;}

function Field({value='',onChange,textarea=false,disabled=false,placeholder,...props}){
  const [local,setLocal]=useState(value);const focused=useRef(false);const changed=useRef(false);const timer=useRef();const latest=useRef(onChange);latest.current=onChange;
  useEffect(()=>{if(!focused.current)setLocal(value)},[value]);
  useEffect(()=>()=>clearTimeout(timer.current),[]);
  const change=e=>{let v=e.target.value;setLocal(v);changed.current=true;clearTimeout(timer.current);timer.current=setTimeout(()=>{latest.current(v);changed.current=false},160)};
  const Component=textarea?Input.TextArea:Input;
  return <Component value={local} disabled={disabled} placeholder={placeholder} onFocus={()=>focused.current=true} onBlur={()=>{focused.current=false;clearTimeout(timer.current);if(changed.current){latest.current(local);changed.current=false}}} onChange={change} {...props}/>;
}

function RemoteList({node}){
 const ref=useRef();useEffect(()=>{ref.current?.querySelector('[data-selected="true"]')?.scrollIntoView({block:'nearest'})},[node.selected.join(','),node.options.length]);
 return <div ref={ref} className="remote-list" role="listbox">{node.options.map((v,i)=><button data-selected={node.selected.includes(i)} className={node.selected.includes(i)?'chosen':''} key={i} onClick={()=>api('list_select',{id:node.id,index:i})}>{v}</button>)}</div>;
}

function RemoteButton({node,busy=false}){return <Button type={node.primary?'primary':'default'} disabled={busy||node.disabled} icon={iconFor(node.text)} onClick={()=>api('invoke',{id:node.id})}>{node.text}</Button>}
function RemoteTable({node,compact=false}){
  const columns=node.columns.map((c,i)=>({title:c.title,dataIndex:c.key,key:c.key,ellipsis:true,...(i?{width:c.width<90?84:undefined}:{}),render:(value)=>i===0?<span className="data-name">{/生命/.test(value)?<HeartFilled className="attribute-symbol"/>:/防御/.test(value)?<SafetyCertificateFilled className="attribute-symbol"/>:null}{value||'—'}</span>:value||'—'}));
  return <Table className={'ink-table '+(compact?'compact-table':'')} size="small" columns={columns} dataSource={node.rows} pagination={false} rowKey="key" scroll={{x:'max-content'}} locale={{emptyText:<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据"/>}} rowClassName={r=>node.selected.includes(r.key)?'selected-row':''} onRow={r=>({onClick:()=>api('select',{id:node.id,key:r.key}),onDoubleClick:()=>node.doubleClick&&api('activate',{id:node.id})})}/>;
}

function RemoteCanvas({node}){
 const dragging=useRef(false);
 const point=(event,kind)=>{const r=event.currentTarget.getBoundingClientRect();api('canvas',{id:node.id,event:kind,x:Math.max(0,Math.min(.999,(event.clientX-r.left)/r.width)),y:Math.max(0,Math.min(.999,(event.clientY-r.top)/r.height))})};
 return <svg className="remote-canvas" viewBox={`0 0 ${node.width} ${node.height}`} onPointerDown={e=>{dragging.current=true;e.currentTarget.setPointerCapture(e.pointerId);point(e,'down')}} onPointerMove={e=>{if(dragging.current)point(e,'move')}} onPointerUp={e=>{point(e,'up');dragging.current=false}}>{node.items.map(i=>{
  const c=i.coords,fill=i.fill==='#409eff'?'#3681a0':i.fill||'none',stroke=i.outline||'none',props={key:i.key,fill,stroke,strokeWidth:Number(i.width)||1};
  if(i.kind==='rectangle')return <rect {...props} x={c[0]} y={c[1]} width={Math.max(0,c[2]-c[0])} height={Math.max(0,c[3]-c[1])} rx="3"/>;
  if(i.kind==='oval')return <ellipse {...props} cx={(c[0]+c[2])/2} cy={(c[1]+c[3])/2} rx={(c[2]-c[0])/2} ry={(c[3]-c[1])/2}/>;
  if(i.kind==='line'||i.kind==='polygon')return React.createElement(i.kind==='line'?'polyline':'polygon',{...props,points:c.join(' '),stroke:i.fill||i.outline||'#777',fill:i.kind==='line'?'none':fill});
  if(i.kind==='text')return <text key={i.key} x={c[0]} y={c[1]} fill={fill} textAnchor={['w','nw','sw'].includes(i.anchor)?'start':['e','ne','se'].includes(i.anchor)?'end':'middle'} dominantBaseline="central" fontSize="13">{i.text}</text>;
  if(i.kind==='image'&&i.src)return <image key={i.key} href={i.src} x={c[0]} y={c[1]}/>;
  return null;
 })}</svg>;
}

function RemoteNode({node,busy=false}){
  const featureTabs=React.useContext(FeatureTabsContext);
  if(!node)return null;
  const n=node,change=value=>api('value',{id:n.id,value});
  switch(n.kind){
    case 'button':return <RemoteButton node={n} busy={busy}/>;
    case 'label':return n.text?<div className={'remote-label '+(n.muted?'muted':'')}>{n.text}</div>:null;
    case 'input':return <Field value={n.value} disabled={busy||n.disabled} onChange={change}/>;
    case 'select':return n.readonly?<Select className="remote-select" value={n.value||undefined} disabled={busy||n.disabled} showSearch={{optionFilterProp:'label'}} options={n.options.map(v=>({value:v,label:v}))} onChange={change} popupMatchSelectWidth={false}/>:<AutoComplete className="remote-select" value={n.value} disabled={busy||n.disabled} options={n.options.map(v=>({value:v}))} onChange={change} filterOption={(input,option)=>option.value.toLowerCase().includes(input.toLowerCase())}/>;
    case 'radio':return <Radio checked={n.value} disabled={busy||n.disabled} onChange={()=>api('check',{id:n.id})}>{n.text}</Radio>;
    case 'check':return <Checkbox checked={n.value} disabled={busy||n.disabled} onChange={()=>api('check',{id:n.id})}>{n.text}</Checkbox>;
    case 'text':return n.readonly?<div className="readable-report">{n.value||'预览结果将在此处显示。'}</div>:<Field value={n.value} textarea autoSize={{minRows:3,maxRows:12}} disabled={busy||n.disabled} onChange={change}/>;
    case 'table':return <RemoteTable node={n}/>;
    case 'canvas':return <RemoteCanvas node={n}/>;
    case 'slider':return <Slider min={n.min} max={n.max} value={n.value} onChange={change}/>;
    case 'image':return <div className="image-preview"><img src={n.src}/><span>{n.text}</span></div>;
    case 'list':return <RemoteList node={n}/>;
    case 'tabs':return featureTabs?<FeatureTabs node={n} onChange={key=>api('tab',{id:n.id,key})}><RemoteNode node={n.body} busy={busy}/></FeatureTabs>:<Tabs className="editor-tabs" type="card" activeKey={n.selected} onChange={key=>api('tab',{id:n.id,key})} items={n.tabs.map(t=>({key:t.key,label:t.label,children:t.key===n.selected?<RemoteNode node={n.body} busy={busy}/>:null}))}/>;
    case 'group':{
      const children=n.children.filter(c=>c.kind!=='label'||c.text);if(!children.length)return null;
      const one=children.length===1&&!n.title;
      return <div className={'remote-group '+(one?'passthrough':n.layout)+(n.title?' titled-group':'')}>
        {n.title&&<h3>{n.title}</h3>}{children.map(c=><RemoteNode key={c.id} node={c} busy={busy}/>)}</div>;
    }
    default:return null;
  }
}

function GearIcon({name}){
 const kind=/衣|袍|裳|甲|服/.test(name)?'robe':/靴|鞋/.test(name)?'boot':/项链|环|珠|坠|佩|琥珀/.test(name)?'ring':/刀|剑|匕|枪|棍/.test(name)?'sword':'robe';
 return <svg className="gear-icon" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">{kind==='robe'?<path d="m8 3 4 2 4-2 6 4-3 5-3-2v11H8V10l-3 2-3-5 6-4Zm1 1 3 5 3-5-3 1Z"/>:kind==='boot'?<path d="M5 2h7v11l5 3 4 1v5H4v-9H3V3h2Zm9 1h5v10h-4l-1-10Z"/>:kind==='ring'?<path d="M9 1h6l2 4-3 4h-4L7 5l2-4Zm-3 6 3 3a6 6 0 1 0 6 0l3-3a10 10 0 1 1-12 0Z"/>:<path d="m19 1 3 1-2 6-10 9-2-2L19 1ZM4 12l8 8-2 2-3-3-4 4-2-2 4-4-3-3 2-2Z"/>}</svg>
}

function Pager({pagination,page}){
 return <div className="list-pagination"><span>{pagination.total?`${(pagination.current-1)*pagination.size+1} – ${Math.min(pagination.current*pagination.size,pagination.total)}`:'0'} <i>/ 共 {pagination.total} 条</i></span><Pagination simple showSizeChanger={false} size="small" current={pagination.current} total={pagination.total} pageSize={pagination.size} onChange={number=>api('page_list',{page,number})}/><Select className="page-size" size="small" value={pagination.size} options={[50,100,200].map(v=>({value:v,label:`${v} 条/页`}))} onChange={size=>api('page_list',{page,size})}/></div>
}

function MainList({data,page,title}){
 const [search,setSearch]=useState(data.query||'');useEffect(()=>setSearch(data.query||''),[data.query]);
 const isEquip=page==='equipment';const key=isEquip?'search':page==='martial'?'martialSearch':'roleSearch';
 const columns=data.list.columns.map((c,i)=>({title:c.title,key:c.key,dataIndex:c.key,...(i===1?{width:isEquip?75:80}:i===2?{width:isEquip?106:70}:{}),ellipsis:true,render:(v)=>i===0?<span className="item-name">{isEquip?<GearIcon name={v}/>:page==='martial'?<ReadOutlined/>:<UserOutlined/>}<span>{v}</span></span>:v||'—'}));
 return <section className="paper-card library-panel"><div className="panel-heading"><AppstoreOutlined/><h2>{title}</h2>{isEquip?<Dropdown menu={{items:[{key:'周目仓库',label:'周目仓库'},{key:'主角背包/穿戴',label:'主角背包 / 穿戴'},{key:'全部装备',label:'全部装备'}],onClick:({key})=>api('set_main',{key:'scope',value:key})}}><Button size="small" type="text" className="scope-button">{data.scope}⌄</Button></Dropdown>:<span className="section-count">{data.pagination.total}</span>}</div>
 <div className="list-search"><Field prefix={<SearchOutlined/>} value={data.query} placeholder={isEquip?'搜索装备名、实例 ID 或型号 ID…':page==='martial'?'搜索武学名称或 ID…':'搜索人物名字、原型 ID 或城市…'} onChange={value=>api('set_main',{key,value})}/><Button onClick={()=>api('set_main',{key,value:''})}>清空</Button></div>
 <div className="list-table-viewport"><Table className="ink-table library-table" rowKey="key" columns={columns} dataSource={data.list.rows} pagination={false} size="small" sticky locale={{emptyText:<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="读取配置后，在此选择编辑条目"/>}} rowClassName={r=>data.list.selected.includes(r.key)?'selected-row':''} onRow={r=>({onClick:()=>api('select',{id:data.list.id,key:r.key})})}/></div>
 <Pager pagination={data.pagination} page={page}/></section>
}

function Equipment({state,invoke}){
 const d=state.equipment;const [effect,setEffect]=useState('attributes');const [group,setGroup]=useState('white');const [drawer,setDrawer]=useState(false);
 const current=d.groups[group];const first=d.detail.split('\n');
 return <div className="split-workspace"><MainList data={d} page="equipment" title="装备列表"/><div className="detail-column">
 <section className="paper-card save-toolbar"><div className="save-picker"><span>目标存档</span><Select value={d.saveIndex<0?undefined:d.saveIndex} placeholder="选择目标存档" options={d.saveOptions.map((v,i)=>({value:i,label:v}))} onChange={index=>api('save_slot',{index})}/><Button icon={<ReloadOutlined/>} disabled={state.busy} onClick={()=>invoke('重新读取')}>重新读取</Button></div><div className="save-actions"><Button className="primary-action" type="primary" icon={<SaveOutlined/>} disabled={state.busy} onClick={()=>invoke('保存装备修改')}>保存装备修改</Button><Button icon={<DatabaseOutlined/>} disabled={state.busy} onClick={()=>invoke('备份恢复')}>备份恢复</Button><Dropdown menu={{items:[{key:'导出修改副本',label:'导出修改副本',icon:<FileTextOutlined/>},{key:'tools',label:'完整配置导入 / 导出',icon:<SettingOutlined/>}],onClick:({key})=>key==='tools'?setDrawer(true):invoke(key)}}><Button icon={<FileTextOutlined/>}>导出 / 更多</Button></Dropdown></div></section>
 <section className="paper-card equipment-detail"><div className="equipment-overview"><div className="detail-title"><span className="eyebrow">当前装备</span><h2>{first[0]}</h2><p>{first[1]||'从左侧选择装备，查看实例与属性。'}</p></div><div className="enhancement-row"><span>强化等级</span><div className="stepper"><Button onClick={()=>api('set_main',{key:'grade',value:Math.max(0,(Number(d.grade)||0)-1)})} disabled={state.busy||!d.list.selected.length}>−</Button><InputNumber min={0} max={20} controls={false} value={Number(d.grade)||0} onChange={value=>value!==null&&api('set_main',{key:'grade',value})} disabled={state.busy||!d.list.selected.length}/><Button onClick={()=>api('set_main',{key:'grade',value:Math.min(20,(Number(d.grade)||0)+1)})} disabled={state.busy||!d.list.selected.length}>＋</Button></div><span className="muted enhancement-help">0 ～ 20；效果达到其解锁等级后启用</span><Button icon={<CopyOutlined/>} disabled={state.busy||!d.list.selected.length} onClick={()=>invoke('复制装备')}>复制装备</Button><Button className="undo-item" icon={<UndoOutlined/>} disabled={state.busy} onClick={()=>invoke('撤销这件装备的存档修改')}>撤销这件装备的存档修改</Button></div></div>
 <div className="attribute-workbench"><div className="section-switch" role="tablist"><button role="tab" aria-selected={effect==='attributes'} className={effect==='attributes'?'active':''} onClick={()=>setEffect('attributes')}>装备词条 <small>（此存档、此装备）</small></button><button role="tab" aria-selected={effect==='effects'} className={effect==='effects'?'active':''} onClick={()=>setEffect('effects')}>强化效果 <small>（同型号装备共同使用）</small></button></div>
 {effect==='attributes'?<div className="attribute-content"><div className="attribute-actions"><div className="segmented-tabs">{[['white','基础属性'],['green','铸造属性'],['blue','蓝字加成']].map(([k,v])=><button className={k===group?'active':''} key={k} onClick={()=>setGroup(k)}>{v}</button>)}</div><div className="edit-actions">{[['add','添加',<PlusOutlined/>],['edit','修改',<EditOutlined/>],['copy','复制',<CopyOutlined/>],['delete','删除',<DeleteOutlined/>]].map(([mode,text,icon])=><Button key={mode} icon={icon} disabled={state.busy||!d.list.selected.length||(mode!=='add'&&!current.selected.length)} onClick={()=>api('attr',{key:group,mode})}>{text}</Button>)}</div></div><p className="table-caption">{group==='white'?'基础属性 · 2 个槽位':group==='green'?'铸造属性 · 7 个槽位':'蓝字加成 · 2 个槽位'}<span>选择词条后可修改、复制或删除</span></p><RemoteTable node={current}/></div>:<div className="effects-content"><RemoteNode node={d.effects} busy={state.busy}/></div>}
 </div></section></div><Drawer title="装备完整配置" open={drawer} width={600} onClose={()=>setDrawer(false)}><RemoteNode node={d.tools} busy={state.busy}/></Drawer></div>
}

function ModuleEditor({state,page,invoke}){
 const [tools,setTools]=useState(false);const d=state.module;if(!d)return <div className="loading-workspace"><Spin/><span>正在准备编辑工作台…</span></div>;
 const title=page==='martial'?'武学列表':'人物列表';
 return <div className="module-workspace"><section className="paper-card module-toolbar"><Toolbar aria-label="编辑操作">{d.buttons.filter(b=>!b.primary&&!/导出/.test(b.text)).map(b=><RemoteButton key={b.id} node={b} busy={state.busy}/>)}<ToolbarDivider/><Button icon={<SettingOutlined/>} onClick={()=>setTools(true)}>更多工具</Button></Toolbar><div>{d.buttons.filter(b=>/导出/.test(b.text)||b.primary).map(b=><RemoteButton key={b.id} node={b} busy={state.busy}/>)}</div></section>
 <div className="module-summary"><span>{d.summary}</span><span className="draft-indicator">{state.dirty?<><i/>有待保存草稿</>:<><CheckCircleFilled/>已同步当前配置</>}</span></div>
 <div className="split-workspace module-split"><MainList data={d} page={page} title={title}/><section className="paper-card module-detail"><div className="module-detail-heading"><span className="eyebrow">{page==='martial'?'武学创作':'人物编辑'}</span><h2>{d.title}</h2></div><div className="module-form"><RemoteNode node={d.form} busy={state.busy}/></div></section></div>
 <Drawer title={page==='martial'?'武学 · 配置与修复工具':'人物 · 配置、同步与修复工具'} width={900} open={tools} onClose={()=>setTools(false)}><RemoteNode node={d.tools} busy={state.busy}/></Drawer></div>
}

function Dialogs({state}){
 const current=state.dialogs?.at(-1);const custom=state.customDialogs?.at(-1);
 return <>{custom&&<Modal className="editor-modal" title={custom.title} open width={980} footer={null} onCancel={()=>api('close_dialog',{id:custom.id})} mask={{closable:false}}><div className="dialog-scroll"><RemoteNode node={custom.body} busy={false}/></div></Modal>}{current&&<Modal className="notice-modal" title={current.title} open zIndex={1800} okText={/confirm/.test(current.kind)?'确认':'知道了'} cancelText="取消" cancelButtonProps={{style:{display:/confirm/.test(current.kind)?undefined:'none'}}} onOk={()=>api('answer',{id:current.id,value:'yes'})} onCancel={()=>api('answer',{id:current.id,value:current.kind==='confirm_cancel'?'cancel':'no'})} mask={{closable:false}}><div className={'notice-body '+current.kind}><InfoCircleFilled/><p>{current.message}</p></div></Modal>}</>;
}

function Desktop(){
 const [state,setState]=useState(null);const [error,setError]=useState('');const [help,setHelp]=useState(false);const pending=useRef(false);const revision=useRef(null);
 const poll=useCallback(async()=>{if(pending.current||typeof window.pywebview?.api?.state!=='function')return;pending.current=true;try{const next=await window.pywebview.api.state(revision.current);if(next?.version){revision.current=next.revision;setState(next);}}catch(e){setError(String(e));}finally{pending.current=false;}},[]);
 refresh=poll;
 useEffect(()=>{const timer=setInterval(poll,260);window.addEventListener('pywebviewready',poll);const close=()=>api('close');window.addEventListener('desktop-request-close',close);return()=>{clearInterval(timer);window.removeEventListener('pywebviewready',poll);window.removeEventListener('desktop-request-close',close)}},[poll]);
 const invoke=text=>{const command=state.commands.find(b=>b.text===text);if(command)return api('invoke',{id:command.id});setError('未找到操作入口：'+text)};
 useEffect(()=>{const handler=e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();if(state)invoke(state.page==='martial'?'保存武学修改':state.page==='role'?'保存人物修改':'保存装备修改')}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler)},[state]);
 if(!state)return <div className="startup"><div className="seal">梦<br/>江<br/>湖</div><h1>梦江湖 · 编辑工作台</h1><Spin/><p>{error||'正在启动桌面控制器…'}</p></div>;
 const nav=[['equipment','装备编辑',<SkinOutlined/>],['features','功能修改',<ToolOutlined/>],['martial','新增 / 编辑武学',<ReadOutlined/>],['role','新增 / 修改人物',<UserOutlined/>]];
 return <div className="desktop-app"><header className="ink-header"><Landscape/><div className="brand"><div className="seal">梦<br/>江<br/>湖</div><div><div className="brand-line"><h1>已有装备/武学/人物编辑器</h1><span className="version-badge">{state.version}</span></div><p>装备属性 <span>｜</span> 武学创作 <span>｜</span> 人物编辑 <span>｜</span> 功能修改</p></div></div><div className="header-motto">江湖路远<br/>自在由心<span>梦</span></div></header>
 <div className="app-body"><section className="paper-card directory-card"><div className="directory-row"><label>游戏目录</label><Field value={state.gamePath} onChange={value=>api('set_main',{key:'gamePath',value})}/><Button icon={<FolderOpenOutlined/>} disabled={state.busy} onClick={()=>invoke('选择目录')}>选择目录</Button><span className="toolbar-rule"/><Button icon={<ReloadOutlined/>} disabled={state.busy} onClick={()=>invoke('读取目录')}>读取目录</Button><Button icon={<UndoOutlined/>} disabled={state.busy} onClick={()=>invoke('还原所有修改')}>还原所有修改</Button><span className="toolbar-rule"/><Button className="mod-button" icon={<SettingOutlined/>} disabled={state.busy} onClick={()=>invoke('外部 MOD 安装兼容')}>外部 MOD 安装兼容</Button></div>
 <div className="sharing-row"><Toolbar aria-label="共享与日志"><Button icon={<FileTextOutlined/>} disabled={state.busy} onClick={()=>invoke('查看改动日志')}>查看改动日志</Button><Button icon={<UploadOutlined/>} disabled={state.busy} onClick={()=>invoke('读取改动效果')}>读取改动效果</Button><Button icon={<DownloadOutlined/>} disabled={state.busy} onClick={()=>invoke('导出改动效果')}>导出改动效果</Button></Toolbar><Button className="bigmap-compat-button" icon={<SettingOutlined/>} disabled={state.busy} onClick={()=>api('bigmap_compat')}>兼容大地图版本</Button>{state.update&&<Updates state={state.update} mobileEnabled={state.mobileEnabled}/>}<span className="sharing-note"><InfoCircleFilled/>日志区分待保存与已保存 · 共享文件读取后预览并备份</span><Tooltip title="关于本次验收版"><Button type="text" size="small" icon={<InfoCircleFilled/>} onClick={()=>setHelp(true)}/></Tooltip></div></section>
 <nav className="workspace-navigation"><TabList appearance="subtle" size="large" selectedValue={state.page} onTabSelect={(_,data)=>api('page',{page:data.value})}>{nav.map(([key,title,icon])=><Tab key={key} value={key} icon={icon}>{title}{['martial','role'].includes(key)&&<span className="beta-label">Beta</span>}</Tab>)}</TabList><span className="workspace-label personal-signature">兰霜容天下第一！</span></nav>
 <main className={'work-area '+(state.busy?'is-busy':'')}>{state.page==='equipment'?<Equipment state={state} invoke={invoke}/>:state.page==='features'?<section className="paper-card feature-workspace"><div className="feature-title"><ToolOutlined/><div><h2>功能修改</h2><p>全局配置或指定存档修改，预览后应用并备份</p></div><Button className="feature-manager-button" disabled={state.busy} onClick={()=>api('manage_features')}>关闭 / 启用功能</Button></div><div className="feature-form"><FeatureTabsContext.Provider value={true}><RemoteNode node={state.feature} busy={state.busy}/></FeatureTabsContext.Provider></div></section>:<ModuleEditor state={state} page={state.page} invoke={invoke}/>}</main>
 <footer className="status-bar"><span className={'status-dot '+(state.busy?'busy':'')}/><span>{state.status}</span>{state.busy&&<Spin size="small"/>}<span className="status-right">{state.dirty?`${state.dirty} 项待保存`:'就绪'}<span>·</span>{state.version}</span></footer></div>
 <Dialogs state={state}/><Modal title={"梦江湖 · "+state.version} open={help} footer={<Button onClick={()=>setHelp(false)}>关闭</Button>} onCancel={()=>setHelp(false)}><p>Fluent UI 工作台骨架 · Ant Design 数据组件 · 自制水墨主题</p><p>编辑界面随 EXE 离线提供。数据读写复用原编辑器逻辑；支持 Ctrl + S 保存当前模块。</p><p>{state.mobileEnabled?"手游资源版支持手游模型、手游立绘、自定义贴图与手游武学恢复；请完整保留 mobile_assets 资源目录。":"标准版支持原版模型、人物立绘和自定义模型贴图。"}</p></Modal>{error&&<Modal title="界面提示" open onOk={()=>setError('')} onCancel={()=>setError('')}><p>{error}</p></Modal>}</div>
}

createRoot(document.getElementById('root')).render(<FluentProvider theme={inkTheme}><ConfigProvider locale={zhCN} theme={antTheme}><Desktop/></ConfigProvider></FluentProvider>);
