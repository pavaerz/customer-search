"""Targeted search phrases and evidence-based business-type checks."""
import re

DIRECT_QUERIES = {
 'A': [
  '"cerchiamo" "realizzare" "sito web" Veneto -lavoro -developer -agenzia',
  '"cerco" "sito ecommerce" negozio Lombardia -lavoro -developer',
  '"cerchiamo" "fornitore" "sito web" Piemonte',
  '"rifare il sito" attività Toscana -agenzia -webagency',
  '"richiesta preventivo" "sito web" azienda Veneto',
  '"realizzazione sito" "negozio" "cerco" Lombardia',
 ],
 'C': [
  '"nuova attività" "realizzare" "sito web" Veneto',
  '"negozio" "vogliamo" "vendita online" Lombardia',
  '"artigianale" "progetto" "ecommerce" Piemonte',
  '"nuovo marchio" "cerchiamo" "ecommerce" Toscana',
 ],
 'D': [
  'falegnameria arredamento su misura Padova contatti sito ufficiale',
  'produttore artigianale alimentare Vicenza vendita prodotti',
  'negozio ceramiche Brescia contatti sito ufficiale',
  'laboratorio artigianale Bergamo prodotti contatti',
  'azienda lavorazioni meccaniche Torino contatti',
  'produttore tessile Biella contatti sito ufficiale',
  'studio professionale Firenze servizi contatti',
  'agriturismo Siena prenotazioni sito ufficiale',
 ],
}

_AGENCY = re.compile(r'\b(?:web agency|digital agency|agenzia (?:web|digital\w*|di comunicazione|di marketing|creativ\w*|pubblicitari\w*)|software house|studio (?:di )?(?:comunicazione|branding|grafico))\b',re.I)
_CREDIT = re.compile(r'website by|powered by|realizzato da|sviluppato da|credits|sito (?:web )?a cura di',re.I)

def agency_identity(parsed):
    """Only own presentation, not a supplier credited in a retailer's footer."""
    heading=' '.join([parsed.get('name') or '',parsed.get('title') or ''])
    if _AGENCY.search(heading):return True
    for line in parsed.get('text','')[:5000].splitlines():
        if _CREDIT.search(line):continue
        if _AGENCY.search(line) and re.search(r'\b(?:siamo|la nostra|we are|our agency)\b',line,re.I):return True
    return False

def direct_project_request(text):
    asking=re.search(r'\b(?:cerchiamo|cerco|cercasi|ricerchiamo|stiamo cercando|abbiamo bisogno|siamo alla ricerca di)\b',text,re.I)
    if not asking or re.search(r'\bnon (?:cerchiamo|cerco|abbiamo bisogno)\b',text,re.I):return False
    scope=text[asking.end():asking.end()+220]
    asset=re.search(r'\b(?:sito (?:web|internet|aziendale)|e-?commerce|shop online|portale|landing page|wordpress|woocommerce)\b',scope,re.I)
    work=re.search(r'\b(?:realizz\w*|rifar\w*|rinnov\w*|svilupp\w*|crea\w*|fornitor\w*|professionista|preventivo|partner)\b',scope,re.I)
    return bool(asset and work and not re.search(r'come trovare|se stai cercando|cerchiamo di|tempo indeterminato|organico interno|assunzione',text,re.I))
