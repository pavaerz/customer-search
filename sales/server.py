import json
import os
import re
import secrets
import signal
import atexit
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,urlencode,parse_qs
from .config import ROOT,DATA,PORT,ORIGIN,ENGINES,STAGES
from .db import Store,now,encode
from .engines import EngineManager
from .intelligence import communication,build_dossier
from .advisor import local_advice
from .providers import PublicWeb
from .campaigns import CampaignManager
from .research_store import ResearchStore
from .grants import answer_requirements,GrantsManager,profile as grant_profile,REGIONS,FORMS,REGIMES,CATALOG
from .research_funnel import Funnel,FEEDBACK
from .research_api import annotate,quality_report,commercial_feedback
from .commercial.storage import Opportunities
from .commercial.catalog import ENGINES as COMMERCIAL_ENGINES
from .commercial.geography import REGIONS as COMMERCIAL_REGIONS
from .search_trial import TrialManager,save_key as save_serper_key,review as review_search_trial

STORE=Store();MANAGER=EngineManager(STORE);CSRF=secrets.token_urlsafe(32)

def state():
    settings=STORE.settings();items=annotate(STORE,STORE.company_list());usage=STORE.usage();campaign=CampaignManager(STORE).state()
    from .commercial.ai_settings import read as ai_settings
    settings={**settings,'commercial_ai':ai_settings(STORE)}
    legacy_job=MANAGER.state()
    job={**legacy_job,**({'running':campaign['running'],'message':campaign['message'],'checked':campaign['examined'],'added':campaign['qualified'],'updated_at':campaign['updated_at']} if campaign else {})}
    return {'commercial_profiles':{**__import__('sales.commercial.catalog',fromlist=['PROFILES']).PROFILES,'deep':__import__('sales.commercial.catalog',fromlist=['DEEP_PROFILE']).DEEP_PROFILE},'commercial_engines':COMMERCIAL_ENGINES,'commercial_regions':COMMERCIAL_REGIONS,'csrf':CSRF,'version':'6.0','agent6_flows':__import__('sales.agent6',fromlist=['FLOWS']).FLOWS,'items':items,'settings':settings,'job':job,'campaign':campaign,'research_quality':quality_report(STORE),'commercial_feedback':commercial_feedback(STORE),'engines':ENGINES,'stages':STAGES,'stats':STORE.stats(),'usage':usage,'serper':__import__('sales.serper_provider',fromlist=['status']).status(STORE,campaign['id'] if campaign else None),'providers':{'tavily':False,'searxng':settings['provider']=='searxng' and bool(os.getenv('SEARXNG_URL')),'serper':settings['provider']=='serper','advisor':'locale' if settings.get('ollama_model') else 'regole'},'legacy_count':len(STORE.legacy())}

