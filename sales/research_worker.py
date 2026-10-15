"""Owned subprocess: killing its process group cancels all its HTTP/model/audit work."""
import argparse
import json
import time
import threading
from datetime import datetime,timezone
from pathlib import Path
from .db import Store,now,digest
from .research_store import ResearchStore
from .research_discovery import seed_campaign,search,inspect_source
from .research_analysis import inspect_candidate
from .research_rules import qualify
from .research_funnel import Funnel
from .research_triage import triage
from .discovery_planner import Planner
from .company_research import verification_priority
from .discovery_control import measure,health,available

def run(path,cid,generation,parent_pid=None):
    store=Store(Path(path));rs=ResearchStore(store);campaign=rs.campaign(cid);funnel=Funnel(rs)
    finished=threading.Event()
    if parent_pid:
        from .worker_lifecycle import watch_owner
        threading.Thread(target=watch_owner,args=(rs,cid,parent_pid,finished),daemon=True).start()
    def check():
        if not rs.active(cid,generation):raise InterruptedError('Arresto richiesto')
    def progress(message):rs.progress(cid,generation,message)
    try:
        from .prospect_scope import apply_scope,task_in_scope
        apply_scope(rs,campaign)
        funnel.constrain_legacy_queue(campaign)
        with store.connect() as c:seeded=bool(c.execute("SELECT 1 FROM research_events WHERE campaign_id=? AND kind='frontier_initialized'",(cid,)).fetchone())
        if seeded:
            Planner(rs).adopt(campaign)
        if not seeded:
            seed_campaign(rs,campaign);check()
            rs.event(cid,'frontier_initialized','Strategie iniziali preparate. La paginazione e le fonti aggiungeranno candidati progressivamente.')
        Planner(rs).restore_company_reviews(campaign)
        while True:
            check();current=rs.campaign(cid)
            if current['qualified']>=current['target']:
                rs.finish(cid,generation,'completed',f"Obiettivo raggiunto: {current['qualified']} aziende qualificate.");break
            Planner(rs).tick(campaign)
            provider_health=health(store)
            if available(store) and (provider_health['failures']>=3 or provider_health.get('last_success')):
                with store.connect() as c:
                    c.execute("UPDATE research_tasks SET state='pending',available_at=?,attempts=0 WHERE campaign_id=? AND kind='search' AND state='blocked'",(now(),cid))
                    c.execute("UPDATE discovery_frontier SET state='pending' WHERE campaign_id=? AND kind='search' AND state='blocked'",(cid,))
            if not available(store):
                with store.connect() as c:
                    c.execute("UPDATE research_tasks SET available_at=? WHERE campaign_id=? AND kind='search' AND state='pending' AND available_at<?",(provider_health['retry_at'],cid,provider_health['retry_at']))
            funnel.fill(campaign)
            task=rs.claim(cid,generation)
            if not task:
                with store.connect() as c:
                    waiting=c.execute("SELECT min(available_at) FROM research_tasks WHERE campaign_id=? AND state='pending'",(cid,)).fetchone()[0]
                    failed=c.execute("SELECT count(*) FROM research_tasks WHERE campaign_id=? AND state IN ('failed','blocked')",(cid,)).fetchone()[0]
                if waiting:
                    rs.progress(cid,generation,'Attendo il prossimo tentativo consentito dai servizi.','waiting',waiting)
                    time.sleep(.3);continue
                rs.finish(cid,generation,'blocked' if failed else 'exhausted','Fonti o controlli non disponibili: puoi riprendere i tentativi.' if failed else 'Copertura disponibile completata: nessun nuovo candidato nelle fonti interrogate. Non significa che il mercato sia esaurito; amplia territori o fonti.');break
            if not task_in_scope(task['kind'],task['strategy'],task['payload'],campaign['filters']):
                rs.task_done(task['id']);continue
            try:
                with measure(rs,campaign,task):
                    if task['kind']=='search':
                        progress(('Serper · Google · ' if store.settings()['provider']=='serper' else 'SearXNG · ')+task['payload']['query']);search(rs,campaign,task,check)
                    elif task['kind']=='source':
                        progress('Verifico la fonte territoriale · '+task['payload']['url']);inspect_source(rs,campaign,task,check)
                    elif task['kind']=='candidate':
                        payload={**task['payload'],'direct_channels':True};url=payload['url'];started=time.monotonic()
                        progress('Selezione preliminare · '+url)
                        funnel.transition(campaign,payload,'discovered','Lettura della pagina originale in corso.')
                        result=triage(store,payload,check);check()
                        from .company_queue import completed_review
                        previous=completed_review(rs,campaign,payload,result)
                        if previous:
                            a=previous['assessment']
                            funnel.transition(campaign,payload,a['status'],
                                'Pagina già compresa nella verifica completata; nessun contenuto nuovo rilevato.',
                                {**result['details'],'identity':previous['identity'],'reused_assessment':previous['id']},previous['id'])
                            rs.event(cid,'reused_review','Verifica già completata riutilizzata per una pagina invariata.',url,{'assessment_id':previous['id']})
                            from .discovery_control import annotate
                            annotate(outcome='duplicate',reused_assessment=previous['id'])
                            rs.task_done(task['id']);continue
                        Planner(rs).follow_company(campaign,payload,result)
                        for query in result.get('resolve_queries',[]):
                            Planner(rs).offer_query(campaign,'explicit',query)
                        result['details']['elapsed_seconds']=round(time.monotonic()-started,2)
                        funnel.transition(campaign,payload,result['state'],result['reason'],result['details'])
                        if result.get('source') or task['strategy']=='sources':
                            funnel.offer(cid,'source','sources',{'url':url,'kind':'html','depth':0,**__import__('sales.commercial_planner',fromlist=['source_payload']).source_payload(payload)},'source:'+digest(url))
                        if (result['state']=='promising' and not result['details'].get('collaboration')) or result.get('resolve'):
                            funnel.offer(cid,'verify',task['strategy'],{**payload,'publisher':result['details'].get('publisher',False),'directory':result['details'].get('directory',False),'verification_priority':verification_priority(result)},'verify:'+digest(url+payload.get('subject','')))
                    else:
                        url=task['payload']['url'];progress('Verifica approfondita · '+url)
                        funnel.transition(campaign,task['payload'],'verifying','Verifica di identità, bisogno e controprove in corso.')
                        excluded=store.target_exclusion(url)
                        if excluded:
                            funnel.transition(campaign,task['payload'],'rejected',excluded['reason']);rs.event(cid,'excluded',excluded['reason'],url);rs.task_done(task['id']);continue
                        started=time.monotonic();result=inspect_candidate(store,{**task['payload'],'direct_channels':True},check,progress);check()
                        if result.get('publisher'):
                            for candidate in result['discovered']:funnel.offer(cid,'candidate',task['strategy'],{**candidate,'company_stage':'identify',**__import__('sales.commercial_planner',fromlist=['source_payload']).source_payload(task['payload']),'acquisition_provider':task['payload'].get('acquisition_provider'),'query_key':task['payload'].get('query_key')},'candidate-url:'+digest(candidate['url']+candidate.get('subject','')))
                            for query in result.get('resolve_queries',[]):Planner(rs).offer_query(campaign,task['strategy'],{**query,**__import__('sales.commercial_planner',fromlist=['source_payload']).source_payload(task['payload']),'company_stage':'identify'})
                            funnel.transition(campaign,task['payload'],'unverifiable' if result.get('incomplete') else 'needs_review',result.get('skip_reason') or 'Fonte editoriale risolta: verificare separatamente le aziende citate.',{'publisher':True,'resolve_subject':False,'resolved_urls':[x['url'] for x in result['discovered']],'resolved_queries':len(result.get('resolve_queries',[])),'excluded_names':result.get('excluded_names',[])})
                            rs.event(cid,'publisher',result.get('skip_reason') or 'Fonte editoriale: '+str(len(result['discovered']))+' siti collegati da identificare. L’editore non è il cliente.',url)
                        else:
                            aid=rs.save(cid,generation,task['id'],result['identity'],result['documents'],result['assessment'])
                            a=rs.opportunity(aid)['assessment'] if aid else result['assessment']
                            from .company_queue import inputs
                            for index,review_input in enumerate(inputs(task['payload'])):
                                detail={'identity':result['identity']}
                                if index==0:detail['deep_seconds']=round(time.monotonic()-started,2)
                                funnel.transition(campaign,review_input,a['status'],'; '.join(a.get('reasons',[])) or a['why'],detail,aid)
                            technical=[m for m in a.get('missing',[]) if 'non verificabile:' in m or 'Analisi locale non completata:' in m]
                            if a['status']=='unverifiable' and technical:
                                error='; '.join(technical)[:900]
                                retry=any(word in error.lower() for word in ('modello','timeout','timed out','429','503','502','connection'))
                                access=a.get('access_issues',[])
                                retry_at=None
                                if access:
                                    retry=all(issue['retryable'] for issue in access)
                                    retry_at=max((issue['retry_at'] for issue in access if issue.get('retry_at')),default=None)
                                    from .discovery_relevance import alternative_query
                                    alternative=alternative_query({**task['payload'],'subject':result['identity']['name'],'company_host':__import__('sales.db',fromlist=['domain']).domain(result['identity']['website'])})
                                    if alternative:Planner(rs).offer_query(campaign,task['strategy'],alternative)
                                rs.event(cid,'incomplete',error,url,{'task_id':task['id']})
                                rs.task_done(task['id'],error,retry=retry,retry_at=retry_at);continue
                    rs.task_done(task['id'])
            except InterruptedError:raise
            except Exception as exc:
                from .serper_provider import CreditLimit
                from .discovery_control import ProviderConfigurationError, QueryError
                if isinstance(exc,(CreditLimit,ProviderConfigurationError)):
                    from .operation_outcomes import safe_error,error_outcome
                    error=safe_error(exc)
                    rs.event(cid,'provider_warning',error,details=error_outcome(exc,task['kind']))
                    rs.task_done(task['id'],error);rs.finish(cid,generation,'blocked',error);break
                from .access_status import describe
                issue=describe(exc)
                from .operation_outcomes import safe_error,error_outcome
                error=safe_error(exc);rs.event(cid,'error',error,task['payload'].get('url'),{'task_id':task['id'],'kind':task['kind'],'strategy':task['strategy'],**error_outcome(exc,task['kind']),**({'access':issue} if issue else {})})
                if task['kind'] in ('candidate','verify'):
                    identity={'name':task['payload']['url'],'website':task['payload']['url'],'identity_status':'unknown','contacts':[]}
                    result=qualify(identity,[],[],{}, {},strategy=task['strategy'],limits=[error])
                    funnel.transition(campaign,task['payload'],'unverifiable',error,{'access':issue} if issue else {})
                    if task['kind']=='verify':rs.save(cid,generation,task['id'],identity,[],result)
                    if issue:
                        from .discovery_relevance import alternative_query
                        alternative=alternative_query(task['payload'])
                        if alternative:
                            if Planner(rs).offer_query(campaign,task['strategy'],alternative):
                                rs.event(cid,'planner','Accesso non riuscito: cerco una fonte alternativa sullo stesso soggetto, senza aggirare il blocco.',task['payload']['url'],{'query':alternative['query']})
                transient=any(s in error.lower() for s in ('timeout','timed out','tempor','429','502','503','nessun motore','connection','urlopen'))
                if issue:transient=issue['retryable']
                if '.pdf' in task['payload'].get('url','').lower() and task['attempts']>=2:transient=False
                rs.task_done(task['id'],error,retry=transient,retry_at=issue.get('retry_at') if issue else None)
                if task['kind']=='search' and not transient and (isinstance(exc,QueryError) or not health(store)['failures']):
                    # A malformed/failed query is not an unavailable provider and
                    # must not strand its branch on status=pending forever.
                    Planner(rs).observed(campaign,task,[],0,False,'query_error')
                if task['kind']=='search' and health(store)['failures']>=3:
                    with store.connect() as c:
                        c.execute("UPDATE research_tasks SET state='blocked',error=? WHERE campaign_id=? AND kind='search' AND state='pending'",('Provider in pausa tecnica; prossima disponibilità '+str(health(store)['retry_at']),cid))
                    rs.event(cid,'provider_warning',store.settings()['provider'].capitalize()+' non disponibile dopo tre tentativi differiti. Posso completare le verifiche sui siti già trovati; Riprendi conserverà le query non eseguite.',details=health(store))
    except InterruptedError:pass
    except Exception as exc:
        from .operation_outcomes import safe_error
        error=safe_error(exc)
        rs.event(cid,'error',error,details={'scope':'system','outcome':'permanent_error'})
        rs.finish(cid,generation,'error','Errore del coordinatore: '+error);raise
    finally:finished.set()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--campaign',type=int,required=True);p.add_argument('--generation',required=True);p.add_argument('--parent-pid',type=int);args=p.parse_args();run(args.db,args.campaign,args.generation,args.parent_pid)
