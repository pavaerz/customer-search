"""Explicit, bounded Serper experiment. Never a paid fallback for campaigns."""
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
from pathlib import Path
from urllib import request, error
from .config import ROOT
from .db import now, encode, digest, domain

LIMIT = 100
RESOLUTION_REQUESTS = 6
RESOLUTION_CANDIDATES = 4
QUERIES = [
    ('explicit', f'"richiesta di offerta" sito web Veneto {now()[:4]}'),
    ('change', f'azienda alimentare Veneto nuova linea prodotti {now()[:4]}'),
    ('change', f'azienda arredamento Veneto espansione mercati esteri {now()[:4]}'),
    ('investment', f'PMI Veneto investe vendita online {now()[:4]}'),
    ('process', 'produttore Veneto ordini B2B catalogo personalizzati rivenditori'),
    ('partner', 'agenzia Veneto cerca freelance sviluppo progetto ecommerce'),
]


def migrate(store):
    with store.connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS search_trials(id INTEGER PRIMARY KEY, state TEXT NOT NULL, generation TEXT NOT NULL, pid INTEGER, message TEXT NOT NULL, report TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS search_trial_requests(id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES search_trials(id), fingerprint TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS search_trial_reviews(run_id INTEGER REFERENCES search_trials(id), url TEXT NOT NULL, verdict TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(run_id,url))')
        c.execute('INSERT OR IGNORE INTO research_schema VALUES (44,?)',(now(),))


def key_path(store):
    return store.path.with_suffix('.serper-key')


def api_key(store):
    path = key_path(store)
    return path.read_text().strip() if path.exists() else os.getenv('SERPER_API_KEY', '').strip()


def save_key(store, value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,200}', value.strip()):
        raise ValueError('Chiave API non valida: copia soltanto la chiave dal pannello Serper')
    if state(store)['running']:
        raise ValueError('Ferma il confronto prima di cambiare la chiave')
    path = key_path(store)
    temporary = path.with_name(path.name+'.'+secrets.token_hex(6))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(value.strip())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Serper: redirect inatteso; chiave non inoltrata')


class SerperHTTPError(ValueError):
    def __init__(self,status,message):
        super().__init__(message)
        self.status=status


def transport(key, payload):
    """Fixed TLS endpoint; credentials never reach pages, redirects, logs or URLs."""
    req = request.Request('https://google.serper.dev/search', data=json.dumps(payload).encode(),
                          headers={'X-API-KEY': key, 'Content-Type': 'application/json'})
    try:
        with request.build_opener(NoRedirect()).open(req, timeout=__import__('sales.commercial.resources',fromlist=['timeout']).timeout(25)) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('Serper: risposta troppo grande')
            return json.loads(raw)
    except error.HTTPError as exc:
        messages = {401:'chiave non valida', 403:'accesso negato o crediti non disponibili', 402:'crediti esauriti', 429:'limite del servizio raggiunto'}
        raise SerperHTTPError(exc.code,'Serper: '+messages.get(exc.code, 'errore HTTP '+str(exc.code))+'. Nessun acquisto automatico.') from None
    except (OSError, ValueError) as exc:
        # Do not propagate a response body or a request containing credentials.
        raise ValueError('Serper: connessione o risposta non verificabile ('+type(exc).__name__+').') from None


def serper_search(store, run_id, generation, query, check):
    check()
    key = api_key(store)
    if not key:
        raise ValueError('Inserisci la chiave Serper in Impostazioni')
    payload = {'q':query, 'gl':'it', 'hl':'it', 'num':10, 'page':1}
    # Reserve before network, including uncertain/error requests. No automatic refund/retry.
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute("SELECT 1 FROM search_trials WHERE id=? AND generation=? AND state='running'", (run_id,generation)).fetchone():
            raise InterruptedError('Confronto fermato')
        if c.execute('SELECT count(*) FROM search_trial_requests').fetchone()[0] >= LIMIT:
            raise ValueError('Prova terminata: raggiunte 100 richieste Serper. Nessuna ricarica automatica.')
        rid = c.execute("INSERT INTO search_trial_requests(run_id,fingerprint,state,created_at) VALUES (?,?,'reserved',?)", (run_id,digest(encode(payload)),now())).lastrowid
    result = transport(key, payload)
    check()
    if not isinstance(result,dict) or not isinstance(result.get('organic'),list):
        raise ValueError('Serper: risposta priva di risultati organici verificabili')
    with store.connect() as c:
        c.execute("UPDATE search_trial_requests SET state='received' WHERE id=?", (rid,))
    return [{'url':r['link'],'title':r.get('title',''),'engines':['google via Serper']} for r in result['organic'][:10] if isinstance(r,dict) and isinstance(r.get('link'),str)]


def metrics(report, reviews):
    out=[]
    for provider in ('serper','searxng'):
        queries=[q for q in report.get('queries',[]) if q['provider']==provider]
        candidates=[x for x in report.get('candidates',[]) if provider in x['providers']]
        examined=[x for x in candidates if x.get('triage')]
        verified={x.get('identity',{}).get('legal_id') or domain(x['url']) for x in examined if x.get('identity',{}).get('identity_status')=='verified'}
        qualified={x.get('identity',{}).get('legal_id') or domain(x['url']) for x in candidates if x.get('assessment',{}).get('status')=='qualified'}
        checked=[x for x in candidates if x['url'] in reviews and x.get('assessment',{}).get('status')=='qualified']
        out.append({'provider':provider,'queries':len(queries),'errors':sum(bool(q.get('error')) for q in queries),
                    'urls':len({r['url'] for q in queries for r in q.get('results',[])}),'examined':len(examined),
                    'verified_companies':len(verified),'promising':sum(x.get('triage',{}).get('state')=='promising' for x in candidates),
                    'deep_checks':sum('assessment' in x for x in candidates),'qualified':len(qualified),
                    'rejected':sum(x.get('assessment',x.get('triage',{})).get('status',x.get('triage',{}).get('state'))=='rejected' for x in candidates),
                    'reviewed':len(checked),'confirmed':sum(reviews[x['url']]['verdict']=='confirmed' for x in checked),
                    'false_positives':sum(reviews[x['url']]['verdict']=='false_positive' for x in checked),
                    'missed_opportunities':sum(reviews.get(x['url'],{}).get('verdict')=='missed' for x in candidates),
                    'data_errors':sum(reviews.get(x['url'],{}).get('verdict')=='data_error' for x in candidates),
                    'query_seconds':round(sum(q.get('seconds',0) for q in queries),2)})
    return out


def state(store):
    migrate(store)
    with store.connect() as c:
        row=c.execute('SELECT * FROM search_trials ORDER BY id DESC LIMIT 1').fetchone()
        used=c.execute('SELECT count(*) FROM search_trial_requests').fetchone()[0]
        reviews={r['url']:dict(r) for r in c.execute('SELECT * FROM search_trial_reviews WHERE run_id=?', (row['id'] if row else 0,))}
    run=dict(row) if row else None
    if run:
        run.pop('generation');run.pop('pid')
        report=json.loads(run['report']);run['metrics']=metrics(report,reviews)
        for candidate in report.get('candidates',[]):
            candidate['review']=reviews.get(candidate['url'])
            # Full original documents stay on disk; the UI gets citations and metadata.
            def summaries(value):
                if isinstance(value,dict):
                    if value.get('content_hash') and value.get('url'):
                        value.pop('text',None);value.pop('research_text',None)
                    for item in value.values():summaries(item)
                elif isinstance(value,list):
                    for item in value:summaries(item)
            summaries(candidate)
        run['report']=report
    return {'configured':bool(api_key(store)),'used':used,'limit':LIMIT,'remaining':max(0,LIMIT-used),'run':run,'running':bool(run and run['state']=='running')}


def review(store, data):
    current=state(store);run=current['run']
    if not run or run['state']=='running':raise ValueError('Attendi la fine del confronto o fermalo prima di revisionare')
    candidate=next((x for x in run['report']['candidates'] if x['url']==data.get('url')),None)
    verdict=data.get('verdict');reason=data.get('reason','')
    if not candidate or verdict not in ('confirmed','false_positive','correct_rejection','missed','data_error') or not isinstance(reason,str) or not 8<=len(reason.strip())<=1000:
        raise ValueError('Scegli un esito e una motivazione specifica di almeno 8 caratteri')
    qualified=candidate.get('assessment',{}).get('status')=='qualified'
    if (verdict in ('confirmed','false_positive')) != qualified:raise ValueError('Esito non compatibile con la valutazione automatica')
    with store.connect() as c:
        c.execute('INSERT OR REPLACE INTO search_trial_reviews VALUES (?,?,?,?,?)',(run['id'],candidate['url'],verdict,reason.strip(),now()))
    return state(store)


class TrialManager:
    _lock=threading.RLock();_workers={}
    def __init__(self,store):self.store=store;migrate(store)
    @property
    def key(self):return str(self.store.path.resolve())
    def start(self, confirmed=False):
        if self.store.settings()['provider']=='serper':
            raise ValueError('Confronto con SearXNG disattivato: usa Cerca clienti, che ora utilizza soltanto Serper. Lo storico rimane consultabile.')
        if confirmed is not True:raise ValueError('Conferma la disponibilità di almeno 12 crediti gratuiti Serper')
        with self._lock:
            status=state(self.store)
            if not status['configured']:raise ValueError('Inserisci prima la chiave Serper')
            if status['remaining']<len(QUERIES)+RESOLUTION_REQUESTS:raise ValueError('Richieste residue insufficienti per un confronto completo')
            with self.store.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute("SELECT 1 FROM search_trials WHERE state='running'").fetchone():raise ValueError('Un confronto è già in corso')
                token=secrets.token_hex(16)
                report={'protocol':'Sei query identiche in Veneto; primi 10 risultati per query, senza filtro temporale. Campione bilanciato: primi 24 URL unici per provider, selezionati alternando le query. Fino a 4 approfondimenti per provider; pagine comuni verificate una sola volta. Nessuna promozione automatica nel CRM. Campione esplorativo, non certifica efficacia commerciale.', 'queries':[], 'candidates':[], 'limits':['Tempi di lettura condivisi per URL comuni: non utilizzabili per confrontare la velocità dei provider.','Budget ignoti restano ignoti. Nessun costo economico attribuito senza dati del conto Serper.','Un verdetto automatico richiede revisione separata delle prove.']}
                report['version']=4
                report['protocol']+=' Protocollo 2: query per settore e bisogno; fino a 6 ricerche aggiuntive di identità e 4 siti aziendali derivati per provider. Questi limiti valgono solo per il confronto, non per le campagne.'
                report['protocol']+=' Variante 4: approfondimenti ordinati per identità, sede e contatti verificati; editori dopo le imprese. Non è un confronto invariato con le prove precedenti.'
                report['protocol']+=' Variante 3: formulazioni naturali; anno corrente nelle ricerche di eventi, senza attribuire automaticamente attualità ai risultati.'
                report['limits'].append('Query e verifiche cambiate rispetto alla prima prova: il confronto storico non isola il solo effetto del provider.')
                rid=c.execute("INSERT INTO search_trials(state,generation,message,report,created_at,updated_at) VALUES ('running',?,?,?,?,?)",(token,'Preparazione del confronto',encode(report),now(),now())).lastrowid
            try:
                proc=subprocess.Popen([sys.executable,'-m','sales.search_trial_worker','--db',self.key,'--run',str(rid),'--generation',token],cwd=ROOT,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                self._workers[self.key]=proc
                with self.store.connect() as c:c.execute('UPDATE search_trials SET pid=? WHERE id=?',(proc.pid,rid))
            except Exception:
                with self.store.connect() as c:c.execute("UPDATE search_trials SET state='error',message='Impossibile avviare il confronto' WHERE id=?",(rid,))
                raise
        return state(self.store)
    def stop(self):
        with self._lock:
            with self.store.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute("SELECT * FROM search_trials WHERE state='running'").fetchone()
                if row:c.execute("UPDATE search_trials SET state='stopped',generation=?,message='Confronto fermato. Le verifiche completate sono conservate.',updated_at=? WHERE id=?",(secrets.token_hex(16),now(),row['id']))
            if not row:return state(self.store)
            proc=self._workers.get(self.key)
            pid=row['pid']
            owned=bool(proc and proc.poll() is None and proc.pid==pid)
            if pid and not owned:
                try:
                    command=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=1).stdout
                    owned='sales.search_trial_worker' in command and self.key in command and '--run '+str(row['id'])+' ' in command
                except (OSError,subprocess.TimeoutExpired):pass
            if owned:
                try:
                    os.killpg(pid,signal.SIGTERM)
                    if proc:
                        try:proc.wait(timeout=1)
                        except subprocess.TimeoutExpired:pass
                    os.killpg(pid,signal.SIGKILL)
                    if proc:proc.wait(timeout=1)
                except ProcessLookupError:pass
        return state(self.store)
    def state(self):
        value=state(self.store);proc=self._workers.get(self.key)
        if value['running'] and proc and proc.poll() is not None:
            with self.store.connect() as c:c.execute("UPDATE search_trials SET state='error',message='Il processo si è interrotto. Le verifiche completate sono conservate.' WHERE id=? AND state='running'",(value['run']['id'],))
            return state(self.store)
        return value
