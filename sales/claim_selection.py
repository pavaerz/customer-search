"""The model selects source spans; all quotations are reconstructed locally.

No fuzzy quotation repair, no snippets and no generated facts. Offsets refer to
exact text shown to the model and stay within each original document chunk.
"""
import re
from .db import digest

KINDS=['event','business','gap','condition','process','request','scope','counterevidence','budget','risk']


def evidence_units(document_id,text,maximum=500):
    units=[]
    # Preserve full short paragraphs and split only at visible whitespace.
    # Windows overlap long paragraphs so a fact crossing one edge is not lost.
    spans=[]
    for paragraph in re.finditer(r'[^\n]+',text):
        if spans and paragraph.end()-spans[-1][0]<=maximum:
            spans[-1]=(spans[-1][0],paragraph.end())
        else:spans.append((paragraph.start(),paragraph.end()))
    for start,end in spans:
        while start<end:
            stop=min(start+maximum,end)
            if stop<end:
                boundary=text.rfind(' ',start+maximum//2,stop)
                if boundary>start:stop=boundary
            quote=text[start:stop].strip()
            if len(quote)>=18:
                offset=start+len(text[start:stop])-len(text[start:stop].lstrip())
                units.append({'id':digest(document_id+':'+str(offset)+':'+quote)[:16],
                              'text':quote,'start':offset,'end':offset+len(quote)})
            if stop>=end:break
            start=max(start+1,stop-80)
            nextword=text.find(' ',start,stop)
            if nextword>=0:start=nextword+1
    return units


def grounded_units(document_id,text,original):
    """Do not merge across content removed by the commercial HTML extractor.

    A cleaned page may join two paragraphs separated by navigation or a consent
    panel in the archived source. Keep only contiguous literal source fragments;
    never repair a quotation or relax the later source check.
    """
    from .research_rules import normalize
    source=normalize(original);out=[];seen=set()
    for unit in evidence_units(document_id,text):
        pieces=[unit] if normalize(unit['text']) in source else []
        if not pieces:
            for line in re.finditer(r'[^\n]+',unit['text']):
                quote=line[0].strip()
                if len(quote)<18 or normalize(quote) not in source:continue
                start=unit['start']+line.start()+len(line[0])-len(line[0].lstrip())
                pieces.append({'id':digest(document_id+':'+str(start)+':'+quote)[:16],
                               'text':quote,'start':start,'end':start+len(quote)})
        for piece in pieces:
            if piece['id'] not in seen:seen.add(piece['id']);out.append(piece)
    return out


def selection_schema(units):
    return {'type':'object','properties':{'claims':{'type':'array','maxItems':8,'items':{
        'type':'object','properties':{'unit_id':{'type':'string','enum':[u['id'] for u in units]},
        'kind':{'type':'string','enum':KINDS}},'required':['unit_id','kind'],'additionalProperties':False}}},
        'required':['claims'],'additionalProperties':False}


def materialize(document_id,text,units,response):
    index={u['id']:u for u in units};claims=[];errors=[];seen=set()
    if not isinstance(response,dict) or not isinstance(response.get('claims'),list):
        return [],['Selezione delle prove non strutturata']
    for selected in response['claims']:
        if not isinstance(selected,dict) or set(selected)!={'unit_id','kind'}:
            errors.append('Selezione non valida: ammessi soltanto ID di estratti e tipo di prova');continue
        unit=index.get(selected['unit_id']);kind=selected['kind']
        if not unit or kind not in KINDS or text[unit['start']:unit['end']]!=unit['text']:
            errors.append('Estratto selezionato non riscontrato nel testo originale');continue
        key=(unit['id'],kind)
        if key in seen:continue
        seen.add(key);claims.append({'document_id':document_id,'kind':kind,'quote':unit['text']})
    return claims,errors
