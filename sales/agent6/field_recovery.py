"""Merge a targeted field repair with saved, source-validated observations."""
import copy
from . import schema


def merge(saved, old_evidence, repaired, evidence, fields):
    allowed=set(fields)&set(schema.FIELDS)
    pool=copy.deepcopy(evidence)
    mapping={}
    for old in old_evidence:
        match=next((e for e in pool if all(e.get(k)==old.get(k)
                   for k in ('result_id','url','hash','offset','original','text'))),None)
        if match is None:
            match={**copy.deepcopy(old),'id':'retained:'+str(len(pool))}
            # Segment IDs from the earlier inference are not reused as new IDs.
            match.pop('segments',None)
            pool.append(match)
        mapping[old['id']]=match['id']
    def ref(value):
        if value is None:return None
        return {**value,'id':mapping.get(value['id'],value['id'])}
    retained=copy.deepcopy(saved)
    retained['kind_ref']=ref(retained.get('kind_ref'))
    retained['facts']=[{**f,'ref':ref(f['ref'])} for f in retained.get('facts',[])]
    new=[f for f in (repaired or {}).get('facts',[]) if f.get('field') in allowed]
    replaced={f['field'] for f in new}
    facts=[f for f in retained['facts'] if f['field'] not in replaced]+new
    raw={k:retained[k] for k in ('result_id','kind','kind_ref','hypothesis')}
    raw.update(facts=facts[:12],missing=[f for f in dict.fromkeys(retained.get('missing',[])) if f not in replaced][:8])
    # Revalidate every retained and repaired fact, including cross-result/hash
    # checks. A field repair cannot overwrite the original commercial direction.
    checked,errors=schema.validate_fields(raw,{'task':schema.READ,
        'result_ids':[raw['result_id']],'evidence':pool})
    out=checked['analyses'][0]
    unresolved=[e for e in saved.get('field_errors',[]) if e.get('field') not in replaced]
    out['field_errors']=unresolved+errors
    out['missing']=list(dict.fromkeys(out['missing']+[e['field'] for e in unresolved if e.get('field')]))
    return out,pool
