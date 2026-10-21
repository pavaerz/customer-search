"""Public generic contacts are observations, not invented application instructions."""
import copy
import gzip
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import test_ai_first_response_channels as h
from sales.agent6 import decision, grounding, response_channels as channels


class OwnerContacts(unittest.TestCase):
    def test_saved_sinfonia_plain_footer_mailbox_has_original_proof(self):
        page=json.loads(gzip.decompress((Path(__file__).parent/
            'fixtures/ai_first/followup53/sinfonia-page.json.gz').read_bytes()))
        identity={'name':'Sinfonia sc','website':'https://www.sinfonialab.it/'}
        found=channels.collect(page,{'origin':'page'},identity,True)
        mail=next(c for c in found if c['value']=='info@sinfonialab.it')
        self.assertEqual(mail['observation_kind'],'general_owner_mailbox')
        self.assertIn(mail['value'],mail['label'])
        docs,proofs,offered=channels.documents(page,'saved-original','unit',found)
        p={'identity':{'name':'Sinfonia sc','domain':'sinfonialab.it'},'unit_id':'unit',
           'evidence':grounding.attach(proofs),'response_channels':offered}
        observations=channels.general_observations(p,True)
        self.assertEqual([x['value'] for x in observations],['info@sinfonialab.it'])
        self.assertEqual(observations[0]['checked_at'],page['checked_at'])
        self.assertTrue(any(d['id']==proofs[0]['document_id'] for d in docs))

    def test_observation_does_not_become_selected_contact_or_make_ready(self):
        p,_=h.payload('<footer><address>info@alfa.example</address></footer>')
        out=h.h.response(p)
        out['facts']=[f for f in out['facts'] if f['field']!='contact']
        b=h.materialize(p,out)
        self.assertEqual(b['contacts'],[])
        self.assertEqual([c['value'] for c in b['observed_owner_contacts']],['info@alfa.example'])
        self.assertFalse(decision.projection(b)['CONTACT_AVAILABLE'])
        self.assertFalse(decision.projection(b)['READY_FOR_OUTREACH'])
        # A cited pertinent channel remains the normal AI selection path.
        b=h.materialize(p)
        self.assertEqual([c['value'] for c in b['contacts']],['info@alfa.example'])
        self.assertEqual(b['observed_owner_contacts'],[])

    def test_generic_visible_contact_scope_required(self):
        for html in ('<footer>info@alfa.example</footer>',
                     '<address>INFO@alfa.example</address>',
                     '<section id="contatti">info@alfa.example</section>'):
            self.assertEqual(len(h.collect(html)),1,html)
        for html in ('<p>info@alfa.example</p>',
                     '<footer><blockquote>info@alfa.example</blockquote></footer>',
                     '<footer><!-- info@alfa.example --></footer>',
                     '<footer><script>info@alfa.example</script></footer>',
                     '<footer><div hidden>info@alfa.example</div></footer>',
                     '<footer><div aria-hidden="true">info@alfa.example</div></footer>',
                     '<footer><span style="display:none">info@alfa.example</span></footer>',
                     '<footer><div class="comments">info@alfa.example</div></footer>',
                     '<footer><div class="privacy">info@alfa.example</div></footer>',
                     '<footer><div class="clients">info@alfa.example</div></footer>',
                     '<footer><p>privacy@alfa.example dpo@alfa.example diego@alfa.example</p></footer>',
                     '<footer>info@other.example info@alfa.example.evil.test</footer>'):
            self.assertEqual(h.collect(html),[],html)

    def test_no_publisher_social_job_card_or_unverified_identity(self):
        for origin in ('labelled_card','JobPosting','SocialMediaPosting'):
            self.assertEqual(h.collect('<footer>info@alfa.example</footer>',origin=origin),[])
        self.assertEqual(h.collect('<footer>info@alfa.example</footer>',owner=False),[])
        p,_=h.payload('<footer>info@alfa.example</footer>')
        self.assertEqual(channels.general_observations(p,False),[])

    def test_proof_cannot_be_borrowed_or_changed(self):
        p,_=h.payload('<footer>info@alfa.example</footer>')
        self.assertEqual(len(channels.general_observations(p,True)),1)
        for field,value in [('unit_id','other'),('url','https://other.example/'),
                            ('original',False),('origin','snippet'),('hash','bad')]:
            altered=copy.deepcopy(p)
            proof=next(e for e in altered['evidence'] if e['id']==altered['response_channels'][0]['evidence_id'])
            proof[field]=value
            self.assertEqual(channels.general_observations(altered,True),[],field)
        p['response_channels'][0]['value']='cv@alfa.example'
        self.assertEqual(channels.general_observations(p,True),[])

    def test_duplicate_footer_addresses_and_link_not_duplicated(self):
        found=h.collect('<footer>info@alfa.example info@alfa.example</footer>')
        self.assertEqual(len(found),1)
        found=h.collect('<footer><a href="mailto:info@alfa.example">info@alfa.example</a></footer>')
        self.assertEqual(len(found),1)
        self.assertNotIn('observation_kind',found[0])

    def test_ui_shows_source_and_limitation_without_inventing_readiness(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const text=fs.readFileSync('static/worklist.js','utf8');
const start=text.indexOf('function agentResponseChannel('),end=text.indexOf('function agent9Assessment(',start);
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const ctx={esc,link:(u,t)=>'<a href="'+esc(u)+'">'+esc(t)+'</a>'};
vm.createContext(ctx);vm.runInContext(text.slice(start,end),ctx);
assert.equal(ctx.agentObservedContacts({}),'');
const html=ctx.agentObservedContacts({observed_owner_contacts:[{type:'email',value:'<img src=x onerror=1>',url:'https://alfa.example/contact',checked_at:'2026-10-20T12:00:00Z'}]});
assert(!html.includes('<img'));assert(html.includes('&lt;img'));
assert(html.includes('Recapito generale'));assert(html.includes('Fonte del contatto'));
assert(html.includes('da confermare'));assert(html.includes('nessun invio effettuato'));
assert(html.includes('2026-10-20'));
"""
        subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)

    def test_reader_preserves_observation_without_an_extra_ai_call(self):
        base=h.h.IntegratedPath();base.setUp()
        try:
            original=h.page('<title>Alfa Srl</title>'+''.join('<p>'+line+'</p>'
                for line in h.h.TEXT.splitlines() if '@' not in line)
                +'<footer><address>info@alfa.example</address></footer>')
            base.w.enqueue('candidate','AGENCIES',{'url':original['url']},'owner-mailbox')
            with base.store.connect() as db:
                row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='owner-mailbox'").fetchone()
                task={**dict(row),'payload':json.loads(row['payload'])}
            def provider(p,cfg,check):
                out=h.h.response(p)
                # Synthetic output deliberately omits contact selection.
                out['facts']=[f for f in out['facts'] if f['field']!='contact']
                out['subject_geography']['fact_indices']=[2]
                return {'output':out,'usage':{}}
            with patch('sales.agent6.research.CompanyWeb.get',return_value=original),patch(
                    'sales.agent6.research.identity_from',return_value=h.IDENTITY),patch(
                    'sales.agent6.research.locate',return_value={'eligible':True,'regions':['Veneto'],'remote_italy':False}),patch(
                    'sales.agent6.ai.infer',side_effect=provider) as ai:
                base.w.execute(task,lambda:None)
            self.assertEqual(ai.call_count,1)
            with base.store.connect() as db:
                b=json.loads(db.execute('SELECT body FROM agent6_records ORDER BY id DESC').fetchone()[0])
                docs=[r[0] for r in db.execute('SELECT text FROM research_documents')]
            self.assertEqual(b['contacts'],[])
            self.assertEqual([c['value'] for c in b['observed_owner_contacts']],['info@alfa.example'])
            self.assertTrue(any('"observation_kind": "general_owner_mailbox"' in d for d in docs))
            self.assertFalse(decision.projection(b)['READY_FOR_OUTREACH'])
        finally:
            base.tearDown()


if __name__=='__main__':
    unittest.main()
