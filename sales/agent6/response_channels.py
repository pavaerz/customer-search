"""Observable response controls on a verified owner's original page.

No submissions, destination downloads or invented contact addresses. A linked
application destination is a published instruction, not a verified open job.
"""
import ipaddress
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, unquote

from sales.db import digest, domain
from sales.providers import canonical
from sales.content_policy import skip_pdf
from sales.commercial.identity import owner_html

APPLICATION = re.compile(r'candid|invia.{0,25}(?:cv|curriculum|portfolio)|apply|application\s+form|submit.{0,25}(?:application|resume|portfolio)', re.I)
NETWORK_JOIN = re.compile(r'(?:entra|unisciti|iscriviti|diventa|crea.{0,15}profilo|join|register|become).{0,80}(?:talent|freelance|developer|professionist|collaborator)', re.I)
CONTACT = re.compile(r'contatt|contact|scrivici|send.{0,12}message|invia.{0,12}messaggio', re.I)
EXCLUDED = re.compile(r'comment|review|testimonial|newsletter|subscribe|login|sign.?in|privacy|gdpr|reclamo|complaint|client.logo|partner.logo|third.party', re.I)
VOID = {'input','br','hr','img','meta','link','source','area','base','embed','param','wbr'}
EMAIL = re.compile(r'(?<![\w.+@-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w@-])')
GENERAL_MAILBOX = re.compile(r'(?:info|contatti|contact|hello|office|segreteria|commerciale|sales|hr|jobs|careers|cv|recruiting)',re.I)


def public_url(raw, base):
    try:
        url = canonical(urljoin(base, raw))
        p = urlsplit(url)
        host = p.hostname
        if not host or '.' not in host or host.endswith(('.local','.localhost','.internal')):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        if skip_pdf(url) or re.search(r'logout|delete|unsubscribe|checkout|[?&](?:token|key|auth|action|session)=',unquote(url),re.I):
            return None
        return url
    except (TypeError,ValueError):
        return None


class Controls(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.forms = []
        self.links = []
        self.public_mailboxes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        inherited = bool(self.stack and self.stack[-1]['excluded'])
        excluded = inherited or tag in ('script','style','template','noscript') or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
        excluded = excluded or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',attrs.get('style',''),re.I))
        excluded = excluded or bool(EXCLUDED.search(' '.join(attrs.get(k,'') or '' for k in ('id','class','aria-label','name','role'))))
        contact_scope = tag in ('footer','address') or bool(re.search(
            r'(?:^|[\s_-])(?:contacts?|contatti)(?:$|[\s_-])',
            ' '.join(attrs.get(k,'') or '' for k in ('id','class')),re.I))
        third_party_scope = bool(re.search(
            r'client|customer|partner|portfolio|testimonial|fornitor|supplier',
            ' '.join(attrs.get(k,'') or '' for k in ('id','class','aria-label')),re.I))
        item = {'tag':tag,'excluded':excluded,'contact_scope':contact_scope,
                'third_party_scope':third_party_scope}
        if not excluded and tag in ('a','form'):
            item['control'] = {'tag':tag,'attrs':{k:v for k,v in attrs.items() if k in ('href','action','id','aria-label')},'text':[],'fields':[]}
            (self.links if tag == 'a' else self.forms).append(item['control'])
        if not excluded and tag in ('input','textarea'):
            form = next((x['control'] for x in reversed(self.stack) if x['tag']=='form' and 'control' in x),None)
            kind = attrs.get('type','text').lower() if tag=='input' else 'textarea'
            if form is not None and kind not in ('hidden','submit','button','reset'):
                # Keep control names/types, never values, uploaded data or tokens.
                form['fields'].append({'type':kind,'name':(attrs.get('name') or '')[:100]})
        if tag not in VOID:
            self.stack.append(item)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i]['tag']==tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1]['excluded']:
            return
        for item in self.stack:
            if 'control' in item:
                item['control']['text'].append(data)
        # Only literal, visible generic mailboxes in an owner's contact scope.
        # An address inside prose, a quotation or an application link remains
        # subject to normal citation/attribution rather than this observation.
        if (any(x['contact_scope'] for x in self.stack)
                and not any(x['tag'] in ('a','form','blockquote','q') or x['third_party_scope'] for x in self.stack)):
            for match in EMAIL.finditer(data):
                value=match.group()
                if GENERAL_MAILBOX.fullmatch(value.split('@')[0]):
                    self.public_mailboxes.append({'tag':'public_email','attrs':{'value':value},
                        'text':[data.strip()[:400]],'fields':[]})


