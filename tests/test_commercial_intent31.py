"""3A.1: real saved campaign-13 excerpts plus labelled synthetic countercases.

HTML wrappers below are reconstructed from saved evidence, not the original DOM.
They test intent attribution; they do not assert a live source or open vacancy.
"""
import gzip
import html
import json
import unittest
from pathlib import Path
from sales.commercial.context import extract, asking, source_kind
from sales.commercial.discovery import assess
from sales.commercial.intent import classify_block
from sales.commercial.qualification import evaluate
from test_commercial_engines import page

with gzip.open(Path(__file__).parent/'fixtures/commercial31/campaign13.json.gz','rt') as f:
    SAVED=json.load(f)


def revision(number):
    return next(r['body'] for r in SAVED['revisions'] if r['id']==number)


def reconstructed(number):
    r=revision(number)
    quotes=list(dict.fromkeys(e['quote'] for b in r['request_blocks'] for e in b['evidence']))
    return {'url':r['url'],'html':'<title>'+html.escape(r['title'])+'</title>'+''.join('<p>'+html.escape(q)+'</p>' for q in quotes),'status':200,'checked_at':r['checked_at']}


class Intent31Tests(unittest.TestCase):
    def test_real_inputcomm_saved_sales_quotes_are_not_requests(self):
        p=reconstructed(707)
        self.assertEqual(extract(p),[])
        r=revision(707)
        result=evaluate('AGENCIES',r['identity'],p,r['geography'])
        self.assertEqual(result['state'],'REJECTED')
        self.assertEqual(result['request_blocks'],[])
        for e in r['evidence']:
            self.assertEqual(classify_block(e['quote'])['intent'],'SELLER_INTENT')

    def test_real_freelancedev_is_platform_not_its_own_buyer(self):
        p=reconstructed(700)
        self.assertIn(source_kind(p),('directory','aggregator'))
        self.assertEqual(extract(p),[])
        for r in SAVED['discovery']:
            if r['url']=='https://freelancedev.it/':
                self.assertEqual(assess(r['body'],'AGENCIES')['decision'],'exclude')

    def test_real_dsi_request_preserved_but_no_contract_invented(self):
        p=reconstructed(713);r=revision(713)
        result=evaluate('AGENCIES',r['identity'],p,r['geography'])
        self.assertEqual(result['state'],'NEEDS_REVIEW')
        self.assertTrue(result['request_blocks'])
        self.assertIsNone(result['contract'])
        self.assertIsNone(result['published_at'])
        self.assertEqual(result['commercial_intent']['intent'],'BUYER_INTENT')

    def test_real_directory_and_bliss_excluded_before_fetch(self):
        counts={}
        for r in SAVED['discovery']:
            if any(s in r['url'] for s in ('ernesto.it/c/','starofservice.it/dir/','blissagency.it/social-media/')):
                result=assess(r['body'],r['engine'],r['body']['origin'])
                self.assertEqual(result['decision'],'exclude',r['url'])
                self.assertIn(result['commercial_intent']['intent'],('DIRECTORY','EDITORIAL'))
                counts[r['url']]=result
        self.assertEqual(len(counts),4)

    def test_source_filter_is_structural_not_domain_blacklist(self):
        for host in ('ernesto.it','starofservice.it','blissagency.it','freelancedev.it','brand.example'):
            result=assess({'url':'https://'+host+'/lavora-con-noi/','title':'Cerchiamo sviluppatore WordPress freelance','content':'Collaborazione tecnica con partita IVA.'},'AGENCIES')
            self.assertEqual(result['decision'],'admit',host)
            self.assertEqual(result['commercial_intent']['intent'],'FREELANCE_OPPORTUNITY')
        result=assess({'url':'https://unknown.example/c/Italia/Veneto/Padova/web','title':'67 sviluppatori web per siti','content':'Scopri i migliori professionisti vicino a te'},'AGENCIES')
        self.assertEqual(result['decision'],'exclude')

    def test_eight_commercial_intents(self):
        cases=[
            ('Cerchiamo uno sviluppatore WordPress per il team.','BUYER_INTENT'),
            ('Offriamo sviluppatori WordPress freelance ai nostri clienti.','SELLER_INTENT'),
            ('Cerchiamo sviluppatore WordPress a tempo indeterminato.','JOB_OFFER'),
            ('Cerchiamo sviluppatore WordPress con partita IVA.','FREELANCE_OPPORTUNITY'),
            ('Trova sviluppatori freelance per il tuo progetto.','DIRECTORY'),
            ('Le migliori agenzie web in Italia','EDITORIAL'),
            ('Pubblica un progetto. Sviluppatori freelance disponibili.','AGGREGATOR'),
            ('Lavoriamo con WordPress.','UNKNOWN')]
        for text,wanted in cases:
            with self.subTest(wanted=wanted):
                self.assertEqual(classify_block(text,title=text)['intent'],wanted)

    def test_bare_ricerca_is_not_recruitment(self):
        for text in ('Siti WordPress sui motori di ricerca.','Ricerca scientifica sul software.','Seleziona la categoria e trova il professionista.','Se sei alla ricerca di un lavoro fatto bene, chiamaci.','Cerco lavoro come sviluppatore freelance.'):
            self.assertFalse(asking(text),text)
        for text in ('Alfa ricerca professionisti per il team.','Ricerca sviluppatore WordPress.','Cerchiamo un professionista WordPress.','Valutiamo collaborazioni WordPress freelance.'):
            self.assertTrue(asking(text),text)

    def test_sell_and_hire_in_distinct_blocks_keeps_actual_request(self):
        p=page('',url='https://agency.example/',extra='<p>Offriamo sviluppo WordPress ai clienti.</p><p>Cerchiamo sviluppatore WordPress freelance per collaborazioni.</p>')
        blocks=extract(p)
        self.assertEqual(len(blocks),1)
        self.assertNotIn('Offriamo',blocks[0]['text'])
        self.assertEqual(blocks[0]['commercial_intent']['intent'],'FREELANCE_OPPORTUNITY')

    def test_agency_accepting_contractors_not_excluded_for_service_intro(self):
        r=assess({'url':'https://agency.example/collabora-con-noi/','title':'Sviluppo software su misura','content':'Realizziamo siti WordPress. Valutiamo collaborazioni con sviluppatori freelance.'},'AGENCIES')
        self.assertEqual(r['decision'],'admit')
        self.assertEqual(r['commercial_intent']['intent'],'FREELANCE_OPPORTUNITY')

    def test_employee_contract_cannot_borrow_freelance_from_other_role(self):
        p=page('',extra='<article><h2>WordPress developer</h2><p>Cerchiamo sviluppatore a tempo indeterminato.</p></article><article><h2>Marketing manager</h2><p>Cerchiamo consulente marketing freelance.</p></article>')
        blocks=extract(p)
        self.assertEqual(len(blocks),1)
        self.assertEqual(blocks[0]['commercial_intent']['intent'],'JOB_OFFER')
        self.assertNotIn('freelance',blocks[0]['text'])

    def test_technical_heading_cannot_make_nontechnical_request_technical(self):
        p=page('',extra='<h2>WordPress developer</h2><p>Cerchiamo copywriter freelance.</p>')
        self.assertEqual(extract(p),[])

    def test_individual_third_party_request_remains_indication(self):
        r=assess({'url':'https://market.example/progetti/314','title':'Alfa cerca sviluppatore WordPress freelance','content':'Progetto di rifacimento sito: referente da verificare.'},'FREELANCE')
        self.assertEqual(r['decision'],'admit')
        self.assertEqual(r['commercial_intent']['intent'],'FREELANCE_OPPORTUNITY')
        self.assertNotIn('state',r)

    def test_plausible_partial_social_does_not_become_verified_or_irrelevant(self):
        r=assess({'url':'https://www.instagram.com/p/Incomplete/','title':'Sviluppatore WordPress freelance','content':'Nuova opportunità, dettagli nel post.'},'FREELANCE')
        self.assertEqual(r['decision'],'admit')
        self.assertEqual(r['commercial_intent']['intent'],'UNKNOWN')
        self.assertLess(r['priority'],55)
        self.assertNotIn('state',r)

    def test_actual_verdurazon_snippet_remains_unverified_hint(self):
        r=next(r for r in SAVED['discovery'] if '/DW3VAcqAi2U/' in r['url'] and r['engine']=='FREELANCE')
        out=assess(r['body'],'FREELANCE')
        self.assertEqual(out['decision'],'admit')
        self.assertEqual(out['commercial_intent']['intent'],'FREELANCE_OPPORTUNITY')
        self.assertNotIn('state',out)
