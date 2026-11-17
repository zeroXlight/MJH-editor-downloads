"""Known native Lua defaults that have no matching protobuf wire field.

Only the exact no-op value is omittable. A nonzero bonus link must remain
visible to strict unknown-field checks; it cannot be silently discarded.
"""
def without_empty_defaults(table,row):
    result=dict(row)
    if table=='Martial' and type(result.get('BonusBaseMartialID')) is int and result['BonusBaseMartialID']==0:
        del result['BonusBaseMartialID']
    return result
