"""Deterministic evidence selection, original spans and explicit omissions (3B.2).

No AI summaries, network or DB access. Canonical channels take precedence over
legacy flattened text. Boilerplate is never allowed to displace a request.
"""
from sales.db import domain
import json
import re
from collections import Counter
from .context import ASK,EXTERNAL,EMPLOYEE
from .intent import request_clause,NEGATED,SELLER_DIRECTION
from .relevance import technical_request

BOILER=re.compile(r'^(?:home|menu|contatti|scopri tutto|vai al contenuto|pagina principale|accetta|rifiuta|cookie|privacy|copyright|×|seguici|leggi tutto)(?:\b|$)|@context|function\s*\(|^\s*[.#][\w-]+\s*\{|^var\s+',re.I)
DATE=re.compile(r'\b20\d\d[-/]\d\d[-/]\d\d\b|scadenza|candidature aperte|annuncio scaduto|posizione chiusa|ricerca conclusa|applications closed',re.I)

def collect(candidate_id,documents,result=None):
    from .ai_schema import fingerprint,minimize,safe_url
    result=result or {};records=[];excluded=Counter();seen=set()
    selected=next((b for b in result.get('request_blocks',[]) if b.get('id')==result.get('selected_block')),None)
    decisive=[e for e in result.get('evidence',[]) if e.get('quote') and e.get('kind')!='measurement']
    for doc in documents:
        details=doc.get('details') or {}
        if isinstance(details,str):
            try:details=json.loads(details)
            except ValueError:details={}
        channels=doc.get('evidence_channels') or details.get('evidence_channels') or {'text':{'text':doc.get('text','')}}
        for channel,data in channels.items():
            text=data.get('text','')
            if not isinstance(text,str):continue
            units=data.get('units') or [{'text':m.group(),'start':m.start(),'end':m.end()} for m in re.finditer(r'[^\n]+',text)]
            source_hash=fingerprint(text);url=doc.get('url','')
            for index,u in enumerate(units):
                raw=u['text'];start=u['start'];end=u.get('end',start+len(raw))
                if not raw.strip():continue
                owner=(result.get('identity') or {}).get('name') or result.get('company')
                identity_footer=bool(result.get('identity',{}).get('identity_status')=='verified' and not result.get('actor_attribution') and owner and owner.casefold() in raw.casefold() and len(raw)<600 and not re.search(r'[{}]|function|@context',raw,re.I) and re.search(r'p\.?iva|partita iva|s\.?r\.?l|copyright|©',raw,re.I) and domain(url)==domain(result.get('identity',{}).get('website') or result.get('website') or ''))
                if ((u.get('excluded') or BOILER.search(raw)) and not identity_footer) or (len(raw)>4000 and re.search(r'[{};].*[{};]',raw)):
                    excluded['boilerplate']+=1;continue
                actor=(result.get('identity') or {}).get('name') or result.get('company')
                identity_span=bool(result.get('identity',{}).get('identity_status')=='verified' and not result.get('actor_attribution') and actor and actor.casefold() in raw.casefold() and domain(url)==domain((result.get('identity') or {}).get('website') or result.get('website') or ''))
                if result.get('demand_assessment',{}).get('version')=='5.1' and selected and url==selected.get('url') and selected.get('channel','').startswith('job:') and channel!=selected['channel'] and not identity_span:
                    excluded['outside_selected_request_channel']+=1;continue
                if selected and url==selected.get('url') and channel==selected.get('channel') and not (selected['start']<=start<selected['end']) and not identity_span:
                    excluded['outside_selected_request']+=1;continue
                if selected and url!=selected.get('url') and result.get('actor_attribution'):
                    excluded['publisher_not_requesting_actor']+=1;continue
                actor=(result.get('identity') or {}).get('name') or result.get('company')
                identity_span=bool(result.get('identity',{}).get('identity_status')=='verified' and not result.get('actor_attribution') and actor and actor.casefold() in raw.casefold() and domain(url)==domain((result.get('identity') or {}).get('website') or result.get('website') or ''))
                quote=minimize(raw).strip()
                if quote.casefold() in seen:excluded['duplicate']+=1;continue
                seen.add(quote.casefold())
                exact=any(e.get('url')==url and e.get('quote')==raw for e in decisive)
                request=bool(request_clause(raw) and technical_request(raw))
                contradiction=bool(NEGATED.search(raw) or EMPLOYEE.search(raw) or SELLER_DIRECTION.search(raw) or re.search(r'scadut|chius[aeo]|non retribuit|applications closed',raw,re.I))
                identity=bool((result.get('company') and str(result['company']).casefold() in raw.casefold()) or re.search(r'partita iva|p\.iva|ragione sociale',raw,re.I) or (selected and start==selected['start']))
                # Nearby units contribute only within the same bounded request.
                context=bool(selected and selected['start']<=start<selected['end'])
                from .target_fit import counterevidence,useful_ai_text
                target_context=result.get('engine')=='WEBSITE_REBUILD' and useful_ai_text(raw)
                target_counter=result.get('engine')=='WEBSITE_REBUILD' and bool(counterevidence(raw))
                contradiction=contradiction or target_counter
                roles=[]
                if identity:roles.append('identity')
                if request:roles.append('request')
                if contradiction:roles.append('counterevidence')
                if DATE.search(raw):roles.append('temporal')
                if EXTERNAL.search(raw) or re.search(r'compenso|retribuit|equity|budget',raw,re.I):roles.append('relationship')
                if target_context:roles.append('commercial_target')
                if not roles:roles=['context' if context else 'accessory']
                technical_recipient=bool(context and technical_request(raw) and re.search(r'sviluppator|developer|team tech|frontend|wordpress|prestashop',raw,re.I))
                if technical_recipient:roles.append('technical_recipient')
                priority=140 if identity_span else 125 if technical_recipient else 130 if target_counter else 118 if target_context else 120 if request else 115 if contradiction else 110 if identity else 95 if exact else 90 if roles!=['accessory'] else 10
                if result.get('demand_assessment',{}).get('version')=='5.1':
                    from .demand import STANDING,ASK as demand_ask,WEB
                    if demand_ask.search(raw) and WEB.search(raw):
                        request=True;roles.append('request')
                    if identity_span:priority=110
                    if request:priority=145
                    if technical_recipient:priority=135
                    if context and STANDING.search(raw) and EXTERNAL.search(raw):
                        priority=145;roles.append('request')
                indexed=doc.get('acquisition')=='search_index' 
                ident='EVIDENCE_'+fingerprint([str(candidate_id),doc.get('id'),url,channel,source_hash,start,end])[:20]
                records.append({'id':ident,'candidate_id':str(candidate_id),'document_id':str(doc.get('id','')),'url':safe_url(url),
                    'source_hash':source_hash,'text_hash':fingerprint(quote),'start':start,'end':end,'channel':channel,'text':quote,
                    'published_at':doc.get('published_at'),'acquired_at':doc.get('checked_at'),
                    'kind':'indexed_text' if indexed else 'text','original_verified':not indexed,
                    'source_type':'search_index' if indexed else 'publisher_page' if result.get('actor_attribution') else 'official_page' if (doc.get('official') or details.get('official')) and result.get('identity',{}).get('identity_status')=='verified' else 'saved_page',
                    'acquisition':doc.get('acquisition','saved_source'),'roles':roles,'rank':priority,
                    'section':selected.get('id') if context else None,'reliability':'indexed_hint' if indexed else 'saved_original',
                    'access_limit':details.get('access_limit'),'minimized':quote!=raw.strip()})
    # Preserve cross-unit counterproof (e.g. number then employee label) and
    # actual measurements separately from reconstructed prose or menu units.
    facts=list(result.get('target_fit',{}).get('counterevidence',[]))
    if result.get('browser',{}).get('completed'):
        facts += [f for f in result.get('evidence',[]) if f.get('kind')=='measurement']
    for fact in facts:
        raw=fact.get('quote','');url=fact.get('url');measured=fact.get('kind')=='measurement'
        doc=next((d for d in documents if d.get('url')==url and raw in d.get('text','')),None)
        if not raw or (not doc and not measured):continue
        quote=minimize(raw).strip()
        if quote.casefold() in seen:continue
        seen.add(quote.casefold());text=doc['text'] if doc else raw;start=text.index(raw)
        records.append({'id':'EVIDENCE_'+fingerprint([str(candidate_id),url,raw,'counter_or_measurement'])[:20],
          'candidate_id':str(candidate_id),'document_id':str((doc or {}).get('id','')),'url':safe_url(url),
          'source_hash':fingerprint(text),'text_hash':fingerprint(quote),'start':start,'end':start+len(raw),
          'channel':'measurement' if measured else 'text','text':quote,'kind':'measurement' if measured else 'text',
          'original_verified':True,'source_type':'saved_measurement' if measured else 'saved_page',
          'roles':['measurement'] if measured else ['counterevidence'],'rank':135,'acquisition':'saved_browser' if measured else 'saved_source',
          'published_at':None,'acquired_at':result.get('checked_at'),'minimized':quote!=raw})
    return sorted(records,key=lambda e:(-e['rank'],e['url'],e['start'])),excluded

