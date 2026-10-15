"""Independent grants workspace with source-backed profile comparisons."""
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
from datetime import date
from .db import now,encode,digest,domain
from .config import ROOT
from .grant_eligibility import EXTRA_DEFAULTS,ENUMS,evaluate

REGIONS=('Veneto','Lombardia','Piemonte','Toscana','Emilia-Romagna','Friuli-Venezia Giulia','Trentino-Alto Adige','Liguria','Valle d’Aosta','Lazio','Marche','Umbria','Abruzzo','Molise','Campania','Puglia','Basilicata','Calabria','Sicilia','Sardegna')
FORMS={'unknown':'Da confermare','professional':'Libero professionista','sole_trader':'Ditta individuale','company':'Società'}
REGIMES={'unknown':'Da confermare','forfettario':'Forfettario','ordinario':'Ordinario','other':'Altro / da precisare'}
CATALOG=[('Invitalia','https://www.invitalia.it/per-le-imprese/incentivi-e-strumenti','Italia'),('Regione Veneto','https://bandi.regione.veneto.it/Public/Index?lang=it','Veneto'),('Camera di Commercio di Padova','https://www.pd.camcom.it/it/incentivi-imprese','Veneto')]
DEFAULT={'vat':'','name':'','ateco':'','region':'Veneto','province':'','legal_form':'unknown','tax_regime':'unknown','started_on':'','activity':'','investment':'',**EXTRA_DEFAULTS}


def migrate(store):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS grant_profile(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL,updated_at TEXT NOT NULL)')
        c.execute('''CREATE TABLE IF NOT EXISTS grant_runs(id INTEGER PRIMARY KEY,state TEXT NOT NULL,generation TEXT NOT NULL,profile TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,pid INTEGER)''')
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_grant_run ON grant_runs((1)) WHERE state='running'")
        c.execute('''CREATE TABLE IF NOT EXISTS grant_tasks(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES grant_runs(id),url TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',error TEXT,UNIQUE(run_id,url))''')
        c.execute('''CREATE TABLE IF NOT EXISTS grant_items(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES grant_runs(id),url TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,checked_at TEXT NOT NULL,UNIQUE(run_id,url))''')

        c.execute('INSERT OR IGNORE INTO research_schema VALUES (43,?)',(now(),))

def valid_vat(vat):
    if not re.fullmatch(r'\d{11}',vat) or len(set(vat))==1:return False
    total=sum(int(vat[i]) for i in (0,2,4,6,8))
    total+=sum((int(vat[i])*2 if int(vat[i])*2<10 else int(vat[i])*2-9) for i in (1,3,5,7,9))
    return (10-total%10)%10==int(vat[-1])


def profile(store,body=None):
    if body is not None:
        if not isinstance(body,dict) or set(body)-set(DEFAULT):raise ValueError('Campi del profilo non validi')
        out={**profile(store),**body}
        for key,value in out.items():
            if key=='facts':
                if not isinstance(value,dict) or len(value)>200 or any(not re.fullmatch(r'[a-f0-9]{64}',k) or v not in ('yes','no','unknown') for k,v in value.items()):raise ValueError('Risposte ai requisiti non valide')
                continue
            if not isinstance(value,str) or len(value)>500:raise ValueError('Valore non valido: '+key)
            out[key]=value.strip()
        out['vat']=re.sub(r'\s','',out['vat']).removeprefix('IT').removeprefix('it')
        if out['vat'] and not valid_vat(out['vat']):raise ValueError('Partita IVA: controlla le 11 cifre e la cifra di controllo')
        if out['ateco'] and not re.fullmatch(r'\d{2}(?:\.?\d{2}){1,2}',out['ateco']):raise ValueError('Inserisci il codice ATECO, per esempio 62.10.00')
        if out['region'] not in REGIONS or out['legal_form'] not in FORMS or out['tax_regime'] not in REGIMES:raise ValueError('Selezione non valida')
        for key,allowed in ENUMS.items():
            if out[key] not in (*allowed,'unknown'):raise ValueError('Selezione non valida: '+key)
        if out['investment_region'] and out['investment_region'] not in REGIONS:raise ValueError('Regione investimento non valida')
        if out['investment_amount']:
            from decimal import Decimal,InvalidOperation
            try:
                value=Decimal(out['investment_amount'].replace(',','.'))
                if not value.is_finite() or value<0 or value>1000000000:raise ValueError('Importo non valido')
                out['investment_amount']=str(value)
            except InvalidOperation:raise ValueError('Importo non valido') from None
        if out['birth_date']:
            try:birthday=date.fromisoformat(out['birth_date'])
            except ValueError:raise ValueError('Data di nascita non valida') from None
            if birthday>date.today():raise ValueError('La data di nascita non può essere futura')
        if out['started_on']:
            try:d=date.fromisoformat(out['started_on'])
            except ValueError:raise ValueError('Data di apertura non valida') from None
            if d>date.today():raise ValueError('La data di apertura non può essere futura')
        with store.connect() as c:c.execute('INSERT INTO grant_profile VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,updated_at=excluded.updated_at',(encode(out),now()))
    with store.connect() as c:r=c.execute('SELECT body FROM grant_profile WHERE id=1').fetchone()
    return {**DEFAULT,**(json.loads(r[0]) if r else {})}


