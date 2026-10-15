"""Keep all decision evidence; compress only repeated business background.

Full quotations remain in the dossier. Evidence beyond model capacity is explicit
incomplete work, never a silently truncated set used for qualification.
"""
import re
import json
from .claim_grounding import DIGITAL_CONTEXT
from .research_rules import FULL,REQUEST,COMPLETED,RISK,EMPLOYEE


def select(signals,capacity=24):
    critical=[];background=[];seen_evidence=set();duplicates=0
    for signal in signals:
        key=(signal.get('document_id'),signal['kind'],' '.join(signal['quote'].split()),signal.get('published_at'),signal.get('official'))
        if key in seen_evidence:
            duplicates+=1;continue
        seen_evidence.add(key)
        text=signal['quote']
        substantive=signal['kind']!='business' or any(pattern.search(text) for pattern in (DIGITAL_CONTEXT,FULL,REQUEST,COMPLETED,RISK,EMPLOYEE)) or re.search(r'budget|corrispettivo|€|\bEUR\b',text,re.I)
        (critical if substantive else background).append(signal)
    selected=list(critical);seen=set()
    for signal in background:
        if signal['document_id'] in seen or len(selected)>=capacity:continue
        seen.add(signal['document_id']);selected.append(signal)
    return selected,{'decision_evidence':len(critical),'background_omitted':len(signals)-len(selected),
                     'duplicates_collapsed':duplicates,'requires_batches':len(selected)>capacity,
                     'method':'Prove decisionali conservate; descrizioni generiche dell’attività rappresentate da un estratto per documento. Tutte le citazioni restano nel dossier.'},[]


MAX_BATCHES=16
MAX_CONTEXT_CHARS=18000


def batches(signals,capacity=16,max_chars=10000):
    """Keep literal citations; never truncate a quote or silently omit a tail."""
    result=[];current=[]
    for signal in signals:
        if len(json.dumps(signal,ensure_ascii=False))>max_chars:
            raise ValueError('Una prova supera il budget del contesto; citazione conservata nel dossier.')
        if current and (len(current)>=capacity or len(json.dumps(current+[signal],ensure_ascii=False))>max_chars):
            result.append(current);current=[]
        current.append(signal)
    if current:result.append(current)
    if len(result)>MAX_BATCHES:raise ValueError('Budget di correlazione esaurito: più di 16 gruppi di prove; revisione non completata.')
    return result


def review_batches(researcher,identity,signals,coverage):
    """Propose on bounded groups, then challenge ONE proposal against EVERY group.

    All reviews must support it. A single contrary/incomplete group vetoes the
    aggregate; citations stay original and the full signals remain in the dossier.
    """
    from .research_analysis import PROPOSAL_SCHEMA,REVIEW_SCHEMA,schema_check
    from .commercial_inference import candidates,review_schema,REVIEW_TASK
    wire=[{k:s.get(k) for k in ('id','kind','quote','url','official','published_at')} for s in signals]
    base={'identity':{k:identity.get(k) for k in ('name','region','group')},'coverage':coverage}
    note={'method':'Proposte per gruppi; revisione della stessa proposta su tutte le prove.','reviewed_ids':[]}
    def call(task,data,schema):
        researcher.check()
        if len(json.dumps(data,ensure_ascii=False))>MAX_CONTEXT_CHARS:raise ValueError('Contesto del gruppo oltre il budget; nessuna revisione completa dichiarata.')
        value=researcher.call(task,data,schema)
        if not schema_check(value,schema):raise ValueError('Output di correlazione non valido o citazioni inesistenti.')
        return value
    try:
        groups=batches(wire);proposals=[]
        # Shared anchors permit cross-document relationships without replacing evidence with prose summaries.
        anchors=[]
        for kind in ('request','event','condition','gap','process'):
            anchors.extend([s for s in wire if s['kind']==kind][:1])
        for group in groups:
            context=list({s['id']:s for s in anchors+group}.values())
            schema=json.loads(json.dumps(PROPOSAL_SCHEMA))
            schema['properties']['support_ids']['items']['enum']=[s['id'] for s in context]
            schema['properties']['budget_signal_id']['enum']=['']+[s['id'] for s in context if s['kind']=='budget']
            proposal=call('Valuta questo gruppo di prove per un progetto digitale completo. Non inventare bisogni o budget. Una descrizione aziendale o difetto tecnico non basta. Conserva gli ID delle citazioni. Se mancano prove, project=none. Le condizioni del canale non sono difetti automatici; considera anche soluzioni esistenti e piccoli interventi.',{**base,'signals':context},schema)
            if proposal['project']!='none':proposals.append(proposal)
        if not proposals:
            return {},{'status':'insufficient','reason':'Nessun progetto documentato nei gruppi esaminati.','context_selection':{**note,'proposal_groups':len(groups)}},[]
        if len({p['project'] for p in proposals})>1:
            raise ValueError('Proposte di categorie diverse: occorre una revisione mirata prima della qualifica.')
        proposal=proposals[0]
        support=[s for s in wire if s['id'] in proposal['support_ids'] or s['id']==proposal['budget_signal_id']]
        support_size=len(json.dumps(support,ensure_ascii=False))
        groups=batches(wire,capacity=max(1,24-len(support)),max_chars=max(1000,12500-support_size))
        reviews=[]
        for group in groups:
            context=list({s['id']:s for s in support+group}.values())
            schema=json.loads(json.dumps(REVIEW_SCHEMA));schema['properties']['support_ids']['items']['enum']=[s['id'] for s in context]
            events,conditions=candidates([s for s in signals if s['id'] in proposal['support_ids']])
            extra=''
            if events and conditions:
                schema['properties']['inference']=review_schema(events,conditions);schema['required'].append('inference');extra=REVIEW_TASK
            review=call('Revisione critica della proposta contro questo gruppo, comprese tutte le controprove. supported solo se il bisogno è concreto e proporzionato a un progetto completo; se basta un piccolo intervento, status=insufficient e small_fix_sufficient=true. Copertura non è adeguatezza; non dedurre assenza da dati mancanti. Cita solo ID presenti.'+extra,{**base,'signals':context,'proposal':proposal},schema)
            reviews.append(review);note['reviewed_ids'].extend(s['id'] for s in group)
        final=dict(reviews[0]);final['status']='contradicted' if any(r['status']=='contradicted' for r in reviews) else 'supported' if all(r['status']=='supported' for r in reviews) else 'insufficient'
        final['small_fix_sufficient']=any(r['small_fix_sufficient'] for r in reviews)
        final['existing_solution_checked']=all(r['existing_solution_checked'] for r in reviews)
        if any(r.get('inference')!=final.get('inference') for r in reviews):final.pop('inference',None)
        final['support_ids']=list(dict.fromkeys(i for r in reviews for i in r['support_ids']))
        final['reason']=next((r['reason'] for r in reviews if r['status']!='supported'),final['reason'])
        final['batch_reviews']=reviews;final['context_selection']={**note,'proposal_groups':len(proposals),'review_groups':len(groups)}
        assert set(note['reviewed_ids'])=={s['id'] for s in wire}
        proposal['checked_sections']=[k for k,v in coverage.items() if v is True]
        return proposal,final,[]
    except InterruptedError:raise
    except Exception as exc:
        return {},{'status':'insufficient','reason':str(exc),'context_selection':note},['Analisi locale non completata: correlazione · '+str(exc)]
