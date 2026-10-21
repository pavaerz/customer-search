"""Offline channel extraction and attribution. No real forms are submitted."""
import json
import unittest
from unittest.mock import patch

import test_ai_first as h
from sales.agent6 import response_channels as channels, decision, grounding

IDENTITY={'name':'Alfa Srl','website':'https://alfa.example/','identity_status':'verified'}
FORM='<form action="/send"><label>Email<input type="email" name="email"></label><textarea name="message"></textarea><input type="hidden" value="secret-never-retain"><button>Invia messaggio</button><label>Accetto la privacy</label></form>'
LINK='<a href="https://jobs.example/apply/alfa">Invia candidatura freelance</a>'


def page(html):
    return {'url':'https://alfa.example/collabora','html':html,'checked_at':h.DATE,'status':200}


def collect(html,origin='page',owner=True):
    return channels.collect(page(html),{'origin':origin},IDENTITY,owner)


def payload(html):
    p=h.payload()
    docs,proofs,offered=channels.documents(page(html),'doc1','unit1',collect(html))
    p['evidence']=grounding.attach(p['evidence']+proofs)
    p['response_channels']=offered
    return p,docs


def output(p):
    out=h.response(p)
    channel=p['response_channels'][0]
    segment=next(s for e in p['evidence'] if e['id']==channel['evidence_id']
                 for s in grounding.segments(e) if channel['value'] in s['text'])
    out['facts'][2]={'field':'contact','segment_id':segment['segment_id']}
    return out


def materialize(p,out=None):
    out,_=decision.validate(out or output(p),p)
    return decision.materialize({'url':page('')['url'],'checked_at':h.DATE,'original':True},
                                out,p['evidence'],p,'AGENCIES')


