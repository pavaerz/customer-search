"""Independent, evidence-first opportunity discovery. No sending and no browser automation."""
import hashlib
import json
import re
import threading
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.robotparser import RobotFileParser

DEFAULT_QUERIES = [
    '"cerchiamo" "WordPress" "freelance" agenzia',
    '"agenzia" "collaboratori" "web developer" freelance',
    '"cercasi" "realizzazione sito" freelance',
    '"cerchiamo" "WooCommerce" collaborazione',
    '"sviluppatore frontend" "partita IVA" remoto',
    '"web agency" "freelance" "lavora con noi"',
    '"cerco" "landing page" sviluppatore',
    '"looking for" "Next.js" "freelance" "Europe"',
    '"cerchiamo" "React" "collaborazione esterna"',
    '"rifare sito" "cerco" professionista',
    '"WordPress" "freelance" "posizioni aperte"',
    '"frontend developer" "contract" "remote Europe"',
]
# No direct access or extraction through a provider for restricted / unevaluated platforms.
BLOCKED = ('play.google.com', 'apps.apple.com', 'linkedin.com', 'indeed.com', 'indeed.it', 'upwork.com', 'addlance.com',
           'freelancer.com', 'freelancer.it', 'freelancer.co.uk', 'freelancer.ca',
           'facebook.com', 'instagram.com', 'x.com', 'reddit.com', 'malt.it', 'malt.com', 'twago.it', 'peopleperhour.com', 'toptal.com',
           'talent.com', 'glassdoor.com', 'glassdoor.it', 'jobsora.com', 'jobsavior.com',
           'jooble.org', 'jobleads.com', 'simplyhired.it', 'simplyhired.com', 'ziprecruiter.com',
           'workingnomads.com', 'trabajo.org', 'jobijoba.it', 'crebs.it', 'lavoricreativi.com',
           'freelanceboard.it', 'remoterocketship.com', 'workana.com', 'fiverr.com', 'reactjobs.io')
SKILLS = {'WordPress': r'\bwordpress\b', 'WooCommerce': r'\bwoocommerce\b',
          'React': r'\breact(?:\.js)?\b', 'Next.js': r'\bnext\.?js\b',
          'HTML': r'\bhtml5?\b', 'CSS / SCSS': r'\b(?:css3?|scss|sass)\b',
          'JavaScript': r'\bjavascript\b', 'UI/UX': r'\b(?:ui\s*[/&-]\s*ux|ux\s*[/&-]\s*ui|web design(?:er)?)\b',
          'GSAP': r'\bgsap\b', 'WebGL': r'\bwebgl\b',
          'Siti / e-commerce / landing page': r'\b(?:siti? (?:web|internet|aziendali)|landing page|e-?commerce)\b'}
