"""Offline accounting against the task-specific prompt and response schema."""
import json,unittest
import test_agent6_campaign32 as support
from sales.agent6 import ai,schema,news_review,grounding
from sales.db import digest
from sales.commercial.ai_tasks import system_for,schema_for


class InputEnvelope(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
    def tearDown(self):self.base.tearDown()
    def test_review_counts_its_own_system_and_structured_schema(self):
        p={'task':news_review.TASK,'observations':[],'events':[]}
        expected=sum(len(s.encode()) for s in (json.dumps(p,ensure_ascii=False),system_for(p['task']),json.dumps(schema_for(p['task']),ensure_ascii=False)))+128
        self.assertEqual(ai.input_bytes(p),expected)
        self.assertNotEqual(system_for(p['task']),schema.SYSTEM)
    def test_budget_trimming_preserves_original_lines_and_source_offsets(self):
        text='Alfa Srl\nWe are looking for a freelance WordPress developer.\n'+'Additional context for the original public page.\n'*180
        evidence={'id':'e1','result_id':'r1','url':'https://alfa.example/jobs','text':text,
            'hash':digest(text),'offset':123,'original':True,'document_id':'fixture'}
        p={'task':schema.READ,'flow':'AZIENDE','result_ids':['r1'],'evidence':[evidence]};seen=[]
        def model(payload,cfg,check):
            seen.append(payload)
            return {'output':{'analyses':[{'result_id':'r1','kind':'UNKNOWN','kind_ref':None,'facts':[],
                'hypothesis':'Synthetic fixture only.','missing':['request']}]},'usage':{}}
        result=ai.call(self.base.store,self.base.c,'AZIENDE','page:fixture',p,lambda:None,model)
        self.assertEqual(result['status'],'completed',result)
        sent=seen[0];self.assertLessEqual(ai.input_bytes(sent),self.base.cfg['max_input_tokens'])
        part=sent['evidence'][0]
        self.assertTrue(part['text'].startswith('Alfa Srl\n'));self.assertLess(len(part['text']),len(text))
        self.assertEqual(part['text'],text[:len(part['text'])]);self.assertEqual(text[len(part['text'])],'\n')
        self.assertEqual(part['hash'],digest(part['text']));self.assertEqual(part['offset'],123)
        for segment in part['segments']:
            self.assertEqual(segment['text'],text[segment['start']:segment['end']])
            grounding.resolve({'segment_id':segment['segment_id']},sent['evidence'])
        self.assertEqual(p['evidence'][0]['text'],text)
    def test_oversized_untrimmable_input_never_reaches_provider(self):
        called=[]
        p={'task':news_review.TASK,'untrusted_context':'x'*40000}
        result=ai.call(self.base.store,self.base.c,'AZIENDE','website:fixture',p,lambda:None,
            lambda *args:called.append(args))
        self.assertEqual(result['error'],'input_budget');self.assertEqual(called,[])
        with self.base.store.connect() as c:
            self.assertEqual(c.execute('select count(*) from commercial_ai_executions where attempt=1').fetchone()[0],0)


if __name__=='__main__':unittest.main()
