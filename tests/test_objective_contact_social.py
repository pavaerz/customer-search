"""Saved real mailto regression and synthetic social URL contracts. No network."""
import gzip
import json
from pathlib import Path
import unittest

from sales.agent6 import evidence,social,social_seeds
from sales.commercial.inspection import document
import test_ai_first_response_channels as response
import test_ai_first_social as posts


class ApplicationEmail(unittest.TestCase):
    def test_real_kondividi_mailto_is_offered_with_literal_cv_label(self):
        source=Path(__file__).parent/'fixtures/ai_first/commercial-originals.json.gz'
        page=json.loads(gzip.decompress(source.read_bytes()))['A'][0]
        identity={'name':'Kondividi Srls','website':'https://kondividi.it/','identity_status':'verified'}
        found=response.channels.collect(page,{'origin':'page'},identity,True)
        cv=next(c for c in found if c['value']=='cv@kondividi.it')
        self.assertEqual(cv['type'],'email')
        self.assertEqual(cv['label'],'Invia il tuo CV')
        self.assertEqual(cv['url'],page['url'])
        docs,proofs,offered=response.channels.documents(page,'saved-original','unit',found)
        proof=next(p for p in proofs if p['id']==next(c['evidence_id'] for c in offered if c['value']==cv['value']))
        self.assertIn('"value": "cv@kondividi.it"',proof['text'])
        self.assertIn('"label": "Invia il tuo CV"',proof['text'])
        self.assertTrue(any(d['id']==proof['document_id'] for d in docs))

    def test_cited_mailto_survives_materialization_without_message_parameters(self):
        p,docs=response.payload('<a href="mailto:cv@alfa.example?subject=private-subject&amp;body=private-body&amp;cc=third@example.com">Invia CV</a>')
        self.assertNotIn('private-',json.dumps((p,docs)))
        self.assertNotIn('third@example.com',json.dumps((p,docs)))
        body=response.materialize(p)
        self.assertEqual([c['value'] for c in body['contacts']],['cv@alfa.example'])
        self.assertEqual(body['open_paid_project'],'UNKNOWN')
        # An uncited channel does not replace a contact fact selected by the AI.
        other=response.materialize(p,response.h.response(p))
        self.assertNotIn('cv@alfa.example',[c['value'] for c in other['contacts']])

    def test_no_third_party_privacy_multiple_or_injected_mailboxes(self):
        for address in ('cv@other.example','privacy@alfa.example','dpo@alfa.example',
                        'cv@alfa.example,third@alfa.example','cv@alfa.example%0ABcc:third@alfa.example',
                        'cv@alfa.example.evil.test','@alfa.example'):
            with self.subTest(address=address):
                self.assertEqual(response.collect('<a href="mailto:'+address+'">Invia CV</a>'),[])
        for attrs in ('class="comments"','hidden','class="privacy"'):
            self.assertEqual(response.collect('<div '+attrs+'><a href="mailto:cv@alfa.example">Invia CV</a></div>'),[])
        for origin in ('SocialMediaPosting','labelled_card','JobPosting'):
            self.assertEqual(response.collect('<a href="mailto:cv@alfa.example">Invia CV</a>',origin=origin),[])

    def test_dedicated_application_not_lost_to_six_generic_controls(self):
        html=''.join('<a href="tel:+39049123'+str(i)+'">Telefono</a>' for i in range(12))
        found=response.collect(html+'<a href="mailto:cv@alfa.example">Invia curriculum</a>')
        self.assertEqual(len(found),6)
        self.assertEqual(found[0]['value'],'cv@alfa.example')