def state(store):
    with store.connect() as c:
        r=c.execute('SELECT * FROM grant_runs ORDER BY id DESC LIMIT 1').fetchone()
        if not r:return {'run':None,'items':[],'tasks':{},'errors':[]}
        run=dict(r);run.pop('generation');run['profile']=json.loads(run['profile'])
        tasks={r[0]:r[1] for r in c.execute('SELECT state,count(*) FROM grant_tasks WHERE run_id=? GROUP BY state',(run['id'],))}
        items=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT * FROM grant_items WHERE run_id=? ORDER BY id DESC',(run['id'],))]
        errors=[dict(r) for r in c.execute("SELECT url,error FROM grant_tasks WHERE run_id=? AND state='failed'",(run['id'],))]
    current=profile(store)
    for item in items:
        b=item['body'];bundle=b.pop('eligibility_bundle',None)
        if bundle:
            ev=evaluate(bundle,current);b['eligibility']=ev;b['status']=ev['status'];b['reason']=ev['reason'];b['documents']=[{k:d[k] for k in ('url','title','checked_at')} for d in bundle['documents']]
        else:
            b['status']='not_analyzed';b['reason']='Questa scheda precede il confronto automatico. Premi Ricerca bandi per analizzarne i requisiti.'
            b['eligibility']={'status':'not_analyzed','checks':[],'questions':[],'blockers':[],'reason':b['reason']}
        b.pop('missing',None);b.pop('match_basis',None)
    return {'run':run,'items':items,'tasks':tasks,'errors':errors}


def answer_requirements(store,body):
    answers=body.get('answers')
    if not isinstance(answers,dict) or not answers:raise ValueError('Indica almeno una risposta')
    allowed={q['key'] for item in state(store)['items'] for q in item['body']['eligibility'].get('declarations',[])}
    if set(answers)-allowed or any(v not in ('yes','no','unknown') for v in answers.values()):raise ValueError('Risposta non valida o requisito non più attuale: aggiorna la scheda')
    p=profile(store);profile(store,{'facts':{**p['facts'],**answers}})
    return state(store)


def official(url):
    try:
        from .providers import canonical
        canonical(url)
    except (ValueError,TypeError):return False
    host=domain(url)
    return any(host==domain(seed) or host.endswith('.'+domain(seed)) for _,seed,_ in CATALOG)


def excerpts(text,pattern):
    out=[]
    for m in re.finditer(pattern,text,re.I):
        start=text.rfind('\n',0,m.start())+1;end=text.find('\n',m.end())
        line=text[start:end if end>=0 else m.end()+350].strip()[:650]
        if line and line not in out:out.append(line)
        if len(out)==3:break
    return out


