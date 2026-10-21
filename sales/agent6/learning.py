"""Read-only operational learning with stable, inspectable strategy families.

No domain bans, predictive probabilities or promotion rules. Technical errors
measure reliability and cost; they do not imply commercial irrelevance.
"""
import json
import re
from collections import defaultdict, Counter
from .commercial_policy import positive_query, REQUEST, EXTERNAL
from . import canonical_flow


def contradicted_negative(record):
    """Read-time reliability guard for old decisions; never rewrite history."""
    if record.get('state')=='REJECTED' and record.get('commercial_fit',{}).get('source_role')=='large_group':
        from sales.commercial.target_fit import GROUP,group_evidence
        docs=[d['text'] for d in record.get('documents',[]) if d.get('original') and d.get('text')]
        mentions=[t for t in docs if GROUP.search(t)]
        if mentions and all(not group_evidence(t,record.get('entity_name')) and
            re.search(r'partner|rivenditor|fornitor|distribut',t,re.I) for t in mentions):return True
    if record.get('state')!='REJECTED' or record.get('kind') not in ('SUPPLIER_OFFER','EDITORIAL','EMPLOYEE_JOB','COMPLETED_PROJECT'):return False
    from .signals import extract_signals
    return any(s['type'] in ('collaboration_invitation','explicit_project_request')
        for doc in record.get('documents',[]) if doc.get('original')
        for s in extract_signals(doc))


def strategy_id(query, flow):
    flow=canonical_flow(flow)
    text=positive_query(query or '').casefold()
    from .social import platform
    sites=re.findall(r'(?<!\S)site:([^\s()]+)',text)
    platforms={platform('https://'+site) for site in sites}-{None}
    channel='linkedin' if 'linkedin.com' in platforms else 'social' if platforms else 'open_web'
    if REQUEST.search(text) and EXTERNAL.search(text):intent='external_invitation'
    elif REQUEST.search(text):intent='project_request'
    elif re.search(r'nuov[oaie] (?:prodott|mercat|serviz)|espansion|launch|rebrand|new (?:product|market)|migrazion',text):intent='business_change'
    elif re.search(r'trasformazione digitale|digital transformation|incentiv|funding|finanziament',text):intent='digital_topic'
    elif re.search(r'portfolio|case stud',text):intent='portfolio'
    else:intent='exploration'
    services=[]
    for key,pattern in [('ecommerce',r'e.?commerce|woocommerce|shopify|magento'),('webapp',r'\bMVP\b|web.?app|software|gestionale|\bERP\b|\bCRM\b'),('website',r'wordpress|frontend|front.end|sit[oi] web|web design|website')]:
        if re.search(pattern,text,re.I):services.append(key)
    return ':'.join((flow or 'UNKNOWN',channel,intent,'+'.join(services) or 'unspecified'))


