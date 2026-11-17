"""Per-character common chat, patched into the game's existing choice callback."""
import json, re

BEGIN='-- ROLE_EDITOR_CHAT_BEGIN'
END='-- ROLE_EDITOR_CHAT_END'
SIGNATURE='function SelectUI:AddSelection(text, func, isLock)'

def validate_chat(value):
    if not isinstance(value,str) or len(value)>12000 or '\x00' in value:
        raise ValueError('闲聊内容须为文本，不能超过 12000 字或包含空字符')
    if len(value.splitlines())>100:raise ValueError('闲聊不能超过 100 段（每行一段）')

def patch_chat(text, records):
    """Only replace callbacks for the literal common chat choice; task choices stay intact."""
    pattern=r'\n?'+re.escape(BEGIN)+r'.*?'+re.escape(END)
    if text.count(BEGIN)!=text.count(END) or text.count(BEGIN)>1:
        raise ValueError('闲聊补丁标记异常，请重新读取配置')
    text=re.sub(pattern,'',text,flags=re.S)
    if text.count(SIGNATURE)!=1:raise ValueError('游戏闲聊入口不兼容，未修改文件')
    rows=[]
    for rid,record in sorted(records.items(),key=lambda pair:int(pair[0])):
        value=record.get('settings',{}).get('chat','');validate_chat(value)
        lines=[line.strip() for line in value.splitlines() if line.strip()]
        if lines:rows.append('['+str(int(rid))+']={'+','.join(json.dumps(line,ensure_ascii=False) for line in lines)+'},')
    if not rows:return text
    block='\n'+BEGIN+'\n'+'''local roleEditorChats = {
'''+ '\n'.join(rows)+'''
}
if text == "闲聊" and self.selectInfo and self.selectInfo.roleID then
    local chatRole = RoleDataManager:GetInstance():GetRoleTypeID(self.selectInfo.roleID)
    local chatLines = roleEditorChats[chatRole]
    if chatLines then
        func = function()
            RemoveWindowImmediately("SelectUI")
            for _, line in ipairs(chatLines) do
                DisplayActionManager:GetInstance():AddAction(DisplayActionType.PLOT_DIALOGUE_STR, false, chatRole, line)
            end
            DisplayActionManager:GetInstance():AddAction(DisplayActionType.RECOVER_INTERACT_STATE, false)
        end
    end
end
'''+END
    return text.replace(SIGNATURE,SIGNATURE+block,1)