def assessment(page,p):
    from .extract import parse_page
    doc=parse_page(page);text=doc['text']
    title=next((h['text'] for h in doc['doc'].headings if h['tag']=='h1' and h['text']),doc['title'])[:300]
    if any(page['url'].split('?')[0].rstrip('/')==seed.split('?')[0].rstrip('/') for _,seed,_ in CATALOG):return None
    if not re.search(r'bando|incentiv|agevolaz|contribut|finanziament',title+' '+text[:4000],re.I):return None
    if re.search(r'gare? d.appalto|amministrazione trasparente|concorso pubblico|bandi di gara',title,re.I):return None
    requirements=excerpts(text,r'beneficiar|possono (?:accedere|partecipare|presentare)|destinatar|requisit|ammissibil')
    if not requirements:return None
    deadlines=excerpts(text,r'scadenza|scade|domande.{0,30}(?:entro|fino|dal)|sportello|termin[ei].{0,20}presentazion')
    amounts=excerpts(text,r'fondo perduto|contributo.{0,40}(?:euro|€|percent)|finanziamento agevolato')
    return {'status':'analyzing','reason':'Analisi dei requisiti in corso.','requirements':requirements,'deadlines':deadlines,'benefit':amounts,'title':title or domain(page['url']),'source_text_hash':digest(text)}



class GrantsManager:
    _lock=threading.RLock();_workers={}
    def __init__(self,store):self.store=store
    def start(self):
        with self._lock:
            p=profile(self.store)
            if not p['activity']:raise ValueError('Descrivi la tua attività nel profilo prima di cercare bandi')
            with self.store.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute("SELECT 1 FROM grant_runs WHERE state='running'").fetchone():raise ValueError('Una ricerca bandi è già in corso')
                token=secrets.token_hex(16)
                cid=c.execute('INSERT INTO grant_runs(state,generation,profile,message,created_at,updated_at) VALUES (?,?,?,?,?,?)',('running',token,encode(p),'Preparazione delle fonti ufficiali',now(),now())).lastrowid
                # Recheck previously collected measures before catalog expansion.
                previous=c.execute('SELECT max(id) FROM grant_runs WHERE id<?',(cid,)).fetchone()[0]
                if previous:
                    for row in c.execute('SELECT url FROM grant_items WHERE run_id=?',(previous,)).fetchall():
                        c.execute("INSERT OR IGNORE INTO grant_tasks(run_id,url,kind) VALUES (?,?,'grant')",(cid,row[0]))
                for _,url,region in CATALOG:
                    if 'pd.camcom.it' in url and p['province'].lower() not in ('pd','padova'):continue
                    if region in ('Italia',p['region']):c.execute("INSERT INTO grant_tasks(run_id,url,kind) VALUES (?,?,'index')",(cid,url))
            try:
                proc=subprocess.Popen([sys.executable,'-m','sales.grants_worker','--db',str(self.store.path.resolve()),'--run',str(cid),'--generation',token],cwd=ROOT,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                self._workers[str(self.store.path.resolve())]=proc
                with self.store.connect() as c:c.execute('UPDATE grant_runs SET pid=? WHERE id=?',(proc.pid,cid))
            except Exception:
                with self.store.connect() as c:c.execute("UPDATE grant_runs SET state='error',message='Avvio del processo non riuscito' WHERE id=?",(cid,))
                raise
            return state(self.store)
    def stop(self):
        with self._lock:
            with self.store.connect() as c:
                c.execute('BEGIN IMMEDIATE');r=c.execute("SELECT * FROM grant_runs WHERE state='running'").fetchone()
                if not r:return state(self.store)
                c.execute("UPDATE grant_runs SET state='stopped',generation=?,message='Ricerca fermata. I risultati letti sono conservati.',updated_at=? WHERE id=?",(secrets.token_hex(16),now(),r['id']))
            proc=self._workers.get(str(self.store.path.resolve()))
            if proc and proc.poll() is None:
                try:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=1)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=1)
                except ProcessLookupError:pass
            elif r['pid']:
                try:
                    cmd=subprocess.check_output(['ps','-p',str(r['pid']),'-o','command='],text=True)
                    if 'sales.grants_worker' in cmd and str(self.store.path.resolve()) in cmd and '--run '+str(r['id'])+' ' in cmd:os.killpg(r['pid'],signal.SIGTERM)
                except (OSError,subprocess.CalledProcessError):pass
            return state(self.store)
    def state(self):
        value=state(self.store);proc=self._workers.get(str(self.store.path.resolve()))
        if value['run'] and value['run']['state']=='running' and proc and proc.poll() is not None:
            with self.store.connect() as c:c.execute("UPDATE grant_runs SET state='error',message='La ricerca si è interrotta. I risultati letti sono conservati.' WHERE id=? AND state='running'",(value['run']['id'],))
            value=state(self.store)
        return value
