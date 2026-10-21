"""Saved C53 search hints; all conclusions remain unverified social leads."""
import copy,gzip,json,unittest
from pathlib import Path
from unittest.mock import patch
from sales.agent6.social_seeds import lookup_worthwhile
import test_ai_first as h

ROWS=json.loads((Path(__file__).parent/'fixtures/ai_first/source56/receipts.json').read_text())

class SocialRecovery(unittest.TestCase):
    def item(self,slug):return next(r for r in ROWS if slug in r['url'])

    def test_saved_sales_training_and_student_posts_do_not_spend_followup(self):
        for slug in ('DetI61QiWXc','DAYZrhpPoMK','DOagy0gEdGe'):
            self.assertFalse(lookup_worthwhile(self.item(slug)),slug)

    def test_saved_concrete_development_hints_remain_eligible_not_verified(self):
        for slug in ('federico-allamprese','DVOGPYKjr9Z'):
            item=self.item(slug);before=dict(item)
            self.assertTrue(lookup_worthwhile(item))
            self.assertEqual(item,before)

    def test_synthetic_real_roles_and_projects_do_not_need_word_freelance(self):
        for text in ('Cerchiamo sviluppatore frontend freelance per il nuovo sito.',
                     'Accettiamo collaboratori esterni WordPress.',
                     'Cerco una persona per un sito web completo.',
                     'Cerco qualcuno per rifare il sito.',
                     'Cerchiamo un partner per sviluppo web.',
                     'Cerchiamo un partner per realizzare un e-commerce.',
                     'Looking for a web developer contractor.',
                     'Cerchiamo un CTO per una applicazione web.'):
            self.assertTrue(lookup_worthwhile({'url':'https://instagram.com/p/synthetic/',
                                              'content':text}),text)

    def test_synthetic_commercial_growth_and_separate_fragments_are_not_technical_requests(self):
        for title,snippet in (('Cerchiamo partner commerciali','Sviluppare nuove opportunità in Veneto.'),
                              ('Consigli WordPress','Cerchiamo partecipanti al seminario.'),
                              ('Lavora con noi','Cerchiamo venditori ... il nostro sito web è online'),
                              ('Sviluppatori freelance','Cerco consigli per il marketing.')):
            self.assertFalse(lookup_worthwhile({'url':'https://instagram.com/p/synthetic/',
                                               'title':title,'content':snippet}))

    def test_saved_discovery_keeps_unread_posts_without_followups_or_false_rejections(self):
        base=h.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        items=[self.item(s) for s in ('DetI61QiWXc','DAYZrhpPoMK','DOagy0gEdGe')]
        with patch('sales.agent6.research.acquire',return_value=items),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('No snippet AI')),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('No social bypass')):
            base.w.execute({'id':1,'kind':'search','strategy':'SOCIAL',
                            'payload':h.query('site:instagram.com/p/ Veneto cerchiamo sviluppatore web')},lambda:None)
        with base.store.connect() as db:
            bodies=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            self.assertEqual(db.execute('SELECT count(*) FROM research_tasks').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_ai_executions').fetchone()[0],0)
        self.assertEqual(len(bodies),3)
        for b in bodies:
            self.assertIsNone(b['decision'])
            self.assertEqual(b['validation_status'],'ACCESS_BLOCKED')
            self.assertFalse(b['social_source']['original_read'])


class OfficialRecovery(unittest.TestCase):
    def test_real_legal_footer_requires_same_verified_vat_and_visible_owner_block(self):
        from sales.agent6.owner_names import collect,verified
        from sales.commercial.identity import establish
        pages=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/social57/official-pages.json.gz').read_bytes()))
        page=pages[0];identity=establish([page]);aliases=collect(page,identity)
        self.assertTrue(any(a['basis']=='owned_legal_footer' and a['name']=='Startup Bakery srl' for a in aliases))
        self.assertTrue(verified({'verified':True,'name':identity['name'],'domain':'startup-bakery.com',
                                 'verified_names':aliases},'Startup Bakery srl'))
        for changed in (page['html'].replace('11196110966','12345678901'),
                        page['html'].replace('<footer','<footer hidden'),
                        page['html'].replace('Startup Bakery srl','Startup Bakery Studios srl')):
            self.assertEqual(collect({**page,'html':changed},identity),[])
        self.assertEqual(collect(page,{**identity,'legal_id':None}),[])

    def test_synthetic_owner_block_cannot_cross_footer_boundaries(self):
        from sales.agent6.owner_names import collect
        schema={'@type':'Organization','name':'Alfa','url':'https://alfa.example/','vatID':'IT11196110966'}
        html='<script type="application/ld+json">'+json.dumps(schema)+'</script>'
        identity={'identity_status':'verified','name':'Alfa','website':'https://alfa.example/',
                  'legal_id':'IT11196110966'}
        for footer in ('<footer><p>Alfa srl</p></footer><footer><p>Via Roma 1</p><p>P.IVA 11196110966</p></footer>',
                       '<footer><div class="clients"><p>Alfa srl</p><p>Via Roma 1</p><p>P.IVA 11196110966</p></div></footer>'):
            self.assertEqual(collect({'url':'https://alfa.example/','html':html+footer},identity),[])

    def test_actual_homepage_verifies_full_legal_name_and_offers_careers_without_using_snippet_as_proof(self):
        pages=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/ai_first/social57/official-pages.json.gz').read_bytes()))
        page=pages[0]
        base=h.IntegratedPath();base.setUp();self.addCleanup(base.tearDown)
        from scripts.run_objective_validation_sol import SOL_CONFIG
        base.c['filters']['commercial']['ai'].update(SOL_CONFIG)
        base.c['filters']['commercial']['ai']['provider']='MOCK'
        base.w.enqueue('candidate','AGENCIES',{'url':page['url'],'original_page':page,
            'indexed_origin':{'company_hint':'Startup Bakery srl','snippet':'UNVERIFIED_FRONTEND_INVITATION'},
            'depth':1,'query':'"Startup Bakery srl" Frontend careers'},'bakery-real')
        with base.store.connect() as db:
            row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='bakery-real'").fetchone()
            task={**dict(row),'payload':json.loads(row['payload'])}
        seen=[]
        def infer(p,c,check):seen.append(copy.deepcopy(p));return {'output':{},'usage':{}}
        with patch('sales.agent6.ai.infer',side_effect=infer),patch(
                'sales.agent6.research.CompanyWeb.get',side_effect=AssertionError('Saved originals only')):
            base.w.execute(task,lambda:None)
        self.assertEqual(len(seen),1)
        self.assertTrue(seen[0]['identity']['verified'])
        self.assertTrue(any('/chi-siamo/lavora-con-noi/' in l['url'] for l in seen[0]['links']))
        self.assertNotIn('UNVERIFIED_FRONTEND_INVITATION',json.dumps(seen[0]['evidence']))
        with base.store.connect() as db:
            bodies=[json.loads(r[0]) for r in db.execute('SELECT body FROM agent6_records')]
            self.assertFalse(any(b.get('decision')=='INTERESTING' for b in bodies))