def select(candidate_id,documents,max_chars=16000,result=None):
    records,excluded=collect(candidate_id,documents,result);selected=[];remaining=max_chars;omitted=[]
    for record in records:
        # Quotes are atomic: no cut through an explicit request to fit a budget.
        if len(record['text'])>remaining or len(selected)>=24:
            omitted.append({'id':record['id'],'reason':'evidence_budget','decisive':'request' in record['roles'] or 'counterevidence' in record['roles']});continue
        selected.append(record);remaining-=len(record['text'])
    metrics={'decisive_evidence_count':sum(bool(set(e['roles'])&{'request','counterevidence'}) for e in records),'evidence_available':len(records)+sum(excluded.values()),'evidence_selected':len(selected),
             'evidence_discarded':len(records)-len(selected)+sum(excluded.values()),'discard_reasons':dict(excluded),
             'omitted':omitted,'decisive_evidence_preserved':all(e in selected for e in records if 'request' in e['roles'] or 'counterevidence' in e['roles']),
             'boilerplate_ratio':0 if selected else None,'boilerplate_measurement':'deterministic_pattern_and_HTML_scope; not_human_precision','source_coverage':{'selected':len({e['url'] for e in selected}),'available':len({d.get('url') for d in documents})},
             'evidence_bundle_tokens':None,'token_measurement':'not_tokenized; UTF-8 byte upper bound at dispatch',
             'evidence_bundle_truncation_reason':'atomic_quotes_exceed_budget' if omitted else None,
             'status':'EVIDENCE_INSUFFICIENT' if not selected or any(e['decisive'] for e in omitted) else 'AVAILABLE'}
    return selected,metrics

def trim_to_payload(payload,system,max_tokens,metrics):
    """Whole payload UTF-8 upper bound; remove lowest-ranked quotes, visibly."""
    evidence=payload['evidence']
    size=lambda:len((system+json.dumps(payload,ensure_ascii=False)).encode())
    while evidence and size()>max_tokens:
        e=evidence.pop();decisive=bool(set(e.get('roles',[]))&{'request','counterevidence'})
        metrics['omitted'].append({'id':e['id'],'reason':'serialized_input_budget','decisive':decisive})
        if decisive:metrics['decisive_evidence_preserved']=False;metrics['status']='EVIDENCE_INSUFFICIENT'
        metrics['evidence_discarded']+=1;metrics['evidence_bundle_truncation_reason']='serialized_input_budget'
    metrics['evidence_selected']=len(evidence);metrics['source_coverage']['selected']=len({e['url'] for e in evidence})
    metrics['evidence_bundle_tokens_upper_bound']=size();return size()
