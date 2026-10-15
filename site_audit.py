"""Evidence-based homepage checks and unmodified PageSpeed/Lighthouse measurements."""
import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib import request, parse, error

class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.title=[]; self.headings=[]; self.meta={}; self.canonical=[]; self.images=[]; self.links=[]; self.schemas=[]; self.active=None; self.parts=[]; self.jsonld=False; self.schema_text=[]
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in ('title','h1','h2','h3'):
            self.active=tag; self.parts=[]
        if tag=='meta': self.meta[a.get('name','').lower()]=a.get('content','')
        if tag=='link' and 'canonical' in a.get('rel','').lower().split(): self.canonical.append(a.get('href',''))
        if tag=='img': self.images.append(a)
        if tag=='a': self.links.append(a.get('href',''))
        if tag=='script' and a.get('type','').lower()=='application/ld+json': self.jsonld=True; self.schema_text=[]
    def handle_data(self,data):
        if self.active: self.parts.append(data)
        if self.jsonld: self.schema_text.append(data)
    def handle_endtag(self,tag):
        if tag==self.active:
            text=' '.join(' '.join(self.parts).split())
            if tag=='title': self.title.append(text)
            else: self.headings.append({'level':tag,'text':text})
            self.active=None
        if tag=='script' and self.jsonld:
            try: self.schemas.append(json.loads(''.join(self.schema_text)))
            except (ValueError, TypeError): self.schemas.append(None)
            self.jsonld=False

def seo_report(html,url):
    d=Document(html)
    rows=[]
    def check(label,ok,detail): rows.append({'label':label,'status':'presente' if ok else 'da approfondire','detail':detail})
    check('Titolo della pagina', bool(any(d.title)), ' | '.join(d.title) or 'Non trovato nell’HTML ricevuto; non prova da solo un problema di indicizzazione.')
    check('Descrizione per i motori', bool(d.meta.get('description')), d.meta.get('description') or 'Meta description non trovata nell’HTML: Google può comunque generare uno snippet.')
    h1=[h['text'] for h in d.headings if h['level']=='h1']
    check('Titolo principale',bool(h1), ' | '.join(h1) or 'H1 non trovato nell’HTML; controllare la gerarchia nel contenuto renderizzato.')
    robots=d.meta.get('robots','')+' '+d.meta.get('googlebot','')
    noindex=bool(re.search(r'\b(noindex|none)\b',robots,re.I))
    check('Direttive di indicizzazione',not noindex, 'Direttiva noindex/none presente: può essere intenzionale.' if noindex else 'Nessun noindex nei meta controllati. Non verifica header HTTP, robots.txt né indicizzazione effettiva.')
    check('URL canonico dichiarato',bool(d.canonical), ', '.join(d.canonical) or 'Canonical non dichiarato nell’HTML; non è automaticamente un errore.')
    missing=sum('alt' not in im for im in d.images)
    check('Attributi alternativi immagini',not missing,f'{missing} immagini senza attributo alt su {len(d.images)}. Alt vuoto può essere corretto per immagini decorative.')
    schema_types=[]
    def walk(node):
        if isinstance(node,dict):
            t=node.get('@type',[]); schema_types.extend([t] if isinstance(t,str) else t if isinstance(t,list) else [])
            for v in node.values():walk(v)
        elif isinstance(node,list):
            for v in node:walk(v)
    for node in d.schemas: walk(node)
    content_checks=[
        {'label':'Titolo della pagina presente','present':bool(any(d.title))},
        {'label':'Titolo principale presente','present':bool(h1)},
        {'label':'Contenuto organizzato in sezioni H2/H3','present':any(h['level'] in ('h2','h3') for h in d.headings)},
        {'label':'Percorso di contatto presente','present':any(re.search(r'mailto:|tel:|contatt|contact',href,re.I) for href in d.links)},
    ]
    return {'scope':'Homepage · HTML ricevuto, non audit completo del sito', 'checks':rows,
            'geo_aeo':{'content_checks':content_checks,'coverage':{'present':sum(c['present'] for c in content_checks),'total':len(content_checks),'label':'Copertura dei segnali tecnici osservati, non voto GEO/AEO né previsione di citazioni AI'},'summary':'Nessun punteggio GEO/AEO ufficiale. Questi segnali descrivono i contenuti, non garantiscono citazioni o ranking nei motori AI.',
                       'headings':d.headings[:20], 'structured_types':sorted(set(str(t) for t in schema_types)),
                       'invalid_jsonld':sum(x is None for x in d.schemas),
                       'note':'Dati strutturati e FAQ non sono requisiti speciali per comparire nelle risposte AI. Va valutata la chiarezza delle risposte, delle fonti e dell’identità aziendale.'}}

def parse_pagespeed(payload,strategy,url):
    lh=payload.get('lighthouseResult') or {}
    if lh.get('runtimeError') or not lh.get('categories'):
        return {'strategy':strategy,'status':'unavailable','message':'Google non ha completato il test; nessun punteggio assegnato.'}
    scores={k:round(v['score']*100) for k,v in lh['categories'].items() if isinstance(v.get('score'),(float,int)) and not isinstance(v.get('score'),bool)}
    audits=lh.get('audits',{})
    metrics={k:audits[k].get('displayValue') for k in ('largest-contentful-paint','cumulative-layout-shift','total-blocking-time','first-contentful-paint','speed-index') if audits.get(k,{}).get('displayValue')}
    issues=[{'title':a.get('title',''),'detail':a.get('displayValue','')} for a in audits.values() if isinstance(a.get('score'),(float,int)) and a['score']<.9 and a.get('scoreDisplayMode') in ('numeric','binary')][:12]
    return {'strategy':strategy,'status':'ok','scores':scores,'metrics':metrics,'issues':issues,
            'fetch_time':lh.get('fetchTime'),'final_url':lh.get('finalUrl',url), 'version':lh.get('lighthouseVersion'),
            'warnings':lh.get('runWarnings',[]), 'field':payload.get('loadingExperience',{}),
            'report_url':'https://pagespeed.web.dev/analysis?'+parse.urlencode({'url':url,'form_factor':strategy}),
            'note':'Misura di laboratorio Google Lighthouse; può variare tra esecuzioni. Non è un voto sul design né una garanzia SEO.'}

def pagespeed(url,strategy):
    params=[('url',url),('strategy',strategy),('locale','it')]+[('category',x) for x in ('performance','accessibility','best-practices','seo')]
    if os.getenv('PAGESPEED_API_KEY'): params.append(('key',os.environ['PAGESPEED_API_KEY']))
    try:
        with request.urlopen('https://www.googleapis.com/pagespeedonline/v5/runPagespeed?'+parse.urlencode(params),timeout=120) as response:
            return parse_pagespeed(json.load(response),strategy,url)
    except error.HTTPError as exc:
        return {'strategy':strategy,'status':'unavailable','message':f'PageSpeed non disponibile (HTTP {exc.code}).'+(' Quota Google esaurita o accesso senza chiave limitato. Configurare PAGESPEED_API_KEY e riprovare.' if exc.code in (403,429) else '')}
    except (OSError,ValueError):
        return {'strategy':strategy,'status':'unavailable','message':'PageSpeed non ha risposto correttamente: nessun punteggio assegnato.'}
