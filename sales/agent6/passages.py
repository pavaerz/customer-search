"""Select original passages before inference; preserve exact source offsets.

An original is not fully reviewed merely because its introduction was read.
Selection is local to each document and never turns a match into qualification.
"""
import re
from sales.db import digest

INVITE = re.compile(r'cerch\w*|ricerch\w*|cercasi|richied\w*\s+(?:la\s+)?collaborazion\w*|collabora con noi|lavora con noi|'
                    r'candidatur\w*|posizion[ei]\s+apert\w*|portfolio\s+spontane\w*|'
                    r'looking for|seeking|join our|open positions?|vacanc\w*|unsolicited applications?|'
                    r'partita\s*iva|freelanc|contractor', re.I)
SCOPE = re.compile(r'web\s*(?:design|develop)|wordpress|frontend|front.end|e.?commerce|'
                   r'sit[oi]\s+(?:web|internet)|software|sviluppator', re.I)
IDENTITY = re.compile(r'\b(?:s\.?r\.?l\.?s?\.?|s\.?p\.?a\.?)\b|partita\s*iva|'
                      r'@[a-z0-9.-]+\.[a-z]{2,}|sede legale', re.I)

# Selection priority only. These conditions must reach the model alongside the
# request; a match is never a commercial decision or a compensation estimate.
CONDITIONS = re.compile(r'nessun[oa]?\s+(?:percepisce\s+)?(?:uno?\s+)?stipendio|'
    r'non\s+(?:retribuit|remunerat)|senza\s+(?:compenso|retribuzione)|'
    r'no\s+(?:salary|pay)|unpaid|equity|chiusura\s+del\s+primo\s+round|'
    r'compenso\s+(?:orario|giornaliero)|tariffa\s+(?:oraria|giornaliera)|hourly rate|per cui sei pagato|'
    r'non\s+(?:sto\s+)?cercando\s+un\s+programmatore|'
    r'(?:posizione|selezione|ricerca)\s+(?:è\s+)?chius|position\s+closed|'
    r'\b\d+\s*(?:[–-]\s*\d+\s*)?ore\s+settimanali|'
    r'smart\s*working\s+\d+\s+giorni|full\s*remote|tipologia\s+contrattuale|'
    r'non (?:ci sono|abbiamo) posizioni aperte|nessuna posizione aperta|no (?:open positions|current vacancies)',re.I)

ELIGIBILITY = re.compile(r'based in (?:a country|one of|the following)|right to work|'
    r'(?:applicants?|candidates?) (?:must|need|are required)|eligible (?:countries|locations)|'
    r'currently (?:employ|engage)|fully remote position|\bresident[ei]\b|\bresidenza\b|permesso di lavoro',re.I)


def source_lines(record):
    text=record.get('text','')
    ranges=record.get('structured_lines')
    if ranges is not None:
        return [(a,b,text[a:b]) for a,b in ranges if 0<=a<b<=len(text)]
    return [(m.start(),m.end(),m[0]) for m in re.finditer(r'[^\n]+',text)]


def invitation_spans(text):
    """Local technical invitations, including negatives that need interpretation."""
    for line in re.finditer(r'[^\n]+', text):
        if INVITE.search(line[0]) and SCOPE.search(line[0]) and not re.search(r'^\s*(?:cerchi (?:una?|il)|stai cercando (?:una?|il))\b',line[0],re.I):
            yield line.start(), line.end()