DEMAND = re.compile(r'\b(?:cerchiamo|cercasi|cerco|ricerchiamo|selezioniamo|stiamo cercando|siamo alla ricerca|looking for|we are hiring|we.re hiring|we are seeking|is seeking|è alla ricerca di|siamo alla ricerca di|cerca un|cerca collabor|posizion[ei] apert[ae])\b', re.I)
FREELANCE = re.compile(r'\b(?:freelanc\w*|partita\s*iva|p\.?\s*iva|collaborazion\w* estern\w*|collaborator\w* estern\w*|contractor|on a contract|contract role)\b', re.I)
ROLE = re.compile(r'\b(?:wordpress|woocommerce|front.?end|web (?:design(?:er)?|develop(?:er|ment)?)|sviluppator\w*|programmat\w*|react|next\.?js|siti? (?:web|internet)|landing page)\b', re.I)
CLOSED = re.compile(r'\b(?:posizione chiusa|annuncio scaduto|ricerca conclusa|position (?:closed|filled)|no longer accepting|applications closed)\b', re.I)
NO_FREELANCE = re.compile(r'\b(?:no freelance|non (?:si )?(?:accettano|cerchiamo|valutiamo) freelance|esclusivamente (?:dipendenti|assunzion\w*)|employees only)\b', re.I)
EMPLOYEE = re.compile(r'\b(?:tempo (?:indeterminato|determinato)|assunzione|apprendistato|tirocinio|internship|permanent employee)\b', re.I)
OTHER_ROLE = re.compile(r'\b(?:copywriter|social media manager|media buyer|project manager|sales manager|graphic designer|java developer|backend developer|back-end developer)\b', re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(url):
    p = urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError('URL non pubblico o non valido')
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/') or '/', urlencode(sorted(query)), ''))


def blocked(url):
    host = (urlsplit(url).hostname or '').lower()
    return any(host == d or host.endswith('.' + d) for d in BLOCKED) or bool(re.search(r'(^|\.)(?:freelancer|indeed)\.', host))


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.parts, self.schemas, self.meta, self.links = [], [], {}, []
        self.hidden = 0
        self.ld = False
        self.raw = []
        self.title = ''
        self.in_title = False
        self.times = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript', 'nav', 'footer'):
            self.hidden += 1
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.ld = True
            self.raw = []
        if tag == 'time' and attrs.get('datetime'):
            self.times.append(attrs['datetime'])
        if tag == 'meta':
            self.meta[attrs.get('property', attrs.get('name', '')).lower()] = attrs.get('content', '')
        if tag == 'a':
            self.links.append(attrs.get('href', ''))
        if tag == 'title':
            self.in_title = True
        if tag in ('p', 'br', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'section', 'article'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag == 'script' and self.ld:
            try:
                self.schemas.append(json.loads(''.join(self.raw)))
            except ValueError:
                pass
            self.ld = False
        if tag in ('script', 'style', 'noscript', 'nav', 'footer'):
            self.hidden = max(0, self.hidden - 1)
        if tag == 'title':
            self.in_title = False
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'section', 'article'):
            self.parts.append('\n')

    def handle_data(self, data):
        if self.ld:
            self.raw.append(data)
        if self.in_title:
            self.title += data
        if not self.hidden and not self.in_title:
            self.parts.append(data)

    @property
    def text(self):
        return '\n'.join(' '.join(s.split()) for s in ''.join(self.parts).splitlines() if s.strip())


def jobs_in(node):
    if isinstance(node, list):
        for v in node:
            yield from jobs_in(v)
    elif isinstance(node, dict):
        types = node.get('@type', [])
        if types == 'JobPosting' or isinstance(types, list) and 'JobPosting' in types:
            yield node
        else:
            for v in node.values():
                yield from jobs_in(v)



def schema_types(node):
    if isinstance(node, list):
        for value in node:
            yield from schema_types(value)
    elif isinstance(node, dict):
        types = node.get('@type', [])
        if isinstance(types, str):
            yield types
        elif isinstance(types, list):
            yield from (value for value in types if isinstance(value, str))
        for value in node.values():
            yield from schema_types(value)


def date_value(value):
    if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}(?:T|$|\s)', value):
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


