"""Rotating free discovery; no campaign request counter or paid fallback."""
import json
from html import unescape
import os
import re
import time
from datetime import datetime,timezone,timedelta
from urllib.parse import urlencode,urljoin,urlsplit
import xml.etree.ElementTree as ET
from .providers import api_json,canonical,blocked
from .research_store import SEEDS,PUBLIC_FEEDS
from .db import digest,now,encode,domain
from .extract import parse_page
from .research_rules import PRIORITY_REGIONS,ALLOWED_REGIONS
from .research_analysis import ResearchWeb,text_with_legal

from .research_strategies import TEMPLATES,SECTORS,SIGNAL,NOISE,strategies_for
from .research_funnel import Funnel
_last_search=0.0

def seed_campaign(rs,campaign):
    cid=campaign['id'];filters=campaign['filters'];regions=filters.get('regions') or ['Veneto']
    funnel=Funnel(rs)
    # Global news and grant feeds belong to source diagnostics, not customer campaigns.
    from .discovery_planner import Planner
    Planner(rs).initialize(campaign)
    funnel.fill(campaign)
    rs.event(cid,'feedback','Esplorazione distribuita tra strategie. Nessun risultato precedente usato come nuovo candidato.')

def search(rs,campaign,task,check):
    global _last_search
    payload={**task['payload'],'direct_channels':True,'strategy':task['strategy']};selected=rs.store.settings()['provider']
    from .discovery_relevance import subject_exclusion
    reason=subject_exclusion(payload.get('subject',''),payload.get('source_documents',[])) if payload.get('subject') and not payload.get('company_host') else None
    if reason:
        from .discovery_planner import Planner
        rs.event(campaign['id'],'acquisition_filter',reason,details={'query':payload['query'],'subject':payload['subject']})
        Planner(rs).observed(campaign,task,[],0,False)
        return {'urls':[],'new_urls':0}
    if selected=='serper':
        from .serper_provider import search as serper_search
        result,cache_hit=serper_search(rs.store,payload['query'],payload['page'],payload.get('period',''),check)
        capabilities={'paging':True,'time_range':True,'engines':['google via Serper']}
        fp=digest(encode([selected,payload['query'],payload['page'],payload.get('period','')]))
    else:
        base=os.getenv('SEARXNG_URL','').rstrip('/');p=urlsplit(base)
        if p.scheme!='http' or p.hostname not in ('localhost','127.0.0.1') or p.username or p.password:raise ValueError('SearXNG locale non configurato')
        from .discovery_control import search_capabilities
        capabilities=search_capabilities(rs.store,base)
        params={'q':payload['query'],'pageno':payload['page'],'format':'json','language':'it-IT','categories':'general','time_range':payload['period']}
        if not capabilities['time_range']:params.pop('time_range',None)
        if capabilities.get('engines'):params['engines']=','.join(capabilities['engines'])
        fp=digest(encode(params));key='v45:search:'+digest(base+'|'+fp+'|'+encode(capabilities.get('engines',[])))
        result=rs.store.cache_get(key,6)
        cache_hit=result is not None
        if result is None:
            while time.monotonic()<_last_search+2:check();time.sleep(.1)
            _last_search=time.monotonic()
            from .discovery_control import free_search
            def request():
                check();rs.store.reserve('searxng');return api_json(base+'/search?'+urlencode(params),timeout=25)
            result=free_search(rs.store,request,capabilities.get('engines',[]));check()
            if not isinstance(result,dict) or not isinstance(result.get('results'),list):raise ValueError('SearXNG: risposta non valida')
            rs.store.cache_set(key,result)
    errors=result.get('unresponsive_engines') or []
    if errors:rs.event(campaign['id'],'provider_warning','Alcuni motori non hanno risposto; procedo con le fonti disponibili.',details={'engines':errors})
    found=[];offered=[];new_count=0;discarded=[]
    outcomes={key:0 for key in ('invalid','not_relevant','suppressed','duplicate','candidate')}
    results=result['results']
    if task['strategy']=='companies' or payload.get('subject'):
        from .company_research import acquisition_rank
        results=sorted(results,key=lambda item:acquisition_rank(item,campaign['filters'].get('target','b2b'),payload.get('subject')) if isinstance(item,dict) else -1,reverse=True)
    elif task['strategy'] in ('partner','explicit'):
        from .direct_channels import visit_priority
        results=sorted(results,key=lambda item:visit_priority(item)[0] if isinstance(item,dict) else -10,reverse=True)
    for result_item in results:
        check()
        if not isinstance(result_item,dict):outcomes['invalid']+=1;continue
        try:url=canonical(result_item['url'])
        except (KeyError,ValueError,TypeError):outcomes['invalid']+=1;continue
        from .direct_channels import linkedin_notice,visit_priority
        if (blocked(url) and not linkedin_notice({**result_item,'url':url})) or NOISE.search(url):outcomes['not_relevant']+=1;continue
        from .prospect_scope import acquisition_exclusion
        reason=acquisition_exclusion({**result_item,'url':url},payload)
        if reason:
            outcomes['not_relevant']+=1
            discarded.append({'url':url,'reason':reason,'engines':result_item.get('engines',[])})
            continue
        if payload.get('followup_depth') and domain(url)!=domain(payload.get('evidence_url','')):outcomes['not_relevant']+=1;continue
        found.append(url)
        if rs.store.target_exclusion(url) or rs.suppressed({'website':url}):outcomes['suppressed']+=1;continue
        from .evaluation_policy import reconsideration,stamp
        reevaluate=reconsideration(rs.store,url,campaign['filters'])
        with rs.store.connect() as c:
            seen=c.execute('SELECT * FROM research_visited WHERE url=?',(url,)).fetchone()
            c.execute('INSERT INTO research_visited VALUES (?,?,?) ON CONFLICT(url) DO NOTHING',(url,now(),now()))
        engines=result_item.get('engines') or []
        provider=('Serper · ' if selected=='serper' else 'SearXNG · ')+', '.join(str(e) for e in engines)
        # Different pages on a company can carry genuinely new events. Candidate key includes URL.
        if reevaluate or payload.get('subject') or not seen or datetime.fromisoformat(seen['last_seen'])<datetime.now(timezone.utc)-timedelta(days=7):
            added=Funnel(rs).offer(campaign['id'],'candidate',task['strategy'],{'url':url,'evaluation_policy':stamp(campaign['filters']),'reevaluation':reevaluate,'title':result_item.get('title',''),'search_snippet':result_item.get('content',''),'acquisition_reason':visit_priority(result_item)[1] if task['strategy'] in ('partner','explicit') else None,'query':payload['query'],'query_page':payload.get('page',1),'source_url':payload.get('evidence_url') or next((d.get('url') for d in payload.get('source_documents',[]) if d.get('url')),url),'region':payload.get('region'),'provider':provider,'acquisition_provider':selected,'query_key':payload.get('query_key'),'company_stage':'identify' if task['strategy']=='companies' else payload.get('company_stage'),'followup_depth':payload.get('followup_depth',0),'strategy':task['strategy'],'filters':campaign['filters'],**{k:payload[k] for k in ('subject','source_documents','subject_quote','subject_method','evidence_url','official_link','company_stage','company_host','company_key','hypothesis','research_intent','root_query_key','investigation_question','alternative_source','direct_channels','search_hint') if k in payload}},'candidate-url:'+digest(url+payload.get('subject',''))+(':'+reevaluate['token'] if reevaluate else ''))
            new_count+=int(added)
            outcomes['candidate' if added else 'duplicate']+=1
            if added:
                offered.append(url)
                with rs.store.connect() as c:c.execute('UPDATE research_visited SET last_seen=? WHERE url=?',(now(),url))
        else:outcomes['duplicate']+=1
    if payload.get('query_key'):
        with rs.store.connect() as c:
            offered=list(dict.fromkeys(offered+[json.loads(r[0])['url'] for r in c.execute("SELECT payload FROM discovery_frontier WHERE campaign_id=? AND kind='candidate' AND json_extract(payload,'$.query_key')=?",(campaign['id'],payload['query_key']))]))
    if discarded:rs.event(campaign['id'],'acquisition_filter',f'{len(discarded)} risultati non aziendali esclusi prima della lettura.',details={'query':payload['query'],'discarded':discarded})
    result_hash=digest(encode(sorted(set(found))))
    with rs.store.connect() as c:
        duplicate_page=c.execute('SELECT 1 FROM research_query_memory WHERE query=? AND result_hash=?',(payload['query'],result_hash)).fetchone()
        c.execute('INSERT OR REPLACE INTO research_query_memory VALUES (?,?,?,?,?)',(fp,payload['query'],now(),result_hash,new_count))
    rs.event(campaign['id'],'discovery',f'{len(set(found))} URL, {new_count} nuovi candidati da verificare.',details={'query':payload['query'],'page':payload['page'],'strategy':task['strategy']})
    from .discovery_control import annotate
    from .discovery_planner import Planner
    annotate(new_urls=new_count, result_urls=len(set(found)), returned_urls=len(results), prefiltered=len(discarded), duplicates=max(0,len(set(found))-new_count), cache_hit=cache_hit, query=payload['query'],hypothesis=payload.get('hypothesis'))
    result_kind='known_results' if not new_count and outcomes['duplicate'] else 'empty' if not results else None
    annotate(acquisition_outcomes=outcomes,outcome='valid' if new_count else 'duplicate' if outcomes['duplicate'] else 'not_relevant',qualified=False)
    Planner(rs).observed(campaign,task,offered,new_count,capabilities['paging'],result_kind)
    # Existing legacy resolution queries also benefit from the same strict page gate.
    return {'urls':offered,'new_urls':new_count}

