"""Shared commercial gates for results, recommendations and follow-up decisions."""
import re
from datetime import datetime,date,timedelta
from urllib.parse import urlsplit
from sales.db import digest,domain
from sales.commercial.demand import geography,technical_fit
from .schema import quote,identity_role
from . import semantics,VERSION
from sales.commercial.indexed_jobs import same_company_name
from sales.commercial.demand import ASK,STANDING

def core(text):
    # No facts, links, dates or pay from neighbouring requests.
    from .source_scope import text_scope
    return text_scope(text)['text']

def temporal(text,checked_at,original,window=14):
    out={'status':'UNKNOWN','published_at':None,'basis':None,'quote':None}
    if not original:return out
    try:today=datetime.fromisoformat(checked_at.replace('Z','+00:00')).date()
    except (ValueError,AttributeError):return out
    match=re.search(r'(?:Posted\s+)?(\d{1,3})\s+(day|week|month|year)s?\s+ago',text[:1600],re.I)
    if match:
        days=int(match[1])*{'day':1,'week':7,'month':28,'year':365}[match[2].lower()]
        out.update(status='STALE' if days>window else 'RECENT',published_at=(today-timedelta(days=days)).isoformat() if match[2].lower() in ('day','week') else None,basis='relative_original_acquisition_anchor',quote=match[0],age_days_lower_bound=days)
    if not match:
        explicit=re.search(r'(?:Posted(?: on)?|Pubblicato(?: il)?|datePosted)\s*[:\-]?\s*(20\d{2}-\d{2}-\d{2})',text[:1600],re.I)
        value=None
        if explicit:
            try:value=date.fromisoformat(explicit[1])
            except ValueError:pass
        if not explicit:
            explicit=re.search(r'Posted(?: on)?\s*:?\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})',text[:1600],re.I)
            if explicit:
                months={m.lower():i for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
                try:value=date(int(explicit[3]),months[explicit[1].lower()],int(explicit[2]))
                except (ValueError,KeyError):pass
        if not explicit:
            explicit=re.search(r'(?:Data di inizio|Pubblicato(?: il)?)\s*:?\s*(\d{1,2})\s+(gen(?:naio)?|feb(?:braio)?|mar(?:zo)?|apr(?:ile)?|mag(?:gio)?|giu(?:gno)?|lug(?:lio)?|ago(?:sto)?|set(?:tembre)?|ott(?:obre)?|nov(?:embre)?|dic(?:embre)?)\s+(20\d{2})\b',text[:1600],re.I)
            if explicit:
                months={m:i for i,m in enumerate(('gen','feb','mar','apr','mag','giu','lug','ago','set','ott','nov','dic'),1)}
                try:value=date(int(explicit[3]),months[explicit[2][:3].lower()],int(explicit[1]))
                except (ValueError,KeyError):pass
        if value:
            days=(today-value).days
            out.update(status='RECENT' if 0<=days<=window else 'STALE' if days>window else 'UNKNOWN',published_at=value.isoformat(),basis='labelled_original_date',quote=explicit[0])
    return out

def money(text):
    # Never borrow salary or funding as project budget.
    result={'kind':'UNKNOWN','amount':None,'currency':None,'quote':None}
    p=re.search(r'\b(?:budget|compenso|compensation|salary|retribuzione|pay|rate|RAL)\s*:?\s*([$€£])\s*(\d+(?:[.,]\d+)*)\s*([^\n]{0,85})',text,re.I)
    if p:
        number=p[2]
        if ',' in number and '.' in number:
            decimal=',' if number.rfind(',')>number.rfind('.') else '.'
            thousands='.' if decimal==',' else ','
            whole,fraction=number.rsplit(decimal,1)
            if len(fraction) not in (1,2) or not re.fullmatch(r'\d{1,3}(?:'+re.escape(thousands)+r'\d{3})+',whole):return result
            number=whole.replace(thousands,'')+'.'+fraction
        elif ',' in number or '.' in number:
            separator=',' if ',' in number else '.';parts=number.split(separator)
            if 1<=len(parts[0])<=3 and all(len(v)==3 for v in parts[1:]):number=''.join(parts)
            elif len(parts)==2 and len(parts[1]) in (1,2):number=parts[0]+'.'+parts[1]
            else:return result
        tail=p[3].lower();head=p[0].lower()
        kind='HOURLY' if re.search(r'per hour|/\s*h(?:our)?\b|hourly|all.ora',tail) else 'ANNUAL_SALARY' if re.search(r'annual|year|annuo|salary|RAL',head,re.I) else 'MONTHLY' if re.search(r'month|mese',tail) else 'PROJECT_BUDGET' if re.search(r'budget|fixed price|prezzo fisso',head) else 'UNKNOWN'
        result={'kind':kind,'amount':float(number),'currency':{'$':'USD','€':'EUR','£':'GBP'}[p[1]],'quote':p[0]}
    return result

def objective(source,window=14):
    text=core(source.get('linked_request_text') or source.get('analysis_text') or source.get('text',''));original=source.get('original',False);title=source.get('title','');bad=[]
    fresh=temporal(text,source.get('checked_at'),original,window)
    if original and source.get('job_date'):
        try:
            days=(date.fromisoformat(source['checked_at'][:10])-date.fromisoformat(source['job_date'][:10])).days
            fresh={'status':'RECENT' if 0<=days<=window else 'STALE' if days>window else 'UNKNOWN','published_at':source['job_date'],'basis':source.get('job_date_basis') or 'JobPosting.datePosted','quote':source['job_date']}
        except (ValueError,KeyError):pass
    budget=money(text) if original else money('')
    if fresh['status']=='STALE':bad.append('stale_request')
    if original and re.search(r'no longer accepting|job (?:is no longer available|was removed)|applications closed|posizione chiusa|HTTP 410',text,re.I):bad.append('closed_request')
    # A company's printed VAT number identifies its business; it says nothing
    # about hiring freelancers. Require a relationship around "partita IVA".
    external=bool(re.search(r'\b(?:freelance|independent contractor|project.based|collaborator\w* estern)|\b(?:contratto|collaborazion\w*|collaborare|incaric\w*|professionist\w*|candidat\w*|rapporto)[^.!?\n]{0,160}\b(?:partita\s*iva|p\.\s*iva)\b',text,re.I))
    employee_terms=r'tempo indeterminato|permanent contract|employment type\s*\nFull-time|assumiamo.{0,80}dipendent|full[ -]time employee|employee[ -]only|solo (?:lavoro )?dipendent'
    employee=any(not re.search(r'\b(?:not|no|non|senza)\s+(?:an?\s+|un\s+|un contratto a\s+)?$',text[max(0,m.start()-30):m.start()],re.I)
                 for m in re.finditer(employee_terms,text,re.I))
    if re.search(r'not (?:a )?freelance|no (?:freelancers|contractors)|non (?:accettiamo|cerchiamo).{0,20}(?:freelance|partita)',text,re.I):external=False;employee=True
    if original and employee and not external:bad.append('employee_job')
    if original and budget['kind']=='PROJECT_BUDGET':
        minimum=5000 if re.search(r'e.?commerce|woocommerce|shopify',title,re.I) else 2000
        if budget['currency']=='EUR' and budget['amount']<minimum:bad.append('budget_below_minimum')
        # A tiny declared foreign budget is a reason to stop for economic review,
        # not an invented exchange rate or estimate of the buyer's wealth.
        if budget['currency'] in ('USD','GBP') and budget['amount']<=500:bad.append('declared_budget_insufficient_for_target')
    supplier=bool(re.search(r'I can help with|We (?:offer|provide|build)|Our .{0,60}team specializes|We design .{0,100}for your clients',text,re.I))
    ask=bool(re.search(r'(?:we (?:are )?(?:looking for|seeking)|cerchiamo|cerco|ricerchiamo).{0,100}(?:freelanc|developer|sviluppator|designer|collaborator)',text,re.I))
    if supplier and not ask:bad.append('supplier_offer')
    if original and re.search(r'\bOpinion\b|\b15 min read\b',text[:2500]) and re.search(r'job posts|hiring signal|articolo|Key Facts',text[:4500],re.I):bad.append('editorial_not_request')
    if original and re.search(r'we were looking.{0,800}delivered',text,re.I|re.S):bad.append('completed_project')
    geo=geography(text)
    if original and geo['status']=='GEO_INCOMPATIBLE_CONFIRMED':bad.append('geo_incompatible')
    return {'counterevidence':bad,'freshness':fresh,'budget':budget,'external':external if original else None,'employee':employee if original else None,'geography':geo,'original':original}

def attributed_money(source,name,owner):
    value=money(source.get('text','')) if source.get('original') else money('')
    if value['kind']=='UNKNOWN':return value,None
    if not owner:return money(''),'Committente e titolarità della fonte non verificati.'
    text=source.get('text','');start=text.find(value['quote']);prefix=text[max(0,start-300):start]
    from sales.commercial.entity_scope import owner_fact
    line=text[text.rfind('\n',0,start)+1:start+len(value['quote'])]
    names=re.findall(r"([A-Z][A-Za-zÀ-ÿ0-9& .'-]{1,70}\s+(?:S\.?r\.?l\.?|S\.?p\.?A\.?|Ltd\.?|LLC))\b",prefix,re.I)
    if not owner_fact(line,name) or names and not same_company_name(names[-1],name):
        return money(''),'Importo nel contesto di un altro soggetto; non attribuito al committente.'
    return {**value,'url':source['url'],'basis':'declared_on_verified_owner_source'},None

def evaluate(source,analysis,evidence,flow,identity=None,window=14):
    from .completion import prepare,relationship,dossier
    analysis,evidence,identity,completion=prepare(source,analysis,evidence,identity)
    body=_evaluate(source,analysis,evidence,flow,identity,window)
    relation=relationship(source,body.get('facts',[]))
    body['source_role']=completion['source_role']
    body['deterministic_completion']=completion
    body['relationship_check']={'status':relation,'basis':'local_request_context'}
    if relation=='NONTECHNICAL_PARTNERSHIP':
        body.update(state='REJECTED',kind='UNKNOWN',signal_recovery=None,opportunity_type='NON_QUALIFICATA',
            reason='La richiesta citata riguarda affiliati, partner commerciali o accoglienza, non sviluppo web.',
            counterevidence=list(dict.fromkeys([*body.get('counterevidence',[]),'nontechnical_partnership'])))
        body['relationship_check']['evidence']=[{'quote':f['quote'],'url':f.get('url'),
            'original':bool(f.get('original'))} for f in body.get('facts',[]) if f['field']=='request']
    elif relation=='MIXED_INVITATIONS':
        body.update(state='NEEDS_REVIEW',kind='UNKNOWN',signal_recovery=None,
            reason='Inviti di natura diversa: isolare la richiesta tecnica prima di attribuire il progetto.',
            missing=sorted(set(body['missing'])|{'request','technical'}))
    elif relation in ('CUSTOMER_PARTNERSHIP','NONTECHNICAL_VOLUNTEERING'):
        body.update(state='REJECTED',kind='SUPPLIER_OFFER' if relation=='CUSTOMER_PARTNERSHIP' else 'UNKNOWN',
            reason='La fonte descrive il rapporto con i clienti, non cerca freelance.' if relation=='CUSTOMER_PARTNERSHIP' else 'Collaborazione volontaria o legale, senza incarico tecnico retribuito documentato.',
            counterevidence=[relation.lower()],signal_recovery=None,opportunity_type='NON_QUALIFICATA')
    elif relation=='PORTAL_MANAGEMENT_UNSPECIFIED':
        body.update(state='NEEDS_REVIEW',kind='UNKNOWN',signal_recovery=None,
            reason='Invito a gestire portali: attività tecnica e rapporto economico non specificati.',
            missing=sorted(set(body['missing'])|{'technical','contract'}))
    elif relation=='INVITATION' and source.get('original') and body.get('kind')=='UNKNOWN' and not body.get('counterevidence'):
        body.update(state='NEEDS_REVIEW',reason='Invito riscontrato; tipo di collaborazione e ambito da chiarire.',
            missing=sorted(set(body['missing'])|{'technical','contract'}))
    if body.get('model_kind')=='EMPLOYEE_JOB' and not body.get('employee') and not body.get('counterevidence') and body.get('relationship',{}).get('status')!='employee_mentioned':
        body.update(state='NEEDS_REVIEW' if source.get('original') else 'DISCOVERED',kind='UNKNOWN',
            reason='Il tipo di contratto non è documentato: non è dimostrato un impiego dipendente.',
            missing=sorted(set(body['missing'])|{'contract'}))
    if completion['source_role']['role'] in ('DIRECTORY','JOB_PORTAL','PUBLISHER','INSTITUTION'):
        # A verified publisher is not a verified client. A separate subject
        # and its official domain are necessary to establish that connection.
        if body.get('identity_verified') and body.get('official_domain') and domain(body['official_domain'])==domain(source['url']):
            body.update(identity_verified=False,official_domain=None,entity_key=None,contacts=[],
                state='REJECTED' if relation in ('NONTECHNICAL_PARTNERSHIP','CUSTOMER_PARTNERSHIP','NONTECHNICAL_VOLUNTEERING') else 'NEEDS_REVIEW' if source.get('original') else 'DISCOVERED')
            body['missing']=sorted(set(body['missing'])|{'entity','official_domain'})
    from .alignment import dimensions
    body['commercial_alignment']=dimensions(body)
    body['completion_queue']=dossier(body)
    return body


def _evaluate(source,analysis,evidence,flow,identity=None,window=14):
    identity=identity or {};g=objective(source,window);facts=[]
    for f in (analysis or {}).get('facts',[]):facts.append({'field':f['field'],**quote(f['ref'],evidence)})
    from .document_units import attribute
    from .signals import extract_signals,contradictions
    facts,unit_withheld,unit_issues,units=attribute(source,facts)
    if units:
        selected={f.get('document_unit_id') for f in facts if f['field']=='request' and f.get('original')}
        unit=next((u for u in units if selected=={u['id']}),None)
        g=objective({**source,'text':unit['text'] if unit else '',
            'analysis_text':None,'linked_request_text':None,'job_date':None},window)
    signals=extract_signals(source);conflicting_signals=contradictions(source,analysis,signals)
    consistency=semantics.inspect(source,analysis,facts)
    consistency['issues']=list(dict.fromkeys(consistency['issues']+unit_issues))
    facts=[f for f in facts if f['field']!='entity' or not identity_role(f['quote'])]
    kind=(analysis or {}).get('kind','UNKNOWN');names=[f['quote'].strip() for f in facts if f['field']=='entity' and len(f['quote'])<180]
    name=names[0] if names else None
    from .identity_aliases import match as match_owner
    alias=match_owner(identity,name,source)
    owner=bool(alias['matched'])
    from .commercial_roles import inspect as roles,webapp_feasibility
    actors=roles(source,kind,facts,identity,owner,name)
    facts=[f for f in facts if f not in [{k:v for k,v in w.items() if k!='reason'} for w in actors['withheld']]]
    consistency['issues']=list(dict.fromkeys(consistency['issues']+actors['issues']))
    official=identity.get('website') if owner else None
    g['budget'],budget_uncertainty=attributed_money(source,name,owner)
    financial={'budget_below_minimum','declared_budget_insufficient_for_target'}
    if g['budget']['kind']=='UNKNOWN':g['counterevidence']=[v for v in g['counterevidence'] if v not in financial]
    request_facts=[f for f in facts if f['field']=='request' and f['original']]
    # Commercial checks apply to the cited request, never an unrelated footer/job.
    request_text='\n'.join(f['quote'] for f in facts if f['original'] and f['field'] in ('request','technical','contract','geography','publication','budget','scope'))
    request_g=objective({**source,'text':request_text,'linked_request_text':None,'analysis_text':None},window) if request_facts else g
    if g['budget']['kind']=='UNKNOWN':request_g['counterevidence']=[v for v in request_g['counterevidence'] if v not in financial]
    body={'version':VERSION,'checked_at':source.get('checked_at'),'flow':flow,'url':source['url'],'title':source.get('title',''),'original':source.get('original',False),'kind':kind,'entity_name':name,'identity_verified':bool(owner),'official_domain':official,'entity_key':digest('official-domain:'+domain(official)) if official else None,'facts':facts,'hypothesis':(analysis or {}).get('hypothesis',''),'missing':list((analysis or {}).get('missing',[])),**g,'state':'DISCOVERED','reason':'Informazioni commerciali ancora da acquisire.','next_verification':None,'contacts':identity.get('contacts',[]) if owner else []}
    body['identity_link']=alias
    if owner:
        body['entity_name']=identity['name']
        body['identity_aliases']=list(dict.fromkeys([identity['name'],name]))
    from .requirements import reconcile
    reconcile(body)
    if owner:
        body['identity']={k:identity.get(k) for k in ('name','legal_name','page_title','name_provenance','website','identity_status','legal_id','legal_id_evidence','legal_id_conflicts','location','region','sector','source_url','basis')}
        body.update(region=identity.get('region'),sector=identity.get('sector'))
    body.update(model_kind=kind,semantic_issues=consistency['issues'],identity_issues=consistency['identity_issues'],relationship=consistency['relationship'],scope_exclusion=consistency['scope_exclusion'],scope_observation=consistency['scope_observation'])
    body.update(actor_attribution=actors,withheld_evidence=actors['withheld'],budget_uncertainty=budget_uncertainty)
    body['withheld_evidence']+=unit_withheld
    body['document_units']=[{k:v for k,v in u.items() if k!='text'} for u in units]
    body['commercial_signals']=signals
    from .commercial_roles import engagement
    body['engagement']=engagement(facts)
    if body['engagement'].get('entrepreneurial') and body['engagement']['status'] in ('EQUITY_ONLY','COFOUNDER_ROLE','UNPAID'):
        # A budget printed near a founder invitation is not a paid commission.
        # Preserve the attributed declaration without treating equity as revenue.
        body['declared_financial_terms']=g['budget']
        g['budget']=money('')
        body['budget']=g['budget']
        body['optional_unknowns']=sorted(set(body.get('optional_unknowns',[]))|{'budget'})
        g['counterevidence']=[v for v in g['counterevidence'] if v not in financial]
        request_g['counterevidence']=[v for v in request_g['counterevidence'] if v not in financial]
    from .alignment import affinity
    body['affinity']=affinity(body)
    if body['affinity']['value']=='CLEARLY_UNRELATED':
        body.update(state='REJECTED',reason='Attività richiesta estranea ai servizi digitali.',
                    counterevidence=['clearly_unrelated_activity'])
        return body
    if owner and source.get('target_exclusion'):
        excluded=source['target_exclusion']
        body.update(state='REJECTED',reason=excluded['reason'],target_exclusion=excluded,counterevidence=[excluded['code']])
        return body
    if consistency['identity_issues']:
        body['missing']=sorted(set(body['missing'])|{'entity'})
    if consistency['scope_exclusion']:
        body.update(state='REJECTED',kind='UNKNOWN' if consistency['issues'] else kind,reason='Ambito non compatibile: ruolo di contenuti/social media, non sviluppo di siti o applicazioni.',counterevidence=['professional_scope_incompatible']);return body
    if consistency['issues']:
        body.update(kind='UNKNOWN',state='DISCOVERED' if not source.get('original') else 'NEEDS_REVIEW',reason='Classificazione contraddittoria: ruolo del soggetto o rapporto di collaborazione non coerente con le prove.',next_verification='Verificare sull’originale tipo di collaborazione, ambito e committente.')
        body['missing']=sorted(set(body['missing'])|{'entity','request','contract','technical','geography','publication'})
        return body
    if owner and identity.get('region') and source.get('allowed_regions') and identity['region'] not in source['allowed_regions'] and g['geography']['status']!='GEO_COMPATIBLE_CONFIRMED':
        body.update(state='REJECTED',reason='Sede fuori dai territori selezionati; collaborazione accessibile da remoto non verificata.',counterevidence=['outside_selected_regions']);return body
    if source.get('technical_error'):
        body.update(state='UNVERIFIABLE',technical_error=source['technical_error'],reason='Fonte non verificabile: '+source['technical_error']);return body
    if kind in ('BUYER_DEMAND','AGENCY_PARTNERSHIP') and request_g['counterevidence']:
        g['counterevidence']=sorted(set(g['counterevidence']+request_g['counterevidence']))
    if kind in ('BUYER_DEMAND','AGENCY_PARTNERSHIP'):
        g['counterevidence']=sorted(set(g['counterevidence']+body['engagement']['counterevidence']))
    if kind in ('EDITORIAL','COMPANY_SIGNAL'):g['counterevidence']=[v for v in g['counterevidence'] if v!='stale_request']
    if conflicting_signals:g['counterevidence']=[v for v in g['counterevidence'] if v!='supplier_offer']
    body['counterevidence']=g['counterevidence']
    if g['counterevidence']:
        body.update(state='REJECTED',reason='Controprove: '+', '.join(g['counterevidence']));return body
    if conflicting_signals:
        body.update(state='NEEDS_REVIEW',reason='La pagina contiene un invito tecnico originale che contraddice lo scarto: verificare separatamente la collaborazione.',
            semantic_issues=body['semantic_issues']+['original_invitation_ignored'],
            signal_recovery={'signal_ids':[s['id'] for s in conflicting_signals],
                'ranges':[[s['start'],s['context_end']] for s in conflicting_signals],
                'basis':'original_invitation_even_when_already_in_model_payload'},
            next_verification='Verificare l’invito, il committente e le condizioni, separandoli dai servizi offerti.')
        body['missing']=sorted(set(body['missing'])|{'request','contract','entity'})
        return body
    if source.get('original') and kind in ('SUPPLIER_OFFER','EDITORIAL'):
        from .passages import coverage
        inspection=coverage([{'id':'r1',**source}],evidence)[0]
        if inspection['uncovered_invitation_spans']:
            body.update(state='NEEDS_REVIEW',reason='Invito tecnico presente in una sezione non coperta dall’analisi: impossibile concludere che la richiesta sia assente.',next_verification='Analizzare il passaggio dell’invito e verificarne soggetto, contratto e attualità.')
            body['missing']=sorted(set(body['missing'])|{'request','contract','publication'})
            return body
    if kind in ('SUPPLIER_OFFER','COMPLETED_PROJECT','EMPLOYEE_JOB','DIRECTORY'):
        # Semantic negative is an attributed interpretation; never a domain ban.
        body.update(state='REJECTED',reason='Interpretazione della fonte: '+kind);return body
    if owner:body['state']='IDENTIFIED'
    if kind=='EDITORIAL' and flow!='NEWS':body.update(state='REJECTED',reason='Fonte editoriale: non una richiesta.');return body
    originals={f['field'] for f in facts if f['original']}
    if kind in ('COMPANY_SIGNAL','EDITORIAL'):
        body.update(state='IDENTIFIED' if owner else 'DISCOVERED',reason='Azienda citata: il segnale non dimostra un progetto da acquistare.',next_verification='Verificare impresa, dominio ufficiale e bisogno digitale specifico.')
        # Implicit business need remains a hypothesis until the contradictory
        # solution, scope and subject checks can be independently established.
        body['missing']=sorted(set(body['missing'])|({'entity'} if not owner else set())|({'signal','digital_gap','scope'}-originals))
        if owner and {'signal','digital_gap'}<=originals:body.update(state='RELEVANT',reason='Segnale e possibile lacuna documentati: necessità e perimetro da validare; non ancora opportunità qualificata.')
        byfield={f['field']:f for f in facts if f['original']}
        required={'signal','digital_gap','scope'}
        if owner and required<=originals:
            signal,gap=byfield['signal'],byfield['digital_gap']
            # Different fragments/republications aren't independent evidence.
            independent=signal['document_id'] and gap['document_id'] and signal['document_id']!=gap['document_id'] and re.sub(r'\W','',signal['quote'].casefold())!=re.sub(r'\W','',gap['quote'].casefold())
            if independent:
                texts=[' '.join(e['text'] for e in evidence if e.get('document_id')==f['document_id']) for f in (signal,gap)]
                grams=[]
                for text in texts:
                    words=re.findall(r'\w+',text.casefold());grams.append({tuple(words[i:i+3]) for i in range(max(0,len(words)-2))})
                if grams[0] and grams[1] and len(grams[0]&grams[1])/min(len(grams[0]),len(grams[1]))>=.85:independent=False
            attributed=all(name.casefold() in f['quote'].casefold() for f in (signal,gap))
            scope=byfield['scope']['quote']
            complete=bool(re.search(r'complete (?:website|redesign|ecommerce)|nuovo sito|rifacimento completo|nuovo e.?commerce',scope,re.I))
            bounded=not re.search(r'web app|gestionale|security|integrazioni critiche',scope,re.I)
            compatible=g['geography']['status']=='GEO_COMPATIBLE_CONFIRMED' or bool(identity.get('region'))
            owned=all(domain(byfield[field]['url'])==domain(official) for field in ('digital_gap','scope'))
            if independent and attributed and owned and complete and bounded and compatible and g['freshness']['status']=='RECENT' and not body['missing']:
                body.update(state='POTENTIAL',evidence_level='CROSS_VERIFIED',independent_evidence={'signal':signal['url'],'digital_gap':gap['url'],'basis':'distinct_attributed_original_documents_not_republications'},reason='Segnale recente e lacuna attribuiti alla stessa impresa; progetto completo sostenuto da prove distinte. Interesse all’acquisto non dichiarato.',next_verification='Confermare interesse e priorità con il referente, senza presumere un budget.')
        return body
    if not analysis:body.update(state='UNVERIFIABLE',reason='Analisi AI non disponibile o invalida; nessuna promozione.');return body
    if kind in ('BUYER_DEMAND','AGENCY_PARTNERSHIP'):
        if not body['original']:body.update(state='DISCOVERED',reason='Pista indicizzata: originale e committente da verificare.')
        elif 'request' in originals:
            body.update(state='RELEVANT',reason='Domanda riscontrata; controlli commerciali ancora da completare.')
            missing=[]
            standing=kind=='AGENCY_PARTNERSHIP' and any(STANDING.search(f['quote']) or re.search(r'siamo sempre alla ricerca di (?:professionisti|collaboratori)|always looking for (?:freelancers|collaborators)',f['quote'],re.I) for f in request_facts)
            if body['engagement']['needs_clarification']:missing.append('paid_contract')
            if not owner:missing.append('entity')
            if source.get('editorial'):missing.append('request')
            entrepreneurial=body['engagement'].get('entrepreneurial',False)
            generic_agency=(kind=='AGENCY_PARTNERSHIP' and owner
                and actors['organization']['role']=='AGENCY' and not request_g['employee']
                and any(re.search(r'cerchiamo collaboratori|looking for collaborators',f['quote'],re.I) for f in request_facts))
            if not request_g['external'] and not entrepreneurial and not generic_agency:missing.append('contract')
            if generic_agency and not request_g['external']:
                body['optional_unknowns']=sorted(set(body.get('optional_unknowns',[]))|{'contract_terms'})
            if not standing and not any(ASK.search(f['quote']) or STANDING.search(f['quote']) for f in request_facts):missing.append('request')
            if any(f['url']!=source['url'] for f in request_facts) and not source.get('request_identity_linked'):missing.append('request')
            local_agency=(kind=='AGENCY_PARTNERSHIP' and owner and identity.get('region') in source.get('allowed_regions',[])
                          and all(domain(f['url'])==domain(official) for f in request_facts)
                          and request_g['geography']['status']!='GEO_INCOMPATIBLE_CONFIRMED')
            body['collaboration_geography']={'eligible':bool(local_agency),'basis':'verified_agency_region_and_own_invitation' if local_agency else 'unresolved',
                'region':identity.get('region') if local_agency else None,'remote_work':'UNKNOWN'}
            if request_g['geography']['status']!='GEO_COMPATIBLE_CONFIRMED' and not local_agency:missing.append('geography')
            # A standing invitation proves the type of relationship, not that
            # a dated vacancy or a current assignment is available today.
            if g['freshness']['status']!='RECENT':missing.append('publication')
            if kind!='AGENCY_PARTNERSHIP' and ('technical' not in originals or technical_fit(source.get('title',''),request_text)['status']!='COMPATIBLE'):missing.append('technical')
            if re.search(r'piccol[oaie] modific|correzion[ei] CSS|content updates|minor (?:fix|change)|simple updates',request_text,re.I):missing.append('scope')
            specific_project=bool(re.search(r'build our|realizzare (?:un|il)|sviluppare (?:un|il)|progetto (?:specifico|completo)|(?:nuov[oa]|per un[ao]?) (?:sito|web app|piattaforma|gestionale|MVP)',request_text,re.I))
            webapp=bool(re.search(r'\bMVP\b|web app|gestionale|platform|piattaforma',request_text,re.I))
            if kind=='AGENCY_PARTNERSHIP' and not specific_project:
                webapp=False  # Skills in an invitation are not a scoped project.
            if webapp:
                body['feasibility']=webapp_feasibility(facts)
                if body['feasibility']['status']!='BOUNDED':missing.append('feasibility')
            # The model's checklist is a proposal. Don't keep a missing flag
            # after the same requirement has passed a source-bound gate.
            # Unknown dates, availability and actual project terms stay unknown.
            resolved={field:'source_bound_gate_passed' for field in
                ('entity','contract','geography') if field not in missing}
            if generic_agency and not request_g['external']:
                resolved['contract']='agency_invitation_terms_unknown_not_employee_only'
            if 'technical' in originals and technical_fit(source.get('title',''),request_text)['status']=='COMPATIBLE':
                resolved['technical']='source_bound_gate_passed'
            from .alignment import contacts as verified_contacts
            if verified_contacts(body):resolved['contact']='public_attributed_channel'
            else:body['optional_unknowns']=sorted(set(body.get('optional_unknowns',[]))|{'contact'})
            if owner and official:resolved['official_domain']='verified_owner_domain'
            if g['freshness']['status']=='RECENT':resolved['publication']='dated_original_request'
            if kind=='AGENCY_PARTNERSHIP' and owner and (request_g['external'] or generic_agency) and not webapp and not specific_project:
                if 'scope' not in missing:resolved['scope']='standing_partner_invitation_not_a_scoped_project'
                resolved['feasibility']='no_specific_webapp_project_claimed'
            body['requirement_resolution']={field:{'basis':basis,'previously_missing':field in body['missing']}
                for field,basis in resolved.items()}
            body['missing']=sorted((set(body['missing'])-set(resolved))|set(missing))
            missing=body['missing']
            if missing:
                labels={'entity':'identità del committente','technical':'competenze richieste nella collaborazione','contract':'modalità di collaborazione',
                    'geography':'compatibilità territoriale','publication':'attualità dell’invito','contact':'contatto professionale',
                    'scope':'perimetro del progetto','feasibility':'sicurezza, integrazioni e manutenzione','closed':'disponibilità ancora aperta'}
                next_check=next((f for f in ('entity','request','contract','technical','geography','publication','closed','contact','scope','feasibility') if f in missing),missing[0])
                body.update(state='NEEDS_REVIEW',reason='Richiesta documentata; da confermare: '+', '.join(labels.get(f,f) for f in missing),
                    next_verification='Verificare '+labels.get(next_check,next_check)+' con il committente o sulla fonte ufficiale.')
            elif entrepreneurial:body.update(state='POTENTIAL',reason='Proposta imprenditoriale documentata; compenso, equity e impegno da valutare separatamente dalle commesse remunerate.')
            elif kind=='AGENCY_PARTNERSHIP':body.update(state='POTENTIAL',reason='Disponibilità a collaborazione documentata; incarichi e volumi non garantiti.')
            else:body.update(state='VERIFIED',reason='Richiesta, soggetto, attualità, rapporto e Italia supportati dalle prove.')
    return body

def followup_links(page,entity_name=None):
    """Only explicit application/official/contact links, never similar-job cards."""
    from sales.extract import parse_page
    from .source_scope import main_html
    html=main_html(page['html'])
    parsed=parse_page({**page,'html':html});out=[]
    for link in parsed['doc'].links:
        # parse_page links may be strings; such unlabelled links have no intent.
        if not isinstance(link,dict):continue
        label=link.get('text') or link.get('anchor','');url=link.get('url') or link.get('href','')
        if re.search(r'similar|related|months? ago|giorni fa',label,re.I):continue
        if re.search(r'apply (?:now|on)|candidati|collabora con noi|lavora con noi|careers|sito ufficiale|official website|contatti|contact',label,re.I):out.append({'url':url,'label':label})
    return out[:3]