def bundle(records, limit=4500, *, compact=False):
    if sum(len(r.get('text','').encode()) for r in records)<=limit and not any(r.get('allowed_ranges') for r in records):
        return [{'id':'e'+str(i+1),'result_id':str(r['id']),'url':r['url'],
            'text':r.get('text',''),'hash':digest(r.get('text','')),'offset':0,
            'original':r.get('original',False),'document_id':r.get('document_id'),
            'checked_at':r.get('checked_at')} for i,r in enumerate(records) if r.get('text','').strip()]
    candidates=[]
    for order, record in enumerate(records):
        text=record.get('text','')
        # Overlapping windows retain the sentence and nearby contract conditions.
        lines=source_lines(record)
        spans=[(100,a,b) for a,b,line in lines if INVITE.search(line) and SCOPE.search(line)
               and not re.search(r'^\s*(?:cerchi (?:una?|il)|stai cercando (?:una?|il))\b',line,re.I)]
        # Explicit source-content ranges are local observations, not a score of
        # commercial need. The allowed ranges below still constrain every quote.
        spans.extend((50, a, b) for a, b in record.get('preferred_spans', []))
        # A role heading and its description are one informative section.
        # Requiring invitation and technology in the SAME line loses job lists.
        role_heading=re.compile(r'(?:(?:senior|junior)\s+)?(?:(?:web|ui\s*/?\s*ux|ux\s*/?\s*ui)\s+designer|(?:frontend|front.end|web|wordpress|woocommerce|full.stack)?\s*(?:developer|engineer)|e.?commerce\s+expert)',re.I)
        for index,(a,b,line) in enumerate(lines):
            if role_heading.fullmatch(line.strip()):
                end=lines[index+1][1] if index+1<len(lines) and lines[index+1][1]-a<1200 else b
                spans.append((145 if re.search(r'web designer|developer',line,re.I) else 135,a,end))
        for line_start,line_end,line in lines:
            if record.get('original') and re.search(r'lavor(?:i|a|are) (?:da )?(?:dove vuoi|ovunque)|work (?:from )?anywhere',line,re.I):
                end=next((e for a,e,t in lines if a>line_start and re.search(r'remoto|remote',t,re.I) and e-line_start<500),line_end)
                spans.append((145,line_start,end))
            if record.get('original') and CONDITIONS.search(line):
                terms=list(CONDITIONS.finditer(line))
                # Repeated remote-work marketing must not crowd out the actual
                # invitation. Closure, compensation and hours keep top priority.
                remote_only=all(re.fullmatch(r'full\s*remote',m[0],re.I) for m in terms)
                spans.append((95 if remote_only else 140,line_start,line_end))
            # Reserve small literal owner/contact anchors in the FIRST read,
            # instead of filling the payload with supplier marketing windows.
            if record.get('original'):
                from .completion import LEGAL
                owner=LEGAL.search(line)
                if owner:
                    a=line_start+owner.start();b=line_start+owner.end()
                    spans.append((130,a,b))
                if re.fullmatch(r'\s*[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\s*',line):spans.append((120,line_start,line_end))
                # Standalone role/technology labels can establish the scope of
                # an external talent invitation without implying an open job.
                if re.fullmatch(r'\s*(?:(?:senior|junior)\s+)?(?:frontend|front.end|web|wordpress|woocommerce|php|javascript|react|next[.]?js)\s+(?:developer|engineer)\s*',line,re.I):
                    spans.append((125,line_start,line_end))
                if re.search(r'(?:inviaci|inviateci|send us).{0,50}portfolio|'
                             r'(?:siamo|we are).{0,25}(?:ricerca di talent|looking for talent)',line,re.I):
                    spans.append((125,line_start,line_end))
            score=60 if INVITE.search(line) else 30 if IDENTITY.search(line) else 0
            if record.get('structured_lines') is not None:
                if CONDITIONS.search(line):spans.append((140,line_start,line_end))
                if ELIGIBILITY.search(line):spans.append((140,line_start,line_end))
                # Preserve role/skills and separately supplied metadata without
                # copying the long description prefix into every passage.
                structured_score=80 if (SCOPE.search(line) or re.search(
                    r'full.stack|co.?founder tecnic|React|Next[./ ]|Supabase|\bCTO\b',line,re.I)) else 10
                if re.search(r'(?m)^  "(?:title|name|datePosted|validThrough|employmentType|jobLocationType|applicantLocationRequirements|hiringOrganization|skills|url)"\s*:',line):
                    structured_score=max(structured_score,130)
                spans.append((structured_score,line_start,line_end))
            if compact and INVITE.search(line):
                # A full invitation (including an unrelated profession) is
                # more informative than a repeated "Lavora con noi" nav label.
                score=90 if len(line.strip())>80 else 40
            if score:spans.append((score,line_start,line_end))
        if record.get('structured_lines') is None:spans.append((20,0,min(len(text),600)))
        for score,a,b in spans:
            ranges=record.get('allowed_ranges') or [[0,len(text)]]
            allowed=next(((s,e) for s,e in ranges if s<=a and b<=e),None)
            if allowed is None:continue
            start=max(0,a-180)
            # Prefer complete lines; never rewrite, normalize or stitch quotations.
            start=text.rfind('\n',0,start)+1
            end=min(len(text),max(b+350,start+900),start+1400)
            if score>=120:start=a;end=b
            elif compact and score>=60:
                # Reserve the complete invitation/condition line before its
                # surroundings; leading marketing text must not displace it.
                start=a
                next_end=text.find('\n',b+1)
                end=next_end if next_end!=-1 and next_end-b<=350 else b
            if b-start>1400:start=a;end=min(len(text),a+1400)
            if record.get('structured_lines') is not None:start=a;end=b
            start=max(start,allowed[0]);end=min(end,allowed[1])
            if record.get('preferred_spans') and end < allowed[1] and text[end:end+1] != '\n':
                # Editorial windows must not manufacture a truncated company
                # name at the input boundary. Keep a complete line/sentence.
                boundary=text.rfind('\n',start,end)
                if boundary <= start:
                    complete=list(re.finditer(r'[.!?](?=\s|$)',text[start:end]))
                    if not complete:continue
                    boundary=start+complete[-1].end()
                end=boundary
            candidates.append((score,order,start,end,record))
    selected=[];remaining=limit
    for score,order,a,b,r in sorted(candidates,key=lambda v:(-v[0],v[1],v[2],-v[3])):
        # A tiny contact anchor must not exclude a larger invitation window
        # containing it (common on short careers pages). Still skip passages
        # already fully covered by a selected range.
        if any(order==o and s<=a and b<=e for o,s,e in selected):continue
        part=r.get('text','')[a:b]
        if compact and any(part==records[o]['text'][s:e] for o,s,e in selected):continue
        size=len(part.encode())
        if not part.strip() or size>remaining:continue
        selected.append((order,a,b));remaining-=size
    result=[]
    for order,a,b in selected:
        r=records[order];text=r['text'][a:b]
        result.append({'id':'e'+str(len(result)+1),'result_id':str(r['id']),
                       'url':r['url'],'text':text,'hash':digest(text),'offset':a,
                       'original':r.get('original',False),'document_id':r.get('document_id'),
                       'checked_at':r.get('checked_at')})
    return result


