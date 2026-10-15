"""Read the official measure and its requirements/FAQ/regulation links safely."""
import re
from urllib.parse import urljoin,urlsplit
from .db import digest
from .providers import canonical,blocked
from .research_analysis import ResearchWeb
from .extract import parse_page

LEGAL_DOMAINS=('gazzettaufficiale.it','eur-lex.europa.eu','mimit.gov.it')

def official_document(url):
 from .grants import official
 from .db import domain
 try:canonical(url)
 except (TypeError,ValueError):return False
 host=domain(url)
 return official(url) or any(host==d or host.endswith('.'+d) for d in LEGAL_DOMAINS)

class GrantWeb(ResearchWeb):
 allow_pdf=True

DETAIL=re.compile(r'requisit|beneficiar|a chi si rivolge|destinatar|normativa|regolamento|testo (?:del |integrale)|bando integrale|allegat|spese ammissibili|settori ammessi|faq|prorog|rettific|decreto|circolare|disciplinare|disposizion',re.I)

def document(page):
 if 'plain_text' in page:text=page['plain_text'];title='Documento ufficiale'
 else:
  d=parse_page(page);text=d['text'];title=next((h['text'] for h in d['doc'].headings if h['tag']=='h1'),d['title'])
  # Ignore cross-promotion, footer and unrelated news on the portal.
  text=re.split(r'\n(?:Notizie in evidenza|Le nostre storie|Servizi a supporto|Termini più cercati)\n',text)[0]
 return {'id':digest(page['url']+'|'+text),'url':page['url'],'title':title,'text':text,'checked_at':page['checked_at'],'content_hash':digest(text)}

def collect(web,page,check=lambda:None,max_documents=12):
 from .grants import official
 docs=[document(page)];seen={canonical(page['url'])};queue=[];limitations=[];root=page['url']
 def enqueue(p,depth):
  if 'plain_text' in p:return
  for link in parse_page(p)['doc'].links:
   if not DETAIL.search(link['text']):continue
   try:u=canonical(urljoin(p['url'],link['url']))
   except ValueError:continue
   if u in seen:continue
   if blocked(u):limitations.append('Documento con accesso automatico non consentito: '+u);continue
   seen.add(u)
   if not official_document(u):limitations.append('Allegato su dominio non abilitato: '+u);continue
   # Only links under the measure directory, PDF attachments, or original
   # portal's detail links. Never follow other named incentive directories.
   path=urlsplit(u).path
   if 'invitalia.it' in u and '/incentivi-e-strumenti/' in path:
    # ON uses both ON-nuove-imprese-tasso-zero and nuove-imprese-tasso-zero.
    slug=urlsplit(root).path.strip('/').split('/')[-1].lower().removeprefix('on-')
    if slug not in path.lower():continue
   if depth>=2:limitations.append('Ulteriore documento ufficiale da acquisire: '+u);continue
   queue.append((u,depth+1))
 enqueue(page,0)
 while queue:
  check()
  if len(docs)>=max_documents:
   limitations.append('Documentazione estesa: ulteriori allegati non ancora analizzati.');break
  url,depth=queue.pop(0)
  try:
   p=web.get(url,refresh=True);check()
   if p['status']!=200 or not official_document(p['url']):raise ValueError('Documento ufficiale non disponibile')
   d=document(p)
   if not d['text'].strip():raise ValueError('Documento privo di testo estraibile')
   docs.append(d);enqueue(p,depth)
  except InterruptedError:raise
  except Exception as exc:limitations.append('Lettura non completata: '+url+' · '+str(exc)[:150])
 return docs,list(dict.fromkeys(limitations))
