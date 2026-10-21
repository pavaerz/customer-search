"""Real saved originals plus labelled synthetic access/attribution controls."""
import copy
import gzip
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6 import evidence, decision
from sales.agent6.discussion import scope
from sales.agent6.response_channels import collect, documents
from sales.agent6.source_context import select_links
from sales.commercial.inspection import document
from sales.commercial.identity import establish
import test_ai_first_response_channels as controls
import test_ai_first as h
from scripts.run_objective_validation_sol import SOL_CONFIG


def original(part):
    rows = json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/completion64/originals.json.gz').read_bytes()))
    return copy.deepcopy(next(r['page'] for r in rows if part in r['url']))


class DiscussionOriginals(unittest.TestCase):
    def packet(self, part):
        page = original(part)
        doc = document(page)
        packet = evidence.packet(page, doc)
        return page, doc, packet, packet['units'][0]

    def test_actual_george_post_reaches_model_instead_of_supplier_comments(self):
        _, doc, packet, unit = self.packet('finding-a-developer')
        selected = evidence.passages(packet, unit, 3000)
        text = '\n'.join(e['text'] for e in selected)
        self.assertIn('by George Terry', text)
        self.assertIn('How do you go about finding a good developer', text)
        self.assertIn("We've had multiple clients ask us", text)
        self.assertNotIn('Upwork', text)
        self.assertNotIn('Hypothetical example', text)
        self.assertEqual(unit['dates'][0]['value'], '2022-04-07')
        for e in selected:
            self.assertEqual(e['text'], doc['text'][e['offset']:e['offset']+len(e['text'])])
        self.assertLessEqual(sum(len(e['text'].encode()) for e in selected), 3000)

    def test_actual_mintgemten_keeps_request_compensation_and_author_together(self):
        page, doc, packet, unit = self.packet('looking-for-developer-partner')
        selected = evidence.passages(packet, unit, 3000, source_content=True)
        text = '\n'.join(e['text'] for e in selected)
        self.assertIn('by mgtmarketplace', text)
        self.assertIn('MintGemTen', text)
        self.assertIn('paid work depending on the fit', text)
        self.assertNotIn('Senior Full Stack Developer with 5+', text)
        self.assertNotIn('concrete.goon', text)  # Author reply needs separate verification.
        self.assertEqual([d['value'] for d in unit['dates']], ['2026-03-12'])
        self.assertIsNone(evidence.metadata_document(page, doc, unit))
        self.assertEqual(collect(page, unit, {'name':'Indie Hackers','website':page['url']}, True), [])
        links = select_links(packet, unit, 'STARTUPS', False)
        self.assertTrue(any(l['url'].endswith('/mgtmarketplace') for l in links))
        self.assertFalse(any('sign-in' in l['url'] for l in links))
        for e in selected:
            self.assertEqual(e['text'], doc['text'][e['offset']:e['offset']+len(e['text'])])

    def test_synthetic_unrecognized_and_ambiguous_layouts_do_not_guess_author(self):
        self.assertIsNone(scope({'html':'<p>by Mario</p><p>Looking for a developer</p>'}, 'by Mario\nLooking for a developer'))
        page = original('finding-a-developer')
        doc = document(page)
        page['html'] += '<div class="post-page__body">A second post with enough text to represent a separate source.</div>'
        self.assertIsNone(scope(page, doc['text']))

    def test_synthetic_hidden_or_commented_markup_does_not_create_post_scope(self):
        html = '<div class="post-page__title">Need a developer</div><div class="post-page__byline">by Alice</div><div class="post-page__body">We are looking for an external developer for a complete website.</div>'
        text = 'Need a developer\nby Alice\nWe are looking for an external developer for a complete website.'
        self.assertIsNotNone(scope({'html':html,'url':'https://forum.example/post/1'}, text))
        for wrapper in ('<div hidden>{}</div>', '<div style="display:none">{}</div>', '<div class="comment">{}</div>'):
            self.assertIsNone(scope({'html':wrapper.format(html),'url':'https://forum.example/post/1'}, text))


