import os
from pathlib import Path
from .prospecting import DIRECT_QUERIES
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
for line in (ROOT/'.env').read_text().splitlines() if (ROOT/'.env').exists() else []:
    if line.strip() and not line.lstrip().startswith('#') and '=' in line:
        key,value=line.split('=',1)
        os.environ.setdefault(key.strip(),value.strip().strip('\"\''))
PORT=int(os.getenv('PORT','8765'))
ORIGIN=f'http://127.0.0.1:{PORT}'
ENGINES={
 'A':{'name':'Domanda esplicita','subtitle':'Richieste concrete di siti ed e-commerce, anche da clienti diretti','color':'blue'},
 'B':{'name':'Agenzie & partner','subtitle':'Collaborazioni e capacità esterna','color':'purple'},
 'C':{'name':'Aziende in crescita','subtitle':'Crescita accompagnata da un progetto web dichiarato','color':'green'},
 'D':{'name':'Esperienza digitale','subtitle':'Nuovi siti di attività locali con problemi misurati','color':'amber'},
 'E':{'name':'Segnali combinati','subtitle':'Informazioni collegate alla stessa azienda','color':'pink'},
}
STAGES={'review':'Da valutare','ready':'Da contattare','contacted':'Contattato','replied':'Risposta ricevuta','proposal':'Preventivo','won':'Cliente acquisito','lost':'Perso','discarded':'Scartato'}
QUERIES={
 'A':['"cerchiamo" "sviluppatore" "freelance" WordPress','"cerco" "realizzazione" "sito" "budget"','looking for freelance React Next.js project remote Europe','richiesta sviluppo landing page freelance Italia'],
 'B':['"agenzia" "collaborazioni" "freelance" "sviluppatore"','"cerchiamo" "WordPress" "partita iva"','agenzia branding nuovi servizi digitali partnership sviluppo','web agency cerca fornitori frontend freelance'],
 'C':['"nuovo laboratorio" artigianale Veneto Toscana', '"nuova sede" "studio" Padova Verona', '"negozio indipendente" apertura Lombardia Piemonte', '"nuovo showroom" "srl" Veneto Toscana'],
 'D':['produzione arredamento azienda Veneto contatti','produttore alimentare Toscana Piemonte sito ufficiale'],
}
QUERIES.update(DIRECT_QUERIES)
DEFAULTS={'preferred_locations':['Veneto','Lombardia','Piemonte','Toscana','Padova','Vicenza','Treviso','Verona','Milano','Brescia','Bergamo','Torino','Firenze'],'excluded_locations':['Marche','Umbria','Campania','Abruzzo','Molise','Puglia','Basilicata','Calabria','Sicilia','Sardegna','Napoli','Salerno','Caserta','Avellino','Benevento','Ancona','Pesaro','Urbino','Macerata','Fermo','Ascoli Piceno','Perugia','Terni'],'provider':'searxng','queries_per_engine':2,'results_per_query':10,'daily_api_limit':None,'monthly_api_limit':None,'time_range':'','cache_hours':24,'minimum_sample':10,'minimum_budget':1000,'rss_feeds':[],'queries':QUERIES,'ollama_model':'','portfolio':'https://designerdimontagna.it/','name':'Diego Pavanello','location':'Padova','technical_limit':3,'min_priority':45}
BLOCKED=('prontopro.it','prontopro.com','link2me.it','freelance360.it','codegrind.it','nicepage.com','quora.com','youtube.com','jobeka.com','nettowork.it','randstad.it','adeccogroup.com','gigroup.it','fashionjobs.com','sortlist.it','sortlist.com','clutch.co','goodfirms.co','designrush.com','agenziecomunicazione.it','github.com','linkedin.com','indeed.com','indeed.it','upwork.com','freelancer.com','addlance.com','facebook.com','instagram.com','x.com','twitter.com','pinterest.com','reddit.com','talent.com','glassdoor.com','glassdoor.it','jobsora.com','jobsavior.com','jooble.org','jobleads.com','simplyhired.it','ziprecruiter.com','workingnomads.com','trabajo.org','jobijoba.it','crebs.it','lavoricreativi.com','remoterocketship.com','workana.com','fiverr.com','play.google.com','apps.apple.com','malt.com','malt.it','peopleperhour.com')
