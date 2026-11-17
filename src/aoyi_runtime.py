"""Normalize the AoYi client limit from live native ingredient limits."""
BEGIN='-- MJH_AOYI_CAPS_217_BEGIN'
END='-- MJH_AOYI_CAPS_217_END'
BRANCH='''    -- MJH_AOYI_CAP_QUERY_217
    if martialBaseData.KFFeature == 1 then
        local cap=self:MJHAoyiMaxLevel(martialData)
        if cap then
            local view={}
            for key,value in pairs(martialData) do view[key]=value end
            view.uiMaxLevel=cap
            return view,martialBaseData
        end
    end
'''

def patch_client(text):
    from engine import DATA_ROOT
    block=(DATA_ROOT/'ui_assets/aoyi_caps.lua').read_text('utf8').strip()
    start=text.index('function MartialDataManager:GetData(')
    end=text.index('\nfunction ',start+1)
    region=text[start:end]
    if '-- MJH_AOYI_CAP_QUERY_217' not in region:
        anchor='    return martialData, martialBaseData'
        if region.count(anchor)!=1:raise ValueError('奥义动态上限读取入口不兼容，未覆盖')
        region=region.replace(anchor,BRANCH+anchor,1);text=text[:start]+region+text[end:]
    if BEGIN in text:
        if text.count(BEGIN)!=1 or text.count(END)!=1:raise ValueError('奥义上限补丁标记异常')
        a=text.index(BEGIN);b=text.index(END,a)+len(END)
        return text[:a]+BEGIN+'\n'+block+'\n'+END+text[b:]
    anchor='return MartialDataManager'
    if text.count(anchor)!=1:raise ValueError('奥义上限脚本导出入口不兼容')
    return text.replace(anchor,BEGIN+'\n'+block+'\n'+END+'\n'+anchor,1)