class NetworkChannels(unittest.TestCase):
    def test_unchanged_real_response_accepts_only_its_cited_manual_signup_route(self):
        case=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/completion64/observed-response.json.gz').read_bytes()))
        p=case['input'];out=json.loads(case['raw_output'])
        value,_=decision.validate(out,p)
        b=decision.materialize({'url':'https://www.developerway.it/developers-freelance','original':True},
                               value,p['evidence'],p,'AGENCIES')
        view=decision.projection(b)
        self.assertTrue(view['READY_FOR_OUTREACH'])
        self.assertEqual(view['arrangement'],'FREELANCE_COLLABORATION')
        self.assertEqual(view['public_channels'][0]['value'],'https://talents.developerway.it/registrati')
        for bad in ('made-up', next(l['id'] for l in p['links'] if l['id']!=out['action']['link_id'])):
            changed=copy.deepcopy(out);changed['action']['link_id']=bad
            with self.assertRaisesRegex(ValueError,'unexpected_action_link'):
                decision.validate(changed,p)
        changed=copy.deepcopy(out);changed['facts']=[f for f in changed['facts'] if f['field']!='contact']
        with self.assertRaisesRegex(ValueError,'unexpected_action_link'):
            decision.validate(changed,p)
        changed=copy.deepcopy(out);changed['action']['type']='STOP'
        with self.assertRaisesRegex(ValueError,'unexpected_action_link'):
            decision.validate(changed,p)

    def test_real_worker_keeps_control_proof_and_scope_after_budget_compaction(self):
        b=h.IntegratedPath();b.setUp()
        try:
            b.c['filters']['commercial']['ai'].update(SOL_CONFIG)
            b.c['filters']['commercial']['ai']['provider']='MOCK'
            page=original('/developers-freelance');seen=[]
            b.w.enqueue('candidate','AGENCIES',{'url':page['url'],'original_page':page},'packing64')
            with b.store.connect() as c:
                r=c.execute("SELECT * FROM research_tasks WHERE fingerprint='packing64'").fetchone()
                task={**dict(r),'payload':json.loads(r['payload'])}
            def infer(payload,cfg,check):
                seen.append(copy.deepcopy(payload))
                return {'output':{},'usage':{}}
            with patch('sales.agent6.ai.infer',side_effect=infer),patch('sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('offline')):
                b.w.execute(task,lambda:None)
                b.w.execute(task,lambda:None)
            self.assertEqual(len(seen),1)  # Resume uses the saved invalid receipt.
            p=seen[0]
            text='\n'.join(e['text'] for e in p['evidence'])
            self.assertIn('Frontend Developer',text)
            self.assertIn('Iscriviti gratuitamente',text)
            self.assertEqual(len(p['response_channels']),1)
            channel=p['response_channels'][0]
            proof=next(e for e in p['evidence'] if e['id']==channel['evidence_id'])
            self.assertIn(channel['value'],proof['text'])
            from sales.commercial.token_count import estimate
            self.assertLessEqual(estimate(p,SOL_CONFIG)['tokens'],SOL_CONFIG['max_input_tokens'])
        finally:
            b.tearDown()

    def test_real_invitation_exposes_signup_without_fetch_or_submission(self):
        page = original('/developers-freelance')
        doc = document(page)
        unit = evidence.packet(page, doc)['units'][0]
        identity = establish([page])
        channels = collect(page, unit, identity, True)
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]['value'], 'https://talents.developerway.it/registrati')
        self.assertEqual(channels[0]['observation_kind'], 'network_join_instruction')
        docs, proofs, offered = documents(page, doc['id'], unit['id'], channels)
        self.assertIn('no current paid assignment', proofs[0]['text'])
        self.assertNotIn('form action', json.dumps(offered))
        self.assertEqual(collect(page, unit, identity, False), [])

    def test_real_home_has_published_path_to_invitation_not_login(self):
        page = original('https://www.developerway.it/')
        identity = establish([page]); unit = {'origin':'page'}
        found = collect(page, unit, identity, True)
        self.assertEqual([c['value'] for c in found], ['https://www.developerway.it/developers-freelance'])
        self.assertNotIn('Accedi', json.dumps(found))

    def test_synthetic_invitation_still_requires_model_contact_citation(self):
        html = '<a href="https://talents.example/register">Entra nel Talent Network</a>'
        p, _ = controls.payload(html)
        selected = controls.materialize(p)
        self.assertTrue(decision.projection(selected)['CONTACT_AVAILABLE'])
        unselected = controls.materialize(p, h.response(p))
        self.assertNotIn('https://talents.example/register', [c['value'] for c in unselected['contacts']])

    def test_synthetic_newsletter_login_clients_and_unsafe_links_stay_excluded(self):
        for label in ('Entra nella newsletter freelance', 'Accedi a talents', 'Trova talenti per la tua azienda'):
            self.assertEqual(controls.collect('<a href="https://talents.example/register">'+label+'</a>'), [])
        for url in ('http://127.0.0.1/register', 'https://talents.example/register?token=secret', 'https://talents.example/a.pdf'):
            self.assertEqual(controls.collect('<a href="'+url+'">Entra nel Talent Network</a>'), [])
        self.assertEqual(controls.collect('<div class="comments"><a href="https://talents.example/register">Entra nel Talent Network</a></div>'), [])

    def test_standing_invitation_never_projects_paid_assignment_even_with_paid_terms(self):
        for relationship in ('OPEN_FREELANCE_COLLABORATION', 'SPONTANEOUS_APPLICATION'):
            body = {'relationship':relationship, 'compensation':'PAID', 'open_paid_project':'UNKNOWN'}
            self.assertEqual(decision.projection(body)['arrangement'], 'FREELANCE_COLLABORATION')
            self.assertFalse(decision.projection(body)['READY_FOR_OUTREACH'])
        self.assertEqual(decision.projection({'relationship':'EXPLICIT_REQUEST','compensation':'PAID'})['arrangement'], 'PAID_DEVELOPMENT_OPPORTUNITY')
        self.assertEqual(decision.projection({'relationship':'OPEN_FREELANCE_COLLABORATION','compensation':'UNPAID'})['arrangement'], 'UNPAID_COLLABORATION')

    def test_real_network_skills_reach_passages_without_inventing_scope(self):
        page = original('/developers-freelance'); doc = document(page)
        pack = evidence.packet(page, doc)
        text = '\n'.join(e['text'] for e in evidence.passages(pack, pack['units'][0], 3000))
        self.assertRegex(text, r'Frontend Developer|PHP Developer|JavaScript Developer')
        self.assertIn('freelance', text)


if __name__ == '__main__':
    unittest.main()