def inspect_source(rs,campaign,task,check):
    url=task['payload']['url'];kind=task['payload']['kind'];web=ResearchWeb(rs.store,check)
    with rs.store.connect() as c:c.execute('INSERT OR IGNORE INTO research_sources(url,kind) VALUES (?,?)',(url,kind))
    try:
        page=web.get(url)
        if page['status']!=200:raise ValueError('Fonte HTTP '+str(page['status']))
        raw=page['html'];urls=[]
        # Robots is enforced by ResearchWeb. Read linked terms, never infer permission from a login page.
        parsed=parse_page(page);terms=[]
        access=task['payload'].get('access_page')
        if access and domain(access)!=domain(page['url']):raise ValueError('Pagina condizioni su dominio diverso dalla fonte')
        access_page=web.get(access) if access else page
        if access_page['status']!=200:raise ValueError('Pagina di accesso della fonte non verificabile')
        access_parsed=parse_page(access_page) if access else parsed
        for link in access_parsed['doc'].links:
            href=urljoin(access_page['url'],link['url'])
            if domain(href)==domain(access_page['url']) and re.search(r'termini|condizioni.*uso|terms.*use|note.legali',link['text']+' '+href,re.I):terms.append(href)
        policy_url=None
        for href in list(dict.fromkeys(terms))[:2]:
            policy=web.get(href);policy_url=href
            if policy['status']!=200:raise ValueError('Condizioni della fonte non verificabili')
            if re.search(r'(?:vietat\w*|non (?:è )?consentit\w*|prohibit\w*).{0,140}(?:scrap\w*|automatizz\w*|automated|robot)',text_with_legal(policy['html']),re.I):raise ValueError('La fonte esclude la raccolta automatizzata nelle condizioni pubbliche')
        if re.search(r'accesso riservato|effettua il login per|accedi per leggere',access_parsed['text'][:2500],re.I):raise ValueError('Fonte riservata: nessun accesso automatico')
        funnel=Funnel(rs);depth=task['payload'].get('depth',0);entries=[];nested=[]
        if kind in ('rss','sitemap') or raw.lstrip().startswith('<?xml'):
            if re.search(r'<!DOCTYPE\s+html',raw,re.I):raise ValueError('La fonte restituisce HTML, non un feed XML leggibile')
            if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():raise ValueError('XML con entità esterne non ammesso')
            tree=ET.fromstring(raw)
            for element in tree.iter():
                tag=element.tag.split('}')[-1]
                if tag not in ('item','entry','url','sitemap'):continue
                fields={x.tag.split('}')[-1]:x for x in element}
                link=fields.get('link') if 'link' in fields else fields.get('loc')
                if link is None:continue
                href=link.get('href') or link.text or ''
                title=fields.get('title');date=next((fields[k].text for k in ('pubDate','published','updated','lastmod') if k in fields),None)
                if tag=='sitemap':nested.append((href,'sitemap'));continue
                summary=next((fields[k].text or '' for k in ('description','summary','content') if k in fields),'')
                entries.append((href,title.text if title is not None else '',date,text_with_legal(summary)[:2000]))
        else:
            for link in parsed['doc'].links:
                href=urljoin(page['url'],link['url'])
                if not link.get('navigation') and domain(href)==domain(page['url']) and SIGNAL.search(link['text']+' '+href):entries.append((href,link['text'],None,''))
            for match in re.finditer(r'<link\b[^>]*>',raw,re.I):
                attrs=dict(re.findall(r'([\w-]+)=["\']([^"\']*)["\']',match[0]))
                if attrs.get('type') in ('application/rss+xml','application/atom+xml') and attrs.get('href'):nested.append((urljoin(page['url'],unescape(attrs['href'])),'rss'))
        if kind=='html' and task['payload'].get('source_scope')!='business_news':
            web.policy(page['url']);origin=urlsplit(page['url']).scheme+'://'+urlsplit(page['url']).netloc
            nested += [(u,'sitemap') for u in web.rules[origin].site_maps() or [] if domain(u)==domain(page['url'])]
        for href,subkind in nested:
            if NOISE.search(href) or depth>=2:continue
            try:href=canonical(urljoin(page['url'],href))
            except ValueError:continue
            if domain(href)!=domain(page['url']):continue
            funnel.offer(campaign['id'],'source','sources',{'url':href,'kind':subkind,'depth':depth+1,'parent_source':url,'access_page':access or page['url'],**{k:task['payload'][k] for k in ('source_scope','publisher','region') if k in task['payload']},**__import__('sales.commercial_planner',fromlist=['source_payload']).source_payload(task['payload'])},'source:'+digest(href))
        accepted=0;old=0;irrelevant=0
        for href,title,date,summary in entries:
            historical=False
            try:href=canonical(urljoin(page['url'],href))
            except ValueError:continue
            if href==url or blocked(href) or NOISE.search(href):irrelevant+=1;continue
            if date:
                try:
                    from email.utils import parsedate_to_datetime
                    try:published=datetime.fromisoformat(date.replace('Z','+00:00'))
                    except ValueError:published=parsedate_to_datetime(date)
                    if published.tzinfo is None:published=published.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc)-published).days>180:old+=1;historical=True
                except (ValueError,TypeError,OverflowError):pass
            # Sitemap modification dates are not publication dates. Original article is still checked.
            topics=strategies_for((title or '')+' '+href.replace('-',' ')+' '+summary)
            if not topics:irrelevant+=1;continue
            from .company_research import selected_strategies
            eligible=[topic for topic in topics if topic in selected_strategies(campaign['filters'])]
            if not eligible:irrelevant+=1;continue
            strategy=eligible[0]
            # Syndicated external entries must establish their own publisher role.
            publisher=domain(href)==domain(page['url']) and bool(task['payload'].get('publisher') or any(domain(url)==domain(seed[1]) for seed in SEEDS+PUBLIC_FEEDS) or re.search(r'confindustria|assolombarda|unione industriali|camera di commercio|venetoup|veneto sviluppo|veneto innovazione',parsed['title']+' '+domain(url),re.I))
            candidate={**__import__('sales.commercial_planner',fromlist=['source_payload']).source_payload(task['payload']),'url':href,'title':title or '','search_snippet':summary,'source_historical':historical,'source_date_hint':date,'source_url':url,'region':task['payload'].get('region'),'provider':'Fonte pubblica / '+kind,'acquisition_provider':'public:'+domain(url),'publisher':publisher,'strategy':strategy,'filters':campaign['filters']}
            from .discovery_relevance import preflight
            reason=preflight(candidate,candidate)
            if reason:
                irrelevant+=1
                rs.event(campaign['id'],'acquisition_filter',reason,url,{'discarded':[{'url':href,'reason':reason}],'source_url':url})
                continue
            added=funnel.offer(campaign['id'],'candidate',strategy,candidate,'candidate-url:'+digest(href))
            accepted+=int(added)
        from .discovery_control import annotate
        annotate(new_urls=accepted, entries=len(entries), old=old, irrelevant=irrelevant)
        with rs.store.connect() as c:
            c.execute('INSERT INTO discovery_source_profiles(url,topics,reliability,discovered_from,checked_at) VALUES (?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET topics=excluded.topics,checked_at=excluded.checked_at',(url,encode(strategies_for(parsed['title']+' '+parsed['text'][:10000])),'Accesso verificato; contenuti da verificare singolarmente',task['payload'].get('parent_source'),now()))
        rs.event(campaign['id'],'source_filter',f'{len(entries)} collegamenti letti; {accepted} pertinenti nuovi; {old} datati; {irrelevant} pagine non pertinenti.',url,{'entries':len(entries),'accepted':accepted,'old':old,'irrelevant':irrelevant})
        with rs.store.connect() as c:c.execute("UPDATE research_sources SET state='available',reason=?,checked_at=?,last_success=?,policy_url=? WHERE url=?",('Pagina pubblica e robots verificati; '+('condizioni collegate lette.' if terms else 'nessun collegamento a condizioni individuato.'),now(),now(),policy_url,url))
        rs.event(campaign['id'],'source',f'Fonte pubblica letta: {accepted} articoli pertinenti nella frontiera.',url)
    except InterruptedError:raise
    except Exception as exc:
        # A large HTML index need not prevent reading its public sitemap. Never fall
        # back after robots/access restrictions, login, CAPTCHA or terms exclusions.
        if kind=='html' and task['payload'].get('source_scope')!='business_news' and 'oltre 1,5 MB' in str(exc) and task['payload'].get('depth',0)<2:
            origin=urlsplit(url).scheme+'://'+urlsplit(url).netloc
            rules=web.rules.get(origin)
            for sitemap in rules.site_maps() or [] if rules else []:
                if domain(sitemap)==domain(url):
                    Funnel(rs).offer(campaign['id'],'source','sources',{'url':sitemap,'kind':'sitemap','depth':task['payload'].get('depth',0)+1,'parent_source':url},'source:'+digest(sitemap))
        with rs.store.connect() as c:c.execute("UPDATE research_sources SET state='unavailable',reason=?,checked_at=? WHERE url=?",(str(exc),now(),url))
        raise
