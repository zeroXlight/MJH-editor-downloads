function MJHPetEmbattle:MJHPetData()
    -- Scroll cell indices in the native UI start at zero.
    local pets=CardsUpgradeDataManager:GetInstance():GetPets() or {}
    local cells={}
    for index,pet in ipairs(pets) do cells[index-1]=pet end
    return cells,#pets
end
function MJHPetEmbattle:MJHRefreshPetList()
    if not self.mjhPetActive then return end
    self.aiPetdata,self.PetsNum=self:MJHPetData()
    if not self.comScrollRect then return end
    local help=self.iCurToggleID==EmBattleSchemeType.EBST_Help or self.iCurToggleID==EmBattleSchemeType.EBST_ArenaHelp
    if help then
        self.comScrollRect.totalCount=(self.AssistTeammatesNums or 0)+self.PetsNum
        self:SortEmbattleRole()
        self.comScrollRect:RefillCells()
    end
end
local mjhPetOnEnable=MJHPetEmbattle.OnEnable
function MJHPetEmbattle:OnEnable(...)
    self.mjhPetActive=true
    if mjhPetOnEnable then mjhPetOnEnable(self,...) end
    -- Do not rerun RefreshUI(): it clears the wheel-war/final-battle context
    -- and makes the native exit button omit the wheel-war cancellation RPC.
    self:AddEventListener('UPDATE_CARDSUPGRADE_UI',function() self:MJHRefreshPetList() end)
    SendRequestRolePetCardOperate(RPCRT_PET_CARD,RPCOT_REQ_DATA,0,0)
end
local mjhPetOnDisable=MJHPetEmbattle.OnDisable
function MJHPetEmbattle:OnDisable(...)
    self.mjhPetActive=false
    self:RemoveEventListener('UPDATE_CARDSUPGRADE_UI')
    if mjhPetOnDisable then return mjhPetOnDisable(self,...) end
end
local mjhPetShowList=MJHPetEmbattle.ShowPetList
function MJHPetEmbattle:ShowPetList(show)
    if not show then return mjhPetShowList(self,show) end
    self.aiPetdata,self.PetsNum=self:MJHPetData()
    self.comScrollRect.totalCount=(self.AssistTeammatesNums or 0)+self.PetsNum
    self:SortEmbattleRole()
    self.comScrollRect:RefillCells()
end
local mjhPetClose=MJHPetEmbattle.CloseUI
function MJHPetEmbattle:CloseUI(...)
    -- Ignore late queued pet responses as soon as closing begins.
    self.mjhPetActive=false
    return mjhPetClose(self,...)
end