class ResponseControls(unittest.TestCase):
    def test_original_form_and_external_application_link_not_a_submission(self):
        found=collect(FORM+LINK+'<a href="tel:+39 049 123456">Telefono</a>')
        self.assertEqual({x['type'] for x in found},{'contact_form','phone','application_link'})
        p,docs=payload(FORM)
        self.assertNotIn('secret-never-retain',json.dumps((p,docs)))
        b=materialize(p)
        self.assertEqual(b['contacts'][0]['type'],'contact_form')
        self.assertTrue(decision.projection(b)['READY_FOR_OUTREACH'])
        self.assertEqual(b['open_paid_project'],'UNKNOWN')
        self.assertIsNone(b['budget']['amount'])
        self.assertIn('delivery not tested',b['contacts'][0]['verification'])
        p,_=payload(LINK)
        self.assertTrue(decision.projection(materialize(p))['CONTACT_AVAILABLE'])
        external=collect(FORM.replace('action="/send"','action="https://forms.example/send"'))
        self.assertEqual(external[0]['value'],page('')['url'])
        self.assertNotIn('forms.example',json.dumps(external))

    def test_no_borrowed_channels_from_publishers_social_listings_or_comments(self):
        for origin in ('labelled_card','JobPosting','SocialMediaPosting'):
            self.assertEqual(collect(FORM+LINK,origin=origin),[])
        self.assertEqual(collect(FORM+LINK,owner=False),[])
        for wrapper in ('<div class="comments">{}</div>','<div id="testimonials">{}</div>',
                        '<div hidden>{}</div>','<div style="display: none">{}</div>',
                        '<script>{}</script>','<div class="client-logo">{}</div>'):
            self.assertEqual(collect(wrapper.format(LINK)),[])
        self.assertEqual(channels.collect(page(LINK),{'origin':'page'},
                                         {**IDENTITY,'website':'https://other.example'},True),[])

    def test_newsletter_login_search_privacy_and_unsafe_forms_are_not_channels(self):
        for html in (
            '<form><input type="email"><button>Newsletter</button></form>',
            '<form><input type="email"><input type="password"><textarea></textarea><button>Contattaci</button></form>',
            '<form><input name="q"><button>Cerca</button></form>',
            '<form id="privacy-complaint"><input type="email"><textarea></textarea><button>Contattaci</button></form>',
            FORM.replace('action="/send"','action="http://127.0.0.1/send"'),
            '<a href="https://jobs.example/privacy">Candidature: informativa privacy</a>',
            '<a href="tel:*123#">Telefono</a>',
        ):
            self.assertEqual(collect(html),[],html)

    def test_application_destinations_cannot_be_pdf_private_or_mutating(self):
        for url in ('javascript:alert(1)','file:///tmp/test','https://127.0.0.1/apply',
                    'https://localhost/apply','https://jobs.local/apply',
                    'https://jobs.example/cv.pdf','https://jobs.example/apply?token=secret',
                    'https://user:pass@jobs.example/apply','https://jobs.example/delete'):
            self.assertEqual(collect('<a href="'+url+'">Invia candidatura</a>'),[],url)

    def test_contact_fact_must_select_observed_proof_not_an_invented_or_other_unit(self):
        p,_=payload(LINK)
        out=output(p)
        p['response_channels'][0]['evidence_id']='other'
        self.assertEqual(materialize(p,out)['contacts'],[])
        p,_=payload(LINK)
        p['response_channels'][0]['url']='https://other.example/'
        self.assertEqual(materialize(p)['contacts'],[])
        p,_=payload(LINK)
        out=h.response(p)  # Email selected; an unused offered form isn't a contact.
        self.assertEqual([x['type'] for x in materialize(p,out)['contacts']],['email'])

    def test_contacts_preserve_crm_and_public_readiness(self):
        p,_=payload(LINK)
        b=materialize(p)
        from sales.db import Store
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'crm.db')
            store.init()
            cid=store.company('https://alfa.example','Alfa Srl',contacts=b['contacts'])
            with store.connect() as db:
                saved=json.loads(db.execute('SELECT contacts FROM companies WHERE id=?',(cid,)).fetchone()[0])
            self.assertEqual(saved,b['contacts'])

    def test_a_response_channel_does_not_make_a_course_or_supplier_interesting(self):
        p,_=payload('<a href="https://training.example/register">Candidati al corso</a>')
        out=output(p)
        out.update(decision='NOT_INTERESTING',reason='È una candidatura al corso, non una richiesta di lavoro.',
                   relationship='UNKNOWN',currentness='UNKNOWN')
        b=materialize(p,out)
        self.assertFalse(decision.projection(b)['READY_FOR_OUTREACH'])
        self.assertFalse(decision.projection(b)['OPPORTUNITY_QUALIFIED'])

    def test_control_ui_labels_escape_untrusted_text_and_do_not_send(self):
        import subprocess
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const text=fs.readFileSync('static/worklist.js','utf8');
const start=text.indexOf('function agentResponseChannel('),end=text.indexOf('function agent9Assessment(',start);
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const ctx={esc,link:(u,t)=>'<a href="'+esc(u)+'">'+esc(t)+'</a>'};
vm.createContext(ctx);vm.runInContext(text.slice(start,end),ctx);
let html=ctx.agentResponseChannel({type:'application_link',value:'https://jobs.example/apply',url:'https://alfa.example/jobs',attribution:'observed_owner_response_control'});
assert(html.includes('Link per candidarsi'));assert(html.includes('nessun invio effettuato'));
html=ctx.agentResponseChannel({type:'phone',value:'<img src=x onerror=alert(1)>',url:'https://alfa.example'});
assert(!html.includes('<img'));assert(html.includes('&lt;img'));
"""
        subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)


class OriginalRead(unittest.TestCase):
    def test_reader_persists_form_proof_and_ready_card_without_email(self):
        base=h.IntegratedPath();base.setUp()
        try:
            original=page('<title>Alfa Srl</title>'+''.join('<p>'+line+'</p>' for line in h.TEXT.splitlines() if '@' not in line)+FORM)
            base.w.enqueue('candidate','AGENCIES',{'url':original['url']},'form-read')
            with base.store.connect() as db:
                row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='form-read'").fetchone()
                task={**dict(row),'payload':json.loads(row['payload'])}
            observed=[]
            def provider(p,cfg,check):
                observed.append(p)
                # Build known response without making an email evidence claim.
                seed=h.response(h.payload())
                for i,(field,needle) in enumerate((('entity','Alfa Srl'),('request','Collaboriamo'),
                                                  ('contact','"value": "https://alfa.example/collabora"'))):
                    seg=next(s for e in p['evidence'] for s in grounding.segments(e) if needle in s['text'])
                    seed['facts'][i]={'field':field,'segment_id':seg['segment_id']}
                geo=next(s for e in p['evidence'] for s in grounding.segments(e) if 'Padova Veneto' in s['text'])
                seed['facts'].append({'field':'geography','segment_id':geo['segment_id']})
                seed['subject_geography']={'status':'IN_TARGET','region':'Veneto','fact_indices':[3],
                                          'reason':'Indirizzo esplicito nella fixture.'}
                return {'output':seed,'usage':{}}
            with patch('sales.agent6.research.CompanyWeb.get',return_value=original),patch(
                    'sales.agent6.research.identity_from',return_value=IDENTITY),patch(
                    'sales.agent6.research.locate',return_value={'eligible':True,'regions':['Veneto'],'remote_italy':False}),patch(
                    'sales.agent6.ai.infer',side_effect=provider):
                base.w.execute(task,lambda:None)
            self.assertEqual(len(observed),1)
            with base.store.connect() as db:
                b=json.loads(db.execute('SELECT body FROM agent6_records ORDER BY id DESC').fetchone()[0])
                texts=[r[0] for r in db.execute('SELECT text FROM research_documents')]
            self.assertTrue(decision.projection(b)['READY_FOR_OUTREACH'],b)
            self.assertTrue(any('"type": "contact_form"' in text for text in texts))
            self.assertNotIn('secret-never-retain',json.dumps(observed))
        finally:
            base.tearDown()