def collect(page, unit, identity, owner_verified):
    """No publisher, social footer, listing-card or unrelated job contacts."""
    if not owner_verified or unit.get('origin')!='page' or unit.get('discussion_scope'):
        return []
    host = domain(identity.get('website') or '')
    if not host or domain(page['url']) != host:
        return []
    controls = Controls(owner_html(page['html']))
    found = []
    # A dedicated application control must survive the bounded evidence packet,
    # even when navigation exposes many generic phone/contact controls first.
    candidates = controls.links + controls.forms + controls.public_mailboxes
    if unit.get('career_role'):
        scoped=Controls(unit['career_role']['html'])
        # Application controls belong to this role only. Generic owner mail
        # and phone remain usable without inheriting another role's form.
        candidates=scoped.links+scoped.forms+scoped.public_mailboxes+[
            c for c in candidates if c['tag']=='public_email' or
            c['tag']=='a' and (c['attrs'].get('href') or '').lower().startswith(('mailto:','tel:'))]
    candidates.sort(key=lambda c: 0 if (APPLICATION.search(
        ' '.join(c['text'])+' '+str(c['attrs'].get('aria-label') or '')) or NETWORK_JOIN.search(
        ' '.join(c['text'])+' '+str(c['attrs'].get('aria-label') or ''))) else
        1 if c['tag']=='public_email' else 2)
    for control in candidates:
        attrs = control['attrs']
        label = re.sub(r'\s+',' ',' '.join(control['text'])).strip()[:400]
        hint = label+' '+str(attrs.get('aria-label') or '')
        if control['tag']=='a' and EXCLUDED.search(hint):
            continue
        if control['tag']=='form' and re.search(r'newsletter|subscribe|login|sign.?in|reclamo|complaint',hint,re.I):
            continue
        kind = None
        if control['tag']=='public_email':
            value=attrs['value']
            if domain('https://'+value.split('@')[-1])!=host:
                continue
            kind='email'
        elif control['tag']=='a':
            raw = attrs.get('href') or ''
            if raw.lower().startswith('mailto:'):
                # Preserve an address published only in href (e.g. "Invia CV").
                # Never retain subject/body/CC, use multiple recipients, infer
                # a mailbox or attribute a third-party address to this owner.
                value = unquote(raw[7:].split('?',1)[0])
                if (not re.fullmatch(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',value)
                        or domain('https://'+value.split('@')[-1]) != host
                        or re.search(r'(?:^|[._+-])(?:privacy|dpo|gdpr|abuse)(?:$|[._+-])',
                                     value.split('@')[0],re.I)):
                    continue
                kind = 'email'
            elif raw.lower().startswith('tel:'):
                value = unquote(raw[4:])
                if not re.fullmatch(r'\+?[\d () .-]{6,30}',value) or not 6<=len(re.sub(r'\D','',value))<=18:
                    continue
                kind = 'phone'
            elif APPLICATION.search(hint) or NETWORK_JOIN.search(hint):
                value = public_url(raw,page['url'])
                if not value or value==canonical(page['url']):
                    continue
                kind = 'application_link'
        else:
            fields = control['fields']
            has_email = any(f['type']=='email' or re.fullmatch(r'(?:your[-_])?e?mail',f['name'],re.I) for f in fields)
            has_message = any(f['type']=='textarea' or f['type']=='file' and APPLICATION.search(hint) for f in fields)
            destination = public_url(attrs.get('action') or page['url'],page['url'])
            if (has_email and has_message and (APPLICATION.search(hint) or CONTACT.search(hint))
                    and destination and not any(f['type']=='password' for f in fields)):
                # The channel remains the owner's page even when its form uses
                # an external processor. Never expose/call a submission action.
                kind,value = 'contact_form',canonical(page['url'])
        if not kind:
            continue
        proof = {'type':kind,'value':value,'label':label,
                 'observation':'Published control on original page; no submission or delivery verification.'}
        if kind=='application_link' and NETWORK_JOIN.search(hint):
            proof.update(observation_kind='network_join_instruction',
                         observation='Published invitation to join a professional network; no current paid assignment or destination availability verified.')
        if control['tag']=='public_email':
            proof.update(observation_kind='general_owner_mailbox',
                observation='Literal generic mailbox in the verified owner contact section. Application relevance and delivery not verified.')
        if control['tag']=='form':
            proof['fields'] = control['fields'][:12]
        if any(x['type']==kind and x['value']==value for x in found):
            continue
        found.append({**proof,'url':page['url'],'actor':identity.get('name')})
        if len(found)==6:
            break
    return found


def documents(page, parent_document, unit_id, channels):
    docs, proofs, offered = [], [], []
    for channel in channels:
        text = json.dumps({k:channel[k] for k in ('type','value','label','observation','observation_kind','fields') if k in channel},ensure_ascii=False,indent=2)
        did = digest(page['url']+':response-control:'+text)
        eid = 'response'+did[:16]
        docs.append({'id':did,'url':page['url'],'text':text,'content_hash':digest(text),
                     'title':'Canale di risposta osservato','checked_at':page['checked_at'],
                     'provider':'Controllo HTML originale, nessun invio','parent_document_id':parent_document})
        proofs.append({'id':eid,'result_id':unit_id,'unit_id':unit_id,'url':page['url'],
                       'text':text,'hash':digest(text),'document_id':did,'offset':0,
                       'original':True,'checked_at':page['checked_at'],'origin':'original_response_control'})
        offered.append({**channel,'evidence_id':eid})
    return docs, proofs, offered


def general_observations(payload, verified):
    """Keep measured generic contacts separate from AI-selected response channels."""
    if not verified:
        return []
    host=domain('https://'+str(payload.get('identity',{}).get('domain') or ''))
    result=[]
    for channel in payload.get('response_channels',[]):
        if (channel.get('observation_kind')!='general_owner_mailbox'
                or channel.get('type')!='email' or domain(channel.get('url',''))!=host):
            continue
        value=channel.get('value','')
        if (not EMAIL.fullmatch(value) or not GENERAL_MAILBOX.fullmatch(value.split('@')[0])
                or domain('https://'+value.split('@')[-1])!=host):
            continue
        proof=next((e for e in payload.get('evidence',[]) if
            e.get('id')==channel.get('evidence_id') and e.get('original')
            and e.get('origin')=='original_response_control' and e.get('url')==channel['url']
            and e.get('unit_id')==payload.get('unit_id')),None)
        if not proof:
            continue
        try:
            observed=json.loads(proof['text'])
        except (ValueError,KeyError):
            continue
        if (observed.get('value')!=value or observed.get('observation_kind')!='general_owner_mailbox'
                or proof.get('hash')!=digest(proof['text'])):
            continue
        result.append({'type':'email','value':value,'url':channel['url'],
            'checked_at':proof.get('checked_at'),'evidence_id':proof['id'],
            'attribution':'observed_general_owner_mailbox','actor':payload['identity'].get('name'),
            'verification':'Public generic owner mailbox; application relevance and delivery not verified.'})
    return list({(c['value'],c['url']):c for c in result}.values())


def attributed(fact, payload, verified):
    if not verified:
        return []
    host = domain('https://'+str(payload.get('identity',{}).get('domain') or ''))
    return [{'type':c['type'],'value':c['value'],'url':c['url'],'actor':c['actor'],
             'attribution':'observed_owner_response_control',
             'verification':'Published on original source; destination availability and delivery not tested.'}
            for c in payload.get('response_channels',[])
            if c['evidence_id']==fact['id'] and c['url']==fact['url']
            and domain(c['url'])==host and c['value'] in fact['quote']]
