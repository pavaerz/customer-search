"""Two-level website assessment: observed barriers, never inferred buying intent."""
import re
from urllib.parse import urljoin
from sales.extract import parse_page
from sales.db import domain,digest
from urllib.parse import urlsplit
from .evaluation import base,finish

def screen(pages,failures,limits=None):
    findings=[]
    home=parse_page(pages[0])
    if 'viewport' not in home['doc'].meta:findings.append({'code':'viewport','severity':'minor','url':pages[0]['url'],'quote':'Meta viewport non presente nel documento HTML.'})
    for f in failures:
        if f.get('status') not in (404,410):continue  # access/robots/timeouts are not defects
        if not re.search(r'contatt|contact|preventiv|prodott|serviz|catalog',f['url'],re.I):continue
        kind='contact' if re.search(r'contatt|contact|preventiv',f['url'],re.I) else 'offer'
        findings.append({'code':'broken_'+kind,'severity':'major','url':f['url'],'quote':f"Pagina {kind} collegata dal sito: risposta HTTP {f['status']}.",'status':f['status']})
    for p in pages:
        parsed=parse_page(p)
        if re.search(r'prodott|serviz|catalog',urlsplit(p['url']).path,re.I) and len(parsed['text'])<60:findings.append({'code':'empty_offer','severity':'moderate','url':p['url'],'quote':'Testo dell’offerta insufficiente nell’HTML; non è ancora un difetto osservato.'})
    incomplete=bool(limits) or any(len(parse_page(p)['text'])<60 for p in pages)
    for f in findings:
        f['category']='INSUFFICIENT_EVIDENCE' if f['code']=='empty_offer' else 'TECHNICAL_ISSUE'
    return {'level':'HTTP','findings':findings,'promising':any(f['severity']=='major' for f in findings) or len({f['code'] for f in findings})>=2,
            'status':'incomplete' if incomplete else 'negative' if not findings else 'indicators',
            'limits':list(limits or []),'scope':'HTML preliminare; adeguatezza non dimostrata'}

def browser_selection(identity,screening,budget):
    relevant=identity.get('identity_status')=='verified' and identity.get('organization',{}).get('category') not in ('directory','public_body','editorial_source')
    from .resources import headroom
    room=headroom(budget)
    available=room['browser_runs']>0 and room['http_reads']>0
    in_area=budget.get('geography_eligible',True)
    fit=budget.get('target_fit')
    fit_ok=fit is None or fit.get('audit_allowed',False)
    selected=relevant and available and in_area and fit_ok
    code='identity_unverified' if not relevant else 'target_not_suitable' if not fit_ok else 'outside_selected_area' if not in_area else 'budget_deferred' if not available else 'indicators' if screening['promising'] else 'relevant_company_priority'
    return {'selected':selected,'sample_percent':None,'policy':'pertinence_before_sampling',
            'target_fit':fit,'code':code,'resources':room,'reason':'Azienda identificata: audit prioritario prima di altre letture accessorie.' if selected else 'Identità insufficiente o risorse audit esaurite; nessun giudizio sulla qualità del sito.'}

