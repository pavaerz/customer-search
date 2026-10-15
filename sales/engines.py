import json
from collections import deque
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit,urljoin
from .config import DATA,ROOT,ENGINES
from .db import now,encode,domain,digest
from .providers import PublicWeb,provider,RSS,canonical,blocked
from .extract import parse_page,classify
from .intelligence import qualify
from .targeting import exclusion
from .selection import useful_evidence
from .prospecting import agency_identity
from site_audit import seo_report

class CandidateRejected(ValueError):
    pass

class EngineManager:
    def __init__(self,store):
        self.store=store;self.lock=threading.Lock();self.stop_event=threading.Event()
        self.job={'running':False,'engine':None,'message':'Pronto. Avvia una ricerca quando vuoi.','checked':0,'added':0,'errors':0}
    def check(self):
        if self.stop_event.is_set():raise InterruptedError('Ricerca fermata; i dati raccolti sono conservati.')
    def progress(self,**values):
        with self.lock:self.job.update(values)
    def state(self):
        with self.lock:return dict(self.job)
    def start(self,engines=None,urls=None):
        engines=engines or list(ENGINES)
        if not isinstance(engines,list) or not engines or any(e not in ENGINES for e in engines):raise ValueError('Motori non validi')
        if urls is not None and (not isinstance(urls,list) or len(urls)>20 or any(not isinstance(u,str) for u in urls)):raise ValueError('URL non validi')
        urls=[canonical(u) for u in urls or []]
        with self.lock:
            if self.job['running']:raise ValueError('Una ricerca è già in corso')
            self.stop_event.clear();self.job={'running':True,'engine':None,'message':'Preparazione fonti…','checked':0,'added':0,'errors':0}
        threading.Thread(target=self.run,args=(list(dict.fromkeys(engines)),urls),daemon=True,name='sales-research').start()
    def run(self,engines,urls=None):
        web=PublicWeb(self.store,self.check)
        totals={'checked':0,'added':0,'errors':0}
        try:
            # Give direct-business discovery the budget first; combinations run last.
            for engine in sorted(engines,key=lambda e:['D','A','C','B','E'].index(e)):
                self.check();self.progress(engine=engine,message='Motore '+engine+' · '+ENGINES[engine]['name'])
                with self.store.connect() as c:run_id=c.execute("INSERT INTO runs(engine,started_at,status) VALUES (?,?,'running')",(engine,now())).lastrowid
                stats={'checked':0,'added':0,'duplicates':0,'rejected':0,'errors':0,'queries':0};status='completed'
                try:
                    if engine=='E':self.combine(run_id,stats)
                    elif engine=='D':self.technical_engine(web,run_id,stats,urls)
                    else:self.discovery(engine,web,run_id,stats,urls)
                except InterruptedError:status='stopped';raise
                except Exception as exc:status='error';stats['errors']+=1;self.store.log(run_id,'error',str(exc))
                finally:
                    if stats['errors'] and status=='completed':status='partial'
                    with self.store.connect() as c:c.execute('UPDATE runs SET status=?,finished_at=?,stats=? WHERE id=?',(status,now(),encode(stats),run_id))
                    for k in totals:totals[k]+=stats[k]
                    self.progress(**totals)
        except InterruptedError:self.progress(message='Ricerca interrotta. Risultati e log conservati.')
        except Exception as exc:self.progress(message='Ricerca non completata: '+str(exc)[:300])
        else:self.progress(message=f"Ricerca completata: {totals['added']} nuove schede, {totals['checked']} verifiche effettuate. "+('Consulta gli errori e i limiti nelle attività.' if totals['errors'] else 'I riscontri sono disponibili nelle schede.'))
        finally:self.progress(running=False,engine=None)
    def candidates(self,engine,run_id,stats,urls,web):
        config=self.store.settings()
        if urls:
            for u in urls:yield {'url':u,'discovery_provider':'URL inserito manualmente'}
            return
        queries=config['queries'][engine]
        with self.store.connect() as c:n=c.execute('SELECT count(*) FROM runs WHERE engine=?',(engine,)).fetchone()[0]-1
        offset=(n*config['queries_per_engine'])%len(queries)
        for i in range(min(config['queries_per_engine'],len(queries))):
            self.check();query=queries[(offset+i)%len(queries)]
            self.progress(message=f'{engine} · Ricerca: {query}')
            try:
                items=provider(self.store).search(query,config);self.check();stats['queries']+=1
                self.store.log(run_id,'query',f'{len(items)} risultati del motore; non ancora verificati',query=query)
                yield from items
            except InterruptedError:raise
            except Exception as exc:
                stats['errors']+=1;self.store.log(run_id,'error',str(exc),query=query)
                # A provider failure must not disable independently configured RSS feeds.

        if engine=='C':
            for feed in config['rss_feeds']:
                self.check()
                excluded=self.store.target_exclusion(feed)
                if excluded:
                    self.store.log(run_id,'rejected','Feed di azienda fuori target: '+excluded['reason'],url=feed);continue
                try:yield from RSS(web).entries(feed)
                except Exception as exc:stats['errors']+=1;self.store.log(run_id,'error',str(exc),url=feed)
    def reject_target(self,page,parsed=None):
        finding=exclusion(page,parsed)
        if finding:self.store.exclude_target(page['url'],finding)
        return finding
    def discovery(self,engine,web,run_id,stats,urls):
        seen=set();pending=deque();original=iter(self.candidates(engine,run_id,stats,urls,web))
        while True:
            if pending:result=pending.popleft()
            else:
                try:result=next(original)
                except StopIteration:break
            self.check();url=result.get('url','')
            try:
                url=canonical(url)
                existing=self.store.target_exclusion(url)
                if existing:
                    stats['rejected']+=1;self.store.log(run_id,'rejected',existing['reason'],url=url);continue
                if url in seen:continue
                seen.add(url);self.progress(message=f'{engine} · Leggo e verifico {domain(url)}')
                page=web.get(url);stats['checked']+=1;self.progress(checked=self.state()['checked']+1)
                if page['status']!=200:raise ValueError('Pagina non leggibile: HTTP '+str(page['status']))
                parsed=parse_page(page)
                finding=self.reject_target(page,parsed)
                if finding:
                    stats['rejected']+=1;self.store.log(run_id,'rejected',finding['reason'],url=finding['url']);continue
                known_location=parsed.get('location') or ''
                if any(re.search(r'(?<!\w)'+re.escape(place)+r'(?!\w)',known_location,re.I) for place in self.store.settings()['excluded_locations']):
                    stats['rejected']+=1;self.store.log(run_id,'rejected','Località dichiarata esclusa dalle preferenze: '+known_location,url=url);continue
                signal_data,reason=classify(parsed,engine,page['url'])
                if not signal_data:
                    stats['rejected']+=1;self.store.log(run_id,'rejected',reason,url=url)
                    # Follow specific first-party detail pages, not listings on another domain.
                    if not result.get('depth') and not blocked(page['url']) and not any(t in reason for t in ('editoriale','Directory','Intermediario')):
                        children=[]
                        for link in parsed['doc'].links:
                            href=urljoin(page['url'],link['url']);label=link['text']+' '+link['url']
                            pattern=r'showroom|nuova.sede|inaugur|nuovo.marchio|nuova.linea' if engine=='C' else r'lavora.con.noi|careers|collabora|jobs/.*(?:wordpress|developer|frontend)'
                            if href.startswith(('http://','https://')) and domain(href)==domain(page['url']) and re.search(pattern,label,re.I):
                                href=canonical(href)
                                if href not in seen and href not in children and href!=url:children.append(href)
                        for href in children[:2]:
                            pending.append({'url':href,'discovery_provider':result.get('discovery_provider','Pagina pubblica')+' · link interno','depth':1})
                            self.store.log(run_id,'follow','Verifico la pagina di dettaglio collegata dalla fonte originale.',url=href)
                    continue
                home_check=page
                home_url=urljoin(page['url'],'/')
                if home_url!=page['url']:
                    try:
                        home_check=web.get(home_url);stats['checked']+=1
                        if home_check['status']!=200:raise ValueError('HTTP '+str(home_check['status']))
                        finding=self.reject_target(home_check)
                    except InterruptedError:raise
                    except Exception as exc:
                        stats['errors']+=1;self.store.log(run_id,'warning','Verifica target sulla homepage non completata: '+str(exc),url=home_url);continue
                    if finding:
                        stats['rejected']+=1;self.store.log(run_id,'rejected',finding['reason'],url=finding['url']);continue
                cid=self.store.company(urljoin(page['url'],'/'),parsed['name'],parsed['sector'],parsed['location'],parsed['contacts'])
                identity=parse_page(home_check)
                self.store.classify_contact(cid,'agencies' if agency_identity(identity) or agency_identity(parsed) else 'direct','Categoria suggerita dalla presentazione del sito; puoi correggerla in Stato e note.',home_check['url'])
                source={**page,'title':parsed['title'],'provider':result.get('discovery_provider','Pagina pubblica'),'source_type':'Annuncio strutturato' if parsed['job'] else 'Comunicazione aziendale' if engine=='C' else 'Pagina aziendale','published_at':parsed['published_at'],'excerpt':signal_data['statement']}
                sid=self.store.source(source,cid)
                meta={'budget':signal_data['budget'],'competition':signal_data['competition'],'ongoing':signal_data['ongoing'],'skills':signal_data['skills'],'date_origin':parsed['date_origin'],'name_basis':parsed['name_basis'],'requirements':signal_data.get('requirements',[])}
                eid=self.store.add_evidence(cid,sid,engine,signal_data['kind'],signal_data['label'],signal_data['statement'],signal_data['date'],metadata=meta)
                # Fetch a company's home page as a second, clearly separated presence check.
                website=urljoin(page['url'],'/');presence=[]
                if engine=='C':
                    try:
                        home=home_check
                        if home['status']==200:
                            hp=parse_page(home);hs=self.store.source({**home,'title':hp['title'],'provider':'Verifica diretta','source_type':'Homepage','excerpt':hp['text'][:600]},cid)
                            self.store.company(website,hp['name'],contacts=hp['contacts'])
                            presence.append(self.store.add_evidence(cid,hs,'C','fact','Presenza digitale verificata','Homepage raggiungibile (HTTP 200). Titolo: '+hp['title'],metadata={'scope':'Homepage; non verifica che tutte le sedi siano elencate'}))
                    except Exception as exc:self.store.log(run_id,'warning','Presenza digitale non completata: '+str(exc),url=website)
                signal_data['contacts']=parsed['contacts'];signal_data['preferred_location']=any(re.search(r'(?<!\w)'+re.escape(place)+r'(?!\w)',known_location,re.I) for place in self.store.settings()['preferred_locations']);score,breakdown=qualify(engine,signal_data,minimum_budget=self.store.settings()['minimum_budget'])
                service=' / '.join(signal_data['skills'][:2]) or ('Sito aziendale / landing page' if engine=='C' else 'Supporto frontend / WordPress')
                reason=signal_data['label']+': '+signal_data['statement'][:230]
                hypothesis=('Potrebbe esserci spazio per '+service+'. Il cambiamento non dimostra intenzione d’acquisto.' if signal_data['kind']=='signal' else 'Verificare che il progetto sia ancora aperto e che il profilo richiesto sia compatibile.')
                missing=signal_data.get('requirements',[])+['Disponibilità attuale del referente','Budget e perimetro del progetto','Requisiti aggiuntivi rispetto alle competenze dichiarate']
                if not signal_data['date']:missing.insert(0,'Data di pubblicazione non disponibile; scheda da verificare')
                if signal_data['competition'] is None:missing.append('Numero di candidati non dichiarato')
                identity=f'request:{cid}:'+digest(' '.join(signal_data['statement'].lower().split())) if signal_data['kind']=='request' else f'{cid}:{engine}'
                ident,added=self.store.prospect(cid,engine,parsed['title'] or signal_data['label'],service,score,breakdown,reason,hypothesis,missing,[eid]+presence,identity)
                stats['added' if added else 'duplicates']+=1
                self.store.log(run_id,'accepted' if added else 'duplicate',f'Scheda {ident}: {signal_data["kind"]}, priorità {score}/100'+('; data assente, da verificare' if not signal_data['date'] else ''),url=url)
            except InterruptedError:raise
            except Exception as exc:stats['errors']+=1;self.store.log(run_id,'error',str(exc),url=url)
    def audit(self,url,web,direct_only=False):
        self.check();page=web.get(url)
        if page['status']!=200:raise ValueError('Homepage non accessibile: HTTP '+str(page['status']))
        parsed=parse_page(page)
        if direct_only and agency_identity(parsed):raise CandidateRejected('Agenzia digitale: per questa ricerca tecnica si privilegiano clienti diretti.')
        location=parsed.get('location') or ''
        if any(re.search(r'(?<!\w)'+re.escape(place)+r'(?!\w)',location,re.I) for place in self.store.settings()['excluded_locations']):
            raise CandidateRejected('Località dichiarata esclusa dalle preferenze: '+location)
        existing=self.store.target_exclusion(page['url']) or self.reject_target(page,parsed)
        if existing:raise CandidateRejected(existing['reason'])
        observations=[];limitations=[]
        # Never submit a form or infer lost sales from HTML observations.
        forms=parsed['doc'].forms
        observations.append({'label':'Moduli presenti nell’HTML','detail':f'{len(forms)} moduli rilevati. Nessun invio effettuato; consegna e validazione lato server non testate.','kind':'fact'})
        if 'viewport' not in parsed['doc'].meta:observations.append({'label':'Viewport mobile non dichiarato','detail':'Meta viewport non presente nell’HTML ricevuto. Verificare il comportamento mobile prima di proporre interventi.','kind':'measurement'})
        if any('noindex' in parsed['doc'].meta.get(k,'').lower() for k in ('robots','googlebot')):observations.append({'label':'Direttiva noindex','detail':'La pagina contiene noindex. Potrebbe essere intenzionale: verificare con il proprietario.','kind':'measurement'})
        links=[]
        for link in parsed['doc'].links:
            if re.search(r'contatt|contact|preventivo|richied|shop|acquista',link['text']+' '+link['url'],re.I):
                href=urljoin(page['url'],link['url'])
                if href.startswith(('http://','https://')) and domain(href)==domain(page['url']) and href not in links:links.append(href)
        for href in links[:3]:
            self.check()
            try:
                target=web.get(href)
                if target['status'] in (404,410):
                    retry=web.get(href,refresh=True)
                    if retry['status']==target['status']:observations.append({'label':'Collegamento importante non raggiungibile','detail':f'{href} restituisce HTTP {target["status"]} in due controlli GET.','kind':'measurement','url':href})
            except Exception as exc:limitations.append('Link non verificabile: '+href+' · '+str(exc))
        if not links:limitations.append('Nessun link di contatto/acquisto riconosciuto nell’HTML. Non prova assenza di CTA nella pagina renderizzata.')
        self.progress(message='D · Test Lighthouse mobile e desktop: '+domain(url))
        with tempfile.TemporaryFile(mode='w+') as output:
            child=subprocess.Popen([sys.executable,'-m','sales.audit_worker',page['url']],cwd=ROOT,stdout=output,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                while child.poll() is None:self.check();time.sleep(.25)
                output.seek(0)
                report=json.load(output) if child.returncode==0 else {'pagespeed':[]}
            finally:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                child.wait()
        report['seo']=seo_report(page['html'],page['url']);report['observations']=observations;report['limitations']=limitations
        for result in report.get('pagespeed',[]):
            if result.get('status')!='ok':limitations.append(result.get('message','Test Lighthouse non completato'));continue
            scores=result.get('scores',{})
            if scores.get('performance',100)<75:
                observations.append({'label':'Prestazioni di laboratorio · '+result['strategy'],'detail':f"Performance {scores['performance']}/100. LCP: {result.get('metrics',{}).get('largest-contentful-paint','non disponibile')}. Misura di laboratorio, non stima di vendite perse.",'kind':'measurement','report_url':result.get('report_url'),'measured_at':result.get('fetch_time')})
            for issue in result.get('issues',[])[:3]:
                if issue.get('title'):observations.append({'label':result['strategy']+' · '+issue['title'],'detail':issue['title']+': '+(issue.get('detail') or 'Riscontro automatico Lighthouse; verificare il contesto e le pagine interessate.'),'kind':'measurement','report_url':result.get('report_url'),'measured_at':result.get('fetch_time')})
        if len([r for r in report.get('pagespeed',[]) if r.get('status')=='ok'])<2:limitations.append('Audit incompleto: non sono disponibili entrambi i test Lighthouse.')
        limitations.append('Chiarezza delle CTA, navigazione completa e conversioni richiedono revisione umana e dati analytics. Non sono attribuiti difetti commerciali automatici.')
        return page,parsed,report
    def technical_engine(self,web,run_id,stats,urls):
        limit=self.store.settings()['technical_limit']
        def targets():
            if urls:
                yield from urls
                return
            # Always discover new businesses, even when the database is already populated.
            for result in self.candidates('D',run_id,stats,[],web):
                url=result.get('url','')
                if blocked(url):continue
                try:yield urljoin(canonical(url),'/')
                except ValueError:continue
            # Fallback for exhausted/unavailable search; don't keep auditing the same sites.
            cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
            with self.store.connect() as c:
                saved=[dict(r) for r in c.execute("""SELECT c.website,c.sector FROM companies c
                    LEFT JOIN audits a ON a.company_id=c.id
                    WHERE c.do_not_contact=0 AND c.prior_contacted=0
                    AND EXISTS (SELECT 1 FROM prospects p WHERE p.company_id=c.id AND p.stage IN ('review','ready'))
                    AND c.domain NOT IN (SELECT domain FROM dismissed_companies)
                    AND c.domain NOT IN (SELECT domain FROM target_exclusions)
                    AND (a.checked_at IS NULL OR a.checked_at<?)
                    ORDER BY c.id DESC""",(cutoff,))]
            for row in saved:
                if not (row['sector'] or '').startswith('Agenzia'):yield row['website']
            for row in self.store.legacy():
                old=row['data']
                if row['kind']=='leads' and old.get('status')=='draft' and old.get('url'):
                    yield old['url']
        seen=set();attempted=0
        for url in targets():
            host=domain(url)
            if not host or host in seen or blocked(url):continue
            seen.add(host)
            if not urls:
                cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
                with self.store.connect() as c:
                    recent=c.execute('SELECT 1 FROM audits a JOIN companies c ON c.id=a.company_id WHERE c.domain=? AND a.checked_at>=?',(host,cutoff)).fetchone()
                if recent:
                    self.store.log(run_id,'duplicate','Sito già misurato negli ultimi 7 giorni: cerco un’altra azienda.',url=url);continue
            if attempted>=limit:break
            self.check()
            try:
                existing=self.store.target_exclusion(url)
                if existing:
                    stats['rejected']+=1;self.store.log(run_id,'rejected',existing['reason'],url=url);continue
                attempted+=1
                page,parsed,report=self.audit(url,web,direct_only=not bool(urls));stats['checked']+=1
                cid=self.store.company(urljoin(page['url'],'/'),parsed['name'],parsed['sector'],parsed['location'],parsed['contacts'])
                self.store.classify_contact(cid,'agencies' if agency_identity(parsed) else 'direct','Categoria suggerita dalla homepage controllata; puoi correggerla in Stato e note.',page['url'])
                sid=self.store.source({**page,'title':parsed['title'],'provider':'Lighthouse locale + verifica diretta','source_type':'Test tecnico','excerpt':'Audit della homepage e fino a tre collegamenti importanti.'},cid)
                ids=[];measurements=0
                for obs in report['observations']:
                    ids.append(self.store.add_evidence(cid,sid,'D',obs['kind'],obs['label'],obs['detail'],confidence='measured' if obs['kind']=='measurement' else 'direct',metadata={k:v for k,v in obs.items() if k not in ('label','detail','kind')}))
                    measurements+=obs['kind']=='measurement'
                for limitation in report['limitations']:ids.append(self.store.add_evidence(cid,sid,'D','limitation','Limite del controllo',limitation))
                with self.store.connect() as c:c.execute('INSERT OR REPLACE INTO audits VALUES (?,?,?)',(cid,encode(report),now()))
                if not measurements:
                    stats['rejected']+=1;self.store.log(run_id,'rejected','Nessun problema specifico misurato sufficiente; audit conservato.',url=url)
                    if attempted>=limit:break
                    continue
                score,points=qualify('D',{'skills':['Frontend'],'contacts':parsed['contacts']},technical_count=measurements)
                ident,added=self.store.prospect(cid,'D','Verifica esperienza digitale','Ottimizzazione frontend / accessibilità',score,points,f'{measurements} riscontri tecnici misurati; nessuna intenzione d’acquisto dimostrata.','Un intervento mirato potrebbe risolvere i problemi rilevati. Prima verificare priorità e impatto con l’azienda.',['Priorità commerciale non dimostrata','Verifica umana dell’impatto','Nessun test di invio moduli effettuato'],ids)
                stats['added' if added else 'duplicates']+=1;self.store.log(run_id,'accepted',f'Audit conservato nella scheda {ident}; priorità limitata a 35.',url=url)
            except InterruptedError:raise
            except CandidateRejected as exc:
                attempted-=1;stats['rejected']+=1;self.store.log(run_id,'rejected',str(exc),url=url)
            except Exception as exc:stats['errors']+=1;self.store.log(run_id,'error',str(exc),url=url)
            if attempted>=limit:break
    def combine(self,run_id,stats):
        with self.store.connect() as c:companies=[dict(r) for r in c.execute('SELECT * FROM companies')]
        for company in companies:
            self.check()
            excluded=self.store.target_exclusion(company['website'])
            if excluded:
                stats['rejected']+=1;self.store.log(run_id,'rejected',excluded['reason'],url=company['website']);continue
            evidence=self.store.evidences(company['id'])
            useful=[e for e in evidence if useful_evidence(e)]
            # The same quotation indexed by A and B is one signal.
            distinct={(e['url'], ' '.join(e['detail'].lower().split())) for e in useful}
            engines={e['engine'] for e in useful};stats['checked']+=1
            if len(engines)<2 or len(distinct)<2 or not engines&{'A','B','C'}:
                stats['rejected']+=1;self.store.log(run_id,'rejected','Servono segnali da almeno due motori, incluso un segnale commerciale.',url=company['website']);continue
            dates=[e['published_at'] for e in useful if e['published_at']]
            signal_data={'kind':'request' if any(e['kind']=='request' for e in useful) else 'signal','date':max(dates) if dates else None,'skills':list({s for e in useful for s in e['metadata'].get('skills',[])}) or ['Frontend'],'contacts':json.loads(company['contacts']),'ongoing':any(e['metadata'].get('ongoing') for e in useful)}
            score,points=qualify('E',signal_data,len({e['url'] for e in useful}),sum(e['kind']=='measurement' for e in useful))
            if not dates:score=min(score,49)
            commercial=next(e for e in useful if e['kind'] in ('request','signal'))
            measured=next((e for e in useful if e['kind']=='measurement'),None)
            reason=commercial['detail'][:220]+(' · '+measured['detail'][:150] if measured else '')
            reason='Motori '+', '.join(sorted(engines))+': '+reason
            ident,added=self.store.prospect(company['id'],'E','Segnali commerciali collegati','Progetto web mirato / supporto continuativo',score,points,reason,'La combinazione rende utile approfondire un progetto mirato. Non dimostra budget, urgenza o volontà d’acquisto.',['Confermare che i segnali riguardino lo stesso progetto','Verificare attualità e referente','Concordare perimetro e budget'],[e['id'] for e in useful])
            stats['added' if added else 'duplicates']+=1;self.store.log(run_id,'accepted' if added else 'duplicate',f'Scheda combinata {ident}; {len(engines)} motori, {len({e["url"] for e in useful})} URL.',url=company['website'])
