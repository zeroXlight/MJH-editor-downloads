"""Fit uploaded 512px portraits to the actual team-list mask, not native pixel size."""
LEGACY_PATCH='''
            -- MJH_TEAM_HEAD_FIT_V242: native SetNativeSize makes a 512px upload overflow the mask.
            local sourceHead = modelData.__Head or modelData.Head
            if type(sourceHead) == "string" and string.find(sourceHead, "#role_editor/head_", 1, true) == 1 then
                local mask = comData.imgHead.transform.parent:GetComponent("RectTransform")
                local size = 128
                if mask and mask.rect.width > 0 and mask.rect.height > 0 then
                    size = math.max(mask.rect.width, mask.rect.height)
                end
                comData.imgHead.rectTransform.sizeDelta = DRCSRef.Vec2(size, size)
                comData.imgHead.rectTransform.anchoredPosition = DRCSRef.Vec2(0, 0)
                comData.imgHead.transform.localScale = DRCSRef.Vec3One
            end
'''
# Imports deliberately replace filenames with a content digest. Detect the
# custom head by its resource namespace in this Head-only rendering path.
PATCH=LEGACY_PATCH.replace('MJH_TEAM_HEAD_FIT_V242','MJH_TEAM_HEAD_FIT_V245').replace('"#role_editor/head_"','"#role_editor/"')
PATCH=PATCH.replace('                local mask','''                local headRect = comData.imgHead.rectTransform
                if not comData.mjhHeadOriginalTransform then
                    comData.mjhHeadOriginalTransform = {pos=headRect.anchoredPosition, scale=headRect.localScale}
                end
                local mask''')
# Match the outer branch only; the nested mask/transform checks stay intact.
PATCH=PATCH.rsplit('            end\n',1)[0]+'''            else
                local originalHead = comData.mjhHeadOriginalTransform
                if originalHead then
                    comData.imgHead.rectTransform.anchoredPosition = originalHead.pos
                    comData.imgHead.rectTransform.localScale = originalHead.scale
                    comData.mjhHeadOriginalTransform = nil
                end
            end
'''

def patch(text):
 anchor='comData.imgHead:SetNativeSize()'
 if text.count(anchor)!=1:raise ValueError('队伍头像尺寸修复入口不兼容，未写入')
 if 'MJH_TEAM_HEAD_FIT_V245' in text:
  if text.count(PATCH)!=1 or text.count('MJH_TEAM_HEAD_FIT_')!=1:raise ValueError('队伍头像尺寸修复已被外部修改，未写入')
  return text
 if 'MJH_TEAM_HEAD_FIT_' in text:
  if text.count(LEGACY_PATCH)!=1 or text.count('MJH_TEAM_HEAD_FIT_')!=1:raise ValueError('旧队伍头像尺寸修复已被外部修改，未写入')
  return text.replace(LEGACY_PATCH,PATCH,1)
 return text.replace(anchor,anchor+PATCH,1)

def repair(data):
 from client_config import Assets
 a=Assets(data);before=a.script('TeamListUI.lua');after=patch(before)
 return data if after==before else a.replace_script('TeamListUI.lua',after)
