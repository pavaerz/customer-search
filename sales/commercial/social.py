"""Indexed social leads and bounded public Instagram text, without sessions.

LinkedIn remains original-source resolution only. Images are not interpreted.
"""
import re
from urllib.parse import urlsplit,urljoin
from sales.providers import blocked
from sales.research_analysis import CompanyWeb
from sales.extract import parse_page
from sales.db import domain,now
from sales.content_policy import require_non_pdf
from .evaluation import base
from .inspection import document
from .attribution import identity,geographic_conflicts
from .geography import locate
from .qualification import evaluate
from .resources import BudgetExceeded

class PublicSocialWeb(CompanyWeb):
    def is_blocked(self,url):
        p=urlsplit(url);host=p.hostname or ''
        if host=='instagram.com' or host.endswith('.instagram.com'):
            return bool(re.search(r'/accounts/|/challenge/|/checkpoint/|/login|/oauth',p.path,re.I))
        return blocked(url)

def inspect_social(store,payload,check=lambda:None):
    url=payload['url'];require_non_pdf(payload);source=payload.get('social','instagram')
    ident={'name':payload.get('subject') or domain(url),'website':url,'identity_status':'unknown','contacts':[],'source_url':url}
    geo=locate([],ident);page={'url':url,'html':'','status':0,'checked_at':now()}
    r=base(payload['commercial_engine'],ident,page,geo)
    r.update(state='UNVERIFIABLE',classification='social_incomplete',source_kind=payload.get('source_kind'),
             reason='Indizio indicizzato: contenuto originale, autore e attualità da verificare.',
             verification={'status':'incomplete','scope':'social'},social={'source':source,'post_url':url,'accessibility':'indexed_only','author':None})
    def result(docs=None):
        found={'identity':ident,'documents':docs or [],'result':r,'followups':[]}
        if r['state']=='UNVERIFIABLE' and r.get('social',{}).get('accessibility')!='public_text':
            return resolve_official(store,payload,found,check)
        return found
    if source=='linkedin':
        from .indexed_jobs import parse_indexed_job
        r['social']['indexed_job']=parse_indexed_job(payload)
        r['reason']='Annuncio/post LinkedIn indicizzato; verifica tramite fonte ufficiale o revisione manuale. Nessun accesso autenticato.'
        return result()
    web=PublicSocialWeb(store,check)
    try:page=web.get(url);check();require_non_pdf(page)
    except (InterruptedError,BudgetExceeded):raise
    except Exception as exc:
        from sales.content_policy import ExcludedPDF
        if isinstance(exc,ExcludedPDF):raise
        from sales.operation_outcomes import safe_error
        r['limits']=[safe_error(exc)];r['social']['accessibility']='unavailable';return result()
    pp=parse_page(page);text=pp['text']
    if page['status']!=200 or re.search(r'login|accounts',urlsplit(page['url']).path,re.I) or (re.search(r'log in|accedi|sign up',text,re.I) and len(text)<600):
        r['social']['accessibility']='unavailable';r['reason']='Post non leggibile pubblicamente; nessuna conclusione sulla pertinenza.';return result()
    r['social']['accessibility']='public_text'
    if not re.search(r'cerchiamo|ricerchiamo|selezion|freelance|partita IVA|looking for',text,re.I) and ('<img' in page['html'].lower() or pp['doc'].meta.get('og:image')):
        r['classification']='requires_multimodal';r['reason']='Il testo disponibile non basta: possibile richiesta nell’immagine, da verificare nella fase multimodale.'
        return result([document(page)])
    page={**page,'public_social':True}
    # Only a linked official domain with a reciprocal social link can establish
    # the publisher. An indexed username alone never verifies a company.
    for link in pp['doc'].links[:3]:
        target=urljoin(url,link['url'])
        if not target.startswith(('https://','http://')) or domain(target)==domain(url) or blocked(target):continue
        require_non_pdf(target)
        try:official=CompanyWeb(store,check).get(target);check()
        except (InterruptedError,BudgetExceeded):raise
        except Exception:continue
        company=identity([official]);op=parse_page(official)
        reciprocal=any(urljoin(target,l['url']).rstrip('/')==url.rstrip('/') for l in op['doc'].links)
        # Exact post backlink avoids claiming a similarly named social author.
        if official['status']==200 and company['identity_status']=='verified' and reciprocal:
            ident=company;r['social']['linked_company']=company['name'];geo=geographic_conflicts(locate([official],ident,text),[],payload.get('allowed_regions'))
            docs=[document(page),document(official,official=True)];break
    else:docs=[document(page)]
    qualified=evaluate(payload['commercial_engine'],ident,page,geo)
    qualified['social']=r['social'];qualified['source_kind']=payload.get('source_kind')
    # No text-level demand is a conclusion about the available text, not images.
    if not qualified.get('request_blocks') and qualified['state']=='REJECTED':
        qualified['reason']='Nessuna richiesta tecnica nel testo pubblico consultato.'
        if '<img' in page['html'].lower() or pp['doc'].meta.get('og:image'):
            qualified.update(state='UNVERIFIABLE',classification='requires_multimodal',reason='Testo insufficiente: verificare separatamente le immagini.',verification={'status':'incomplete','scope':'multimodal'})
    r=qualified
    return result(docs)


