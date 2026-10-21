"""Canonical selectable spans. The model selects IDs; it does not copy proof.

IDs are scoped to a hashed evidence block and exact offsets. They cannot move
between results or survive a changed document. Legacy quote/offset responses
remain readable for historical replay, but new provider schemas use IDs only.
"""
import re
from sales.db import digest, encode


def segments(evidence):
    text = evidence['text']
    spans = set()
    # Sentence/line boundaries preserve punctuation and source offsets.
    for match in re.finditer(r'[^\n]+', text):
        start = match.start()
        for part in re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ý])', match[0]):
            pos = text.find(part, start, match.end())
            if pos < 0:
                continue
            for chunk in re.finditer(r'[^;|]+', part):
                a, b = pos + chunk.start(), pos + chunk.end()
                while a < b and text[a].isspace(): a += 1
                while b > a and text[b-1].isspace(): b -= 1
                if 0 < b-a <= 1500: spans.add((a, b))
            start = pos + len(part)
    # Small, literal anchors let identity/date/contact claims select their own
    # evidence without assigning a whole careers headline as a company name.
    patterns = (
        r'\b[A-ZÀ-Ý][\wÀ-ÿ&. -]{1,75}\s+(?:S\.?r\.?l\.?|S\.?p\.?A\.?|Ltd\.?|LLC)\b',
        r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',
        r'(?:Posted(?: on)?|Pubblicato(?: il)?|datePosted)\s*:?\s*(?:20\d{2}-\d{2}-\d{2}|\d+\s+(?:days?|weeks?)\s+ago)',
    )
    for pattern in patterns:
        spans.update((m.start(), m.end()) for m in re.finditer(pattern, text))
    # Legal ownership labels are not part of a company name. Preserve the
    # literal full name (including SRLS), rather than a whole footer sentence.
    legal = r'((?:[A-ZÀ-Ý][\wÀ-ÿ&.-]*\s+){1,6}(?:S\.?\s*r\.?\s*l\.?\s*s?\.?|S\.?\s*p\.?\s*A\.?|LLC|Ltd\.?))'
    for match in re.finditer(r'(?:proprietà di|ragione sociale\s*:|owned by|copyright\s*(?:©)?\s*20\d{2})\s+'+legal, text, re.I):
        a,b=match.span(1)
        while a<b and text[b-1] in '. ':b-=1
        spans.add((a,b))
    return [{'segment_id': 's'+digest(encode([evidence['id'], evidence['hash'], a, b]))[:20],
             'start': a, 'end': b, 'text': text[a:b]}
            for a, b in sorted(spans)]


def attach(evidence):
    return [{**e, 'segments': segments(e)} for e in evidence]


def provider_payload(payload):
    """Send each passage once; keep full text/hash/offsets in local validation.

    This projection also prevents metadata bloat from silently dropping the
    decisive end of a document when segment references are enabled.
    """
    if payload.get('task') not in ('RESEARCH_SCREEN_6','RESEARCH_READ_6','COMMERCIAL_DECISION_1'):
        return payload
    compact=(payload['task']=='COMMERCIAL_DECISION_1' and payload.get('reading_coverage_version')==1 and payload.get('unit_id') and all(
        e.get('unit_id')==payload['unit_id'] for e in payload.get('evidence',[])))
    if compact:
        # One isolated decision unit is already declared at payload level.
        # Group only identical sources; segment IDs retain block/hash/offset
        # binding in local validation. No text or source attribution is merged.
        sources={}
        for e in payload.get('evidence',[]):
            key=(e.get('url'),e.get('original'))
            source=sources.setdefault(key,{'url':key[0],'original':key[1],'segments':{}})
            source['segments'].update({s['segment_id']:s['text'] for s in segments(e)})
        return {**payload,'evidence':list(sources.values())}
    return {**payload,'evidence':[
        {**{k:e.get(k) for k in ('id','result_id','url','original','unit_id')},
         'segments':{s['segment_id']:s['text'] for s in segments(e)}}
        for e in payload.get('evidence',[])]}



def resolve(ref, evidence):
    """Never repair an unknown ID, cross-source reference or modified content."""
    from .schema import ValidationError
    if set(ref) != {'segment_id'} or not isinstance(ref['segment_id'], str):
        raise ValidationError('invalid_segment_reference')
    found = []
    for e in evidence:
        if e['hash'] != digest(e['text']):
            raise ValidationError('wrong_source', cause='content_hash_mismatch')
        # Recompute canonical spans: supplied metadata is not authority.
        for segment in segments(e):
            if segment['segment_id'] == ref['segment_id']:
                found.append({'id': e['id'], 'start': segment['start'], 'end': segment['end']})
    if len(found) != 1:
        raise ValidationError('unknown_or_ambiguous_segment')
    return found[0]
