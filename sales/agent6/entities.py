"""Reversible company dossier projection over immutable research records.

Never merge by name, source publisher, social profile or an AI-proposed VAT.
The projection has no writes: every link exposes the records and evidence that
justify it. Removing/correcting a claim rebuilds the view without losing history.
Request-level decisions, contact state and facts remain attached to their source.
"""
import re
import json
from collections import defaultdict
from sales.db import domain,digest
from . import canonical_flow

PLATFORMS={'linkedin.com','instagram.com','facebook.com','x.com','twitter.com',
           'youtube.com','tiktok.com','reddit.com','mastodon.social','bsky.app','indeed.com','careerjet.it'}


def vat(value):
    """Italian public business identifier, syntax/check digit, not registry lookup."""
    text=re.sub(r'\s','',str(value or '')).upper()
    if not re.fullmatch(r'IT\d{11}',text):return None
    numbers=[int(n) for n in text[2:]]
    if len(set(numbers))==1:return None
    total=sum(numbers[:10:2])+sum(2*n if n<5 else 2*n-9 for n in numbers[1:10:2])
    return text if (10-total%10)%10==numbers[-1] else None


def anchor(row):
    b=row['body'];identity=b.get('identity') or {};host=domain(b.get('official_domain') or '')
    if not b.get('identity_verified') or not host or any(host==p or host.endswith('.'+p) for p in PLATFORMS):
        return {'domain':None,'legal_id':None,'proofs':[]}
    legal=vat(identity.get('legal_id'));proofs=[]
    if legal and not identity.get('legal_id_conflicts'):
        for f in identity.get('legal_id_evidence') or []:
            if (f.get('original') and domain(f.get('url') or '')==host and f.get('checked_at')
                and f.get('content_hash') and f.get('method') in ('owned_organization_schema','owned_legal_text')
                and vat(f.get('legal_id'))==legal
                and legal[2:] in re.sub(r'\s','',str(f.get('quote') or ''))):proofs.append(f)
    return {'domain':host,'legal_id':legal if proofs else None,'proofs':proofs}


def index(rows):
    anchors={r['id']:anchor(r) for r in rows};by_domain=defaultdict(set)
    for a in anchors.values():
        if a['domain'] and a['legal_id']:by_domain[a['domain']].add(a['legal_id'])
    mapping={};groups=defaultdict(list);links={}
    for r in rows:
        a=anchors[r['id']];host=a['domain'];ids=by_domain[host]
        if host and len(ids)>1:
            # A reused/shared domain with conflicting legal identities cannot
            # bridge two businesses through an older record without a VAT.
            raw='conflict:'+host+':'+(a['legal_id'] or r['request_key'])
            reason='conflicting_legal_identities_same_domain'
        elif host:
            raw='vat:'+next(iter(ids)) if ids else 'domain:'+host
            reason='same_published_legal_id' if ids else 'same_verified_official_domain'
        else:
            raw='request:'+r['request_key'];reason='unresolved_subject_no_company_merge'
        key=digest('entity-view:'+raw);mapping[r['id']]=key;groups[key].append(r)
        links[r['id']]={'record_id':r['id'],'campaign_id':r['campaign_id'],'request_key':r['request_key'],
            'domain':host,'legal_id':a['legal_id'],'basis':reason,'proofs':a['proofs'],
            'identity_source':(r['body'].get('identity') or {}).get('source_url') or r['body'].get('official_domain'),
            'identity_checked_at':r['body'].get('checked_at')}
    return {'record_keys':mapping,'groups':dict(groups),'links':links}