class SocialReferenceAliases(unittest.TestCase):
    def test_known_aliases_preserve_post_identity_and_deduplicate_manual_input(self):
        a='https://www.instagram.com/p/Example/'
        b='https://instagram.com/p/Example/?igsh=discard'
        self.assertTrue(social.same_reference(a,b))
        self.assertEqual(social_seeds.normalize([a,b]),[a])
        self.assertTrue(social_seeds.links_post({'url':'https://owner.example/',
            'html':'<a href="'+b+'">Annuncio originale</a>'},a))
        self.assertTrue(social.same_reference('https://it.linkedin.com/jobs/view/123/?trk=feed',
                                             'https://www.linkedin.com/jobs/view/123'))

    def test_no_different_posts_profiles_hosts_or_unknown_parameters(self):
        a='https://www.instagram.com/p/Example/'
        for other in ('https://instagram.com/p/example/','https://instagram.com/p/Another/',
                      'https://instagram.com/Example/','https://instagram.com/reel/Example/',
                      'https://evil.instagram.com/p/Example/',
                      'https://instagram.com.evil.test/p/Example/',
                      a+'?id=another','https://user:secret@instagram.com/p/Example/'):
            with self.subTest(other=other):self.assertFalse(social.same_reference(a,other))
        self.assertFalse(social.same_reference('https://linkedin.com/company/alfa','https://linkedin.com/jobs/view/123'))
        self.assertFalse(social.same_reference(None,a))

    def test_post_scope_accepts_known_host_alias_but_still_excludes_comments(self):
        page=posts.post_page('https://www.instagram.com/p/Example/',profile='https://instagram.com/alfa/')
        page['html']=page['html'].replace('"url": "https://www.instagram.com/p/Example/"',
                                        '"url": "https://instagram.com/p/Example/?igsh=discard"')
        packet=evidence.packet(page,document(page))
        self.assertEqual(len(packet['units']),1)
        text='\n'.join(p['text'] for p in evidence.passages(packet,packet['units'][0]))
        self.assertIn(posts.REQUEST,text)
        self.assertNotIn(posts.COMMENT,text)
        page['html']=page['html'].replace('/p/Example/?','/p/Another/?')
        self.assertEqual(evidence.packet(page,document(page))['units'],[])

    def test_job_scope_and_reciprocal_link_require_same_specific_job(self):
        url='https://it.linkedin.com/jobs/view/123456/'
        job={'@type':'JobPosting','url':'https://www.linkedin.com/jobs/view/123456/?trk=feed',
             'title':'Frontend freelance','description':'Remote from Italy.',
             'hiringOrganization':{'name':'Alfa Srl','url':posts.OFFICIAL}}
        page={'url':url,'checked_at':posts.harness.DATE,'status':200,
              'html':'<script type="application/ld+json">'+json.dumps(job)+'</script>'}
        doc=document(page);packet=evidence.packet(page,doc)
        self.assertEqual(len(packet['units']),1)
        ctx=social.scoped_context(page,doc,packet['units'][0],'Alfa Srl')
        owner={'url':posts.OFFICIAL,'checked_at':page['checked_at'],'status':200,
               'html':'<h1>Alfa Srl</h1><a href="'+job['url']+'">Annuncio</a>'}
        identity={'identity_status':'verified','name':'Alfa Srl','website':posts.OFFICIAL}
        self.assertTrue(social.reciprocal(ctx,owner,identity)['verified'])
        for ref in ('https://www.linkedin.com/jobs/view/999999/','https://www.linkedin.com/company/alfa/'):
            owner['html']='<a href="'+ref+'">Lavora con noi</a>'
            self.assertFalse(social.reciprocal(ctx,owner,identity)['verified'])

    def test_profile_alias_does_not_remove_owner_verification_requirement(self):
        ctx={'original_read':True,'author_profile':'https://it.linkedin.com/company/alfa/',
             'author_name':'Alfa Srl','url':'https://linkedin.com/posts/alfa-123/','reposted':False}
        owner={'url':posts.OFFICIAL,'checked_at':posts.harness.DATE,'status':200,
               'html':'<a href="https://www.linkedin.com/company/alfa/?trk=site">Il nostro profilo</a>'}
        identity={'identity_status':'verified','name':'Alfa Srl','website':posts.OFFICIAL}
        self.assertTrue(social.reciprocal(ctx,owner,identity)['verified'])
        self.assertFalse(social.reciprocal(ctx,owner,{**identity,'name':'Beta Srl'})['verified'])
        self.assertFalse(social.reciprocal({**ctx,'reposted':True},owner,identity)['verified'])
