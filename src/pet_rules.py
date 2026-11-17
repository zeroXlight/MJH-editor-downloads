"""Pet form costs and the one-time native-save testing allowance."""
from fractions import Fraction
from feature_save import NativeSave,record,u32
from meridian_resource import increase

# Private, nonexpiring resource flag. It travels with a copied save, unlike an
# editor-side receipt, and never enters any of the game's visible currencies.
GRANT_MARKER=0x00E22213

def unlock_cost(rank):
    if type(rank) is not int or not 1<=rank<=7:raise ValueError('未知宠物品质')
    return 1000*(1<<(rank-1))

def upgrade_cost(current_level):
    if type(current_level) is not int or not 1<=current_level<10:raise ValueError('宠物等级不在可升级范围')
    value=Fraction(1000*3**current_level,2**current_level)
    return (value.numerator+value.denominator-1)//value.denominator

def grant_initial(data):
    save=NativeSave(data)
    rows=save.indexed(61,ordered=False)
    if GRANT_MARKER in rows:
        row=rows[GRANT_MARKER]
        if bytes(row)!=bytes(record(40,p16=GRANT_MARKER,p20=GRANT_MARKER,p24=1)):
            raise ValueError('宠物首次赠送标记被其他数据占用，未修改')
        return data,False
    increase(save,30000)
    rows[GRANT_MARKER]=record(40,p16=GRANT_MARKER,p20=GRANT_MARKER,p24=1)
    save.tables[61]=[rows[k] for k in sorted(rows)]
    return save.bytes(),True
