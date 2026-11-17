"""Native meridian balance, verified against the local 2065/32802 protocol.

Table 6 is the single native meridians record (56 bytes), not the inventory
resource counter. Its uint64 at offset 24 is shared by meridians and pets.
"""
import struct

MAX_BALANCE=(1<<63)-1

def balance(save):
    rows=save.tables[6]
    if len(rows)>1:raise ValueError('经脉存档有多个全局记录，已跳过')
    if not rows:return 0
    row=rows[0]
    if len(row)!=56 or any(row[:24]):
        raise ValueError('经脉记录布局不兼容，已跳过')
    value=struct.unpack_from('<Q',row,24)[0]
    if value>MAX_BALANCE:raise ValueError('经脉经验超出游戏整数范围，已跳过')
    return value

def increase(save,amount):
    if type(amount) is not int or amount<=0:raise ValueError('增加的经脉经验必须是正整数')
    before=balance(save)
    if before>MAX_BALANCE-amount:raise ValueError('增加后经脉经验会溢出，未修改')
    if not save.tables[6]:save.tables[6].append(bytearray(56))
    struct.pack_into('<Q',save.tables[6][0],24,before+amount)
    return before,before+amount
