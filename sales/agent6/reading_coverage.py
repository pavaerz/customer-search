"""Prefer the complete isolated original when the EXISTING input cap permits.

No extra inference, budget increase, source joining or changed qualification.
Do not mistake a fetched page for evidence actually presented to the model.
"""
from sales.db import digest
from sales.commercial.token_count import estimate


def expand(payload, packet, unit, config):
    # Preserve existing scoped selectors and historical references when they
    # already fit. Structured jobs and editorial/discussion units have additional
    # description/author boundaries; their specialised selectors stay authoritative.
    try:
        if estimate(payload,config)['tokens']<=config['max_input_tokens']:return payload
    except (ImportError,OSError,ValueError):return payload
    if unit.get('origin')=='JobPosting' or unit.get('discussion_scope') or (
            payload.get('flow')=='NEWS' and not payload.get('identity',{}).get('verified')):
        return payload
    payload={**payload,'reading_coverage_version':1}
    text=unit['text'];document_id=unit.get('document_id',packet['document_id'])
    ranges=unit.get('allowed_ranges') or [[0,len(text)]]
    if unit.get('discussion_scope'):
        # The established discussion selector has additional author boundaries.
        return payload
    if len(text.encode())>config['max_input_tokens']*4:return payload
    full=[]
    for index,(a,b) in enumerate(ranges):
        if not 0<=a<b<=len(text):return payload
        part=text[a:b]
        full.append({'id':'complete-source-'+str(index),'result_id':payload['unit_id'],
            'unit_id':payload['unit_id'],'url':packet['final_url'],'original':True,
            'text':part,'hash':digest(part),'document_id':document_id,
            'offset':unit.get('offset',0)+a,'checked_at':packet['observed_at']})
    # Replace only this unit's original excerpts. Keep distinct owner metadata,
    # response controls, measured observations and any attributed parent source.
    keep=[e for e in payload['evidence'] if not (
        e.get('document_id')==document_id and e['url']==packet['final_url']
        and e.get('origin') not in ('original_metadata','browser_or_html_measurement','original_response_control'))]
    candidate={**payload,'evidence':keep+full,
        'source_coverage':{'document_id':document_id,'complete_selected_unit':True,
            'scope':'isolated_original_unit_not_entire_site','ranges':[[unit.get('offset',0)+a,unit.get('offset',0)+b] for a,b in ranges]}}
    try:
        from .grounding import segments
        complete=all(not remainders(e,segments(e)).strip() for e in full)
        if complete and estimate(candidate,config)['tokens']<=config['max_input_tokens']:return candidate
        # Spend remaining INPUT capacity on this destination, not more calls.
        # Respect the same local-unit and editorial boundaries as normal reading.
        from .evidence import passages
        ceiling=min(len(text.encode()),config['max_input_tokens'])
        essential=[e for e in keep if e.get('url')==packet['final_url']]
        for allowance in list(range(ceiling, 1499, -250))+[1500]:
            parts=passages(packet,unit,allowance,
                source_content=payload.get('flow')=='NEWS' and not payload.get('identity',{}).get('verified'))
            for i,e in enumerate(parts):
                e.update(id='expanded-source-'+str(i),result_id=payload['unit_id'],unit_id=payload['unit_id'])
            attempt={**payload,'evidence':keep+parts,'source_coverage':{
                'document_id':document_id,'complete_selected_unit':False,
                'scope':'isolated_original_excerpts','ranges':[[e['offset'],e['offset']+len(e['text'])] for e in parts]}}
            if estimate(attempt,config)['tokens']<=config['max_input_tokens']:return attempt
            focused={**attempt,'evidence':essential+parts,
                'source_coverage':{**attempt['source_coverage'],'parent_excerpts_included':False}}
            if estimate(focused,config)['tokens']<=config['max_input_tokens']:return focused
    except (ImportError,OSError,ValueError):pass
    return payload


def measured(packet, unit, evidence):
    """Coverage of the returned inference evidence, never of the HTTP download."""
    doc=unit.get('document_id',packet['document_id']);offset=unit.get('offset',0)
    wanted=[[offset+a,offset+b] for a,b in (unit.get('allowed_ranges') or [[0,len(unit['text'])]])]
    from .grounding import segments
    ranges=sorted([e['offset']+s['start'],e['offset']+s['end']] for e in evidence
                  if e.get('document_id')==doc and e.get('url')==packet['final_url'] for s in segments(e))
    merged=[]
    for a,b in ranges:
        if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    covered={i for a,b in merged for i in range(a,b)}
    complete=bool(merged) and all(i in covered or unit['text'][i-offset].isspace() or unit['text'][i-offset] in ';|'
        for a,b in wanted for i in range(a,b))
    return {'document_id':doc,'complete_selected_unit':complete,
            'scope':'isolated_original_unit_not_entire_site' if complete else 'isolated_original_excerpts',
            'ranges':merged,'basis':'returned_inference_evidence_not_downloaded_page'}


def remainders(evidence, spans):
    """Characters not transmitted by the selectable-segment projection."""
    covered=set()
    for s in spans:covered.update(range(s['start'],s['end']))
    return ''.join(c for i,c in enumerate(evidence['text']) if i not in covered and c not in ';|')
