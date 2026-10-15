"""CustomerSearch: applicazione locale, Python 3.11+, senza dipendenze esterne."""
import base64
import hashlib
import http.client
import ipaddress
import json
import os
import random
import re
import secrets
import socket
import subprocess
import sys
import signal
import sqlite3
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime
from email.message import EmailMessage
from email.headerregistry import Address
from html.parser import HTMLParser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, parse, request, robotparser
from zoneinfo import ZoneInfo
from opportunities import OpportunityService, BLOCKED as OPPORTUNITY_BLOCKED
from technical_audit import technical_report, selection_evidence
from company_finance import extract_vat, reported_profit, valid_vat

ROOT = Path(__file__).resolve().parent
for line in (ROOT / '.env').read_text().splitlines() if (ROOT / '.env').exists() else []:
    if line.strip() and not line.lstrip().startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('\"\''))
PORT = int(os.getenv('PORT', '8765'))
ORIGIN = f'http://127.0.0.1:{PORT}'
REDIRECT = os.getenv('GOOGLE_REDIRECT_URI', ORIGIN + '/auth/google/callback')
DATA = ROOT / 'data'
DB = DATA / 'customers.sqlite3'
EXPECTED_EMAIL = 'pavanello93@gmail.com'
CSRF = secrets.token_urlsafe(32)
LOCK = threading.Lock()
STOP_SEARCH = threading.Event()
DAILY_SEARCH_LIMIT = 30
MONTHLY_SEARCH_LIMIT = 930
SERPER_DAILY_LIMIT = 100
SERPER_TOTAL_LIMIT = 2400
SEARXNG_STATUS = {'message': 'Configurato · in attesa della prima ricerca', 'retry_after': 0}
JOB = {'running': False, 'checked': 0, 'added': 0, 'message': 'Pronto per la prima ricerca.'}
OAUTH = {}
UA = 'CustomerSearch/1.0'
EMAIL = re.compile(r'^[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')


def today():
    return datetime.now(ZoneInfo('Europe/Rome')).date().isoformat()