def summarize(events, reviews, records,corrections=None):
    """Aggregate real executions and latest evidence/outcomes, not plan prose."""
    from .record_views import current_original
    versions=defaultdict(list)
    for rid,body in records.items():
        if body.get('request_key'):versions[body['request_key']].append({'id':rid,'body':body})
    preserved={}
    for values in versions.values():
        selected,failure=current_original(sorted(values,key=lambda r:r['id'],reverse=True))
        if failure:preserved[failure['record_id']]=selected['id']
    groups=defaultdict(lambda:{'queries':set(),'domains':set(),'labels':set(),'originals':set(),'relevant':set(),'verified':set(),'potential':set(),
        'technical_errors':set(),'rejections':set(),'policy_exclusions':0,'results':0,'ai_calls':0,'ai_cost':0.0,'feedback':{},'quality':{},'uncertain':set(),'manual_irrelevant':set(),'promising':set(),'attribution_errors':set(),'completed_audits':set()})
    def group(flow, body):
        flow=canonical_flow(flow)
        key=strategy_id(body.get('query'),flow)
        g=groups[key];g['flow']=flow;g['labels'].add(body.get('strategy') or 'unattributed')
        return g
    # One final evaluation per request, even if it appeared in many campaigns.
    decisions=set()
    for row in sorted(events,key=lambda r:r['id'],reverse=True):
        b=json.loads(row['body']) if isinstance(row['body'],str) else row['body'];flow=row['flow']
        if not b.get('query'):continue
        g=group(flow,b)
        if row['kind']=='query':
            g['queries'].add((row['campaign_id'],' '.join(re.findall(r'\w+',b['query'].casefold()))))
            g['results']+=b.get('results',0);g['policy_exclusions']+=len(b.get('policy_rejections',[]))
        elif row['kind']=='model':
            # Cache reads and denied reservations are not provider calls.
            if b.get('status') in ('completed','invalid','error','timeout','cancelled'):
                g['ai_calls']+=1;g['ai_cost']+=b.get('estimated_cost') or 0
        elif row['kind']=='decision':
            record=records.get(b.get('record_id'),{})
            key=record.get('request_key') or b.get('request_key') or str(b.get('record_id'))
            if b.get('record_id') in preserved:
                # Record the failed interpretation without erasing the valid
                # assessment of the identical original from commercial memory.
                if b.get('technical_error'):g['technical_errors'].add(key)
                continue
            if (flow,key) in decisions:continue
            decisions.add((flow,key));g['domains'].add(b.get('domain'))
            if record.get('original') or b.get('original'):g['originals'].add(key)
            from .completion import dossier
            if record.get('url') and dossier(record)['promising']:g['promising'].add(key)
            if record.get('identity_issues') or record.get('deterministic_completion',{}).get('superseded_entity') or contradicted_negative(record):g['attribution_errors'].add(key)
            if record.get('website_audit',{}).get('browser_status')=='COMPLETE':g['completed_audits'].add(key)
            if (corrections or {}).get(key,{}).get('relevance',{}).get('value')=='irrelevant':
                # Correcting an automatic attribution must never erase the
                # user's separate commercial judgment about that same lead.
                g['manual_irrelevant'].add(key);continue
            if b.get('technical_error'):g['technical_errors'].add(key);continue
            if b.get('semantic_conflict') or b.get('scope_exclusion') or contradicted_negative(record):
                g['uncertain'].add(key);continue
            if b['state'] in ('RELEVANT','POTENTIAL','VERIFIED') and (record.get('original') or b.get('original')):g['relevant'].add(key)
            if key in g['originals'] and b['state']=='VERIFIED':g['verified'].add(key)
            if key in g['originals'] and b['state']=='POTENTIAL':g['potential'].add(key)
            if b['state']=='REJECTED':
                (g['rejections'] if b.get('negative_feedback_reliable') else g['uncertain']).add(key)
    # CRM and manual events share the same request key; latest state wins.
    for row in sorted(reviews,key=lambda r:r['created_at']):
        b=json.loads(row['body']) if isinstance(row['body'],str) else row['body']
        if not b.get('query'):continue
        key=b.get('request_key') or str(row['record_id'])
        target='quality' if row['kind'] in ('quality_confirmed','false_positive') else 'feedback'
        group(row['flow'],b)[target][key]=row['kind']
    out=[]
    for key,g in groups.items():
        n=len(g['queries']);enough=n>=3
        # A bounded descriptive adjustment; unknowns/transport failures are not
        # negatives. Human outcomes remain visible, with a bounded preference.
        auto=(len(g['relevant'])+2*len(g['verified'])+.5*len(g['promising']-g['relevant'])-.5*(len(g['rejections'])+g['policy_exclusions']))/max(1,n) if enough else 0
        outcomes=Counter(g['feedback'].values());human=sum({'interesting':1,'not_interesting':-1,'contacted':.25,'replied':1,'proposal':1.5,'won':2,'lost':-.25,'restore':0}.get(v,0) for v in g['feedback'].values())/max(1,len(g['feedback']))
        quality=Counter(g['quality'].values());reviewed=len(g['quality'])
        human+=(quality['quality_confirmed']-quality['false_positive'])/max(1,reviewed)
        out.append({'strategy_id':key,'flow':g['flow'],'labels':sorted(g['labels']),'queries':n,'domains':len(g['domains']-{None}),
            'results':g['results'],'original_pages_read':len(g['originals']),'relevant':len(g['relevant']),'verified':len(g['verified']),'potential':len(g['potential']),
            'promising_dossiers':len(g['promising']),'attribution_errors':len(g['attribution_errors']),'completed_browser_audits':len(g['completed_audits']),
            'estimated_cost_per_qualified_dossier':round(g['ai_cost']/len(g['verified']|g['potential']),6) if g['verified']|g['potential'] else None,
            'ai_calls_per_qualified_dossier':g['ai_calls']/len(g['verified']|g['potential']) if g['verified']|g['potential'] else None,
            'technical_errors':len(g['technical_errors']),'verified_rejections':len(g['rejections']),'uncertain_decisions':len(g['uncertain']),'manually_irrelevant':len(g['manual_irrelevant']),
            'policy_exclusions':g['policy_exclusions'],'ai_calls':g['ai_calls'],'estimated_ai_cost':round(g['ai_cost'],8),
            'human_reviews':len(g['feedback']),'outcomes':dict(outcomes),'sample_sufficient':enough,
            'priority_adjustment':round(max(-3,min(3,auto))+max(-2,min(2,human)),3),
            'rejected_by_user':outcomes['not_interesting'],'quality_reviews':reviewed,'quality_sample_sufficient':reviewed>=20,
            'false_positives':quality['false_positive'] if reviewed else None,'precision':quality['quality_confirmed']/reviewed if reviewed else None,
            'basis':'observed_evidence_and_manual_outcomes_not_sales_probability'})
    return sorted(out,key=lambda s:(s['flow'],s['strategy_id']))