def evaluate(identity,pages,geo,screening,browser=None):
    result=base('WEBSITE_REBUILD',identity,pages[0],geo);result['title']='Valutazione del sito · '+str(identity.get('name',''))
    result['skills']=['Sito aziendale'];result['screening']=screening;result['browser']=browser or {};result['project']='Possibile rifacimento completo, da delimitare con l’azienda.'
    if not browser and not screening['promising']:
        incomplete=screening.get('status')=='incomplete'
        result.update(state='UNVERIFIABLE' if incomplete else 'REJECTED',classification='screen_incomplete' if incomplete else 'insufficient_problems' if screening['findings'] else 'screen_negative',reason='Screening incompleto; nessuna conclusione sulla qualità del sito.' if incomplete else 'Nessun indizio preliminare sufficiente; adeguatezza del sito non verificata in browser.')
    elif not browser or not browser.get('completed') or browser.get('requested_level')=='BASIC':
        result.update(state='UNVERIFIABLE',classification='insufficient',reason='Audit BASIC completato; verifica STANDARD/DEEP necessaria prima di valutare un rifacimento.' if browser and browser.get('completed') and browser.get('requested_level')=='BASIC' else 'Controllo browser incompleto: nessuna gravità presunta dagli errori di accesso.')
        result['limits']+=((browser or {}).get('limits') or ['Verifica approfondita non disponibile.'])
    else:
        # Corroborate broken destinations with an actual link in a rendered page.
        linked=set(browser.get('links',[]))
        facts=[f for f in screening['findings'] if f['code'].startswith('broken_') and f['url'] in linked]
        facts += browser.get('findings',[])
        facts=[{**f,'category':f.get('category') or ('ACCESSIBILITY_ISSUE' if f['code'] in ('mobile_content','desktop_content','horizontal_overflow','obstructed_controls') else 'TECHNICAL_ISSUE')} for f in facts]
        major=[f for f in facts if f['severity']=='major'];dimensions={f['code'] for f in major}
        significant=len(dimensions)>=2 and len({f['url'] for f in major})>=2
        moderate=bool(major or any(f['severity']=='moderate' for f in facts))
        result.update(state='POTENTIAL' if significant else 'REJECTED',classification='significant' if significant else 'insufficient_problems' if moderate else 'browser_completed',reason='Problemi documentati su più percorsi: valutare con l’azienda se un intervento completo è necessario.' if significant else 'Browser completato: problemi insufficienti per motivare un rifacimento.' if moderate else 'Browser completato senza barriere rilevate nel perimetro misurato; non è un audit completo.')
        result['evidence']=[{**f,'method':'HTTP status and rendered link' if f['code'].startswith('broken_') else 'rendered DOM measurements','measurement_limits':['Only the recorded pages and viewports; no conversion or buying intent measurement.'],'kind':'measurement','certainty':'observed','checked_at':pages[0]['checked_at'],'published_at':None} for f in facts]
        result['consequence']='Le barriere osservate possono rendere più difficile consultare l’offerta o raggiungere i contatti; effetto su vendite e conversioni non misurato.'
        result['limits']+=['Nessuna richiesta di acquisto dimostrata.','Confrontare un rifacimento con correzioni mirate prima di proporre un preventivo.']
    significant=result['classification']=='significant';moderate=result['classification']=='moderate'
    result['browser_outcome']=browser.get('outcome') if browser and browser.get('outcome') else 'completed' if browser and browser.get('completed') else 'timeout' if browser and any('timeout' in x.lower() or 'temporale' in x.lower() for x in browser.get('limits',[])) else 'access_error' if browser else screening.get('browser_selection',{}).get('code','not_selected')
    result['verification']={'status':'complete' if browser and browser.get('completed') else 'incomplete','scope':'browser' if browser else 'screening','screening':screening.get('status'),'browser_completed':bool(browser and browser.get('completed'))}
    if browser and browser.get('outcome')=='budget_deferred':
        result.update(classification='browser_budget_deferred',reason='Screening HTTP conservato; risorse per l’audit esaurite. Nessun giudizio negativo sul sito.',deferred_resource=browser.get('deferred_resource','browser_runs'))
    from .browser import audit_state
    result['audit_state']=audit_state(browser)
    result['analysis_levels']={'HTTP':screening.get('status','unknown'),
                               'DOM':('completed' if browser.get('completed') else browser.get('outcome','partial')) if browser and browser.get('executed',True) else 'not_executed',
                               'ADVANCED':(browser or {}).get('levels',{}).get('BROWSER_ADVANCED',{}).get('status','not_executed')}
    result['commercial_advisory']=commercial_advisory(identity,result)
    result['observation_types']=[{**f,'observation_type':'NOT_TESTED' if f.get('category')=='INSUFFICIENT_EVIDENCE' else 'VERIFIED_UX_ISSUE' if f.get('category')=='ACCESSIBILITY_ISSUE' else 'VERIFIED_TECHNICAL_ISSUE'} for f in result['evidence']]
    if not browser or not browser.get('completed'):
        result['analysis_limit_type']='QUOTA_EXHAUSTED' if result.get('deferred_resource') else 'ACCESS_LIMITATION' if result['browser_outcome'] in ('robots','access_error','tls_error') else 'NOT_VERIFIED'
    result['observation_categories']=sorted({f.get('category','TECHNICAL_ISSUE') for f in result['evidence']}) or ['INSUFFICIENT_EVIDENCE']
    finish(result,identity,[('Gravità',35 if significant else 15 if moderate else 0,'Problemi corroborati dal browser e dalle risposte HTTP.'),('Intervento',20 if significant else 5 if moderate else 0,'Più percorsi compromessi, non una stima economica.'),('Compatibilità',15 if significant or moderate else 0,'Problemi affrontabili nello sviluppo del sito.'),('Prove',20 if browser and browser.get('completed') and result['evidence'] else 0,'Misure osservate e URL delle pagine.'),('Contattabilità',10 if result['contacts'] else 0,'Canale aziendale pubblico.')])
    if result['state']=='POTENTIAL':result['priority']='high' if significant else 'secondary'
    return result


def commercial_advisory(identity,result):
    """Consultative labels, no official-state changes or buying-intent claims."""
    facts=[f for f in result.get('evidence',[]) if f.get('kind')=='measurement' and f.get('severity') in ('moderate','major')]
    identified=identity.get('identity_status')=='verified'
    plausible=identified and result.get('geography',{}).get('eligible',False) and result.get('classification')=='significant'
    contact=plausible and bool(result.get('contacts'))
    return {'status':'CONTACT_READY' if contact else 'COMMERCIALLY_PLAUSIBLE' if plausible else 'TECHNICALLY_INTERESTING' if facts else 'NOT_ENOUGH_EVIDENCE',
            'decision_authority':'advisory_only','official_domain_verified':identified,
            'basis':[f['code'] for f in facts],'contact_available':bool(result.get('contacts')),
            'budget':None,'purchase_intent':None,
            'next_action':'Confrontare rifacimento e interventi mirati con il referente.' if plausible else 'Raccogliere prove sufficienti prima di proporre un rifacimento.',
            'limits':['Budget e interesse aziendale non dimostrati.','Impatto economico non misurato.']}
