"""Controlled live comparison; same evidence gates, no writes to the production CRM."""
import argparse
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from .db import Store, now, encode, domain
from .providers import api_json, canonical, blocked
from .discovery_control import free_search, search_capabilities
from .research_triage import triage
from .research_analysis import inspect_candidate
from .search_trial import QUERIES, RESOLUTION_REQUESTS, RESOLUTION_CANDIDATES, serper_search


def searxng_search(store, query, check):
    base=os.getenv('SEARXNG_URL','').rstrip('/');parsed=urlsplit(base)
    if parsed.scheme!='http' or parsed.hostname not in ('localhost','127.0.0.1') or parsed.username or parsed.password:
        raise ValueError('SearXNG locale non configurato')
    capabilities=search_capabilities(store,base)
    check()
    result=free_search(store,lambda:api_json(base+'/search?'+urlencode({'q':query,'format':'json','language':'it-IT','categories':'general','pageno':1}),timeout=25),capabilities.get('engines'))
    check()
    return result['results'][:10],result.get('unresponsive_engines',[])


def sample(queries, maximum=24):
    """Round-robin queries, then union providers: shared URL has a single verdict."""
    selected={}
    for provider in ('serper','searxng'):
        lists=[q for q in queries if q['provider']==provider and not q.get('error')]
        seen=set()
        for position in range(10):
            for query in lists:
                if len(seen)>=maximum:break
                if position>=len(query['results']):continue
                result=query['results'][position];url=result['url']
                if url in seen:continue
                seen.add(url)
                candidate=selected.setdefault(url,{'url':url,'title':result.get('title',''),'providers':[],'strategy':query['strategy'],'query':query['query']})
                if provider not in candidate['providers']:candidate['providers'].append(provider)
    return list(selected.values())


