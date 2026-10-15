"""Transparent priority rules. Never a purchase probability."""
from datetime import datetime,timezone

def qualify(engine,signal,source_count=1,technical_count=0,minimum_budget=1000):
    date=signal.get('date');age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(date[:10]).date()).days if date else None
    points={'Richiesta esplicita':30 if signal.get('kind')=='request' else 0,
            'Segnale commerciale':18 if engine in ('B','C','E') and signal.get('kind')!='request' else 0,
            'Recenza documentata':15 if age is not None and age<=30 else 8 if age is not None and age<=90 else 0,
            'Competenze pertinenti':min(12,4*len(signal.get('skills',[]))),
            'Località prioritaria dichiarata':4 if signal.get('preferred_location') else 0,'Fonte originale letta':10,'Contatto pubblico':5 if signal.get('contacts') else 0,
            'Continuità dichiarata':5 if signal.get('ongoing') else 0,
            'Riscontri tecnici specifici':min(8,technical_count*4),
            'Fonti distinte':min(5,max(0,source_count-1)*3)}
    if signal.get('requirements'):points['Requisiti da confermare nel profilo']=-min(15,5*len(signal['requirements']))
    if signal.get('competition') is not None and signal['competition']>=100:points['Concorrenza dichiarata elevata']=-15
    # Missing economic data contributes zero. No inferred revenue/budget from company size.
    points['Budget noto']=0
    budget=signal.get('budget') or ''
    import re
    amount=re.search(r'(\d[\d.]*)\s*(?:€|euro|EUR)',budget,re.I)
    if amount:
        value=int(amount.group(1).replace('.',''))
        points['Budget noto']=5 if value>=minimum_budget else -10
    score=max(0,min(100,sum(points.values())))
    if engine=='D':score=min(score,35)
    if not date and engine in ('A','B','C'):score=min(score,49)
    return score,points

def build_dossier(item,profile):
    ev=[e for e in item['evidence'] if e['kind'] not in ('limitation','hypothesis')]
    requests=[e for e in ev if e['kind']=='request'];measurements=[e for e in ev if e['kind']=='measurement']
    budget=next((e['metadata'].get('budget') for e in ev if e['metadata'].get('budget')),None)
    competition=next((e['metadata'].get('competition') for e in ev if e['metadata'].get('competition') is not None),None)
    facts=[{'id':e['id'],'text':e['detail'],'url':e['url'],'kind':e['kind'],'date':e['published_at'],'checked_at':e['checked_at']} for e in ev]
    missing=list(item['missing'])
    if not item['contact_basis']:missing.append('Stabilire un presupposto di contatto appropriato; l’email pubblica non è consenso.')
    if item['prior_contacted']:missing.append('Già contattata nella versione precedente: verificare lo storico prima di un nuovo messaggio.')
    if item['do_not_contact']:missing.append('Azienda segnata NON CONTATTARE.')
    timing=('La fonte descrive una ricerca esplicita: verifica che sia ancora aperta e usa il canale indicato.' if requests else 'Il segnale può motivare una verifica esplorativa; non dimostra urgenza né intenzione di acquisto.')
    if not item['latest_date']:timing='Data non disponibile: prima verifica se la richiesta o il cambiamento sono ancora attuali.'
    return {'mode':'Regole locali · nessun modello generativo attivo','why':item['reason'],'service':item['service'],'hypothesis':item['hypothesis'],'timing':timing,'value':budget or 'Non stimabile dalle fonti disponibili. Definire ambito, vincoli e budget con il committente.','competition':competition,'differentiation':'Mostrare un progetto realmente pertinente del proprio portfolio e spiegare il contributo su '+item['service']+'. Non attribuire risultati economici o seniority non documentati.','next_step':'Non contattare: preferenza registrata.' if item['do_not_contact'] else 'Verificare attualità, referente e canale di candidatura.' if requests else 'Confermare l’esigenza ipotizzata prima di preparare un preventivo.','missing':list(dict.fromkeys(missing)),'facts':facts,'method':'Priorità calcolata con pesi espliciti, non probabilità di vendita. Il testo non certifica la disponibilità del committente.'}

def communication(item,profile):
    d=build_dossier(item,profile);evidence=[e for e in item['evidence'] if e['kind'] in ('request','signal','measurement','fact')]
    if not evidence: raise ValueError('Nessun riscontro sufficiente per una proposta')
    e=sorted(evidence,key=lambda e:({'request':0,'signal':1,'measurement':2,'fact':3}.get(e['kind'],4)))[0]
    fact=' '.join(e['detail'].split())[:380]
    opener=('Ho letto la vostra richiesta' if e['kind']=='request' else 'Ho letto il vostro aggiornamento' if e['kind']=='signal' else 'Durante un controllo del vostro sito ho rilevato questo punto')
    subject=('Collaborazione per '+item['service'])[:180]
    message=f"Buongiorno,\n\nsono {profile['name']}, freelance di {profile['location']}. Mi occupo di design e sviluppo web.\n\n{opener}: «{fact}».\nFonte: {e['url']}\n\nPotrei supportarvi su {item['service']}. Vi andrebbe di confrontarci sull’ambito del progetto e capire se il mio contributo può essere utile?\n\nIl mio portfolio: {profile['portfolio']}\n\n{profile['name']}"
    if e['kind']!='request':message=message.replace('Vi andrebbe di confrontarci sull’ambito del progetto e capire se il mio contributo può essere utile?','Se questo è un tema che state valutando, vi andrebbe di confrontarci? Prima di proporre un intervento vorrei capire le vostre priorità.')
    proposal=f"Ipotesi di intervento: {item['service']}.\n\nPunto di partenza verificato: {fact}\nFonte: {e['url']}\n\nDa concordare: obiettivi, perimetro, deliverable, accessi e tempi.\nValore: {d['value']}\n\nQuesta è una traccia di discussione, non un preventivo approvato."
    followup=f"Buongiorno,\nriprendo il messaggio relativo a {item['service']}. Se il tema è ancora attuale, resto disponibile per un confronto. Se non rientra nelle vostre priorità, nessun problema.\n\n{profile['name']}"
    return {'subject':subject,'email':message,'proposal':proposal,'followup':followup,'rationale':d['why'],'mode':'Bozza locale basata su riscontri citati','generated_at':datetime.now(timezone.utc).isoformat()}