@contextmanager
def db():
    conn = sqlite3.connect(DB, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init():
    DATA.mkdir(mode=0o700, exist_ok=True)
    os.chmod(DATA, 0o700)
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY, domain TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            url TEXT NOT NULL, email TEXT NOT NULL, email_source TEXT NOT NULL,
            findings TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft', created TEXT NOT NULL,
            sent_at TEXT, message_id TEXT, error TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS runs (day TEXT PRIMARY KEY, started TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS search_usage (day TEXT PRIMARY KEY, requests INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS serper_usage (day TEXT PRIMARY KEY, requests INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS searxng_usage (day TEXT PRIMARY KEY, requests INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS search_candidates (
            id INTEGER PRIMARY KEY, domain TEXT UNIQUE NOT NULL,
            item TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
        ''')
        c.execute('''CREATE TABLE IF NOT EXISTS query_performance (
            key TEXT PRIMARY KEY, sector TEXT NOT NULL, city TEXT NOT NULL, area TEXT NOT NULL,
            requests INTEGER NOT NULL DEFAULT 0, returned INTEGER NOT NULL DEFAULT 0,
            fresh INTEGER NOT NULL DEFAULT 0, checked INTEGER NOT NULL DEFAULT 0,
            drafts INTEGER NOT NULL DEFAULT 0)''')
        for column, definition in (('attempts','INTEGER NOT NULL DEFAULT 0'), ('retry_after','REAL NOT NULL DEFAULT 0'), ('last_reason',"TEXT NOT NULL DEFAULT ''")):
            if column not in {r[1] for r in c.execute('PRAGMA table_info(search_candidates)')}:
                c.execute(f'ALTER TABLE search_candidates ADD COLUMN {column} {definition}')
        if 'query_key' not in {r[1] for r in c.execute('PRAGMA table_info(search_candidates)')}:
            c.execute("ALTER TABLE search_candidates ADD COLUMN query_key TEXT")
        for column in ('site_audit', 'vat', 'finance', 'outcome', 'outcome_note', 'outcome_updated'):
            if column not in {r[1] for r in c.execute('PRAGMA table_info(leads)')}:
                c.execute(f"ALTER TABLE leads ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        if 'context' not in {r[1] for r in c.execute('PRAGMA table_info(leads)')}:
            c.execute("ALTER TABLE leads ADD COLUMN context TEXT NOT NULL DEFAULT '[]'")
        for key, value in {'name': 'Diego Pavanello', 'website': 'https://designerdimontagna.it', 'signature': 'Front-end-Designer', 'daily': False}.items():
            c.execute('INSERT OR IGNORE INTO settings VALUES (?, ?)', (key, json.dumps(value)))
        suppress_contacted_companies(c)
        c.execute("UPDATE settings SET value='false' WHERE key='daily'")
        c.execute("UPDATE leads SET status='uncertain', error='Invio interrotto: verifica in Gmail prima di qualsiasi nuovo contatto.' WHERE status='sending'")
    os.chmod(DB, 0o600)
    OPPORTUNITIES.init()


def settings():
    with db() as c:
        result = {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}
    subject, body = template_defaults(result)
    result.setdefault('allow_api_fallback', False)
    result.setdefault('template_subject', subject)
    result.setdefault('template_body', body)
    return result


def save_settings(values):
    with db() as c:
        for key, value in values.items():
            c.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', (key, json.dumps(value)))


def api_json(url, data=None, headers=None, form=False):
    headers = dict(headers or {})
    payload = None
    if data is not None:
        payload = (parse.urlencode(data) if form else json.dumps(data)).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    with request.urlopen(request.Request(url, payload, headers), timeout=25) as response:
        return json.load(response)


def public_resource(url, redirects=4, policy=None):
    """Pin the connection to a validated public IP, including on redirects."""
    if policy:
        policy(url)
    p = parse.urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('URL non consentito')
    port = p.port or (443 if p.scheme == 'https' else 80)
    if port not in (80, 443):
        raise ValueError('Porta non consentita')
    addresses = socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)
    ips = [a[4][0] for a in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('Sono consentiti solo siti pubblici')
    conn = http.client.HTTPConnection(p.hostname, port, timeout=10)
    sock = socket.create_connection((ips[0], port), timeout=10)
    try:
        if p.scheme == 'https':
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=p.hostname)
        conn.sock = sock
        conn.request('GET', parse.urlunsplit(('', '', p.path or '/', p.query, '')),
                     headers={'Host': p.netloc, 'User-Agent': UA, 'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        if response.status in (301, 302, 303, 307, 308):
            if redirects <= 0:
                raise ValueError('Troppi reindirizzamenti')
            destination = parse.urljoin(url, response.getheader('Location', ''))
            return public_resource(destination, redirects - 1, policy=policy)
        raw = response.read(1_500_001)
        if len(raw) > 1_500_000:
            raise ValueError('Pagina troppo grande')
        content_type = response.getheader('Content-Type', '')
        return response.status, raw, content_type, url
    finally:
        conn.close()
        sock.close()


def public_page(url, redirects=4, policy=None):
    status, raw, content_type, final = public_resource(url, redirects, policy=policy)
    if 'text/' not in content_type:
        raise ValueError('Contenuto non testuale')
    charset = re.search(r'charset=([\w-]+)', content_type)
    return status, raw.decode(charset.group(1) if charset else 'utf-8', errors='replace'), final


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.links, self.emails, self.images, self.text = [], [], [], []
        self.link_labels = {}
        self.anchor_href = None
        self.anchor_parts = []
        self.viewport = False
        self.title = ''
        self.in_title = False
        self.hidden = 0
        self.base_url = ''
        self.headings = []
        self.heading_tag = None
        self.heading_parts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'base' and a.get('href') and not self.base_url:
            self.base_url = a['href']
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'title':
            self.in_title = True
        if tag in ('h1', 'h2', 'h3'):
            self.heading_tag, self.heading_parts = tag, []
        if tag == 'meta' and a.get('name', '').lower() == 'viewport':
            self.viewport = True
        if tag == 'a' and a.get('href'):
            href = a['href']
            self.anchor_href, self.anchor_parts = href, []
            if href.lower().startswith('mailto:'):
                email = parse.unquote(href[7:].split('?')[0]).strip()
                if EMAIL.fullmatch(email):
                    self.emails.append(email)
            else:
                self.links.append(href)
        if tag == 'img' and a.get('src'):
            self.images.append(a['src'])

    def handle_endtag(self, tag):
        if tag == 'a' and self.anchor_href is not None:
            self.link_labels[self.anchor_href] = ' '.join(' '.join(self.anchor_parts).split())[:100]
            self.anchor_href = None
        if tag == self.heading_tag:
            self.headings.append(' '.join(' '.join(self.heading_parts).split()))
            self.heading_tag = None
        if tag == 'title':
            self.in_title = False
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, text):
        if self.in_title:
            self.title += text
        if not self.hidden:
            if self.anchor_href is not None:
                self.anchor_parts.append(text)
            self.text.append(text)
            if self.heading_tag:
                self.heading_parts.append(text)

    def contacts(self):
        visible = re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', ' '.join(self.text))
        return list(dict.fromkeys(e.lower() for e in self.emails + visible if EMAIL.fullmatch(e)))


def hostname(url):
    return (parse.urlsplit(url).hostname or '').lower().removeprefix('www.')


class SearchStopped(Exception):
    pass


def check_search_stop():
    if STOP_SEARCH.is_set():
        raise SearchStopped()


def page_context(page, source):
    """Short, verbatim page headings, never instructions or generated facts."""
    result = []
    for heading in page.headings:
        if not 12 <= len(heading) <= 100 or len(heading.split()) < 2:
            continue
        if re.search(r'cookie|privacy|newsletter|consenso|accedi|login|benvenut|contatt|scopri|leggi|clicca|menu|istruzion|ignore|prompt|password|https?://', heading, re.I):
            continue
        if heading.lower().strip(' .!?') in ('chi siamo', 'i nostri servizi', 'i nostri prodotti', 'le ultime notizie', 'su di noi'):
            continue
        if heading not in [r['text'] for r in result]:
            result.append({'text': heading, 'source': source})
    return result[:3]


INSPECTION_REASON = 'unavailable'
ANALYSIS_LOCAL = threading.local()
INSPECTION_TIMEOUT = None
RETRY_REASONS = {'unavailable', 'timeout', 'browser_error', 'load_budget', 'resource_error', 'dynamic_request', 'empty_page','audit_unavailable'}

def incomplete_reason(review):
    reasons = review.get('incomplete_reasons', [])
    for text, code in (('Tempo di caricamento esaurito', 'timeout'), ('Budget di caricamento raggiunto', 'load_budget'), ('Browser non disponibile', 'browser_error'), ('Errore del browser', 'browser_error'), ('Contenuto della pagina insufficiente', 'empty_page'), ('Richiesta dinamica non eseguita', 'dynamic_request')):
        if text in reasons:
            return code
    return 'resource_error'


def branded_public_mailbox(email, source, website):
    """Fallback only for a brand-named mailbox on the site's contact page."""
    provider_domains = {'gmail.com', 'outlook.com', 'hotmail.com', 'hotmail.it',
                        'live.it', 'libero.it', 'virgilio.it', 'alice.it',
                        'tin.it', 'tiscali.it', 'yahoo.it', 'yahoo.com'}
    local, provider = email.lower().split('@', 1)
    brand = re.sub(r'[^a-z0-9]', '', hostname(website).split('.')[0])
    mailbox = re.sub(r'[^a-z0-9]', '', local)
    contact_page = re.search(r'contatt|contact', parse.urlsplit(source).path, re.I)
    return (len(brand) >= 6 and mailbox == brand and provider in provider_domains
            and hostname(source) == hostname(website) and bool(contact_page))


def inspect_site(url):
    global INSPECTION_REASON
    INSPECTION_REASON = 'unavailable'
    check_search_stop()
    p = parse.urlsplit(url)
    root = parse.urlunsplit((p.scheme, p.netloc, '/', '', ''))
    robot_url = parse.urljoin(root, 'robots.txt')
    status, rules, _ = public_page(robot_url)
    robot = robotparser.RobotFileParser()
    if status == 200:
        robot.parse(rules.splitlines())
    elif status not in (404, 410):
        return None
    else:
        robot.parse([])
    last_request = time.monotonic()
    delay = max(0.6, robot.crawl_delay(UA) or 0)
    if delay > 30:
        return None

    def visit(target):
        nonlocal last_request
        check_search_stop()
        if hostname(target) != hostname(root) or not robot.can_fetch(UA, target):
            raise ValueError('Pagina esclusa dal controllo')
        time.sleep(max(0, delay - (time.monotonic() - last_request)))
        check_search_stop()
        try:
            result = public_page(target)
            if hostname(result[2]) != hostname(root):
                raise ValueError('Reindirizzamento verso un altro sito')
            return result
        finally:
            last_request = time.monotonic()

    status, html, final = visit(root)
    if status != 200:
        return None
    page = Page(html)
    if public_entity(final, page.title + ' ' + ' '.join(page.headings)):
        INSPECTION_REASON = 'not_business'
        return None
    company_text = ' '.join(page.text)
    context = page_context(page, final)
    findings = []
    def finding(kind, text, source):
        findings.append({'kind': kind, 'text': text, 'source': source, 'checked_at': datetime.now(ZoneInfo('Europe/Rome')).isoformat()})
    contacts = [(e, final) for e in page.contacts()]
    link_base = parse.urljoin(final, page.base_url) if page.base_url else final
    labels = {parse.urljoin(link_base, href).split('#')[0]: label for href, label in page.link_labels.items()}
    links = list(dict.fromkeys(parse.urljoin(link_base, href).split('#')[0] for href in page.links))
    links = [link for link in links if parse.urlsplit(link).scheme in ('https', 'http') and hostname(link) == hostname(final) and link != final]
    links.sort(key=lambda link: 0 if re.search(r'contatt|contact', link, re.I) else (1 if re.search(r'preventiv|chi-siamo', link, re.I) else 2))
    enough_identity = is_srl(company_text) and any(e.split('@')[1].removeprefix('www.') == hostname(final) for e, _ in contacts)
    for link in links[:0 if enough_identity else 3]:
        try:
            code, content, source = visit(link)
            if code == 200:
                inner = Page(content)
                if public_entity(source, inner.title):
                    INSPECTION_REASON = 'not_business'
                    return None
                company_text += ' ' + ' '.join(inner.text)
                contacts.extend((e, source) for e in inner.contacts())
                context.extend(page_context(inner, source))
        except (OSError, ValueError, http.client.HTTPException):
            continue
    # Prefer the site's domain; restrict external mailboxes to branded contact-page evidence.
    contacts = [(e, source) for e, source in contacts if not re.search(r'(^|[.@_-])(pec|noreply|no-reply)([.@_-]|$)', e)]
    contacts.sort(key=lambda item: 0 if item[0].split('@')[1].removeprefix('www.') == hostname(final) else 1)
    same_domain = [(e, source) for e, source in contacts if e.split('@')[1].removeprefix('www.') == hostname(final)]
    if not is_srl(company_text):
        INSPECTION_REASON = 'not_business'
        return None
    if not same_domain:
        alternatives = [(e, source) for e, source in contacts if branded_public_mailbox(e, source, final)]
        if len({e for e, _ in alternatives}) == 1:
            same_domain = alternatives
    if outside_search_area(company_text):
        INSPECTION_REASON = 'outside_area'
        return None
    if not same_domain:
        INSPECTION_REASON = 'no_email'
        return None
    site_report=technical_report(final,html,DATA,check_search_stop)
    selection=selection_evidence(site_report)
    if not selection:
        results=site_report.get('pagespeed',[])
        complete=len(results)==2 and all(r.get('status')=='ok' and all(k in r.get('scores',{}) for k in ('performance','seo','accessibility','best-practices')) for r in results)
        INSPECTION_REASON='no_issue' if complete else 'audit_unavailable'
        return None
    email, source = same_domain[0]
    name = ' '.join(page.title.split())[:160] or hostname(final)
    unique_context = list({item['text']: item for item in context}.values())[:6]
    return {'domain':hostname(final), 'name':name, 'url':final, 'email':email,
            'email_source':source, 'findings':selection, 'context':unique_context, 'site_audit':site_report,
            'vat':extract_vat(company_text)}


def legacy_draft(lead, profile):
    observations = '\n'.join('• ' + f['text'] for f in lead['findings'])
    signature = '\n'.join(filter(None, [profile['name'], profile['website'], profile['signature']]))
    return (f"Un paio di osservazioni sul sito {lead['domain']}",
            f"Buongiorno,\n\nsono {profile['name']} e realizzo siti web. Visitando {lead['url']} ho annotato questi aspetti:\n\n"
            f"{observations}\n\nSi tratta di osservazioni sulle pagine pubbliche, non di un audit completo. "
            "Posso aiutarvi a valutare gli interventi e a migliorare il sito, partendo da questi punti.\n\n"
            "Se è un tema che vi interessa, vi va di parlarne?\n\n" + signature +
            '\n\nSe preferite non ricevere altre mie comunicazioni, rispondete a questa email e non vi ricontatterò.')


def previous_draft(lead, profile):
    """Plain language; uncertain technical signals must not become observed defects."""
    kinds = {f.get('kind', '') for f in lead['findings']}
    if 'Link interrotto' in kinds:
        observation = ('Ho notato che uno dei collegamenti porta a una pagina che non si apre. '
                       'Chi sta cercando informazioni sulla vostra attività potrebbe fermarsi lì.')
        proposal = 'Potrei aiutarvi a sistemare questi passaggi e rendere più semplice trovare i vostri servizi e contattarvi.'
    elif any(kind.startswith('Mobile') for kind in kinds):
        observation = ('Mi piacerebbe aiutarvi a rendere il sito più comodo da consultare dal telefono, '
                       'con i vostri servizi e i contatti facili da trovare.')
        proposal = 'Prima di proporvi cambiamenti, guarderei insieme a voi cosa vale davvero la pena migliorare.'
    else:
        # HTTP and image references alone do not prove a visible usability issue.
        observation = ('Vi scrivo per proporvi una revisione del sito, partendo da come presentate '
                       'la vostra attività e da quanto è semplice mettersi in contatto con voi.')
        proposal = 'L’idea è capire insieme se c’è qualcosa che possiamo rendere più chiaro e curato, senza cambiare tutto per forza.'
    signature = '\n'.join(filter(None, [profile['name'], profile['signature'], profile['website']]))
    return (f"Una proposta per il sito {lead['domain']}",
            f"Buongiorno,\n\nsono {profile['name']}, mi occupo di realizzare siti web. "
            f"Ho visitato {lead['domain']} e volevo scrivervi due righe.\n\n"
            f"{observation}\n\n{proposal}\n\n"
            "Vi andrebbe se vi mandassi un paio di idee da cui partire?\n\n"
            f"{signature}\n\nSe preferite non essere ricontattati, basta dirmelo.")


def detailed_draft(lead, profile):
    context = lead.get('context', [])
    if isinstance(context, str):
        context = json.loads(context)
    topics = list(dict.fromkeys(c['text'] for c in context))[:2]
    if topics:
        references = ' e '.join('«' + topic + '»' for topic in topics)
        detail = (f'Mi sono soffermato in particolare su {references}. '
                  'Partirei proprio da questi contenuti per costruire una nuova presentazione, '
                  'con pagine dedicate, immagini scelte con cura e un percorso semplice per chi vuole saperne di più.')
    else:
        name = ' '.join(lead.get('name', '').split()).strip(' .:|')
        if name and name != lead['domain'] and len(name) <= 160:
            detail = (f'La pagina si presenta come «{name}». Mi piacerebbe partire da ciò che raccontate '
                      'per dare più spazio alla vostra identità, con contenuti ben organizzati e contatti facili da trovare.')
        else:
            detail = ('Lavorerei su una presentazione chiara di quello che fate, con immagini scelte con cura '
                      'e un percorso semplice per chi vuole conoscervi meglio e mettersi in contatto con voi.')
    broken = next((f for f in lead['findings'] if f.get('kind') == 'Link interrotto'), None)
    if broken:
        source = broken.get('source', '')
        location = parse.urlsplit(source).path
        reference = f' ({location})' if location and len(location) <= 80 else ''
        detail += (f' Ho anche trovato un collegamento a una pagina che non si apre{reference}: '
                   'nel nuovo sito curerei anche questi passaggi, per non interrompere chi sta cercando informazioni.')
    elif any(f.get('kind', '').startswith('Mobile') for f in lead['findings']):
        detail += ' Dedicherei particolare attenzione a chi visita il sito dal telefono, per rendere comodo leggere e contattarvi anche da lì.'
    signature = '\n'.join(filter(None, [profile['name'], profile['signature'].replace('Front-end-Designer', 'Front-end Designer'), profile['website']]))
    return (f"Un’idea per ripensare {lead['domain']}",
            f"Buongiorno,\n\nsono {profile['name']}, mi occupo di design e sviluppo di siti web.\n\n"
            f"Ho visitato {lead['domain']} e mi piacerebbe proporvi una nuova direzione per il sito, "
            "ripensandolo da zero con un’immagine attuale e una struttura che dia più spazio a quello che fate.\n\n"
            f"{detail}\n\n"
            "L’idea sarebbe creare qualcosa di completamente nuovo, curando sia l’aspetto visivo sia la facilità di navigazione.\n\n"
            "Se state valutando un rinnovamento del sito, mi farebbe piacere confrontarmi con voi, capire le vostre esigenze e raccontarvi come imposterei il progetto.\n\n"
            f"Può interessarvi?\n\n{signature}\n\n"
            "Se preferite non essere ricontattati, è sufficiente farmelo sapere.")


def remove_quoted_paragraph(body):
    prefixes = ('Mi sono soffermato in particolare su ', 'La pagina si presenta come ',
                'Lavorerei su una presentazione chiara di quello che fate,')
    return '\n\n'.join(p for p in body.split('\n\n') if not p.startswith(prefixes))


def prior_layout_draft(lead, profile):
    subject, body = detailed_draft(lead, profile)
    body = remove_quoted_paragraph(body)
    website = profile.get('website', '')
    if website:
        body = '\n'.join(website_label(website) if line.strip() == website else line for line in body.split('\n'))
    return subject, body


def standard_draft(lead, profile):
    signature = '\n'.join(filter(None, [profile['name'], profile['signature'].replace('Front-end-Designer', 'Front-end Designer'), website_label(profile.get('website', ''))]))
    return (f"Un’idea per ripensare {lead['domain']}",
            f"Buongiorno,\n\nsono {profile['name']}, mi occupo di design e sviluppo di siti web.\n\n"
            f"Ho visitato {lead['domain']} e credo ci sia l’opportunità di ripensare il sito da zero, "
            "con un’immagine più attuale e una struttura capace di valorizzare meglio la vostra azienda, "
            "i servizi che offrite e ciò che vi distingue.\n\n"
            "Non penso a un semplice restyling, ma a un nuovo sito progettato intorno alla vostra realtà, "
            "più curato dal punto di vista visivo, semplice da navigare e pensato per presentare al meglio l’azienda online.\n\n"
            "Se state valutando un rinnovamento, mi farebbe piacere confrontarmi con voi, capire le vostre esigenze "
            "e raccontarvi come potremmo impostare il progetto.\n\n"
            f"Può essere un tema di vostro interesse?\n\n{signature}\n\n"
            "Se preferite non essere ricontattati, è sufficiente farmelo sapere.")


FINANCE_BUSY = set()


def lookup_finance(lead_id):
    with LOCK:
        if lead_id in FINANCE_BUSY:
            raise ValueError('Ricerca economica già in corso per questa azienda.')
        FINANCE_BUSY.add(lead_id)
    try:
        with db() as c:
            row = c.execute("SELECT * FROM leads WHERE id=? AND status NOT IN ('deleted','excluded')", (lead_id,)).fetchone()
        if not row:
            raise ValueError('Azienda non disponibile')
        lead = dict(row)
        vat = lead.get('vat') or ''
        if not vat:
            code, html, source = public_page(lead['url'])
            if code == 200 and hostname(source) == lead['domain']:
                vat = extract_vat(' '.join(Page(html).text))
        result = {'status':'missing_vat', 'message':'Partita IVA univoca non trovata: nessuna associazione economica automatica.', 'checked_at':datetime.now(ZoneInfo('Europe/Rome')).isoformat()}
        if vat:
            response = search_web(f'"{vat}" "utile" "esercizio"')
            records = []
            for item in response.get('results', [])[:4]:
                url = item.get('url', '')
                try:
                    parts = parse.urlsplit(url)
                    robots_url = parse.urlunsplit((parts.scheme, parts.netloc, '/robots.txt', '', ''))
                    status, rules, _ = public_page(robots_url)
                    robot = robotparser.RobotFileParser()
                    if status not in (200,404,410): continue
                    robot.parse(rules.splitlines() if status==200 else [])
                    if not robot.can_fetch(UA, url): continue
                    delay = robot.crawl_delay(UA) or 0
                    if delay>5: continue
                    time.sleep(max(.6,delay))
                    code, html, source = public_page(url)
                    if code != 200 or hostname(source) != hostname(url): continue
                    page = Page(html)
                    for record in reported_profit(' '.join(page.text), vat):
                        records.append({**record, 'source':source, 'source_type':'Sito aziendale' if hostname(source)==lead['domain'] else 'Fonte pubblica esterna'})
                except (OSError, ValueError, http.client.HTTPException):
                    continue
            result = {'status':'unavailable', 'vat':vat, 'message':'Nessun utile con anno e importo espliciti associabile in modo univoco alla partita IVA nelle pagine consultabili.', 'checked_at':datetime.now(ZoneInfo('Europe/Rome')).isoformat()}
            if records:
                year=max(r['year'] for r in records)
                latest=[r for r in records if r['year']==year]
                if len({r['amount_eur'] for r in latest})==1:
                    result.update(status='reported', record=latest[0], message='Importo riportato dalla fonte, da verificare nel bilancio depositato. Non è una stima del budget per il sito.')
                else:
                    result.update(status='conflict', message='Le fonti riportano importi discordanti per lo stesso anno: nessun utile assegnato.', sources=list({r['source'] for r in latest}))
        with db() as c:
            c.execute('UPDATE leads SET vat=?,finance=? WHERE id=?',(vat,json.dumps(result),lead_id))
        return result
    finally:
        with LOCK:
            FINANCE_BUSY.discard(lead_id)


AUDIT_BUSY = set()

def audit_website(lead_id):
    with LOCK:
        if lead_id in AUDIT_BUSY: raise ValueError('Analisi già in corso per questa azienda.')
        AUDIT_BUSY.add(lead_id)
    try:
        with db() as c:
            row=c.execute("SELECT url,site_audit FROM leads WHERE id=? AND status NOT IN ('deleted','excluded')",(lead_id,)).fetchone()
        if not row: raise ValueError('Azienda non disponibile.')
        cached=json.loads(row['site_audit'] or '{}')
        if cached.get('selection_policy') and cached.get('completed_at',0)>time.time()-3600:return cached
        code,html,final=public_page(row['url'])
        if code!=200:raise ValueError('Homepage non raggiungibile per il controllo.')
        report=technical_report(final,html,DATA,lambda:None)
        report['completed_at']=time.time()
        with db() as c: c.execute('UPDATE leads SET site_audit=? WHERE id=?',(json.dumps(report),lead_id))
        return report
    finally:
        with LOCK: AUDIT_BUSY.discard(lead_id)


def redesign_reason(lead):
    reasons=[]
    from ux_checks import qualifies
    for f in lead.get('findings',[]):
        if f.get('kind') in ('Valutazione manuale','SEO · Lighthouse'): reasons.append(f['text'])
        elif f.get('kind')=='Usabilità · layout' and f.get('qualifies') and not f.get('incomplete'):
            if 'ux_findings' in f:
                reasons.extend(item['text'] for item in f['ux_findings'] if qualifies([item]))
            else: reasons.append(f.get('text',''))
    return ' '.join(dict.fromkeys(reasons))


def practical_observation(lead):
    for item in lead.get('findings', []):
        if item.get('kind') != 'Link interrotto':
            continue
        source = item.get('source', '')
        if not source or hostname(source) != lead['domain']:
            continue
        label = ' '.join(item.get('label', '').split())
        if label and len(label) <= 80:
            detail = f'il collegamento “{label}” dalla pagina iniziale porta a una pagina non trovata'
        else:
            detail = f'un collegamento dalla pagina iniziale porta a una pagina non trovata ({source})'
        path = parse.urlsplit(source).path.lower()
        if re.search(r'contatt|contact|preventiv', path + ' ' + label.lower()):
            impact = 'Chi vuole chiedervi informazioni rischia quindi di interrompersi proprio al momento di contattarvi.'
        elif re.search(r'prodott|catalog|servizi', path + ' ' + label.lower()):
            impact = 'È un passaggio che può fermare chi sta cercando di capire meglio cosa offrite.'
        else:
            impact = 'Sistemarlo renderebbe più semplice proseguire la visita senza incontrare una pagina di errore.'
        return f'Navigando sul vostro sito, {detail}. {impact}'
    for item in lead.get('findings', []):
        if item.get('kind') == 'Mobile · controllo' and item.get('overflow_confirmed') and not item.get('incomplete'):
            return ('Aprendo il vostro sito nel controllo da smartphone, parte del contenuto supera la larghezza dello schermo. '
                    'Lavorerei su questo punto per rendere più comoda la lettura dal telefono, con i contenuti che si adattano allo spazio disponibile.')
    for item in lead.get('findings', []):
        if item.get('kind') == 'Immagine non disponibile' and item.get('verified'):
            return ('Nella pagina iniziale del vostro sito c’è un’immagine che non risulta disponibile nei due controlli effettuati. '
                    'Ripristinarla aiuterebbe a presentare la pagina senza elementi mancanti.')
        if item.get('kind') == 'Connessione' and item.get('source', '').startswith('http://'):
            return ('L’indirizzo della pagina iniziale che ho visitato si apre senza una connessione protetta. '
                    'Sistemerei questo accesso, così chi arriva da quel collegamento viene accompagnato direttamente alla versione protetta del sito.')
    return ''


def prior_practical_draft(lead, profile):
    subject, body = standard_draft(lead, profile)
    observation = practical_observation({**lead, 'findings': [f for f in lead.get('findings', []) if f.get('kind') in ('Link interrotto', 'Mobile · controllo')]})
    if observation:
        start = body.index(f"Ho visitato {lead['domain']}")
        end = body.index('Non penso a un semplice restyling', start)
        body = body[:start] + observation + '\n\n' + body[end:]
    return subject, body


def default_draft(lead, profile):
    return (f"Un’idea per il sito {lead['domain']}",
            f"Buongiorno,\n\nsono {profile['name']}, mi occupo di design e sviluppo di siti web.\n\n"
            f"Vi scrivo dopo aver visitato {lead['domain']}. Credo ci siano diversi aspetti su cui poter intervenire per rinnovarne l’immagine "
            "e costruire una presenza online più attuale, capace di valorizzare maggiormente la vostra azienda, i servizi che offrite e ciò che vi distingue.\n\n"
            "Non penso a un semplice restyling, ma a un nuovo sito progettato intorno alla vostra realtà, più curato dal punto di vista visivo, "
            "semplice da navigare e pensato per presentare al meglio l’azienda online.\n\n"
            "Se state valutando un rinnovamento del sito, sarei lieto di confrontarmi con voi, capire le vostre esigenze "
            "e raccontarvi come imposterei un nuovo progetto.\n\n"
            "Se l’idea può essere di vostro interesse, mi farebbe piacere approfondirla insieme.\n"
            f"Vi lascio il mio sito: {website_label(profile.get('website', ''))}\n\n"
            f"{profile['name']}\n{profile['signature'].replace('Front-end-Designer', 'Front-end Designer')}")


def template_defaults(profile):
    return default_draft({'domain':'{sito}'}, {**profile, 'name':'{nome}', 'signature':'{firma}', 'website':'{mio_sito}'})


def draft(lead, profile):
    subject, body = template_defaults(profile)
    values = {'sito':lead['domain'], 'nome':profile['name'], 'firma':profile['signature'].replace('Front-end-Designer', 'Front-end Designer'), 'mio_sito':website_label(profile['website'])}
    def render(text):
        return re.sub(r'\{(sito|nome|firma|mio_sito)\}', lambda match: values[match.group(1)], text)
    return render(profile.get('template_subject', subject)), render(profile.get('template_body', body))


def apply_template_to_drafts():
    profile = settings()
    with db() as c:
        rows = c.execute("SELECT id,domain FROM leads WHERE status='draft'").fetchall()
        for row in rows:
            subject, body = draft(dict(row), profile)
            validate_message('test@example.org', subject, body)
            c.execute("UPDATE leads SET subject=?,body=? WHERE id=? AND status='draft'", (subject, body, row['id']))
    return len(rows)


def website_label(website):
    return re.sub(r'^https?://', '', website, flags=re.I).rstrip('/')


def email_html(body, website):
    label = website_label(website)
    valid = parse.urlsplit(website).scheme in ('http', 'https') and bool(parse.urlsplit(website).hostname)
    lines = []
    for line in body.split('\n'):
        if valid and line.strip() in (website, label):
            lines.append(f'<strong><a href="{escape(website, quote=True)}" style="color:inherit;text-decoration:none">{escape(label)}</a></strong>')
        elif valid and line.strip() == 'Vi lascio il mio sito: ' + label:
            lines.append(f'Vi lascio il mio sito: <a href="{escape(website, quote=True)}">{escape(label)}</a>')
        else:
            lines.append(escape(line))
    return '<!doctype html><html><body><div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6">' + '<br>'.join(lines) + '</div></body></html>'


BUSINESS_SECTORS = [
    'azienda metalmeccanica lavorazioni', 'azienda produzione serramenti',
    'impresa edile ristrutturazioni', 'azienda impianti elettrici industriali',
    'azienda arredamenti su misura', 'azienda lavorazione legno',
    'azienda stampaggio materie plastiche', 'azienda carpenteria metallica',
    'azienda automazione industriale', 'azienda imballaggi produzione',
    'azienda logistica trasporti', 'azienda forniture industriali',
]
EXCLUDED_DOMAINS = ['facebook.com', 'instagram.com', 'linkedin.com', 'tripadvisor.it',
                    'paginegialle.it', 'paginebianche.it', 'europages.it', 'kompass.com',
                    'informazione-aziende.it', 'ufficiocamerale.it', 'registroimprese.it',
                    'wikipedia.org', 'youtube.com', 'indeed.com']

SEARCH_AREAS = [
    ('Veneto', ['Verona', 'Vicenza', 'Padova', 'Treviso', 'Venezia', 'Rovigo', 'Belluno']),
    ('Lombardia', ['Milano', 'Brescia', 'Bergamo', 'Monza', 'Como', 'Varese', 'Mantova', 'Cremona', 'Pavia', 'Lecco', 'Lodi', 'Sondrio']),
    ('Nord Italia', ['Torino', 'Cuneo', 'Novara', 'Genova', 'Savona', 'Trento', 'Bolzano', 'Udine', 'Pordenone', 'Trieste', 'Bologna', 'Modena', 'Parma', 'Reggio Emilia', 'Aosta']),
    ('Centro Italia', ['Firenze', 'Prato', 'Pisa', 'Lucca', 'Roma', 'Latina', 'Viterbo']),
]


FOCUS_CITIES = {
    'Veneto': set(SEARCH_AREAS[0][1]),
    'Lombardia': set(SEARCH_AREAS[1][1]),
    'Piemonte': {'Torino', 'Cuneo', 'Novara'},
    'Toscana': {'Firenze', 'Prato', 'Pisa', 'Lucca'},
}
FOCUS_ROTATION = ('Veneto', 'Lombardia', 'Piemonte', 'Toscana') * 2 + ('Altre zone',) * 2


def focus_region(plan):
    return next((region for region, cities in FOCUS_CITIES.items() if plan[1] in cities), 'Altre zone')


def outside_search_area(text):
    # Excluded regions: Umbria, Marche, South and islands; require a locality after the postal code.
    # Do not mistake VAT numbers or a generic mention of a city for an address.
    return bool(re.search(r'(?<![\w])(?:0[5-9]|[6-9]\d)\d{3}\s*[-–,]?\s+[A-Za-zÀ-ÿ]{2,}', text))


def exclude_outside_candidates():
    allowed = {query_key(plan) for plan in search_plan()}
    count = 0
    with db() as c:
        for row in c.execute("SELECT id,item,query_key FROM search_candidates WHERE status IN ('pending','retry')").fetchall():
            item = json.loads(row['item'])
            if (row['query_key'] and row['query_key'] not in allowed) or outside_search_area(item.get('title','')+' '+item.get('content','')):
                c.execute("UPDATE search_candidates SET status='dismissed',last_reason='outside_area',retry_after=0 WHERE id=?", (row['id'],))
                count += 1
    return count


def search_plan():
    # Rotate sector and city together, covering every combination once per area.
    return [(sector, cities[(round_index + index) % len(cities)], area)
            for area, cities in SEARCH_AREAS for round_index in range(len(cities))
            for index, sector in enumerate(BUSINESS_SECTORS)]


def query_key(plan):
    return json.dumps(plan, ensure_ascii=False, separators=(',', ':'))


def choose_query():
    plans = search_plan()
    with db() as c:
        stats = {r['key']:dict(r) for r in c.execute('SELECT * FROM query_performance')}
    total_requests = sum(r['requests'] for r in stats.values())
    region = FOCUS_ROTATION[total_requests % len(FOCUS_ROTATION)]
    plans = [p for p in plans if focus_region(p) == region]
    # Cover every city/sector combination inside the selected region before repeating.
    cycle = min(stats.get(query_key(p), {}).get('requests', 0) for p in plans)
    remaining = [p for p in plans if stats.get(query_key(p), {}).get('requests', 0) == cycle]
    choices = remaining
    total_requests = sum(r['requests'] for r in stats.values())
    if total_requests % 3 == 0:
        return choices[0]
    def score(plan):
        rows = [r for r in stats.values() if r['sector'] == plan[0] and focus_region((r['sector'], r['city'], r['area'])) == region]
        requests = sum(r['requests'] for r in rows)
        returned = sum(r['returned'] for r in rows)
        fresh = sum(r['fresh'] for r in rows)
        checked = sum(r['checked'] for r in rows)
        drafts = sum(r['drafts'] for r in rows)
        return ((fresh + 1) / (returned + requests + 2)) * ((drafts + 1) / (checked + 4))
    # A small window keeps geographic/sector diversity even when one sector wins.
    return max(choices[:24], key=score)


def search_performance():
    with db() as c:
        totals = dict(c.execute('SELECT coalesce(sum(requests),0) requests, coalesce(sum(returned),0) returned, coalesce(sum(fresh),0) fresh, coalesce(sum(checked),0) checked, coalesce(sum(drafts),0) drafts FROM query_performance').fetchone())
        totals['best'] = [dict(r) for r in c.execute('SELECT sector,city,area,requests,fresh,checked,drafts FROM query_performance WHERE drafts>0 ORDER BY 1.0*drafts/requests DESC, drafts DESC LIMIT 3')]
    return totals


def public_entity(url, text=''):
    domain = hostname(url)
    if re.search(r'(^|\.)(gov|edu|comune|comuni|provincia|regione|istruzione|asl|ausl|ats)(\.|$)', domain):
        return True
    return bool(re.search(r'\b(comune di|comune d[’\x27]|comune [a-zà-ù]|municipio|sito istituzionale|amministrazione comunale|regione (veneto|lombardia|piemonte|toscana)|provincia di|ministero|azienda sanitaria|istituto comprensivo|camera di commercio|università degli studi|ente pubblico)\b', text, re.I))


def is_srl(text):
    return bool(re.search(r'\bs\s*\.?\s*r\s*\.?\s*l(?:\s*\.?\s*s)?\b|societ[àa] a responsabilit[àa] limitata', text, re.I))


def business_result(item):
    domain = hostname(item.get('url', ''))
    if not domain or any(domain == d or domain.endswith('.' + d) for d in EXCLUDED_DOMAINS):
        return False
    text = (item.get('title', '') + ' ' + item.get('content', '')).lower()
    if outside_search_area(item.get('title','')+' '+item.get('content','')):
        return False
    if public_entity(item.get('url', ''), item.get('title', '')):
        return False
    return not re.search(r'\b(elenco aziende|directory|offerte di lavoro|annunci di lavoro|le migliori \d+|top \d+)\b', text)


def refresh_generated_drafts():
    """Migrate only exact old generated text; preserve user edits and sent mail."""
    with db() as c:
        if c.execute("SELECT 1 FROM settings WHERE key='template_body'").fetchone():
            return 0
    profile = settings()
    updated = 0
    with db() as c:
        for row in c.execute("SELECT * FROM leads WHERE status='draft'").fetchall():
            lead = dict(row)
            if public_entity(lead['url'], lead['name']):
                c.execute("UPDATE leads SET status='excluded' WHERE id=? AND status='draft'", (lead['id'],))
                continue
            lead['findings'] = json.loads(lead['findings'])
            lead['site_audit'] = json.loads(lead.get('site_audit') or '{}')
            old_subject, old_body = lead['subject'], lead['body']
            if (old_subject, old_body) in (legacy_draft(lead, profile), previous_draft(lead, profile), detailed_draft(lead, profile), prior_layout_draft(lead, profile), standard_draft(lead, profile), prior_practical_draft(lead, profile)):
                subject, body = draft(lead, profile)
                if (subject, body) == (old_subject, old_body):
                    continue
                c.execute("UPDATE leads SET subject=?, body=? WHERE id=? AND status='draft' AND subject=? AND body=?",
                          (subject, body, lead['id'], old_subject, old_body))
                updated += 1
            else:
                cleaned = remove_quoted_paragraph(old_body)
                if cleaned != old_body:
                    c.execute("UPDATE leads SET body=? WHERE id=? AND status='draft' AND body=?", (cleaned, lead['id'], old_body))
                    updated += 1
    return updated


def count_today():
    with db() as c:
        return c.execute('SELECT count(*) FROM leads WHERE created=?', (today(),)).fetchone()[0]


class SearchLimitError(ValueError):
    pass


def search_usage():
    with db() as c:
        row = c.execute('SELECT requests FROM search_usage WHERE day=?', (today(),)).fetchone()
    return row[0] if row else 0


def monthly_search_usage():
    with db() as c:
        return c.execute('SELECT coalesce(sum(requests),0) FROM search_usage WHERE day LIKE ?', (today()[:7] + '%',)).fetchone()[0]


def tavily_search(query):
    check_search_stop()
    # Reserve before the network call: failures and restarts cannot bypass the cap.
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        monthly = c.execute('SELECT coalesce(sum(requests),0) FROM search_usage WHERE day LIKE ?', (today()[:7] + '%',)).fetchone()[0]
        if monthly >= MONTHLY_SEARCH_LIMIT:
            raise SearchLimitError('Raggiunto il limite di 930 ricerche del mese. Potrai avviare altre ricerche il mese prossimo.')
        c.execute('INSERT OR IGNORE INTO search_usage VALUES (?, 0)', (today(),))
        changed = c.execute('UPDATE search_usage SET requests=requests+1 WHERE day=? AND requests<?', (today(), DAILY_SEARCH_LIMIT))
        if changed.rowcount != 1:
            raise SearchLimitError('Raggiunto il limite di 30 ricerche Tavily di oggi. Potrai avviarne altre domani; le bozze restano disponibili.')
    return api_json('https://api.tavily.com/search', {
        'query': query, 'topic': 'general', 'search_depth': 'basic',
        'auto_parameters': False, 'max_results': 20,
        'include_answer': False, 'include_raw_content': False,
        'include_images': False,
        'exclude_domains': EXCLUDED_DOMAINS,
    }, headers={'Authorization': 'Bearer ' + os.environ['TAVILY_API_KEY']})


def serper_usage():
    with db() as c:
        daily = c.execute('SELECT coalesce(sum(requests),0) FROM serper_usage WHERE day=?', (today(),)).fetchone()[0]
        total = c.execute('SELECT coalesce(sum(requests),0) FROM serper_usage').fetchone()[0]
    return daily, total


def remaining_searches():
    if os.getenv('SEARXNG_URL') and not settings()['allow_api_fallback']:
        return 100
    tavily = min(DAILY_SEARCH_LIMIT - search_usage(), MONTHLY_SEARCH_LIMIT - monthly_search_usage()) if os.getenv('TAVILY_API_KEY') else 0
    daily, total = serper_usage()
    serper = min(SERPER_DAILY_LIMIT - daily, SERPER_TOTAL_LIMIT - total) if os.getenv('SERPER_API_KEY') else 0
    return max(0, tavily) + max(0, serper) + (100 if os.getenv('SEARXNG_URL') else 0)


def searxng_usage():
    with db() as c:
        return c.execute('SELECT coalesce(sum(requests),0) FROM searxng_usage WHERE day=?', (today(),)).fetchone()[0]


def searxng_search(query):
    check_search_stop()
    base = os.environ['SEARXNG_URL'].rstrip('/')
    parsed = parse.urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('SearXNG deve essere un servizio locale.')
    with db() as c:
        c.execute('INSERT INTO searxng_usage VALUES (?,1) ON CONFLICT(day) DO UPDATE SET requests=requests+1', (today(),))
    response = api_json(base + '/search?' + parse.urlencode({'q': query, 'format': 'json', 'language': 'it-IT', 'categories': 'general'}))
    results = response.get('results', [])
    if not isinstance(results, list):
        raise ValueError('Risposta SearXNG non valida')
    return {'results': [item for item in results if isinstance(item, dict) and item.get('url')]}


def serper_search(query):
    check_search_stop()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        total = c.execute('SELECT coalesce(sum(requests),0) FROM serper_usage').fetchone()[0]
        if total >= SERPER_TOTAL_LIMIT:
            raise SearchLimitError('Crediti iniziali Serper riservati all’app esauriti. Non vengono acquistati altri crediti.')
        c.execute('INSERT OR IGNORE INTO serper_usage VALUES (?,0)', (today(),))
        changed = c.execute('UPDATE serper_usage SET requests=requests+1 WHERE day=? AND requests<?', (today(), SERPER_DAILY_LIMIT))
        if changed.rowcount != 1:
            raise SearchLimitError('Raggiunto il limite di 100 ricerche Serper di oggi.')
    result = api_json('https://google.serper.dev/search', {'q': query, 'gl': 'it', 'hl': 'it', 'num': 10},
                      headers={'X-API-KEY': os.environ['SERPER_API_KEY']})
    return {'results': [{'url': item.get('link', ''), 'title': item.get('title', ''),
                         'content': item.get('snippet', '')} for item in result.get('organic', [])]}


def search_web(query, use_local=True):
    check_search_stop()
    local_only = bool(os.getenv('SEARXNG_URL')) and not settings()['allow_api_fallback']
    if local_only and not use_local:
        raise SearchLimitError('Limite di richieste SearXNG per questo avvio raggiunto. Puoi avviare un altro gruppo.')
    if use_local and os.getenv('SEARXNG_URL') and time.monotonic() >= SEARXNG_STATUS['retry_after']:
        try:
            result = searxng_search(query)
            if result['results']:
                SEARXNG_STATUS.update(message='Attivo · nessun credito API consumato', retry_after=0)
                return result
            SEARXNG_STATUS['message'] = 'Nessun risultato per questa ricerca' if local_only else 'Nessun risultato · uso dei motori alternativi'
            if local_only:
                return result
        except (OSError, ValueError, http.client.HTTPException):
            SEARXNG_STATUS.update(message='SearXNG non raggiungibile: verifica Docker' if local_only else 'Non disponibile · uso dei motori alternativi', retry_after=time.monotonic() + 60)
    if local_only:
        raise SearchLimitError('SearXNG non disponibile. Apri Docker e riprova. Tavily e Serper non sono stati utilizzati.')
    if os.getenv('TAVILY_API_KEY'):
        try:
            return tavily_search(query)
        except SearchLimitError:
            if not os.getenv('SERPER_API_KEY'):
                raise
        except error.HTTPError as exc:
            if exc.code not in (429, 432, 433) or not os.getenv('SERPER_API_KEY'):
                raise
    if os.getenv('SERPER_API_KEY'):
        return serper_search(query)
    raise SearchLimitError('Nessun motore disponibile in questo momento. Puoi riprovare più tardi.')


def company_match(c, lead, contacted_only=False):
    """Keep company history as a permanent suppression list."""
    lead = dict(lead)
    vat = lead.get('vat', '')
    vat = vat if valid_vat(vat) else ''
    condition = " AND (status IN ('sending','sent','uncertain','gmail_pending') OR sent_at IS NOT NULL)" if contacted_only else ''
    return c.execute("""SELECT 1 FROM leads WHERE id!=? AND
        (lower(domain)=lower(?) OR lower(trim(email))=lower(trim(?))
         OR (?!='' AND vat=?))""" + condition,
        (lead.get('id', -1), lead['domain'], lead['email'], vat, vat)).fetchone()


def suppress_contacted_companies(c):
    # Preserve sent/pending history; only remove unsent alias proposals.
    for other in c.execute("SELECT * FROM leads WHERE status='draft'").fetchall():
        if company_match(c, other, contacted_only=True):
            c.execute("UPDATE leads SET status='excluded',error='Azienda già contattata.' WHERE id=?", (other['id'],))
    suppress_known_candidates(c)


def suppress_known_candidates(c):
    c.execute("""UPDATE search_candidates SET status='done',last_reason='duplicate',retry_after=0
        WHERE status IN ('pending','retry') AND domain IN (SELECT domain FROM leads)""")


def pending_candidates():
    with db() as c:
        return c.execute("SELECT count(*) FROM search_candidates WHERE status='pending' OR (status='retry' AND retry_after<=?)", (time.time(),)).fetchone()[0] + c.execute("SELECT count(*) FROM leads WHERE status='review_pending'").fetchone()[0]


def deferred_candidates():
    with db() as c:
        return c.execute("SELECT count(*) FROM search_candidates WHERE status='retry' AND retry_after>?", (time.time(),)).fetchone()[0]


def cache_candidates(items, plan=None):
    fresh = 0
    if plan and plan not in search_plan():
        return 0
    with db() as c:
        for item in items:
            if not business_result(item):
                continue
            domain = hostname(item.get('url', ''))
            if c.execute('SELECT 1 FROM leads WHERE domain=?', (domain,)).fetchone():
                continue
            result = c.execute('INSERT OR IGNORE INTO search_candidates(domain,item,query_key) VALUES (?,?,?)', (domain, json.dumps(item), query_key(plan) if plan else None))
            fresh += result.rowcount
        if plan:
            key = query_key(plan)
            c.execute('INSERT OR IGNORE INTO query_performance(key,sector,city,area) VALUES (?,?,?,?)', (key, *plan))
            c.execute('UPDATE query_performance SET requests=requests+1, returned=returned+?, fresh=fresh+? WHERE key=?', (len(items), fresh, key))
    return fresh


def inspect_with_deadline(url, timeout=INSPECTION_TIMEOUT):
    """Isolate browser/DNS/network stalls; Stop also kills the browser descendants."""
    ANALYSIS_LOCAL.reason = 'unavailable'
    process = subprocess.Popen([sys.executable, str(ROOT / 'app.py'), '--inspect', url],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, start_new_session=True)
    deadline = time.monotonic() + timeout if timeout is not None else None
    try:
        while True:
            check_search_stop()
            remaining = deadline - time.monotonic() if deadline is not None else None
            if remaining is not None and remaining <= 0:
                ANALYSIS_LOCAL.reason = 'timeout'
                return None
            try:
                output, _ = process.communicate(timeout=min(.25, remaining) if remaining is not None else .25)
                if process.returncode != 0:
                    return None
                result = json.loads(output)
                ANALYSIS_LOCAL.reason = result.get('reason', 'unavailable')
                return result.get('lead')
            except subprocess.TimeoutExpired:
                continue
    finally:
        # The browser may outlive the Python child, so clean up its process group too.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()


def analyze_candidate(candidate):
    ANALYSIS_LOCAL.reason = 'unavailable'
    with db() as c:
        if c.execute('SELECT 1 FROM leads WHERE domain=?', (candidate['domain'],)).fetchone():
            return None, 'duplicate'
    try:
        lead = inspect_with_deadline(json.loads(candidate['item'])['url'])
        return lead, getattr(ANALYSIS_LOCAL, 'reason', 'unavailable')
    except (OSError, ValueError, http.client.HTTPException):
        return None, 'unavailable'


def stage_unassessed_drafts():
    """Preserve emails, but remove unassessed prospects from ready-to-review drafts."""
    count = 0
    with db() as c:
        for row in c.execute("SELECT id,findings FROM leads WHERE status='draft'").fetchall():
            if any(f.get('kind') == 'Opportunità commerciale' for f in json.loads(row['findings'])):
                c.execute("UPDATE leads SET status='review_pending' WHERE id=?", (row['id'],))
                count += 1
    return count


def reassess_pending_drafts():
    with db() as c:
        rows = [dict(row) for row in c.execute("SELECT id,url,domain FROM leads WHERE status='review_pending' ORDER BY id")]
    restored = 0
    def assess(row):
        ANALYSIS_LOCAL.reason = 'unavailable'
        result = inspect_with_deadline(row['url'])
        return result, getattr(ANALYSIS_LOCAL, 'reason', 'unavailable')
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(assess, row): row for row in rows}
        for future in as_completed(futures):
            check_search_stop()
            row = futures[future]
            result, reason = future.result()
            if not result:
                if reason not in RETRY_REASONS:
                    with db() as c:
                        c.execute("UPDATE leads SET status='review_rejected' WHERE id=? AND status='review_pending'", (row['id'],))
                continue
            with db() as c:
                updated = c.execute("UPDATE leads SET findings=?,site_audit=?,status='draft' WHERE id=? AND status='review_pending'",
                                    (json.dumps(result['findings']), json.dumps(result.get('site_audit',{})), row['id'])).rowcount
            restored += updated
            with LOCK:
                JOB.update(added=restored, message='Rivalutazione delle schede precedenti: controllo effettivo del sito in corso.')
    return restored


def search_worker():
    checked, added, requests = 0, 0, 0
    counts = dict.fromkeys(('no_email', 'not_business', 'no_issue', 'duplicate', 'outside_area', *sorted(RETRY_REASONS)), 0)
    try:
        exclude_outside_candidates()
        with LOCK:
            JOB['message'] = 'Valutazione delle schede precedenti in corso.'
        added = reassess_pending_drafts()
        queries = search_plan()
        profile = settings()
        local_start = searxng_usage()
        request_budget = remaining_searches()
        while added < 20:
            check_search_stop()
            focus_cities = sorted(set().union(*FOCUS_CITIES.values()))
            with db() as c:
                candidates = [dict(r) for r in c.execute("SELECT * FROM search_candidates WHERE status='pending' OR (status='retry' AND retry_after<=?) ORDER BY CASE WHEN json_extract(query_key, '$[1]') IN (" + ','.join('?' for _ in focus_cities) + ") THEN 0 ELSE 1 END, CASE status WHEN 'pending' THEN 0 ELSE 1 END, id LIMIT ?", (time.time(), *focus_cities, min(3, 20-added))).fetchall()]
            if not candidates:
                if requests >= request_budget:
                    break
                plan = choose_query()
                sector, city, area = plan
                query = f'{sector} {city} srl contatti -comune -ministero -directory -elenco -lavoro'
                with LOCK:
                    JOB['message'] = f'Ricerca aziende S.r.l. · {area} · {city}'
                result = search_web(query, use_local=searxng_usage() - local_start < 100)
                requests += 1
                cache_candidates(result.get('results', []), plan)
                time.sleep(1)
                continue
            with LOCK:
                JOB.update(active=[c['domain'] for c in candidates], counts=dict(counts),
                           message=f"Analisi di {len(candidates)} siti in parallelo · Lighthouse mobile/desktop, un test alla volta")
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(analyze_candidate, candidate): candidate for candidate in candidates}
                for future in as_completed(futures):
                    candidate = futures[future]
                    lead, reason = future.result()
                    check_search_stop()
                    checked += 1
                    before_added = added
                    with db() as c:
                        c.execute('BEGIN IMMEDIATE')
                        if c.execute("SELECT status FROM search_candidates WHERE id=?", (candidate['id'],)).fetchone()[0] == 'dismissed':
                            continue
                        if lead:
                            same_email = company_match(c, lead)
                            if not same_email:
                                subject, body = draft(lead, settings())
                                cursor = c.execute('INSERT OR IGNORE INTO leads (domain,name,url,email,email_source,findings,subject,body,created,context) VALUES (?,?,?,?,?,?,?,?,?,?)',
                                    (lead['domain'], lead['name'], lead['url'], lead['email'], lead['email_source'], json.dumps(lead['findings']), subject, body, today(), json.dumps(lead.get('context', []))))
                                added += cursor.rowcount
                                if cursor.rowcount:
                                    c.execute('UPDATE leads SET vat=?,site_audit=? WHERE id=?', (lead.get('vat',''), json.dumps(lead.get('site_audit',{})), cursor.lastrowid))
                                if not cursor.rowcount:
                                    counts['duplicate'] += 1
                                    reason = 'duplicate'
                            else:
                                counts['duplicate'] += 1
                                reason = 'duplicate'
                        else:
                            counts[reason if reason in counts else 'unavailable'] += 1
                        retry = not lead and reason in RETRY_REASONS and candidate.get('attempts',0) < 1
                        c.execute('UPDATE search_candidates SET status=?,attempts=attempts+1,last_reason=?,retry_after=? WHERE id=?', ('retry' if retry else 'done', 'selected' if lead and added>before_added else reason, time.time()+86400 if retry else 0, candidate['id']))
                        if candidate.get('query_key'):
                            c.execute('UPDATE query_performance SET checked=checked+1, drafts=drafts+? WHERE key=?', (added-before_added, candidate['query_key']))
                    with LOCK:
                        JOB.update(added=added, checked=checked, counts=dict(counts),
                                   active=[d for d in JOB.get('active', []) if d != candidate['domain']])
        if added == 20:
            message = f'Obiettivo raggiunto: 20 nuovi siti con bozza pronta. {checked} siti esaminati. Puoi avviare un altro gruppo di 20.'
        else:
            message = (f'Ricerca terminata con meno di 20 risultati: {added}/20 nuovi siti, {checked} esaminati. '
                       'Raggiunto il budget di richieste di questo avvio o dei motori. Le bozze trovate sono salvate.')
    except SearchStopped:
        message = f'Ricerca fermata: {added}/20 nuove bozze salvate. I siti ancora da analizzare restano in coda.'
    except SearchLimitError as exc:
        message = f'{added}/20 nuove bozze salvate. {exc}'
    except error.HTTPError as exc:
        message = f'{added}/20 nuove bozze salvate. Il motore ha risposto HTTP {exc.code}. Controlla le quote nelle impostazioni.'
    except Exception:
        message = f'Ricerca interrotta da un errore di rete o configurazione. {added}/20 nuove bozze salvate; i siti in coda restano disponibili.'
    finally:
        with LOCK:
            JOB.update(running=False, stopping=False, added=added, checked=checked, message=message, counts=dict(counts), active=[])


def recover_layout_candidates():
    """One-time recovery of candidates rejected only by the previous layout gate."""
    key = 'commercial_candidates_v1'
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM settings WHERE key=?', (key,)).fetchone():
            return 0
        recovered = c.execute("""UPDATE search_candidates SET status='pending',retry_after=0
            WHERE status IN ('done','retry')
            AND last_reason IN ('no_issue','dynamic_request','resource_error','load_budget','browser_error','empty_page')
            AND domain NOT IN (SELECT domain FROM leads)""").rowcount
        c.execute('INSERT INTO settings(key,value) VALUES (?,?)', (key, 'true'))
    exclude_outside_candidates()
    return recovered


def recover_technical_candidates():
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM settings WHERE key='lighthouse_selection_v1'").fetchone():return 0
        count=c.execute("""UPDATE search_candidates SET status='pending',retry_after=0,attempts=0
            WHERE status IN ('done','retry') AND last_reason IN
            ('no_issue','dynamic_request','resource_error','load_budget','browser_error','empty_page','timeout')
            AND domain NOT IN (SELECT domain FROM leads)""").rowcount
        c.execute("UPDATE leads SET status='review_pending' WHERE status='review_rejected'")
        c.execute("INSERT INTO settings(key,value) VALUES ('lighthouse_selection_v1','true')")
    exclude_outside_candidates()
    return count


def start_search():
    if not (os.getenv('SEARXNG_URL') or os.getenv('TAVILY_API_KEY') or os.getenv('SERPER_API_KEY')):
        raise ValueError('Configura SearXNG, Tavily o Serper nel file .env e riavvia il server.')
    if not settings()['website']:
        raise ValueError('Inserisci il tuo sito nelle impostazioni prima di generare le email.')
    with LOCK:
        if JOB['running']:
            raise ValueError('Una ricerca è già in corso.')
        if remaining_searches() <= 0 and pending_candidates() == 0:
            raise SearchLimitError('Richieste disponibili esaurite. Controlla i contatori Tavily e Serper nelle impostazioni.')
        with db() as c:
            c.execute('INSERT OR REPLACE INTO runs VALUES (?, ?)', (today(), datetime.now().isoformat()))
        STOP_SEARCH.clear()
        JOB.update(running=True, stopping=False, checked=0, added=0, message='Avvio della ricerca…', counts={}, active=[])
        threading.Thread(target=search_worker, daemon=True).start()


def stop_search():
    with LOCK:
        if JOB['running']:
            STOP_SEARCH.set()
            JOB.update(stopping=True, message='Arresto in corso: attendo la richiesta già partita. Le bozze raccolte restano salvate.')


def token_save(tokens):
    path = DATA / 'google-token.json'
    temp = DATA / ('google-token-' + secrets.token_hex(8) + '.tmp')
    fd = os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(tokens, f)
    os.replace(temp, path)


def token_read():
    path = DATA / 'google-token.json'
    return json.loads(path.read_text()) if path.exists() else {}


def access_token():
    tokens = token_read()
    if not tokens:
        raise ValueError('Collega Gmail dalle impostazioni.')
    if tokens.get('expires_at', 0) < time.time() + 60:
        if not tokens.get('refresh_token'):
            raise ValueError('Collega nuovamente Gmail: autorizzazione scaduta.')
        refreshed = api_json('https://oauth2.googleapis.com/token', {'grant_type': 'refresh_token', 'refresh_token': tokens['refresh_token'], 'client_id': os.getenv('GOOGLE_CLIENT_ID'), 'client_secret': os.getenv('GOOGLE_CLIENT_SECRET')}, form=True)
        tokens.update(refreshed)
        tokens['expires_at'] = time.time() + refreshed['expires_in']
        token_save(tokens)
    return tokens['access_token']


def validate_message(email, subject, body):
    if not isinstance(email, str) or not EMAIL.fullmatch(email) or '\r' in email or '\n' in email:
        raise ValueError('Indirizzo email non valido.')
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 250 or '\n' in subject or '\r' in subject:
        raise ValueError('Oggetto non valido (massimo 250 caratteri, una sola riga).')
    if not isinstance(body, str) or not body.strip() or len(body) > 20000:
        raise ValueError('Testo obbligatorio, massimo 20.000 caratteri.')


def prepare_gmail(lead_id):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        lead = c.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
        if not lead or lead['status'] != 'draft':
            raise ValueError('Messaggio già aperto o non disponibile. Verifica in Gmail.')
        validate_message(lead['email'], lead['subject'], lead['body'])
        if company_match(c, lead, contacted_only=True):
            raise ValueError('Indirizzo già contattato o da verificare in Gmail.')
        url = 'https://mail.google.com/mail/?' + parse.urlencode({'view':'cm', 'fs':'1', 'authuser':EXPECTED_EMAIL, 'to':lead['email'], 'su':lead['subject'], 'body':lead['body']})
        c.execute("UPDATE leads SET status='gmail_pending', error='' WHERE id=?", (lead_id,))
        return url


OUTCOMES = {'awaiting', 'replied', 'interested', 'declined', 'customer', 'do_not_contact'}


def save_outcome(lead_id, outcome, note):
    if outcome not in OUTCOMES or not isinstance(note, str) or len(note) > 3000:
        raise ValueError('Esito o nota non validi')
    with db() as c:
        result = c.execute("UPDATE leads SET outcome=?,outcome_note=?,outcome_updated=? WHERE id=? AND status='sent'", (outcome,note,datetime.now(ZoneInfo('Europe/Rome')).isoformat(),lead_id))
        if result.rowcount != 1:
            raise ValueError('Puoi registrare un esito solo per un invio già confermato.')


def confirm_gmail(lead_id):
    with db() as c:
        result = c.execute("UPDATE leads SET status='sent', outcome='awaiting', sent_at=?, message_id='manual-gmail' WHERE id=? AND status='gmail_pending'", (datetime.now(ZoneInfo('Europe/Rome')).isoformat(), lead_id))
        if result.rowcount != 1:
            raise ValueError('Messaggio non disponibile per la conferma.')
        suppress_contacted_companies(c)



def send_lead(lead_id):
    # Atomically claim the draft: double-clicks and concurrent requests cannot resend it.
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        lead = c.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
        if not lead or lead['status'] != 'draft':
            raise ValueError('Questa bozza non è disponibile per l’invio.')
        validate_message(lead['email'], lead['subject'], lead['body'])
        previous = company_match(c, lead, contacted_only=True)
        if previous:
            raise ValueError('Questo indirizzo è già stato contattato o ha un invio da verificare.')
        if not token_read():
            raise ValueError('Collega Gmail dalle impostazioni.')
        c.execute("UPDATE leads SET status='sending', error='' WHERE id=?", (lead_id,))
    attempted = False
    try:
        token = access_token()
        msg = EmailMessage()
        msg['From'] = Address(display_name=settings()['name'], addr_spec=EXPECTED_EMAIL)
        msg['To'] = lead['email']
        msg['Subject'] = lead['subject']
        msg.set_content(lead['body'])
        msg.add_alternative(email_html(lead['body'], settings()['website']), subtype='html')
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        attempted = True
        response = api_json('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', {'raw': raw}, {'Authorization': 'Bearer ' + token})
        with db() as c:
            c.execute("UPDATE leads SET status='sent', sent_at=?, message_id=? WHERE id=?", (datetime.now(ZoneInfo('Europe/Rome')).isoformat(), response['id'], lead_id))
    except Exception as exc:
        uncertain = attempted and not (isinstance(exc, error.HTTPError) and 400 <= exc.code < 500)
        message = 'Esito incerto: controlla la posta inviata in Gmail. Il reinvio è bloccato per evitare duplicati.' if uncertain else 'Invio non riuscito. Verifica il collegamento Gmail e riprova.'
        with db() as c:
            c.execute('UPDATE leads SET status=?, error=? WHERE id=?', ('uncertain' if uncertain else 'draft', message, lead_id))
        raise ValueError(message) from exc


def opportunity_search(query, provider, time_range='month'):
    """Dedicated provider adapter; shares budgets, never the company-search stop event."""
    if provider == 'searxng':
        base = os.getenv('SEARXNG_URL', '').rstrip('/')
        parts = parse.urlsplit(base)
        if parts.scheme != 'http' or parts.hostname not in ('127.0.0.1', 'localhost'):
            raise ValueError('SearXNG locale non configurato. Apri Docker o scegli Tavily.')
        with db() as c:
            c.execute('INSERT INTO searxng_usage VALUES (?,1) ON CONFLICT(day) DO UPDATE SET requests=requests+1', (today(),))
        result = api_json(base + '/search?' + parse.urlencode({'q': query, 'format': 'json', 'language': 'it-IT', 'categories': 'general', 'time_range': time_range}))
    else:
        if not os.getenv('TAVILY_API_KEY'):
            raise ValueError('Tavily non configurato. Inserisci la chiave in .env oppure scegli SearXNG.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            monthly = c.execute('SELECT coalesce(sum(requests),0) FROM search_usage WHERE day LIKE ?', (today()[:7] + '%',)).fetchone()[0]
            if monthly >= MONTHLY_SEARCH_LIMIT:
                raise ValueError('Quota mensile Tavily esaurita (930 richieste condivise).')
            c.execute('INSERT OR IGNORE INTO search_usage VALUES (?,0)', (today(),))
            if c.execute('UPDATE search_usage SET requests=requests+1 WHERE day=? AND requests<?', (today(), DAILY_SEARCH_LIMIT)).rowcount != 1:
                raise ValueError('Quota giornaliera Tavily esaurita (30 richieste condivise).')
        result = api_json('https://api.tavily.com/search', {
            'query': query, 'topic': 'general', 'search_depth': 'basic', 'auto_parameters': False,
            'max_results': 10, 'include_answer': False, 'include_raw_content': False,
            'include_images': False, 'exclude_domains': list(OPPORTUNITY_BLOCKED),
            **({'time_range': time_range} if time_range else {}),
        }, headers={'Authorization': 'Bearer ' + os.environ['TAVILY_API_KEY']})
    items = result.get('results')
    if not isinstance(items, list):
        raise ValueError('Risposta del motore non valida')
    return [item for item in items[:20] if isinstance(item, dict) and isinstance(item.get('url'), str)]


def opportunity_page(url, policy=None, robots=False):
    # robots redirects fail closed; all content redirects re-check domain policy and robots.
    if robots:
        return public_page(url, redirects=0)
    return public_page(url, policy=policy)


OPPORTUNITIES = OpportunityService(db, opportunity_search, opportunity_page)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # OAuth codes and query parameters must never enter access logs.
        pass

    def reply(self, status, body, content_type='application/json; charset=utf-8', extra=None):
        payload = json.dumps(body, ensure_ascii=False).encode() if content_type.startswith('application/json') else body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def trusted_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{PORT}'

    def do_GET(self):
        if not self.trusted_host():
            return self.reply(403, {'error': 'Apri l’app da ' + ORIGIN})
        path = parse.urlsplit(self.path).path
        if path == '/api/opportunities':
            return self.reply(200, OPPORTUNITIES.state())
        if path == '/opportunities.js':
            return self.reply(200, (ROOT / 'static' / 'opportunities.js').read_bytes(), 'text/javascript; charset=utf-8')
        if path in ('/', '/app.js', '/style.css'):
            filename = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[path]
            mime = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8', '/style.css': 'text/css; charset=utf-8'}[path]
            return self.reply(200, (ROOT / 'static' / filename).read_bytes(), mime)
        if re.fullmatch(r'/site-reviews/[a-f0-9]{24}-(390|1366)\.png',path):
            image=DATA / 'site-reviews' / path.rsplit('/',1)[1]
            return self.reply(200,image.read_bytes(),'image/png') if image.exists() else self.reply(404,{'error':'Immagine non disponibile'})
        if re.fullmatch(r'/site-reviews/lighthouse-(?:\d+|[a-f0-9]{24})-(mobile|desktop)\.json',path):
            report=DATA / 'site-reviews' / path.rsplit('/',1)[1]
            return self.reply(200,json.loads(report.read_text())) if report.exists() else self.reply(404,{'error':'Report non disponibile'})
        if path == '/api/state':
            with db() as c:
                leads = [dict(r) for r in c.execute("SELECT * FROM leads WHERE status NOT IN ('deleted','excluded','review_pending','review_rejected') ORDER BY id DESC")]
            for lead in leads:
                lead['findings'] = json.loads(lead['findings'])
                visible_findings=[]
                for finding in lead['findings']:
                    if finding.get('kind')=='Usabilità · layout' and 'ux_findings' in finding:
                        useful=[f for f in finding['ux_findings'] if f.get('code')!='small_text']
                        if not useful: continue
                        finding={**finding,'ux_findings':useful,'text':' '.join(f['text'] for f in useful)}
                    visible_findings.append(finding)
                lead['findings']=visible_findings
                lead['site_audit'] = json.loads(lead.get('site_audit') or '{}')
                lead['context'] = json.loads(lead['context'])
                lead['selection_reason'] = ' '.join(f['text'] for f in selection_evidence(lead['site_audit'])) or redesign_reason(lead)
                lead['needs_review'] = not bool(lead['selection_reason']) or any(f.get('manual_review') for f in lead['findings'])
                lead['finance'] = json.loads(lead['finance']) if lead.get('finance') else None
            with LOCK:
                job = dict(JOB)
            return self.reply(200, {'csrf': CSRF, 'leads': leads, 'settings': settings(), 'job': job, 'today_count': count_today(), 'pending_candidates': pending_candidates(), 'deferred_candidates': deferred_candidates(), 'search_performance': search_performance(), 'gmail': {'connected': bool(token_read()), 'email': EXPECTED_EMAIL, 'configured': bool(os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET'))}, 'search_configured': bool(os.getenv('SEARXNG_URL') or os.getenv('TAVILY_API_KEY') or os.getenv('SERPER_API_KEY')), 'search_providers': {'searxng': {'configured': bool(os.getenv('SEARXNG_URL')), 'today': searxng_usage(), 'status': SEARXNG_STATUS['message']}, 'tavily': {'configured': bool(os.getenv('TAVILY_API_KEY')), 'today': search_usage(), 'month': monthly_search_usage()}, 'serper': {'configured': bool(os.getenv('SERPER_API_KEY')), 'today': serper_usage()[0], 'total': serper_usage()[1]}}})
        if path == '/auth/google/callback':
            query = parse.parse_qs(parse.urlsplit(self.path).query)
            state = query.get('state', [''])[0]
            cookie = self.headers.get('Cookie', '')
            session = next((v.partition('=')[2] for v in cookie.split('; ') if v.startswith('oauth_session=')), '')
            with LOCK:
                pending = OAUTH.pop(state, None)
            if not pending or time.time() - pending['time'] > 600 or not secrets.compare_digest(session, pending['session']):
                return self.reply(400, 'Accesso scaduto o non valido. Torna alle impostazioni e riprova.', 'text/plain; charset=utf-8')
            try:
                code = query.get('code', [''])[0]
                if not code:
                    raise ValueError('Accesso non autorizzato')
                tokens = api_json('https://oauth2.googleapis.com/token', {'code': code, 'client_id': os.getenv('GOOGLE_CLIENT_ID'), 'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'), 'redirect_uri': REDIRECT, 'grant_type': 'authorization_code', 'code_verifier': pending['verifier']}, form=True)
                profile = api_json('https://openidconnect.googleapis.com/v1/userinfo', headers={'Authorization': 'Bearer ' + tokens['access_token']})
                if profile.get('email', '').lower() != EXPECTED_EMAIL or not profile.get('email_verified'):
                    raise ValueError('Account diverso da quello richiesto')
                if 'https://www.googleapis.com/auth/gmail.send' not in tokens.get('scope', '').split():
                    raise ValueError('Permesso di invio non concesso')
                tokens['expires_at'] = time.time() + tokens['expires_in']
                token_save(tokens)
                return self.reply(302, '', 'text/plain', {'Location': '/?gmail=connected', 'Set-Cookie': 'oauth_session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/auth/google/callback'})
            except Exception:
                return self.reply(400, 'Collegamento non completato. Usa pavanello93@gmail.com, autorizza l’invio e verifica la configurazione OAuth.', 'text/plain; charset=utf-8')
        self.reply(404, {'error': 'Pagina non trovata'})

    def do_POST(self):
        if not self.trusted_host() or self.headers.get('Origin') != ORIGIN or self.headers.get('X-CSRF-Token') != CSRF:
            return self.reply(403, {'error': 'Richiesta non autorizzata. Ricarica la pagina.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 100000:
                raise ValueError('Richiesta troppo grande')
            body = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body, dict):
                raise ValueError('Richiesta non valida')
            path = parse.urlsplit(self.path).path
            if path == '/api/opportunities/search':
                OPPORTUNITIES.start()
            elif path == '/api/opportunities/stop':
                OPPORTUNITIES.stop.set()
            elif path == '/api/opportunities/config':
                OPPORTUNITIES.configure(body)
            elif re.fullmatch(r'/api/opportunities/\d+', path):
                return self.reply(200, OPPORTUNITIES.update(int(path.rsplit('/',1)[1]), body))
            elif path == '/api/search':
                start_search()
            elif path == '/api/search/stop':
                stop_search()
            elif path == '/api/settings':
                values = {key: body[key] for key in ('name', 'website', 'signature', 'template_subject', 'template_body', 'allow_api_fallback') if key in body}
                if 'allow_api_fallback' in values and not isinstance(values['allow_api_fallback'], bool):
                    raise ValueError('Impostazione motori non valida')
                for key in ('name', 'website', 'signature'):
                    if key in values and (not isinstance(values[key], str) or len(values[key]) > 2000):
                        raise ValueError('Impostazioni non valide')
                if 'name' in values and not values['name'].strip():
                    raise ValueError('Inserisci il tuo nome')
                if values.get('website') and (parse.urlsplit(values['website']).scheme not in ('http', 'https') or not parse.urlsplit(values['website']).hostname):
                    raise ValueError('Inserisci il sito completo, ad esempio https://iltuosito.it')
                if 'daily' in values and not isinstance(values['daily'], bool):
                    raise ValueError('Programmazione non valida')
                for key, limit in (('template_subject', 250), ('template_body', 18000)):
                    if key in values and (not isinstance(values[key], str) or not values[key].strip() or len(values[key]) > limit):
                        raise ValueError('Template vuoto o troppo lungo')
                if any(ch in values.get('template_subject', '') for ch in ('\r', '\n')):
                    raise ValueError('Oggetto su una sola riga')
                preview = {**settings(), **values}
                subject, text = draft({'domain':'azienda-esempio.it'}, preview)
                validate_message('test@example.org', subject, text)
                if body.get('apply_template', False) is not False and body.get('apply_template') is not True:
                    raise ValueError('Scelta non valida')
                save_settings(values)
                if body.get('apply_template'):
                    return self.reply(200, {'ok':True, 'updated':apply_template_to_drafts()})
            elif path == '/api/gmail/connect':
                if not os.getenv('GOOGLE_CLIENT_ID') or not os.getenv('GOOGLE_CLIENT_SECRET'):
                    raise ValueError('Configura GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET nel file .env e riavvia. Trovi i passaggi nelle impostazioni.')
                state, session, verifier = (secrets.token_urlsafe(40) for _ in range(3))
                with LOCK:
                    OAUTH.clear()
                    OAUTH[state] = {'time': time.time(), 'session': session, 'verifier': verifier}
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                url = 'https://accounts.google.com/o/oauth2/v2/auth?' + parse.urlencode({'client_id': os.environ['GOOGLE_CLIENT_ID'], 'redirect_uri': REDIRECT, 'response_type': 'code', 'scope': 'openid email https://www.googleapis.com/auth/gmail.send', 'access_type': 'offline', 'prompt': 'consent', 'login_hint': EXPECTED_EMAIL, 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'})
                return self.reply(200, {'url': url}, extra={'Set-Cookie': f'oauth_session={session}; HttpOnly; SameSite=Lax; Path=/auth/google/callback; Max-Age=600'})
            elif path == '/api/gmail/disconnect':
                (DATA / 'google-token.json').unlink(missing_ok=True)
            elif re.fullmatch(r'/api/leads/\d+/(edit|delete|send|compose|confirm|finance|outcome|audit)', path):
                lead_id, action = int(path.split('/')[3]), path.split('/')[4]
                if action == 'audit':
                    return self.reply(200, {'ok':True,'audit':audit_website(lead_id)})
                if action == 'outcome':
                    save_outcome(lead_id, body.get('outcome'), body.get('note'))
                    return self.reply(200, {'ok':True})
                if action == 'finance':
                    return self.reply(200, {'ok':True, 'finance':lookup_finance(lead_id)})
                if action in ('send', 'compose'):
                    return self.reply(200, {'url': prepare_gmail(lead_id)})
                elif action == 'confirm':
                    confirm_gmail(lead_id)
                else:
                    with db() as c:
                        if action == 'edit':
                            validate_message(body.get('email'), body.get('subject'), body.get('body'))
                            result = c.execute("UPDATE leads SET email=?,subject=?,body=?,error='' WHERE id=? AND status='draft'", (body['email'], body['subject'], body['body'], lead_id))
                        else:
                            result = c.execute("UPDATE leads SET status='deleted' WHERE id=? AND status='draft'", (lead_id,))
                        if result.rowcount != 1:
                            raise ValueError('Bozza non disponibile: aggiorna la pagina.')
            else:
                return self.reply(404, {'error': 'Operazione non trovata'})
            self.reply(200, {'ok': True})
        except (ValueError, KeyError, TypeError) as exc:
            self.reply(400, {'error': str(exc)})
        except Exception:
            self.reply(500, {'error': 'Operazione non completata. Verifica la configurazione e riprova.'})


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--inspect':
        try:
            result = inspect_site(sys.argv[2])
        except Exception:
            result = None
        print(json.dumps({'lead': result, 'reason': INSPECTION_REASON}))
        sys.exit(0)
    init()
    refresh_generated_drafts()
    stage_unassessed_drafts()
    recover_technical_candidates()
    exclude_outside_candidates()
    print(f'CustomerSearch disponibile su {ORIGIN}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