def run(path, rid, token):
    store=Store(Path(path))
    def active(c):return c.execute("SELECT 1 FROM search_trials WHERE id=? AND generation=? AND state='running'",(rid,token)).fetchone()
    def check():
        with store.connect() as c:
            if not active(c):raise InterruptedError('Confronto fermato')
    def save(message, status='running'):
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not active(c):raise InterruptedError('Confronto fermato')
            c.execute('UPDATE search_trials SET report=?,message=?,state=?,updated_at=? WHERE id=?',(encode(report),message,status,now(),rid))
    with store.connect() as c:
        row=c.execute('SELECT report FROM search_trials WHERE id=?',(rid,)).fetchone()
        report=json.loads(row[0])
    try:
        # Snapshot preserves exclusions, manual categories, model config and commercial memory.
        folder=store.path.parent/'search-trials';folder.mkdir(exist_ok=True,mode=0o700)
        path=folder/f'trial-{rid}.sqlite3'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
        with store.connect() as source,closing(sqlite3.connect(path)) as target:source.backup(target)
        scratch=Store(path)
        halted=set()
        for index,(strategy,query) in enumerate(QUERIES):
            # Alternate first provider to reduce systematic ordering effects.
            for provider in (('serper','searxng') if index%2==0 else ('searxng','serper')):
                check()
                if provider in halted:continue
                save(f'{provider.capitalize()} · ricerca {index+1}/{len(QUERIES)} · {query}')
                started=time.monotonic();entry={'provider':provider,'strategy':strategy,'query':query,'results':[],'checked_at':now()}
                try:
                    if provider=='serper':raw=serper_search(store,rid,token,query,check)
                    else:raw,entry['engine_errors']=searxng_search(scratch,query,check)
                    seen=set()
                    for result in raw:
                        if not isinstance(result,dict):continue
                        try:url=canonical(result['url'])
                        except (ValueError,KeyError,TypeError):continue
                        if blocked(url) or url in seen:continue
                        seen.add(url)
                        entry['results'].append({'url':url,'title':str(result.get('title',''))[:300],'engines':result.get('engines',[])})
                except InterruptedError:raise
                except Exception as exc:
                    entry['error']=str(exc)[:600]
                    # No repeated failed credit consumption or hidden failover.
                    halted.add(provider)
                entry['seconds']=round(time.monotonic()-started,3);report['queries'].append(entry)
                save('Risultati di ricerca salvati; sono pagine candidate, non clienti qualificati.')
                for _ in range(20):check();time.sleep(.1)
        report['candidates']=sample(report['queries'])
        for index,candidate in enumerate(report['candidates']):
            check();save(f'Lettura fonte originale {index+1}/{len(report["candidates"])} · '+domain(candidate['url']))
            started=time.monotonic()
            payload={**candidate,'provider':' / '.join(candidate['providers']),'filters':{'regions':['Veneto']}}
            try:
                result=triage(scratch,payload,check)
                candidate['triage']=result;candidate['identity']=result['details'].get('identity',{})
                candidate['documents']=[result['details']['document']] if result['details'].get('document') else []
            except InterruptedError:raise
            except Exception as exc:candidate['triage']={'state':'unverifiable','reason':str(exc)[:700],'details':{}}
            candidate['read_seconds']=round(time.monotonic()-started,2)
            save('Verifica preliminare salvata')
        chosen=set();resolution_requests={'serper':0,'searxng':0};resolved_counts={'serper':0,'searxng':0}
        for provider in ('serper','searxng'):
            eligible=[x for x in report['candidates'] if provider in x['providers'] and (x.get('triage',{}).get('state')=='promising' or x.get('triage',{}).get('resolve'))]
            from .company_research import verification_priority
            eligible.sort(key=lambda x:verification_priority(x.get('triage',{})),reverse=True)
            chosen.update(x['url'] for x in eligible[:4])
        for candidate in report['candidates']:
            if candidate['url'] not in chosen:continue
            check();save('Verifica approfondita · '+domain(candidate['url']))
            payload={**candidate,'provider':' / '.join(candidate['providers']),'filters':{'regions':['Veneto']},'publisher':candidate['triage'].get('details',{}).get('publisher',False)}
            started=time.monotonic()
            try:
                result=inspect_candidate(scratch,payload,check,lambda message:save(message+' · '+domain(candidate['url'])))
                if result.get('publisher'):
                    candidate['resolution']={k:v for k,v in result.items() if k not in ('documents',)}
                    candidate['assessment']={'status':'needs_review','why':'Fonte editoriale: il campione richiede ulteriori verifiche dei soggetti citati. L’editore non è un cliente.','missing':['Identità dei soggetti e bisogno digitale da verificare']}
                    children=[{**child,'providers':candidate['providers']} for child in result.get('discovered',[])]
                    # Names suggested by the model remain hypotheses until the official pages agree.
                    for query in result.get('resolve_queries',[]):
                        if candidate.get('resolution_depth',0)>=1:break
                        for provider in candidate['providers']:
                            check()
                            if provider in halted or resolution_requests[provider]>=RESOLUTION_REQUESTS:continue
                            resolution_requests[provider]+=1
                            entry={'provider':provider,'strategy':candidate['strategy'],'query':query['query'],'purpose':'identity','parent_url':candidate['url'],'results':[],'checked_at':now()};query_started=time.monotonic()
                            try:
                                if provider=='serper':raw=serper_search(store,rid,token,query['query'],check)
                                else:raw,entry['engine_errors']=searxng_search(scratch,query['query'],check)
                                for item in raw:
                                    try:url=canonical(item['url'])
                                    except (ValueError,KeyError,TypeError):continue
                                    if blocked(url):continue
                                    entry['results'].append({'url':url,'title':item.get('title','')})
                                children.extend({**query,**item,'providers':[provider],'official_link':False} for item in entry['results'][:2])
                            except InterruptedError:raise
                            except Exception as exc:entry['error']=str(exc)[:600];halted.add(provider)
                            entry['seconds']=round(time.monotonic()-query_started,3);report['queries'].append(entry);save('Ricerca del sito dell’impresa citata salvata')
                            for _ in range(20):check();time.sleep(.1)
                    candidate['resolution']['followed_urls']=[]
                    for child in children:
                        check()
                        if candidate.get('resolution_depth',0)>=1:break
                        providers=[p for p in child['providers'] if resolved_counts[p]<RESOLUTION_CANDIDATES]
                        if not providers:continue
                        try:url=canonical(child['url'])
                        except (ValueError,TypeError):continue
                        if blocked(url):continue
                        existing=next((x for x in report['candidates'] if domain(x['url'])==domain(url) and x.get('subject')==child.get('subject')),None)
                        if existing:
                            for provider in providers:
                                if provider not in existing['providers']:existing['providers'].append(provider);resolved_counts[provider]+=1
                            candidate['resolution']['followed_urls'].append(existing['url'])
                            continue
                        child={**child,'url':url,'providers':providers,'parent_url':candidate['url'],'resolution_depth':1,'filters':{'regions':['Veneto']}}
                        for provider in providers:resolved_counts[provider]+=1
                        try:
                            child['triage']=triage(scratch,child,check)
                            child['identity']=child['triage']['details'].get('identity',{})
                            child['documents']=[child['triage']['details']['document']] if child['triage']['details'].get('document') else []
                            if child['triage']['state'] not in ('rejected','unverifiable') and not child['triage']['details'].get('publisher'):chosen.add(url)
                        except InterruptedError:raise
                        except Exception as exc:child['triage']={'state':'unverifiable','reason':str(exc)[:700],'details':{}}
                        report['candidates'].append(child);candidate['resolution']['followed_urls'].append(url);save('Azienda citata in verifica; l’articolo resta una fonte, non un cliente.')
                else:
                    candidate['identity']=result['identity'];candidate['assessment']=result['assessment'];candidate['documents']=result['documents']
            except InterruptedError:raise
            except Exception as exc:candidate['assessment']={'status':'unverifiable','why':str(exc)[:700]}
            candidate['deep_seconds']=round(time.monotonic()-started,2)
            save('Valutazione approfondita salvata; revisione delle prove ancora necessaria.')
        incomplete=any(q.get('error') for q in report['queries'])
        report['finished_at']=now()
        save('Campione completato. Confronta prove, scarti e verifiche incomplete; il numero di URL non dimostra efficacia commerciale.', 'partial' if incomplete else 'completed')
    except InterruptedError:pass
    except Exception as exc:
        try:save('Confronto interrotto: '+str(exc)[:500],'error')
        except InterruptedError:pass


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True);parser.add_argument('--run',type=int,required=True);parser.add_argument('--generation',required=True)
    args=parser.parse_args();run(args.db,args.run,args.generation)