def official_hints(payload):
    """Explicit domains in the result title are leads, never identity evidence.

    Snippets can merge subjects; do not extract domains or names from them.
    """
    title=str(payload.get('title') or payload.get('discovery',{}).get('title') or '')
    domains=list(dict.fromkeys(re.findall(r'\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:it|com|eu|net|org)\b',title,re.I)))
    return ['https://'+d.lower()+'/' for d in domains if not blocked('https://'+d) and domain('https://'+d) not in ('instagram.com','linkedin.com','facebook.com')][:2]


def resolve_official(store,payload,partial,check):
    """Bounded lawful alternative. Same-post backlink + verified company.

    Only documents actually read are evidence; no merged indexed snippets.
    Manual review remains available when the relationship cannot be proved.
    """
    from .context import followups,TECH
    from .evaluation import skills
    from sales.providers import canonical
    from sales.content_policy import skip_pdf
    r=partial['result'];social=r['social'];hints=official_hints(payload)
    social.update(official_candidates=hints,official_checks=[],subject_hint=domain(hints[0]) if len(hints)==1 else None,
                  identity_status='unknown',review_state='unavailable' if social['accessibility']=='unavailable' else 'interesting')
    if not hints:return partial
    # Ambiguous titles do not justify choosing a company automatically.
    if len(hints)!=1:
        social['official_checks'].append({'status':'ambiguous_identity','reason':'Più domini nel titolo: attribuzione da verificare.'});return partial
    web=CompanyWeb(store,check);docs=partial['documents'];read_limit=min(3,payload.get('max_reads',6));reads=0
    def read(url):
        nonlocal reads
        check();require_non_pdf(url)
        if reads>=read_limit:raise ValueError('Limite letture della verifica alternativa raggiunto')
        reads+=1;p=web.get(url);check();require_non_pdf(p)
        if p['status']!=200:raise ValueError('Fonte ufficiale candidata HTTP '+str(p['status']))
        return p
    def failure(url,exc):
        from sales.operation_outcomes import safe_error
        social['official_checks'].append({'url':url,'status':'unavailable','reason':safe_error(exc)})
    target=hints[0]
    try:home=read(target)
    except (InterruptedError,BudgetExceeded):raise
    except Exception as exc:failure(target,exc);return partial
    docs.append(document(home,official=False));company=identity([home]);hp=parse_page(home)
    def same_post(link):
        try:return canonical(urljoin(home['url'],link['url']))==canonical(payload['url'])
        except (ValueError,TypeError):return False
    reciprocal=any(same_post(l) for l in hp['doc'].links)
    if company.get('identity_status')!='verified' or not reciprocal:
        social['official_checks'].append({'url':home['url'],'status':'identity_unverified','reason':'Identità societaria e collegamento ufficiale al post non entrambi verificati.','checks':{'company_identity':company.get('identity_status')=='verified','exact_post_backlink':reciprocal},'document_id':docs[-1]['id']});return partial
    docs[-1]=document(home,official=True);social.update(identity_status='verified',linked_company=company['name'],review_state='identified')
    partial['identity']=company;r['company']=company['name'];r['website']=company['website'];r['contacts']=company.get('contacts',[])
    social['official_checks'].append({'url':home['url'],'status':'identity_verified','document_id':docs[-1]['id'],'reason':'Identità societaria verificata e link ufficiale allo stesso post.'})
    indexed_title=str(payload.get('title') or payload.get('discovery',{}).get('title') or '')
    expected=set(skills(indexed_title))
    pages=[home]
    links=[l['url'] for l in followups(home) if domain(l['url'])==domain(home['url']) and not skip_pdf(l['url'])]
    for link in list(dict.fromkeys(links))[:max(0,read_limit-reads)]:
        try:
            p=read(link)
            if domain(p['url'])!=domain(home['url']):
                docs.append(document(p,official=False))
                social['official_checks'].append({'url':p['url'],'status':'identity_unverified','reason':'Redirect a un dominio diverso: committente non attribuibile senza ulteriori prove.'})
                continue
            pages.append(p);docs.append(document(p,official=True))
        except (InterruptedError,BudgetExceeded):raise
        except Exception as exc:failure(link,exc)
    for p in pages:
        geo=geographic_conflicts(locate([home,p],company,parse_page(p)['text']),[],payload.get('allowed_regions'))
        candidate=evaluate(payload['commercial_engine'],company,p,geo)
        role_matches=bool(expected.intersection(candidate.get('skills',[]))) if expected else bool(TECH.search(indexed_title) and candidate.get('skills'))
        if not candidate.get('request_blocks') or not role_matches:continue
        # Current official request is independent evidence, not proof that the
        # original social post is still active or has the same publication date.
        social['official_checks'].append({'url':p['url'],'status':'request_found','reason':candidate['reason'],'state':candidate['state']})
        if candidate['classification']=='expired':social['review_state']='inactive'
        elif candidate['state']=='VERIFIED':social['review_state']='official_confirmed'
        candidate['social']=social;candidate['limits'].append('Prove riferite alla fonte ufficiale; data e stato del post social restano sconosciuti.')
        partial['result']=candidate;return partial
    r['geography']=geographic_conflicts(locate([home],company),[],payload.get('allowed_regions'))
    r['reason']='Azienda collegata al post; richiesta equivalente non confermata dalle pagine ufficiali consultate.'
    return partial