def analyze(html, url, clock=None):
    """Only accept demand found on the fetched original page; snippets never establish facts."""
    clock = clock or datetime.now(timezone.utc).date()
    if blocked(url):
        return None, 'Fonte esclusa: piattaforma o catalogo, non richiesta verificata'
    d = Document(html)
    postings = [j for s in d.schemas for j in jobs_in(s)]
    if len(postings) > 1:
        return None, 'Elenco con più annunci: serve il link della singola richiesta'
    job = postings[0] if postings else {}
    editorial = {'Article', 'BlogPosting', 'NewsArticle'} & set(schema_types(d.schemas))
    if editorial and not job:
        return None, 'Contenuto editoriale: non è un annuncio di progetto verificato'
    text = Document(str(job['description'])).text if job.get('description') else d.text
    title = str(job.get('title') or d.title).strip()[:240]
    if (re.search(r'\b(?:job board|\d+ offerte di lavoro|\d+ jobs|jobs found|risultati di ricerca|start your search|browse (?:all )?(?:remote )?jobs|explore the fully remote)\b', title + ' ' + text[:700], re.I)
            or re.search(r'/(?:lavoro-|jobs/search|search/jobs|offerte-di-lavoro/?)', urlsplit(url).path, re.I)):
        return None, 'Elenco generico: manca il link di una richiesta singola'
    if re.search(r'/blog/|/tag/|/category/|/come-|/guide/', urlsplit(url).path, re.I):
        return None, 'Articolo o pagina informativa'
    # Isolate the demand sentence so unrelated roles and footer skills cannot qualify it.
    lines = text.splitlines()
    candidates = []
    for line in lines:
        demand = DEMAND.search(line)
        # The object being sought must be a web role/project, not a plugin mentioned
        # in an article that happens to contain WordPress and freelance elsewhere.
        if not demand or not ROLE.search(line[demand.end():demand.end() + 160]):
            continue
        if OTHER_ROLE.search(line[:160]) or re.search(r'^(?:sei |stai |come |are you |how to )|whether you[’\']re looking|whether you are looking|we[’\']ve got you covered', line, re.I):
            continue
        candidates.append(line)
    if not candidates and job and ROLE.search(title) and FREELANCE.search(text):
        candidates = [title + '. ' + text[:650]]
    if not candidates:
        return None, 'Nessuna richiesta esplicita pertinente nel contenuto originale'
    selected = next((line for line in candidates if len(line) > 100 and FREELANCE.search(line)), candidates[0])
    evidence = selected[:1100]
    start = text.find(selected)
    # Stop before another demand, even on a careers page listing multiple roles.
    scope = text[max(0, start):max(0, start) + 4500] if start >= 0 else text[:4500]
    next_demand = DEMAND.search(scope, len(selected))
    if next_demand:
        scope = scope[:next_demand.start()]
    if CLOSED.search(scope) or NO_FREELANCE.search(scope):
        return None, 'Richiesta chiusa o freelance esclusi'
    external = bool(FREELANCE.search(scope))
    direct = bool(re.search(r'\b(?:cerco|cercasi|looking for|need)\b', evidence, re.I) and re.search(r'realizz|rifar|svilupp|build|creat|redesign', evidence, re.I))
    if EMPLOYEE.search(scope) and not external:
        return None, 'Annuncio di assunzione senza apertura freelance'
    if not external and not direct:
        return None, 'Collaborazione esterna non esplicita'
    tech = [name for name, pattern in SKILLS.items() if re.search(pattern, scope, re.I)]
    if not tech:
        return None, 'Competenze non compatibili'
    published = date_value(job.get('datePosted'))
    date_source = 'JobPosting.datePosted' if published else None
    if not published:
        published = date_value(d.meta.get('article:published_time'))
        date_source = 'article:published_time' if published else None
    if not published and len(d.times) == 1:
        published = date_value(d.times[0])
        date_source = 'Elemento time della pagina' if published else None
    if published and published > clock:
        published, date_source = None, None
    expiry = date_value(job.get('validThrough'))
    if expiry and expiry < clock:
        return None, 'Data di scadenza superata'
    age = (clock - published).days if published else None
    if age is not None and age > 180:
        return None, 'Annuncio pubblicato da oltre 180 giorni'
    remote = re.search(r'\b(?:full remote|fully remote|da remoto|remot[oa]|remote|smart working|telelavoro)\b', scope, re.I)
    italy = urlsplit(url).hostname.endswith('.it') or bool(re.search(r'\b(?:italia|italy|italiano|italiana|padova|milano|torino|roma|bologna|firenze)\b', scope, re.I))
    if not italy and not remote:
        return None, 'Richiesta internazionale senza remoto esplicito'
    restricted = re.search(r'\b(?:US only|USA only|UK only|must (?:reside|be based) in (?:the )?(?:US|UK)|only (?:US|UK) residents)\b', scope, re.I)
    if restricted:
        return None, 'Remoto limitato a un paese non compatibile'
    organization = job.get('hiringOrganization') or {}
    company = organization.get('name') if isinstance(organization, dict) else None
    location = None
    locations = job.get('jobLocation', [])
    for loc in locations if isinstance(locations, list) else [locations]:
        address = loc.get('address', {}) if isinstance(loc, dict) else {}
        if isinstance(address, dict):
            location = ', '.join(str(address[k]) for k in ('addressLocality', 'addressRegion', 'addressCountry') if address.get(k)) or None
        if location:
            break
    if not location:
        local_match = re.search(r'(?:Sede(?: di lavoro)?|Localit[àa]|Location)\s*:\s*([^\n.]{2,100})', scope, re.I)
        location = local_match.group(1).strip() if local_match else None
    budget_match = re.search(r'(?:€\s*\d[\d.,]*(?:\s*[-–/]\s*€?\s*\d[\d.,]*)?|\d[\d.,]*\s*(?:€|euro|EUR))(?:\s*(?:al giorno|/giorno|/ora|per hour|per day|mensili))?', scope, re.I)
    budget = budget_match.group(0) if budget_match else None
    salary = job.get('baseSalary')
    if not budget and salary:
        budget = json.dumps(salary, ensure_ascii=False)[:500]
    agency = bool(re.search(r'\b(?:agenzia|agency|studio di comunicazione|software house|network)\b', text[:2000], re.I))
    category = 'B' if external and agency else 'C' if external else 'A'
    ongoing = bool(re.search(r'continuativ|long.term|ongoing|medio.lungo', scope, re.I))
    contact = bool(re.search(r'candidat|apply|invia.*(?:cv|portfolio)|scrivici|@[\w.-]+', scope, re.I))
    points = {'Competenze compatibili': min(20, 8 + 4 * len(tech)), 'Richiesta esplicita': 20,
              'Recenza documentata': 20 if age is not None and age <= 30 else 10 if age is not None and age <= 90 else 0,
              'Freelance esplicito': 15 if external else 8, 'Italia / remoto': 10 if italy else 5,
              'Budget dichiarato': 5 if budget else 0, 'Continuità dichiarata': 5 if ongoing else 0,
              'Indicazioni candidatura': 5 if contact else 0}
    score = sum(points.values())
    limitations = ['Classificazione e punteggio sono euristiche; disponibilità effettiva da confermare al committente.']
    if age is None:
        score = min(score, 59)
        limitations.append('Data di pubblicazione assente: non conteggiata tra le opportunità recenti.')
    elif age > 90:
        score = min(score, 45)
        limitations.append('Annuncio più vecchio di 90 giorni.')
    elif age > 30:
        score = min(score, 69)
        limitations.append('Annuncio più vecchio di 30 giorni.')
    if not company:
        limitations.append('Nome del committente non estratto con certezza: consultare la fonte.')
    if remote and re.search(r'ibrid|hybrid|in sede|on.site', scope, re.I):
        limitations.append('Sono menzionate anche presenze in sede: verificare la compatibilità con Padova.')
    if re.search(r'\b(?:\d+ anni|\d+ years|senior|php|mysql|java\b|spring|shopify|angular)\b', scope, re.I):
        limitations.append('La richiesta contiene seniority o competenze aggiuntive: non sono attribuite al tuo profilo.')
    # Use the actual demand as title on broad careers pages, rather than invent a role.
    if not ROLE.search(title):
        title = evidence[:160]
    return dict(title=title, company=company, description=scope[:4500], source=urlsplit(url).hostname,
                url=canonical(url), published=published.isoformat() if published else None, date_source=date_source,
                location=location, mode='Remoto menzionato' if remote else 'Non dichiarata', budget=budget,
                technologies=tech, category=category, project_type=' / '.join(t for t in tech if t in ('WordPress', 'WooCommerce', 'React', 'Next.js', 'Siti / e-commerce / landing page')) or 'Frontend / web design',
                score=score, score_details=points, limitations=limitations, evidence=evidence,
                verified_at=now(), verification='Pagina originale letta', ongoing=ongoing,
                sources=[canonical(url)]), None


