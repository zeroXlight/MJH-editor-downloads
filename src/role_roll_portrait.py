"""Normalize uploaded portraits in the interaction roulette only."""
BEGIN='-- MJH_ROLE_ROLL_PORTRAIT_BEGIN'
END='-- MJH_ROLE_ROLL_PORTRAIT_END'
BLOCK='''-- MJH_ROLE_ROLL_PORTRAIT_BEGIN
    local rect = self.comRoleCGImg.rectTransform
    if not self.mjhRollOriginalRect then
        self.mjhRollOriginalRect = {anchorMin=rect.anchorMin, anchorMax=rect.anchorMax,
            pivot=rect.pivot, pos=rect.anchoredPosition, scale=rect.localScale,
            preserve=self.comRoleCGImg.preserveAspect}
    end
    if type(strCG) == "string" and string.sub(strCG,1,13) == "#role_editor/"
        and not string.match(strCG,"^#role_editor/disguise_cg_[0-9a-f]+%.png$") then
        rect.anchorMin = DRCSRef.Vec2(0.5,0)
        rect.anchorMax = DRCSRef.Vec2(0.5,0)
        rect.pivot = DRCSRef.Vec2(0.5,0)
        rect.anchoredPosition = DRCSRef.Vec2(0,0)
        rect.localScale = DRCSRef.Vec3(-1,1,1)
        rect.sizeDelta = DRCSRef.Vec2(720,720)
        self.comRoleCGImg.preserveAspect = true
    else
        local old = self.mjhRollOriginalRect
        rect.anchorMin=old.anchorMin
        rect.anchorMax=old.anchorMax
        rect.pivot=old.pivot
        rect.anchoredPosition=old.pos
        rect.localScale=old.scale
        self.comRoleCGImg.preserveAspect=old.preserve
        self.comRoleCGImg:SetNativeSize()
    end
    -- MJH_ROLE_ROLL_PORTRAIT_END'''

def patch_roll(text):
    if BEGIN in text:
        if text.count(BEGIN)!=1 or text.count(END)!=1:raise ValueError('转盘立绘补丁标记异常')
        start=text.index(BEGIN);end=text.index(END,start)+len(END)
        return text[:start]+BLOCK+text[end:]
    needle='self.comRoleCGImg:SetNativeSize()'
    if text.count(needle)!=1:raise ValueError('转盘立绘代码不匹配，未修改客户端')
    return text.replace(needle,BLOCK,1)
