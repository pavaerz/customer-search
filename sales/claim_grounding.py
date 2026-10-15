"""Literal support for commercial claim types, independent of model confidence.

A quotation can be real while its commercial interpretation is wrong. Unsupported
need/request/process labels become business context, not technical errors or proof
that the company needs a website. Original type remains visible for diagnostics.
"""
import re

DIGITAL_CONTEXT=re.compile(r'\bsito\b|web|e.?commerce|portale|piattaforma|gestional|software|online|digitale|catalogo|email|e-mail|excel|modul[oi]|prenotazion|ordin[ei]|preventiv|configurator',re.I)
NEGATIVE=re.compile(r'\bnon\b.{0,50}(?:possibil|permett|consent|gestisc|support|disponibil|funzion|riusc|abbiamo|offr)|manca(?:no)?\b|assenz[ae]|inadeguat|impossibil|error[ei]|duplicazion|ricopi|incompatibil|obsolet|insufficient|limitat|manualment',re.I)
PROCESS_CONTEXT=re.compile(r'ordin[ei]|preventiv|prenotazion|configurator|multilistino|portale|gestional|software|excel|email|e-mail|modul[oi]|area riservata|integrazion.{0,30}(?:sistem|dati|erp)|\bERP\b|\bCRM\b',re.I)
UNAVAILABLE_SOLUTION=re.compile(r'\bnon\s+(?:è|sono|risulta|risultano)\s+(?:(?:ancora|più|attualmente)\s+)?(?:disponibil\w*|operativ\w*|accessibil\w*|possibile\s+(?:effettuare|inviare|accedere|ordinare))|\b(?:sito|portale|shop|piattaforma|accesso)\b[^.!?\n]{0,80}\b(?:sospes\w*|bloccato|non funziona|in progettazione)|\b(?:sarà|saranno)\s+(?:presto\s+)?(?:disponibil\w*|operativ\w*|online)',re.I)


def grounded_kind(kind,quote):
    from .research_rules import REQUEST,FULL,CLOSED_REQUEST
    if kind=='counterevidence' and UNAVAILABLE_SOLUTION.search(quote) and not CLOSED_REQUEST.search(quote):
        # A literal quote can still be mislabelled: an unavailable/future tool
        # is not an operating solution. Do not turn that mistake into a new gap
        # or buying need either; keep the original statement as context.
        return 'business'
    if kind=='condition':
        from .commercial_inference import declared_condition
        if not declared_condition(quote):return 'business'
    if kind=='gap' and not (DIGITAL_CONTEXT.search(quote) and NEGATIVE.search(quote)):return 'business'
    if kind=='process' and not PROCESS_CONTEXT.search(quote):return 'business'
    if kind=='request' and not (REQUEST.search(quote) and FULL.search(quote)):return 'business'
    return kind


def grounded_signals(signals):
    result=[]
    for signal in signals:
        kind=grounded_kind(signal['kind'],signal['quote'])
        note=('La citazione dichiara una soluzione non disponibile o futura; non dimostra uno strumento operativo.'
              if signal['kind']=='counterevidence' else 'La citazione descrive l’attività, ma non documenta il bisogno digitale attribuito dal modello.')
        result.append({**signal,'kind':kind,**({'model_kind':signal.get('model_kind',signal['kind']),'classification_note':note} if kind!=signal['kind'] else {})})
    return result