def coverage(records,evidence):
    out=[]
    for r in records:
        ranges=[(e['offset'],e['offset']+len(e['text'])) for e in evidence
                if e['result_id']==str(r['id']) and e['url']==r['url']]
        signals=[(a,b) for a,b in invitation_spans(r.get('text',''))
                 if not r.get('allowed_ranges') or any(s<=a and b<=e for s,e in r['allowed_ranges'])]
        out.append({'url':r['url'],'document_characters':len(r.get('text','')),
                    'selected_ranges':ranges,'invitation_spans':signals,
                    'uncovered_invitation_spans':[(a,b) for a,b in signals
                        if not any(s<=a and e>=b for s,e in ranges)],
                    'basis':'selected_passages_not_full_document_review'})
    return out


def recovery_bundle(records, signals, limit=4500):
    """Repair a missed invitation with its conditions and exact identity lines.

    No concatenated quotations: each range stays within its original document.
    Do not spend the repair payload on the same supplier introduction again.
    """
    selected=[]
    for record in records:
        text=record.get('text','');ranges=[]
        for signal in signals:
            if signal.get('url')!=record['url']:continue
            start=max(0,signal['start']-180);start=text.rfind('\n',0,start)+1
            end=min(len(text),signal['end'])
            # Respect a known ad boundary when recovering a multi-unit page.
            unit=next((u for u in record.get('document_units',[]) if u['start']<=signal['start']<u['end']),None)
            if unit:start=max(start,unit['start']);end=min(end,unit['end'])
            ranges.append([start,end])
        if not ranges:continue
        for line in re.finditer(r'[^\n]+',text):
            if IDENTITY.search(line[0]):ranges.append(list(line.span()))
        selected.append({**record,'allowed_ranges':ranges})
    return bundle(selected,limit)
