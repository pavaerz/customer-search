"""Shared qualification of scoped evidence; engine-specific commercial policy."""
import re
from datetime import date
from sales.extract import parse_page
from sales.direct_channels import digital_supplier
from .context import position_sections, extract, expired, EXTERNAL, EMPLOYEE, ASK, channels
from .intent import classify_block, request_nature
from sales.db import digest
from .evaluation import base, finish, skills, compensation


def evaluate(engine, identity, page, geo):
    blocks=extract(page)
    empty=base(engine,identity,page,geo)
    empty['published_at']=None
    empty['position_sections']=position_sections(page)
    empty['request_blocks']=[{k:v for k,v in b.items() if k!='text'} for b in blocks]
    empty['verification']={'status':'complete' if blocks else 'incomplete','scope':'original_request' if blocks else 'extraction_only','extraction_complete':True,'identity_verified':identity.get('identity_status')=='verified','request_verified':False,'currently_open':False,'blocks_found':len(blocks)}
    if not blocks:
        empty.update(state='REJECTED',classification='no_collaboration' if engine=='AGENCIES' else 'no_request' if engine=='STARTUPS' else 'irrelevant',reason='Nessuna richiesta tecnica attribuibile in un blocco della fonte originale.')
        source=channels(page)['visible'];visible='\n'.join(u['text'] for u in source['units'] if not u['excluded']);intent=classify_block(visible,url=page['url'],title=empty['title'])
        empty['commercial_intent']=intent
        hints=[]
        for unit in source['units']:
            if unit['excluded']:continue
            # Preserve individual, addressable collaboration clauses, never the
            # whole guide as a current request or a startup identity.
            from .intent import clauses
            for clause in clauses(unit['text']):
                from .request_profile import collaboration_signal
                if request_nature(clause['quote'])!='GENERAL_COLLABORATION_POLICY' and not (engine=='AGENCIES' and collaboration_signal(clause['quote'])):continue
                start=unit['start']+clause['start'];end=unit['start']+clause['end']
                hints.append({'url':page['url'],'quote':source['text'][start:end],'channel':'visible','start':start,'end':end,'source_hash':digest(source['text']),'kind':'partner_policy','certainty':'fact','checked_at':page['checked_at'],'published_at':None})
        if hints:
            empty['partner_hint']={'kind':'GENERAL_COLLABORATION_POLICY','current_open_request':False,'route_to':'AGENCIES','evidence':hints,'identity_verified':identity.get('identity_status')=='verified'}
            empty['evidence'].extend(hints)
            empty.update(classification='general_collaboration_policy',reason='Pratica di collaborazione con esterni descritta; nessuna richiesta attuale dimostrata.')
            if engine=='AGENCIES':empty['state']='NEEDS_REVIEW'
        elif intent['commercial_role']=='EDITORIAL':empty.update(classification='editorial',reason='Guida informativa: nessuna richiesta tecnica attuale attribuibile.')
        if not hints and intent['commercial_role'] in ('SELLER','PARTNERSHIP_SELLER'):
            empty.update(classification='seller',reason=intent['reason'])
        for unit in source['units']:
            if unit['excluded']:continue
            if any(e['quote'] in unit['text'] for e in intent['seller_evidence']+intent['negations']):
                empty['evidence'].append({'url':page['url'],'quote':unit['text'],'channel':'visible','start':unit['start'],'end':unit['end'],
                    'source_hash':digest(source['text']),'kind':'commercial_direction','certainty':'fact','checked_at':page['checked_at'],'published_at':None})
        return empty
    agency=identity.get('group')=='agencies' or identity.get('organization',{}).get('category')=='digital_agency' or digital_supplier(parse_page(page))
    results=[]
    for block in blocks:
        r={**empty,'limits':[],'commercial_intent':block.get('commercial_intent'),'evidence':block['evidence'],'selected_block':block['id'],'dates':block['dates']}
        project_actor=block.get('actor_role')=='PROJECT'
        if project_actor:
            r.update(company=block['subject'],requesting_actor=block['subject'],actor_role='PROJECT',
                     actor_attribution={'publisher':identity.get('name'),'requesting_actor':block['subject'],'roles':['PROJECT','REQUESTING_ACTOR'],'basis':'bounded_project_heading','identity_verified':False,'block_id':block['id']})
        text=block['text'];published=block['dates']['published_at'];r['published_at']=published
        from .request_profile import relationship
        r['relationship']=relationship(text)
        age=(date.today()-date.fromisoformat(published)).days if published else None
        r['skills']=skills(text+' '+str(block['role'] or ''));r['compensation']=compensation(text)
        intent=block['commercial_intent']
        employee=intent.get('commercial_role')=='EMPLOYER' or any(c['code']=='conflicting_contracts' for c in intent.get('contradictions',[]))
        external=intent.get('relationship')=='external' or any(c['code']=='conflicting_contracts' for c in intent.get('contradictions',[]))
        invitation_text=text
        for negation in intent.get('negations',[]):invitation_text=invitation_text.replace(negation['quote'],'')
        invitation=bool(re.search(r'accettiamo|valutiamo|siamo aperti|collaborazioni continuative|entra nel nostro network|cerchiamo spesso|figure sempre ricercate|candidati come partner|diventa partner',invitation_text,re.I))
        # Past relationships alone are not an invitation to new collaborators.
        active=bool(ASK.search(text))
        closed=expired(block) or block['negative']
        old=age is not None and age>180
        if engine=='FREELANCE':
            if closed or (old and not (agency and invitation)):
                r.update(state='REJECTED',classification='expired',reason='Richiesta scaduta o annuncio datato non attuale; data della risorsa distinta.')
            elif employee and not external:
                r.update(state='REJECTED',classification='employee',contract='employment',reason='Posizione dipendente/tirocinio, non una collaborazione esterna.')
            elif external:
                r.update(state='VERIFIED' if age is not None and not employee else 'NEEDS_REVIEW',classification='external',contract='external',reason='Richiesta tecnica esterna riconosciuta nel blocco originale.')
                if agency and invitation:
                    r['route_to']='AGENCIES';r['reason']='Disponibilità freelance dell’agenzia: verifica nel canale partner.';r['state']='NEEDS_REVIEW'
            else:r.update(classification='ambiguous',reason='Richiesta tecnica riconosciuta; natura esterna del contratto da verificare.')
        elif engine=='AGENCIES':
            if not agency:r.update(state='REJECTED',classification='not_agency',reason='Identità di agenzia/software house non dimostrata.')
            elif closed or (employee and not external):r.update(state='REJECTED',classification='no_external_collaboration',reason='Collaborazione chiusa o ruolo dipendente.')
            elif external:
                r.update(state='VERIFIED' if not invitation and active and age is not None and 0<=age<=180 else 'NEEDS_REVIEW',classification='ongoing' if invitation else 'open_collaboration' if active else 'generic_availability',contract='external',reason='Disponibilità continuativa a collaborazioni tecniche esterne.' if invitation else 'Collaborazione esterna riconosciuta; verificare apertura e attualità.')
            else:r.update(classification='generic_availability',reason='Ruolo riconosciuto, modalità contrattuale non sufficientemente documentata.')
        else:
            startup=bool(re.search(r'start[ -]?up|founder|fondator|nuovo progetto imprenditoriale',text+' '+parse_page(page)['title'],re.I))
            founder=bool(re.search(r'(?:cerchiamo|cerco|cerca|ricerca|looking for)\s+(?:(?:un|una|un nuovo|tre|due|a)\s+)?(?:co[ -]?founder|cofondator|socio tecnic)',text,re.I))
            equity=bool(re.search(r'\bequity\b|quota equity|quote societarie|partecipazione societaria',text,re.I))
            cash=bool(re.search(r'retribuit|compenso (?:in denaro|economico)|\bcash\b|budget (?:di|del progetto)',text,re.I)) and not re.search(r'non retribuit|senza (?:compenso|cash|budget)|no cash',text,re.I)
            r['compensation']={**compensation(text),'type':'hybrid' if cash and equity else 'equity' if equity else 'cash' if cash else 'undisclosed','quote':next((e['quote'] for e in block['evidence'] if re.search(r'equity|retribuit|compenso|budget',e['quote'],re.I)),None)}
            if not startup:r.update(state='REJECTED',classification='not_startup',reason='Richiesta tecnica riconosciuta, identità startup non dimostrata.')
            elif closed or old or (employee and not external):r.update(state='REJECTED',classification='closed_or_employee',reason='Richiesta scaduta/non recente o dipendente.')
            else:
                clear=bool(founder or equity or cash or external or re.search(r'partner tecnico|collaborazion|fornitore|MVP',text,re.I))
                r.update(state='POTENTIAL' if founder or equity else 'VERIFIED' if clear and published else 'NEEDS_REVIEW',classification='cofounder' if founder else 'equity' if equity else 'paid_development' if cash else 'technical_collaboration' if clear else 'ambiguous',contract='founder' if founder else 'external' if clear else None,reason='Richiesta tecnica riconosciuta; equity distinta da commessa pagata.' if founder or equity else 'Richiesta tecnica originale, da valutare nel suo perimetro.')
                if equity:r['limits'].append('Equity non è denaro; fattibilità e accordi societari non verificati.')
        if intent.get('contradictions'):
            r.update(state='NEEDS_REVIEW',classification='contradictory_request',reason='Richiesta e controprove discordanti nello stesso blocco: verifica manuale necessaria.')
            r['limits'].append('Contraddizione commerciale irrisolta; entrambe le evidenze sono conservate.')
        if not published and not (engine=='AGENCIES' and invitation):r['limits'].append('Data della richiesta sconosciuta; disponibilità attuale non confermata.')
        if employee and external and r['state']!='REJECTED':r['state']='NEEDS_REVIEW';r['limits'].append('Modalità contrattuali alternative o discordanti nel medesimo blocco.')
        if block['source_kind']=='job_portal' and identity.get('identity_status')!='verified':
            if r['state'] in ('VERIFIED','POTENTIAL'):r['state']='NEEDS_REVIEW'
            r['limits'].append('Editore dell’annuncio distinto dal committente; identità ufficiale non risolta.')
        r['verification']={**empty['verification'],'checks':{
            'identity':identity.get('identity_status')=='verified','attributable_request':bool(intent.get('buyer_evidence')),
            'technical':intent['technical'],'compatible_relationship':bool(external or r.get('contract')=='founder'),
            'original_source':bool(block['evidence']),'no_contradiction':not bool(intent.get('contradictions')),
            'temporal_basis':bool((invitation and external) or (age is not None and 0<=age<=180))},
            'currentness':'standing_invitation' if invitation and external else 'recent_publication' if age is not None and 0<=age<=180 else 'unknown',
            'availability_verified':False,'request_verified':False,'currently_open':False}
        r=finish(r,identity,[('Richiesta',25,'Blocco originale con intenzione di collaborazione.'),('Compatibilità tecnica',20 if r['skills'] else 0,'Ruoli del medesimo blocco.'),('Contratto',20 if external else 0,'Natura esterna dichiarata.'),('Attualità',15 if invitation or (age is not None and 0<=age<=180) else 0,'Invito continuativo o data annuncio tipizzata.'),('Prove',15,'Estratti con canale e coordinate verificabili.'),('Contatto',5 if r['contacts'] else 0,'Canale attribuito all’azienda.')])
        subject=re.sub(r'\W','',str(block.get('subject') or '').casefold())
        owner=re.sub(r'\W','',str(identity.get('name') or '').casefold())
        requested_subject=re.sub(r'\W','',str(intent.get('requested_subject') or '').casefold())
        if (subject and subject!=owner) or (requested_subject and requested_subject!=owner):
            if r['state'] in ('VERIFIED','POTENTIAL'):r['state']='NEEDS_REVIEW'
            r['limits'].append('Datore/committente dichiarato diverso dal proprietario identificato: relazione da verificare.')
        if project_actor:
            if r['state'] in ('VERIFIED','POTENTIAL'):r['state']='NEEDS_REVIEW'
            r['verification']['checks']['identity']=False
            r['verification']['identity_verified']=False
            r['limits'].append('Progetto ospitato: identità ufficiale e contatto propri da verificare, senza ereditare quelli dell’editore.')
            r['contacts']=[]
        if geo.get('conflicts') or not geo.get('eligible'):
            if r['state'] in ('VERIFIED','POTENTIAL'):r['state']='NEEDS_REVIEW'
            if geo.get('conflicts'):r['limits'].append('Località discordanti: verifica necessaria prima della qualifica.')
        if block.get('segmentation_uncertain'):
            r.update(state='UNVERIFIABLE',classification='segmentation_incomplete',reason='Annunci non separabili con sufficiente affidabilità; nessun contratto trasferito tra ruoli.',verification={'status':'incomplete','scope':'segmentation'})
        if r['state'] not in ('VERIFIED','POTENTIAL'):r['priority']='review'
        if r['state']=='VERIFIED':
            clause=intent.get('request_clause') or ''
            decisive=next((e for e in block['evidence'] if clause in e['quote']),None)
            if not decisive:
                r.update(state='NEEDS_REVIEW',priority='review',reason='Estratto determinante non riconciliato con le prove originali.')
            else:
                r['verification']['request_verified']=True
                r['verified_proof']={'subject':identity.get('name'),'quote':decisive['quote'],'url':decisive['url'],
                    'request_type':intent['commercial_role'],'collaboration_type':r.get('contract'),'reason':r['reason'],
                    'temporal_limits':'Invito continuativo osservato; nessuna commessa aperta o disponibilità confermata.' if invitation else 'Pubblicazione recente; disponibilità della richiesta non confermata direttamente.',
                    'status':'verified_request','evidence':decisive,'published_at':published,'observed_at':page['checked_at']}
        if r['state']=='NEEDS_REVIEW' and intent.get('contradictions'):r['verification']['status']='contradictory'
        results.append(r)
    rank={'VERIFIED':4,'POTENTIAL':3,'NEEDS_REVIEW':2,'UNVERIFIABLE':1,'REJECTED':0}
    return max(results,key=lambda r:(rank[r['state']],r['score']))
