"""Source-bound decisions; no model output, inferred date or invented compensation."""
import re
from datetime import date
from sales.extract import parse_page,SKILLS
from .catalog import VERSIONS
def base(engine,identity,page,geo):
    parsed=parse_page(page)
    from .job_activity import extract_page
    activity=extract_page(page) if engine!='WEBSITE_REBUILD' else []
    return {'engine':engine,'rule_version':VERSIONS[engine],'state':'NEEDS_REVIEW','classification':'ambiguous',
            'job_activity_evidence':activity,'title':parsed['title'],'company':identity.get('name'),'url':page['url'],'website':identity.get('website'),
            'published_at':parsed.get('published_at'),'checked_at':page['checked_at'],'skills':[],
            'contract':None,'compensation':{'type':'undisclosed','amount':None,'quote':None},'geography':geo,
            'contacts':identity.get('contacts',[]),'evidence':[],'reason':'Informazioni insufficienti.',
            'limits':[],'score':0,'score_detail':{},'priority':'review','project':None}

def finish(result,identity,parts):
    result['score_detail']={label:{'points':points,'reason':reason} for label,points,reason in parts}
    result['score']=sum(x[1] for x in parts)
    if result['state'] in ('VERIFIED','POTENTIAL'):
        if result['engine']!='WEBSITE_REBUILD':
            intent=result.get('commercial_intent') or {}
            checks=(result.get('verification') or {}).get('checks') or {}
            if (intent.get('commercial_role') not in ('BUYER','PARTNERSHIP_BUYER','FREELANCE_BUYER')
                    or not intent.get('buyer_evidence') or intent.get('contradictions')
                    or (result.get('verification') or {}).get('status')!='complete'
                    or not checks or not all(checks.values())):
                result['state']='NEEDS_REVIEW'
                result['limits'].append('Requisiti di prova commerciale non soddisfatti; il punteggio non sostituisce la verifica.')
            quote=' '.join(e['quote'] for e in result['evidence'])
            first_person=re.search(r'cerchiamo|cerco\b|ricerchiamo|selezioniamo|siamo alla ricerca|we are|looking for|accettiamo|valutiamo|siamo aperti|collaboriamo|nostr[oa]|entra nel nostro',quote,re.I)
            named=bool(identity.get('name') and identity['name'].casefold() in quote.casefold())
            careers=bool(re.search(r'/(?:jobs|careers|lavora-con-noi|collabora-con-noi|posizioni-aperte)(?:/|$)',result['url'],re.I))
            intermediary=re.search(r'per conto di|nostr[oi] client|un cliente cerca',quote,re.I)
            if intermediary or not(first_person or named or careers):
                result['state']='NEEDS_REVIEW';result['limits'].append('Attribuzione della richiesta al committente non sufficientemente verificata; possibile intermediario o citazione di terzi.')
        try:
            if result.get('published_at') and date.fromisoformat(result['published_at'][:10])>date.today():
                result['state']='NEEDS_REVIEW';result['limits'].append('Data di pubblicazione futura: attualità non verificata.')
        except ValueError:pass
        if identity.get('identity_status')!='verified':result['state']='NEEDS_REVIEW';result['limits'].append('Identità e dominio ufficiale da verificare.')
        if not result['geography']['eligible']:result['state']='REJECTED' if result['geography']['country']=='Estero' else 'NEEDS_REVIEW';result['limits'].append(result['geography']['reason'])
    result['priority']='high' if result['state']=='VERIFIED' and result['score']>=70 else 'secondary' if result['state']=='POTENTIAL' else 'review'
    return result

def skills(quote):
    return [name for name,pattern in {**SKILLS,'Backend':r'backend|back-end|node\.?js|python|php','Web app / MVP':r'web app|MVP|piattaforma|CTO|software'}.items() if re.search(pattern,quote,re.I)]

def compensation(quote):
    """Only an explicitly labelled fee in the same request; never funding or RAL."""
    match=re.search(r'\b(?:budget|compenso|corrispettivo)\s*(?:del progetto|di|:)?\s*(?:€\s*)?(\d{1,3}(?:\.\d{3})+|\d{3,7})(?:,00)?\s*(?:€|euro)\b',quote,re.I)
    return {'type':'cash' if match else 'undisclosed','amount':int(match[1].replace('.','')) if match else None,'currency':'EUR' if match else None,'quote':match[0] if match else None}
