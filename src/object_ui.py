"""Selected object export and reviewable recursive import for all three pages."""
import copy,json
from pathlib import Path
from tkinter import filedialog,messagebox
from collections import Counter
from object_bundle import Store,read_bundle,write_bundle,allocate,plan_import,key,validate_packet,IncompleteGraph,missing_report
from object_extras import collect,import_extras
from engine import ensure_closed,transaction

def export_selected(host,kind,page=None):
    if host.busy or not host.catalog:return
    try:
        if Path(host.game_path.get()).resolve()!=host.catalog.root:raise ValueError('游戏目录输入已变化，请重新读取')
        overlay={};instance=None
        if kind=='Item':
            if not host.current:raise ValueError('请先选择装备')
            from engine import effect_payloads
            ident=host.current['type'];overlay=effect_payloads(host.catalog,{ident:host.current_effect()})
            instance=host.current_draft()
        elif kind=='Martial':
            if not page.available():return
            if getattr(page,'animation_dirty',False) and not page.stage_animation():return
            if page.dirty and not page.stage_basic():return
            ident=page.current;lib=copy.deepcopy(page.library);overlay,_=lib.plan()
        else:
            if not page.available():return
            if page.dirty and not page.stage():return
            ident=page.current;lib=copy.deepcopy(page.library);overlay,_=lib.plan()
        path=filedialog.asksaveasfilename(title='导出所选对象及全部组合／词条依赖',defaultextension='.mjhobject',filetypes=[('所选对象完整配置包','*.mjhobject')],parent=host)
        if not path:return
        def work():
            from object_report import write_report
            report_path=Path(path).with_suffix('.依赖检查.txt')
            store=Store(host.catalog.root,overlay)
            try:packet,files=collect(store,kind,ident)
            except IncompleteGraph as e:
                write_report(report_path,e.report)
                raise ValueError(str(e)+'\n未写入配置包。详细引用来源：'+str(report_path)) from e
            if instance is not None:packet['extras']['equipment_instance']=instance
            validate_packet(packet);write_bundle(path,packet,files)
            write_report(report_path,missing_report(packet))
            counts=Counter(n['table'] for n in packet['nodes'].values())
            warnings=packet['extras'].get('compatibility_warnings',[])
            if warnings:Path(str(path)+'.兼容提示.txt').write_text('\n'.join(warnings),encoding='utf8')
            return counts,missing_report(packet),report_path,warnings
        def finish(result):
            counts,report,report_path,warnings=result
            host.status.set('已导出所选完整配置：'+str(path))
            messagebox.showinfo('导出完成（含文本提醒）' if report else '导出完成','只导出了所选对象及其依赖，不写入游戏。\n'+str(path)+'\n\n'+ '\n'.join(f'{k}：{n} 条' for k,n in counts.items())+'\n\n必需依赖缺失：0 条。'+('\n来源有 '+str(len(report))+' 条显示文本缺失；实际效果数据已保留。' if report else '')+'\n依赖检查报告：'+str(report_path)+('\n兼容提示：'+str(len(warnings))+' 项，见同名兼容提示文件。' if warnings else ''),parent=host)
        host.martial_page.worker('正在递归收集所选对象配置、组合及词条…',work,finish)
    except Exception as e:host.error(e)