def dossier(graph,rid):
    key=graph['record_keys'][rid];rows=graph['groups'][key];requests=defaultdict(list)
    for r in rows:requests[r['request_key']].append(r)
    signals=[];proofs=[];seen=set()
    for request_key,versions in requests.items():
        ordered=sorted(versions,key=lambda r:(r['updated_at'],r['id']),reverse=True)
        current=next((r for r in ordered if r['body'].get('original')),ordered[0]);b=current['body']
        signals.append({'record_id':current['id'],'request_key':request_key,'campaigns':sorted({r['campaign_id'] for r in versions}),
            'flows':sorted({canonical_flow(f) for r in versions for f in r['body'].get('flows',[r['flow']])}),
            'saved_state':current['state'],'opportunity_type':b.get('opportunity_type'),
            'url':b['url'],'title':b.get('title'),'reason':b.get('reason'),'checked_at':b.get('checked_at'),
            'original':bool(b.get('original')),'identity_verified':bool(b.get('identity_verified'))})
        for r in versions:
            for f in r['body'].get('facts',[]):
                signature=(r['id'],f.get('document_id'),f.get('url'),f.get('field'),f.get('quote'))
                if signature in seen:continue
                seen.add(signature);proofs.append({**f,'record_id':r['id'],'campaign_id':r['campaign_id'],'flow':r['flow']})
    return {'key':key,'names':sorted({r['body']['entity_name'] for r in rows if r['body'].get('entity_name')}),
        'domains':sorted({graph['links'][r['id']]['domain'] for r in rows}-{None}),
        'flows':sorted({f for s in signals for f in s['flows']}),'signals':signals,'evidence':proofs,
        'links':[graph['links'][r['id']] for r in rows],
        'qualification':'per_request_no_automatic_promotion_from_combined_evidence',
        'basis':'read_only_reversible_projection_no_historical_rewrite'}


def group_worklist(items,graph,view):
    """One visible business per selected view; keep all request actions separate."""
    grouped=defaultdict(list)
    for item in items:grouped[graph['record_keys'][item['id']]].append(item)
    out=[]
    buckets={'contacted':0,'replied':0,'proposal':0,'won':0,'lost':0,'verified':1,'potential':2,'review':3,'new':4,'excluded':5}
    for key,choices in grouped.items():
        # A filter on a request must select a matching representative, never
        # display an unrelated stronger request in its place.
        matches=[i for i in choices if i['worklist']['bucket']==view or view=='ready' and i['worklist']['bucket'] in ('verified','potential') or view=='all' and i['worklist']['bucket']!='excluded']
        r=min(matches or choices,key=lambda i:(buckets.get(i['worklist']['bucket'],9),-i['id']))
        d=dossier(graph,r['id'])
        out.append({**r,'company_dossier':{k:d[k] for k in ('key','names','domains','flows','signals','basis')},'body':{**r['body'],'flows':d['flows']},
            'worklist':{**r['worklist'],'company_key':key,'request_count':len(d['signals']),
                'matching_requests':len(matches),'campaigns':sorted({c for s in d['signals'] for c in s['campaigns']})}})
    return out


def commercial_hold(c,body):
    """Resolve known exclusions/contact history across proven company aliases.

    Called within the caller's transaction. No entity IDs, decisions or CRM
    records are merged or rewritten. A new proof may link an alias, but never
    revoke an explicit exclusion or silently create a second outreach target.
    """
    from .memory import request_key
    rows=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT * FROM agent6_records')]
    candidate={'id':-1,'campaign_id':None,'request_key':request_key(body),'body':body}
    graph=index(rows+[candidate]);linked=graph['groups'][graph['record_keys'][-1]]
    ids={r['id'] for r in linked if r['id']!=-1};domains={graph['links'][r['id']]['domain'] for r in linked}-{None}
    exclusions={};contacted=False
    for f in c.execute('SELECT record_id,kind FROM agent6_feedback ORDER BY id'):
        if f['record_id'] not in ids:continue
        if f['kind'] in ('not_interesting','restore'):exclusions[graph['record_keys'][f['record_id']]]=f['kind']
        if f['kind'] in ('contacted','replied','proposal','won','lost'):contacted=True
    if 'not_interesting' in exclusions.values():return 'Esclusione manuale conservata per la stessa azienda verificata.'
    for r in c.execute('SELECT domain,do_not_contact,prior_contacted FROM companies'):
        if r['domain'] not in domains:continue
        if r['do_not_contact']:return 'Non contattare: esclusione registrata su un dominio collegato alla stessa azienda.'
        contacted=contacted or bool(r['prior_contacted'])
    for r in c.execute("SELECT c.domain FROM prospects p JOIN companies c ON c.id=p.company_id WHERE p.stage IN ('contacted','replied','proposal','won','lost')"):
        if r['domain'] in domains:contacted=True
    return 'Azienda già contattata o gestita: nuove prove conservate nello storico.' if contacted else None
