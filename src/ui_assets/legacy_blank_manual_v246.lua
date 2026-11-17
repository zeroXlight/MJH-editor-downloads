-- MJH_BLANK_MANUAL_V246
do
    function CLASS:MakeSecret()
        local manager = MartialDataManager:GetInstance()
        if not self.dynData or not self.typeData or not manager:MartialCouldMake(self.typeData) then
            return
        end
        local martialID = self.dynData.uiID
        local function submit()
            if not self.dynData or self.dynData.uiID ~= martialID then return end
            if PlayerSetDataManager:GetInstance():GetMakeMartialSecretBook() < 1 then
                SystemUICall:GetInstance():Toast('空白秘籍不足，请前往杭州本杰明商店购买（1铜币/本，每个游戏月限20本）。')
                return
            end
            SendClickMakeMartialSecret(martialID)
        end
        local itemnum = PlayerSetDataManager:GetInstance():GetMakeMartialSecretBook()
        if itemnum < 1 then
            SystemUICall:GetInstance():Toast('空白秘籍不足，请前往杭州本杰明商店购买（1铜币/本，每个游戏月限20本）。')
            return
        end
        OpenWindowImmediately('GeneralBoxUI', {
            GeneralBoxType.COSTITEM_TIP,
            {
                title = '抄录武学',
                text = string.format(GetLanguageByID(730009), GetLanguageByID(self.typeData.NameID)),
                ItemID = ID_ITEM_MakeMartialSceret,
                ItemNum = itemnum,
                ItemCost = 1,
            },
            submit,
        })
    end
end
-- MJH_BLANK_MANUAL_END
