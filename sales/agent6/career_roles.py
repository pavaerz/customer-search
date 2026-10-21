"""Literal role sections on verified owners' careers pages, not qualification.

Split only corroborated heading/body ranges. Never transfer another vacancy's
hours, location, contract or application link to the selected role.
"""
import re
from urllib.parse import urlsplit, urljoin
from sales.extract import Document
from sales.db import digest


def separate(page, packet, owner):
    if not owner or len(packet['units']) != 1 or packet['units'][0]['origin'] != 'page':
        return
    if not re.search(r'lavora[-_/ ]*con[-_/ ]*noi|careers?|jobs?|lavoro', urlsplit(page['url']).path, re.I):
        return
    html=page['html'];text=packet['units'][0]['text']
    headings=list(re.finditer(r'<h([12])\b[^>]*>.*?</h\1\s*>',html,re.I|re.S))
    roles=[]
    for i,h in enumerate(headings):
        title=Document(h[0]).text
        if not 4<=len(title)<=120:continue
        if re.search(r'candidatur|contatt|competenze|requisiti|come |perch[eé]|lavora con noi|application|contact us',title,re.I):continue
        end=headings[i+1].start() if i+1<len(headings) else len(html)
        fragment=html[h.start():end]
        footer=re.search(r'<footer\b',fragment,re.I)
        if footer:fragment=fragment[:footer.start()]
        parsed=Document(fragment);body=parsed.text
        # Multiple independent invitations, not sections of a services catalogue.
        if not re.search(r'cerchiamo|stiamo cercando|siamo alla ricerca|looking for|seeking',body,re.I):continue
        if not re.search(r'candidatur|application|apply|invia.{0,25}(?:CV|curriculum)',body,re.I):continue
        if len(body)<200 or text.count(body)!=1:continue
        start=text.index(body)
        roles.append({'id':packet['document_id']+':role:'+digest(title)[:16],
            'origin':'page','text':body,'offset':start,'dates':[],
            'career_role':{'title':title,'html':fragment,
                'links':list(dict.fromkeys(urljoin(page['url'],x['url']) for x in parsed.links)),
                'basis':'literal_heading_and_invitation_on_verified_owner'}})
    if len(roles)>=2 and len({r['id'] for r in roles})==len(roles):
        # A page-wide closure must not disappear when old individual roles
        # remain below it. Keep the whole page for this negative control.
        prefix=text[:roles[0]['offset']]
        if re.search(r'non (?:ci sono|abbiamo) posizioni aperte|nessuna posizione aperta|no (?:open positions|current vacancies)',prefix,re.I):
            return
        # Page metadata dates do not automatically date each vacancy.
        from .evidence import dates
        for r in roles:r['dates']=dates(r['text'],unit_id=r['id'])
        packet['units']=roles


def owner_proof(page, doc, unit, identity):
    """Exact visible owner name only, not another role's text or conditions."""
    if not unit.get('career_role'):return None
    name=identity.get('name') or ''
    matches=list(re.finditer(re.escape(name),doc['text'],re.I)) if name else []
    if not matches:return None
    m=matches[-1];part=m[0]
    return {'id':'role-owner','result_id':unit['id'],'unit_id':unit['id'],
        'url':page['url'],'text':part,'hash':digest(part),'document_id':doc['id'],
        'offset':m.start(),'original':True,'checked_at':page['checked_at']}