def fingerprint(item):
    # Exact long demand is conservative across sources; generic short headlines never merge.
    normalized = ' '.join(re.findall(r'\w+', item['evidence'].lower()))
    employer = ' '.join(re.findall(r'\w+', (item.get('company') or '').lower()))
    return hashlib.sha256((employer + '|' + normalized).encode()).hexdigest() if employer and len(normalized) >= 100 else None


def draft(item):
    return (f"Buongiorno,\n\nho letto la vostra richiesta su {item['url']} relativa a «{item['title']}».\n\n"
            f"Sono Diego Pavanello, freelance di Padova. Mi occupo di {', '.join(item['technologies'])}. "
            "Mi piacerebbe approfondire il progetto e capire se posso esservi utile.\n\n"
            "Possiamo confrontarci su obiettivi, tempi e modalità della collaborazione?\n\n"
            "Diego Pavanello\nhttps://designerdimontagna.it")


class OpportunityService:
    def __init__(self, db, search, fetch):
        self.db, self.search, self.fetch = db, search, fetch
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.job = {'running': False, 'message': 'Pronto per la ricerca sperimentale.'}
        self.robots = {}
        self.last_fetch = {}

    def init(self):
        with self.db() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, fingerprint TEXT,
                    payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', notes TEXT NOT NULL DEFAULT '',
                    draft TEXT NOT NULL DEFAULT '', first_seen TEXT NOT NULL, last_seen TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS opportunities_fingerprint ON opportunities(fingerprint);
                CREATE TABLE IF NOT EXISTS opportunity_urls (url TEXT PRIMARY KEY, opportunity_id INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS opportunity_runs (
                    id INTEGER PRIMARY KEY, started TEXT NOT NULL, finished TEXT, status TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS opportunity_config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')
            c.execute("UPDATE opportunity_runs SET status='interrupted',finished=? WHERE status='running'", (now(),))

    def config(self):
        with self.db() as c:
            values = {r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM opportunity_config')}
        return {'queries': DEFAULT_QUERIES, 'batch_size': 6, 'provider': 'tavily', 'time_range': 'month', **values}

    def configure(self, values):
        queries = values.get('queries')
        if not isinstance(queries, list) or not 1 <= len(queries) <= 60 or any(not isinstance(q, str) or not 5 <= len(q.strip()) <= 350 for q in queries):
            raise ValueError('Inserisci da 1 a 60 query, da 5 a 350 caratteri ciascuna.')
        batch = values.get('batch_size', 6)
        if type(batch) is not int or not 1 <= batch <= 12:
            raise ValueError('Ogni avvio può eseguire da 1 a 12 query.')
        provider = values.get('provider', 'tavily')
        if provider not in ('tavily', 'searxng'):
            raise ValueError('Motore non valido')
        time_range = values.get('time_range', 'month')
        if time_range not in ('', 'month', 'week'):
            raise ValueError('Periodo di ricerca non valido')
        with self.db() as c:
            for key, value in {'queries': [q.strip() for q in queries], 'batch_size': batch, 'provider': provider, 'time_range': time_range}.items():
                c.execute('INSERT OR REPLACE INTO opportunity_config VALUES (?,?)', (key, json.dumps(value)))

    def state(self):
        with self.db() as c:
            items = [{**json.loads(r['payload']), **{k: r[k] for k in ('id', 'status', 'notes', 'draft', 'first_seen', 'last_seen')}} for r in c.execute('SELECT * FROM opportunities ORDER BY id DESC')]
            runs = [{**dict(r), 'summary': json.loads(r['summary'])} for r in c.execute('SELECT * FROM opportunity_runs ORDER BY id DESC LIMIT 20')]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        today = datetime.now(timezone.utc).date()
        for item in items:
            pub = date_value(item.get('published'))
            age = (today - pub).days if pub else None
            cap = 59 if age is None else 35 if age > 180 else 45 if age > 90 else 69 if age > 30 else 100
            item['score'] = min(item['score'], cap)
            if age is not None and age > 30:
                item['limitations'].append('Recenza aggiornata oggi: pubblicato ' + str(age) + ' giorni fa.')
        recent = sum(not i.get('selection_error') and i['status'] != 'discarded' and i['first_seen'] >= cutoff and i.get('published') is not None and 0 <= (today - date_value(i['published'])).days <= 30 for i in items)
        with self.lock:
            job = dict(self.job)
        return {'items': items, 'runs': runs, 'job': job, 'config': self.config(), 'weekly_recent': recent}

    def save(self, item):
        stamp = now()
        fp = fingerprint(item)
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            existing = c.execute('SELECT * FROM opportunities WHERE url=? OR id IN (SELECT opportunity_id FROM opportunity_urls WHERE url=?) OR (fingerprint=? AND fingerprint IS NOT NULL) ORDER BY id LIMIT 1', (item['url'], item['url'], fp)).fetchone()
            if existing:
                previous = json.loads(existing['payload'])
                item['sources'] = sorted(set(previous.get('sources', []) + item['sources']))
                # Keep strongest documented date / original URL when an undated syndicated copy arrives.
                if previous.get('published') and not item.get('published'):
                    item = {**previous, 'sources': item['sources']}
                c.execute('UPDATE opportunities SET payload=?,last_seen=? WHERE id=?', (json.dumps(item), stamp, existing['id']))
                for alias in item['sources']:
                    c.execute('INSERT OR IGNORE INTO opportunity_urls VALUES (?,?)', (alias, existing['id']))
                return False
            ident = c.execute('INSERT INTO opportunities(url,fingerprint,payload,first_seen,last_seen) VALUES (?,?,?,?,?)', (item['url'], fp, json.dumps(item), stamp, stamp)).lastrowid
            c.execute('INSERT OR IGNORE INTO opportunity_urls VALUES (?,?)', (item['url'], ident))
            return True

    def update(self, ident, body):
        with self.db() as c:
            row = c.execute('SELECT * FROM opportunities WHERE id=?', (ident,)).fetchone()
            if not row:
                raise ValueError('Opportunità non trovata')
            if json.loads(row['payload']).get('selection_error') and (body.get('generate_draft') or body.get('status') in ('new', 'saved')):
                raise ValueError('Questa pagina è stata esclusa perché non è un annuncio.')
            status = body.get('status', row['status'])
            notes = body.get('notes', row['notes'])
            if status not in ('new', 'saved', 'discarded', 'contacted') or not isinstance(notes, str) or len(notes) > 10000:
                raise ValueError('Stato o note non validi')
            message = draft(json.loads(row['payload'])) if body.get('generate_draft') else body.get('draft', row['draft'])
            if not isinstance(message, str) or len(message) > 18000:
                raise ValueError('Bozza non valida')
            c.execute('UPDATE opportunities SET status=?,notes=?,draft=? WHERE id=?', (status, notes, message, ident))
            return {'ok': True, 'draft': message}

    def check_stop(self):
        if self.stop.is_set():
            raise InterruptedError('Ricerca interrotta: risultati già trovati conservati.')

    def policy(self, url):
        self.check_stop()
        canonical(url)
        if blocked(url):
            raise ValueError('Fonte esclusa: accesso automatizzato non abilitato')
        p = urlsplit(url)
        origin = urlunsplit((p.scheme, p.netloc, '', '', ''))
        if origin not in self.robots:
            status, content, _ = self.fetch(origin + '/robots.txt', robots=True)
            if status in (404, 410):
                content = ''
            elif status != 200:
                raise ValueError('robots.txt non verificabile')
            parser = RobotFileParser()
            parser.parse(content.splitlines())
            self.robots[origin] = parser
        rules = self.robots[origin]
        if not rules.can_fetch('CustomerSearch', url):
            raise ValueError('Accesso escluso da robots.txt')
        delay = max(1, rules.crawl_delay('CustomerSearch') or 0)
        rate = rules.request_rate('CustomerSearch')
        if rate:
            delay = max(delay, rate.seconds / max(1, rate.requests))
        remaining = delay - (time.monotonic() - self.last_fetch.get(origin, 0))
        if remaining > 0 and self.stop.wait(remaining):
            self.check_stop()
        self.last_fetch[origin] = time.monotonic()

    def start(self):
        with self.lock:
            if self.job['running']:
                raise ValueError('La ricerca opportunità è già in corso')
            self.stop.clear()
            self.job = {'running': True, 'checked': 0, 'added': 0, 'duplicates': 0, 'queries': 0, 'message': 'Avvio ricerca…'}
        threading.Thread(target=self.run, daemon=True, name='opportunities').start()

    def run(self):
        config = self.config()
        stats = {'queries': [], 'checked': 0, 'added': 0, 'duplicates': 0, 'rejected': {}, 'rejected_details': [], 'errors': []}
        rejected = Counter()
        run_id = None
        status = 'completed'
        self.robots, self.last_fetch = {}, {}
        try:
            with self.db() as c:
                run_id = c.execute("INSERT INTO opportunity_runs(started,status) VALUES (?,'running')", (now(),)).lastrowid
                count = c.execute('SELECT count(*) FROM opportunity_runs').fetchone()[0] - 1
            queries = config['queries']
            offset = (count * config['batch_size']) % len(queries)
            chosen = [queries[(offset + n) % len(queries)] for n in range(min(config['batch_size'], len(queries)))]
            seen = set()
            for query in chosen:
                self.check_stop()
                with self.lock:
                    self.job['message'] = 'Ricerca: ' + query
                results = self.search(query, config['provider'], config['time_range'])
                stats['queries'].append({'query': query, 'returned': len(results)})
                with self.lock:
                    self.job['queries'] = len(stats['queries'])
                for result in results:
                    self.check_stop()
                    try:
                        url = canonical(result.get('url', ''))
                        if url in seen:
                            continue
                        seen.add(url)
                        if blocked(url):
                            rejected['Fonte non abilitata'] += 1
                            stats['rejected_details'].append({'url':url,'reason':'Fonte non abilitata'})
                            continue
                        with self.lock:
                            self.job['message'] = 'Verifica richiesta: ' + urlsplit(url).hostname
                        code, html, final = self.fetch(url, policy=self.policy)
                        stats['checked'] += 1
                        if code != 200:
                            rejected['Pagina non accessibile (HTTP ' + str(code) + ')'] += 1
                            stats['rejected_details'].append({'url':url,'reason':'HTTP ' + str(code)})
                            continue
                        item, reason = analyze(html, final)
                        if item:
                            if self.save(item):
                                stats['added'] += 1
                            else:
                                stats['duplicates'] += 1
                        else:
                            rejected[reason] += 1
                            stats['rejected_details'].append({'url':url,'reason':reason})
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        rejected['Verifica non completata'] += 1
                        stats['errors'].append({'url': result.get('url', ''), 'reason': str(exc)[:240]})
                    finally:
                        with self.lock:
                            self.job.update({k: stats[k] for k in ('checked', 'added', 'duplicates')}, queries=len(stats['queries']))
            if stats['errors']:
                status = 'partial'
        except InterruptedError:
            status = 'stopped'
        except Exception as exc:
            status = 'error'
            stats['errors'].append({'reason': str(exc)[:240]})
        finally:
            stats['rejected'] = dict(rejected)
            message = f"{stats['added']} nuove opportunità · {stats['duplicates']} già presenti · {stats['checked']} pagine controllate."
            if status == 'error':
                message += ' Ricerca non completata: ' + stats['errors'][-1]['reason']
            elif status == 'stopped':
                message += ' Ricerca fermata.'
            elif not stats['added']:
                message += ' Nessuna nuova richiesta verificata: consulta gli scarti e prova altre query.'
            if stats['errors']:
                message += ' Alcune fonti non sono state verificabili: dettagli nello storico.'
            if run_id:
                with self.db() as c:
                    c.execute('UPDATE opportunity_runs SET finished=?,status=?,summary=? WHERE id=?', (now(), status, json.dumps(stats), run_id))
            with self.lock:
                self.job.update(running=False, message=message)
