"""Discovery hypotheses, never qualification rules. Stable keys retain 4.0 attribution."""
import re
STRATEGIES={
 'companies':'Aziende da investigare',
 'explicit':'Richieste di progetti', 'startup':'Startup e nuove iniziative',
 'investment':'Investimenti e beneficiari', 'local':'Nuove attività locali',
 'change':'Cambiamenti aziendali', 'gap':'Opportunità digitali',
 'hiring':'Assunzioni strategiche', 'process':'Processi digitalizzabili',
 'partner':'Partner complementari', 'tender':'Gare compatibili',
 'correlation':'Correlazione delle prove', 'sources':'Nuove fonti pubbliche'}
TEMPLATES={
 'companies':['{sector} {area} azienda contatti'],
 'explicit':['site:linkedin.com/posts/ "cerchiamo" "freelance" (WordPress OR frontend OR "web designer") {area}', '"rifacimento sito" "fornitore" {area}', 'site:linkedin.com/jobs/view/ "partita iva" (WordPress OR frontend OR "web developer") {area}', '"cerchiamo" "freelance" "sito web" {area}', '"richiesta di offerta" "e-commerce" {area}'],
 'startup':['startup "lancia" {area} {sector}', '"nuova impresa" {area} {sector}', '"incubatore" "nuovo progetto" {area}'],
 'investment':['"beneficiari" "digitalizzazione" {area}', '{sector} "investimento" "vendita online" {area}', '"finanziamento" "nuova piattaforma" {area}'],
 'local':['"nuova apertura" {area} {sector}', '"inaugurazione" "prenotazioni" {area}', '"nuova attività" {area} {sector}'],
 'change':['azienda {sector} {area} nuova linea prodotti', 'azienda {sector} {area} espansione mercati esteri', '{sector} "nuovo marchio" {area}'],
 'gap':['{sector} {area} "distributori" "catalogo"', '{sector} {area} "nuovi servizi"', '{sector} {area} "mercati esteri"'],
 'hiring':['"responsabile e-commerce" {area}', '"marketing manager" "espansione" {area}', '"digital manager" {area} {sector}'],
 'process':['{sector} {area} "ordini" "Excel" -software -gestionale', '{sector} {area} "su misura" "richiesta preventivo"', '{sector} {area} "rivenditori" "modulo ordine"'],
 'partner':['"WordPress" "freelance" "lavora con noi"', '"frontend" "freelance" "lavora con noi"', 'agenzia {area} "cerchiamo" "freelance" WordPress', '"studio grafico" "cerchiamo" "sviluppatore" {area}', '"agenzia" "commessa" "partner tecnico" {area}', 'site:linkedin.com/posts/ agenzia "cerchiamo" "freelance" {area}'],
 'tender':['"manifestazione di interesse" "sito web" {area}', '"avviso" "realizzazione portale" {area}', '"affidamento" "e-commerce" {area}'],
 'sources':['"notizie imprese" {area} {sector}', '"startup" "notizie" {area}', '"comunicati imprese" {area}'],
}
SECTORS=('produzione alimentare','servizi professionali','turismo','meccanica','commercio','arredamento','artigianato','formazione')
PATTERNS={
 'explicit':r'cerchiamo|cerco|richiesta.{0,12}(?:offerta|preventivo)|ricerca.{0,20}fornitore',
 'startup':r'start.?up|nuov[ae] impres[ae]|premio cambiamenti|imprese innovative|incubator|nuovo progetto imprenditoriale',
 'investment':r'investiment|finanziament|beneficiar|agevolazion',
 'local':r'nuova apertura|inaugura|nuova attività|apre.{0,30}(?:negozio|studio|laboratorio)',
 'change':r'nuova linea|nuov[oa] (?:marchio|brand|divisione)|espansion|internazional|nuov[oa].{0,20}(?:sede|showroom|servizio|prodotto)|acquisizion',
 'gap':r'export|distributor|mercati esteri|nuovi servizi|vendita online|catalogo',
 'hiring':r'responsabile.{0,15}(?:e.?commerce|marketing|digital)|marketing manager|digital manager',
 'process':r'configura|multilistino|ordini.{0,60}(?:email|excel)|prenotazion|area riservata|portale b2b',
 'partner':r'partner tecnico|collaborazion|white.?label|outsourc|studio grafico|consulenza marketing',
 'tender':r'\b(?:manifestazione.{0,8}interesse|band[oi]|gar[ae]|affidament[oi]|avviso pubblico)\b',
}
SIGNAL=re.compile('|'.join('(?:'+v+')' for v in PATTERNS.values()),re.I)
DIGITAL=re.compile(r'sito web|sito aziendale|e.?commerce|portale|piattaforma|gestionale|web app|sviluppatore|sviluppo web',re.I)
NOISE=re.compile(r'/(?:tag|category|categoria|author|autore|comments|privacy|cookie|login|wp-json|mappa-del-sito|sitemap)(?:/|$)|(?:tag|category|author|location|page)-sitemap|comments/feed|[?&](?:filtered|print|replytocom)=|/unioni_e_raggruppamenti/',re.I)
def strategies_for(text):return [key for key,pattern in PATTERNS.items() if re.search(pattern,text,re.I)]