def import_selected(host,kind):
    if host.busy or not host.catalog:return
    if Path(host.game_path.get()).resolve()!=host.catalog.root:host.error(ValueError('游戏目录输入已变化，请重新读取'));return
    if host.has_changes():host.error(ValueError('请先保存或撤销当前草稿，再导入完整配置包'));return
    if kind=='Item' and host.save is None:host.error(ValueError('请先选择目标存档；导入装备会添加到该存档的周目仓库'));return
    path=filedialog.askopenfilename(title='导入所选对象完整配置包',filetypes=[('所选对象完整配置包','*.mjhobject')],parent=host)
    if not path:return
    root=host.catalog.root;save=host.save if kind=='Item' else None
    def work():
        packet,files=read_bundle(path)
        if packet['kind']!=kind:raise ValueError('配置包类别与当前页面不一致')
        from object_service import prepare
        directory=root/'ModProject/GameProject/Mod_MJH/Json';inventory=set(directory.glob('*.json'))
        store=Store(root);packet,mapping,payloads,originals,rows=prepare(store,packet,files)
        if kind=='Item':
            from object_equipment import generate
            item=mapping[key('Item',packet['root'])]
            draft=packet['extras'].get('equipment_instance',{'grade':0,'white':[],'green':[],'blue':[]})
            raw,instance=generate(save,item,rows['Item'][item],draft)
            if save.path.read_bytes()!=save.data:raise ValueError('目标存档在读取后发生变化，请重新读取')
            store.read(save.path);payloads[save.path]=raw
        originals.update(store.reads)
        for p,b in originals.items():
            if (p.read_bytes() if p.exists() else None)!=b:raise ValueError('配置在预览期间变化，请重新预览：'+str(p))
        if set(directory.glob('*.json'))!=inventory:raise ValueError('模组列表在预览期间变化，请重新预览')
        return packet,mapping,payloads,originals,inventory,{t:len(v) for t,v in rows.items()}
    def prepared(result):
        packet,mapping,payloads,originals,inventory,added=result;counts=Counter(n['table'] for n in packet['nodes'].values())
        root_token=key('@Role' if kind=='Role' else kind,packet['root']);new=mapping[root_token]
        conflicts=[f'{t} → {v}' for t,v in mapping.items() if int(t.split(':')[1])!=v]
        detail='人物武学依赖先核对原ID，再查找当前游戏同名武学，战斗词条一致时复用。暂不比较人物属性和精通加成，仍核对威力系数、招式、触发与奥义配方；保留目标原有配置及上限。天赋保持原ID完整功能核对。\n根对象：'+str(packet['root'])+' → '+str(new)+'\n\n包内关联：'+'；'.join(f'{k} {n}条' for k,n in counts.items())+'\n实际新增：'+str(sum(added.values()))+' 条\n编号映射变化：'+str(len(conflicts))+' 处\n'+ '\n'.join(conflicts[:12])
        if kind=='Item':detail+='\n\n装备将添加到：'+str(save.path)+' 的周目仓库。'
        reused=packet['extras'].get('import_reused',{})
        if reused:detail+='\n\n按实际效果复用已有词条／作用范围／天赋等配置：'+str(len(reused))+' 条。'
        identities=packet['extras'].get('import_identity_reused',{})
        if identities:detail+='\n按当前匹配规则复用武学／天赋：'+str(len(identities))+' 条。'
        matches=packet['extras'].get('import_martial_matches',[])
        chosen=[r for r in matches if r['target_id'] is not None]
        if chosen:detail+='\n武学复用：\n'+'\n'.join(f"{r['name']}：{r['source_id']} → {r['target_id']}" for r in chosen[:8])
        different=[r for r in matches if r['target_id'] is None and r['same_name_candidates']]
        if different:detail+='\n同名但战斗配置不同或未能证明一致，将新建：'+'、'.join(r['name'] for r in different[:8])
        missing=missing_report(packet)
        if missing:detail+='\n\n来源缺少显示文本：'+str(len(missing))+' 条，实际效果数据已保留。'+str([r['target'] for r in missing[:8]])
        warnings=packet['extras'].get('compatibility_warnings',[])
        if warnings:detail+='\n\n兼容提示（已跳过）：\n'+'\n'.join(warnings[:8])
        detail+='\n\n确认后备份并写入。现有对象配置不会被覆盖；公共场景和原生素材引用已检查兼容。'
        if not messagebox.askokcancel('完整配置包导入预览',detail,parent=host):return
        def commit():
            ensure_closed()
            if set((root/'ModProject/GameProject/Mod_MJH/Json').glob('*.json'))!=inventory:raise ValueError('模组列表在确认期间变化，请重新预览')
            for p,b in originals.items():
                if (p.read_bytes() if p.exists() else None)!=b:raise ValueError('配置在确认期间变化，请重新预览：'+str(p))
            return transaction(root,payloads,originals,'导入所选'+{'Item':'装备','Role':'人物','Martial':'武学'}[kind]+'完整配置包')
        def finish(backup):
            host.martial_page.reset();host.role_page.reset();host.reload()
            host.status.set(f'导入完成，根对象编号 {new}。备份：{backup}')
            messagebox.showinfo('导入完成',f'根对象新编号：{new}\n关联配置已导入。请重新读取对应页面。\n\n备份：{backup}',parent=host)
        host.martial_page.worker('正在备份并导入完整配置包…',commit,finish)
    host.martial_page.worker('正在检查组合依赖、重分配编号并生成导入预览…',work,prepared)