class Handler(BaseHTTPRequestHandler):
    def reply(self,status,body,mime='application/json; charset=utf-8'):
        data=body if isinstance(body,bytes) else (json.dumps(body,ensure_ascii=False).encode() if mime.startswith('application/json') else str(body).encode())
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass
    def trusted(self):return self.headers.get('Host')==f'127.0.0.1:{PORT}'
    def do_GET(self):
        if not self.trusted():return self.reply(403,{'error':'Apri l’app da '+ORIGIN})
        path=urlsplit(self.path).path
        try:
            if path=='/agent6.js':return self.reply(200,(ROOT/'static/agent6.js').read_bytes(),'text/javascript; charset=utf-8')
            if path=='/worklist.js':return self.reply(200,(ROOT/'static/worklist.js').read_bytes(),'text/javascript; charset=utf-8')
            if path=='/api/agent6/records':
                from .agent6.api import listing
                return self.reply(200,listing(STORE,{k:v[-1] for k,v in parse_qs(urlsplit(self.path).query).items()}))
            if path=='/api/agent6/worklist':
                from .agent6.worklist import listing
                return self.reply(200,listing(STORE,{k:v[-1] for k,v in parse_qs(urlsplit(self.path).query).items()}))
            if path=='/api/agent6/intelligence':
                from .agent6.api import intelligence
                return self.reply(200,intelligence(STORE))
            if re.fullmatch(r'/api/agent6/records/\d+',path):
                from .agent6.api import dossier
                return self.reply(200,dossier(STORE,int(path.rsplit('/',1)[1])))
            if path=='/commercial.js':return self.reply(200,(ROOT/'static/commercial.js').read_bytes(),'text/javascript; charset=utf-8')
            if path=='/api/commercial/catalog':return self.reply(200,{'engines':COMMERCIAL_ENGINES,'regions':COMMERCIAL_REGIONS})
            if path=='/api/commercial/ai-settings':
                from .commercial.ai_settings import read
                return self.reply(200,read(STORE))
            if path=='/api/commercial/discovery':
                from .commercial.storage import discovery_listing
                return self.reply(200,discovery_listing(STORE,{k:v[-1] for k,v in parse_qs(urlsplit(self.path).query).items()}))
            if path=='/api/commercial/opportunities':return self.reply(200,Opportunities(STORE).listing({k:v[-1] for k,v in parse_qs(urlsplit(self.path).query).items()}))
            if path=='/api/commercial/recommendations':
                from .commercial.recommendation_store import listing
                return self.reply(200,listing(STORE,{k:v[-1] for k,v in parse_qs(urlsplit(self.path).query).items()}))
            if re.fullmatch(r'/api/commercial/opportunities/\d+',path):return self.reply(200,Opportunities(STORE).get(int(path.rsplit('/',1)[1])))
            if re.fullmatch(r'/site-reviews/commercial-[a-f0-9]{24}\.png',path):
                p=STORE.path.parent/'site-reviews'/path.rsplit('/',1)[1]
                if p.is_file():return self.reply(200,p.read_bytes(),'image/png')
            static={'/search-trial.js':('search-trial.js','text/javascript; charset=utf-8'),'/grants.js':('grants.js','text/javascript; charset=utf-8'),'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/research.js':('research.js','text/javascript; charset=utf-8')}
            if path in static:
                filename,mime=static[path];return self.reply(200,(ROOT/'static'/filename).read_bytes(),mime)
            if path=='/api/grants':return self.reply(200,GrantsManager(STORE).state())
            if path=='/api/grants/profile':return self.reply(200,{'profile':grant_profile(STORE),'regions':REGIONS,'forms':FORMS,'regimes':REGIMES,'sources':CATALOG})
            if path=='/api/state':return self.reply(200,state())
            if path=='/api/search-trial':return self.reply(200,TrialManager(STORE).state())
            if path=='/api/campaigns':
                with STORE.connect() as c:ids=[r[0] for r in c.execute('SELECT id FROM campaigns ORDER BY id DESC LIMIT 50')]
                return self.reply(200,[ResearchStore(STORE).campaign(i) for i in ids])
            if re.fullmatch(r'/api/campaigns/\d+',path):return self.reply(200,ResearchStore(STORE).campaign(int(path.rsplit('/',1)[1])))
            if path=='/api/opportunities':
                params={k:v[-1] for k,v in parse_qs(urlsplit(self.path).query).items()}
                return self.reply(200,ResearchStore(STORE).opportunities(params,int(params.get('offset',0)),int(params.get('limit',50))))
            if re.fullmatch(r'/api/opportunities/\d+',path):return self.reply(200,ResearchStore(STORE).opportunity(int(path.rsplit('/',1)[1])))
            if path=='/api/candidates':
                return self.reply(200,Funnel(ResearchStore(STORE)).listing({k:v[-1] for k,v in parse_qs(urlsplit(self.path).query).items()}))
            if re.fullmatch(r'/api/campaigns/\d+/diagnostics',path):
                from .discovery_control import diagnostics
                return self.reply(200,diagnostics(ResearchStore(STORE),int(path.split('/')[3])))
            if re.fullmatch(r'/api/campaigns/\d+/paths',path):
                from .discovery_trace import paths
                params=parse_qs(urlsplit(self.path).query)
                return self.reply(200,paths(STORE,int(path.split('/')[3]),params.get('offset',[0])[0],params.get('limit',[20])[0]))
            if re.fullmatch(r'/api/campaigns/\d+/metrics',path):return self.reply(200,Funnel(ResearchStore(STORE)).metrics(int(path.split('/')[3])))
            if path=='/api/history':return self.reply(200,STORE.history())
            if path=='/api/legacy':return self.reply(200,STORE.legacy())
            if path=='/api/sources':
                with STORE.connect() as c:rows=[dict(r) for r in c.execute('SELECT * FROM sources ORDER BY id DESC')]
                return self.reply(200,rows)
            if re.fullmatch(r'/api/prospects/\d+',path):
                item=annotate(STORE,[STORE.company_detail(int(path.rsplit('/',1)[1]))])[0];item['dossier']=build_dossier(item,STORE.settings());return self.reply(200,item)
            if re.fullmatch(r'/site-reviews/lighthouse-[a-f0-9]{24}-(mobile|desktop)\.json',path):
                p=DATA/'site-reviews'/path.rsplit('/',1)[1]
                if p.is_file():return self.reply(200,p.read_bytes())
            return self.reply(404,{'error':'Risorsa non disponibile'})
        except ValueError as exc:self.reply(400,{'error':str(exc)})
        except Exception:self.reply(500,{'error':'Errore locale di lettura. Consulta il terminale e riprova.'})
    def do_POST(self):
        if not self.trusted() or self.headers.get('Origin')!=ORIGIN or self.headers.get('X-CSRF-Token')!=CSRF:return self.reply(403,{'error':'Richiesta non autorizzata. Ricarica l’app.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<=length<=100000:raise ValueError('Richiesta troppo grande')
            body=json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body,dict):raise ValueError('Richiesta non valida')
            path=urlsplit(self.path).path
            if path=='/api/agent6/preview':
                from .agent6.api import preview
                return self.reply(200,preview(STORE,body.get('filters',{})))
            if re.fullmatch(r'/api/agent6/records/\d+/corrections',path):
                from .agent6.annotations import save
                return self.reply(200,save(STORE,int(path.split('/')[4]),body.get('changes'),body.get('note')))
            if re.fullmatch(r'/api/agent6/records/\d+/(feedback|save)',path):
                from .agent6.memory import feedback
                from .agent6.api import save_contact
                rid=int(path.split('/')[4])
                return self.reply(200,feedback(STORE,rid,body.get('kind'),body.get('note','')) if path.endswith('/feedback') else save_contact(STORE,rid))
            if path=='/api/commercial/search-plan':
                from .commercial.search_intelligence import preview
                return self.reply(200,preview(STORE,body.get('filters',{})))
            if path=='/api/commercial/ai-settings':
                from .commercial.ai_settings import save
                return self.reply(200,save(STORE,body))
            if re.fullmatch(r'/api/commercial/opportunities/\d+/social-review',path):return self.reply(200,Opportunities(STORE).social_review(int(path.split('/')[4]),body))
            if re.fullmatch(r'/api/commercial/opportunities/\d+/job-observation',path):
                from .commercial.recommendation_store import record_observation
                return self.reply(200,record_observation(STORE,int(path.split('/')[4]),body))
            if re.fullmatch(r'/api/commercial/opportunities/\d+/job-review',path):
                from .commercial.recommendation_store import review
                return self.reply(200,review(STORE,int(path.split('/')[4]),body))
            if re.fullmatch(r'/api/commercial/opportunities/\d+/action',path):return self.reply(200,Opportunities(STORE).action(int(path.split('/')[4]),body.get('action')))
            if path=='/api/search-trial/key':
                save_serper_key(STORE,body.get('key'));return self.reply(200,TrialManager(STORE).state())
            if path=='/api/search-trial/start':return self.reply(200,TrialManager(STORE).start(body.get('free_credits_confirmed')))
            if path=='/api/search-trial/stop':return self.reply(200,TrialManager(STORE).stop())
            if path=='/api/search-trial/review':return self.reply(200,review_search_trial(STORE,body))
            if path=='/api/grants/profile':return self.reply(200,grant_profile(STORE,body))
            if path=='/api/grants/answers':return self.reply(200,answer_requirements(STORE,body))
            if path=='/api/grants/start':return self.reply(200,GrantsManager(STORE).start())
            if path=='/api/grants/stop':return self.reply(200,GrantsManager(STORE).stop())
            if path in ('/api/campaigns','/api/research'):
                if MANAGER.state()['running']:raise ValueError('Attendi il completamento del controllo tecnico in corso')
                filters=body.get('filters') or {}
                if filters.get('agent_version')=='6.0':
                    filters={**filters,'decision_engine':'ai_first_1','discovery_triage_version':1,'continuation_version':1}
                else:
                    raise ValueError('Per nuove campagne usa la ricerca AI-first. Le campagne storiche restano consultabili e riprendibili.')
                return self.reply(200,CampaignManager(STORE).start(filters,body.get('target',50)))
            elif re.fullmatch(r'/api/campaigns/\d+/(stop|resume)',path):
                parts=path.split('/');manager=CampaignManager(STORE);ident=int(parts[3])
                return self.reply(200,manager.stop(ident) if parts[4]=='stop' else manager.resume(ident))
            elif re.fullmatch(r'/api/opportunities/\d+/review',path):
                return self.reply(200,ResearchStore(STORE).review(int(path.split('/')[3]),body.get('verdict'),body.get('reason')))
            elif path=='/api/commercial-outcomes':
                return self.reply(200,Funnel(ResearchStore(STORE)).outcome(body.get('kind'),body.get('note',''),body.get('candidate_id'),body.get('assessment_id')))
            elif path=='/api/research/stop':
                campaign=CampaignManager(STORE).state()
                if campaign and campaign['running']:CampaignManager(STORE).stop(campaign['id'])
                MANAGER.stop_event.set()
            elif path=='/api/settings':STORE.configure(body)
            elif path=='/api/backup':
                from scripts.backup import backup
                return self.reply(200,{'ok':True,'path':backup()})
            elif re.fullmatch(r'/api/prospects/\d+/(update|draft|advisor|compose|confirm|audit|dismiss|restore)',path):
                parts=path.split('/');ident=int(parts[3]);action=parts[4];item=STORE.company_detail(ident);ident=item['id']
                if action in ('dismiss','restore'):return self.reply(200,STORE.set_dismissed(ident,action=='dismiss'))
                if item['dismissed_at']:raise ValueError('Ripristina la proposta prima di aggiornarla.')
                if action=='update':return self.reply(200,STORE.update_company(ident,body))
                if action=='draft':
                    if item['do_not_contact']:raise ValueError('Azienda segnata non contattare')
                    draft=body.get('draft') if 'draft' in body else communication(item,STORE.settings())
                    STORE.save_draft(ident,draft);return self.reply(200,draft)
                if action=='advisor':return self.reply(200,local_advice(item,STORE.settings()))
                if action=='audit':
                    campaign=CampaignManager(STORE).state()
                    if campaign and campaign['running']:raise ValueError('Ferma la ricerca prima di un controllo tecnico manuale')
                    MANAGER.start(['D'],[item['website']])
                if action=='compose':
                    if item['do_not_contact']:raise ValueError('Azienda segnata non contattare')
                    if body.get('confirmed') is not True:raise ValueError('Conferma di aver verificato destinatario, testo e presupposto di contatto')
                    if not item['contact_basis']:raise ValueError('Registra il presupposto del contatto nella scheda')
                    recipient=body.get('recipient','').strip()
                    if not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+',recipient):raise ValueError('Email non valida')
                    draft=item['draft']
                    if not draft.get('email') or not draft.get('subject'):raise ValueError('Genera e salva prima la bozza')
                    if '\n' in draft['subject'] or '\r' in draft['subject']:raise ValueError('Oggetto su una sola riga')
                    with STORE.connect() as c:c.execute('INSERT INTO interactions(prospect_id,kind,detail,created_at) VALUES (?,?,?,?)',(ident,'compose','Bozza aperta manualmente in Gmail; invio non confermato.',now()))
                    # Only open Google's composer. This application never calls messages.send.
                    return self.reply(200,{'url':'https://mail.google.com/mail/?'+urlencode({'view':'cm','fs':'1','to':recipient,'su':draft['subject'],'body':draft['email']})})
                if action=='confirm':
                    if body.get('confirmed') is not True:raise ValueError('Conferma manualmente l’invio effettuato')
                    with STORE.connect() as c:
                        if not c.execute("SELECT 1 FROM interactions WHERE prospect_id=? AND kind='compose'",(ident,)).fetchone():raise ValueError('Nessuna apertura Gmail registrata; usa lo stato manuale se hai contattato tramite un altro canale')
                    return self.reply(200,STORE.update_company(ident,{'stage':'contacted','interaction':'Invio confermato manualmente dopo verifica in Gmail.'}))
            else:return self.reply(404,{'error':'Operazione non disponibile'})
            self.reply(200,{'ok':True})
        except (ValueError,KeyError,TypeError) as exc:self.reply(400,{'error':str(exc)})
        except Exception:self.reply(500,{'error':'Operazione non completata. Nessun messaggio è stato inviato automaticamente.'})
    def log_message(self,format,*args):pass

def initialize_runtime():
    """Called only after this process has acquired the HTTP listening socket."""
    STORE.init();STORE.migrate_legacy(DATA/'customers.sqlite3')
    from .local_model import ensure_local_model
    model=ensure_local_model()
    if not model['available']:print(model['reason'],flush=True)
    elif 'qwen2.5:7b' in model.get('models',[]) and not STORE.settings()['ollama_model']:STORE.configure({'ollama_model':'qwen2.5:7b'})
    supervisor=CampaignManager(STORE);supervisor.recover()
    grants=GrantsManager(STORE);grants.stop()
    trials=TrialManager(STORE);trials.stop()
    atexit.register(trials.stop)
    atexit.register(grants.stop)
    atexit.register(supervisor.close)
    def shutdown(signum,frame):
        trials.stop();grants.stop();supervisor.close();raise SystemExit(0)
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGHUP,shutdown)
def main():
    # Binding must precede migrations/recovery: a second launch must not pause
    # the active worker or change its database before failing with EADDRINUSE.
    try:
        http=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    except OSError as exc:
        import errno
        if exc.errno==errno.EADDRINUSE:
            raise SystemExit(f'Porta {PORT} già occupata. CustomerSearch potrebbe essere già aperto: {ORIGIN}. Chiudi il processo esistente prima di riavviare.') from None
        raise
    try:
        initialize_runtime()
        from .agent6 import VERSION
        print('CustomerSearch '+VERSION+' · '+ORIGIN,flush=True)
        http.serve_forever()
    finally:
        http.server_close()
