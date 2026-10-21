"""OpenAI Chat Completions contract fixtures; no sockets, key lookup or inference."""
import copy
import json
import unittest
from unittest.mock import Mock,patch
from sales.commercial import ai_provider
from sales.commercial.ai import validate_config
from sales.commercial.ai_schema import response_schema,unknown_output

class OpenAIContract(unittest.TestCase):
    def setUp(self):
        self.cfg=validate_config({'enabled':True,'provider':'REMOTE','mode':'shadow','model':'gpt-5.4-mini','endpoint':'https://api.openai.com/v1/chat/completions'})
        self.payload={'candidate_id':'fixture','evidence':[]}
        self.data={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(unknown_output(self.payload)),'refusal':None}}], 'usage':{'prompt_tokens':100,'completion_tokens':60,'total_tokens':160,'prompt_tokens_details':{'cached_tokens':20},'completion_tokens_details':{'reasoning_tokens':10}}}

    def request(self,data=None,status=200,raw=None):
        response=Mock(status=status)
        response.read.return_value=raw if raw is not None else json.dumps(self.data if data is None else data).encode()
        connection=Mock();connection.getresponse.return_value=response
        with patch.dict('os.environ',{'CUSTOMERSEARCH_AI_API_KEY':'fixture-key-not-real'},clear=True),patch.object(ai_provider,'_PinnedHTTPS',return_value=connection) as factory:
            try:return ai_provider._request(self.cfg,self.payload),connection,factory
            finally:connection.close.assert_called_once()

    def test_chat_completions_request_bearer_schema_and_model_parameters(self):
        result,connection,factory=self.request()
        factory.assert_called_once_with('api.openai.com',None,timeout=30)
        args=connection.request.call_args
        self.assertEqual(args.args[:2],('POST','/v1/chat/completions'))
        self.assertEqual(args.kwargs['headers']['Authorization'],'Bearer fixture-key-not-real')
        body=json.loads(args.kwargs['body'])
        self.assertEqual(body['model'],'gpt-5.4-mini')
        self.assertEqual(body['max_completion_tokens'],1000)
        self.assertEqual(body['reasoning_effort'],'none');self.assertFalse(body['store'])
        for unsupported in ('max_tokens','temperature','top_p','tools','stream'):
            self.assertNotIn(unsupported,body)
        self.assertNotIn('fixture-key-not-real',json.dumps(body))
        self.assertEqual(body['response_format']['type'],'json_schema')
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertEqual(result['usage'],{'input_tokens':100,'output_tokens':60,'total_tokens':160,'cached_input_tokens':20,'reasoning_tokens':10})
        self.assertNotIn('reported_cost',result)

    def test_schema_all_objects_are_closed_required_and_nullable(self):
        def walk(node):
            if isinstance(node,dict):
                if node.get('type')=='object':
                    self.assertFalse(node['additionalProperties'])
                    self.assertEqual(set(node['required']),set(node['properties']))
                for v in node.values():walk(v)
            elif isinstance(node,list):
                for v in node:walk(v)
        walk(response_schema())
        self.assertEqual(response_schema()['properties']['actor']['type'],['string','null'])

    def test_research_segment_contract_serialized_without_duplicate_document(self):
        from sales.agent6 import schema,grounding
        evidence=grounding.attach(schema.bundle([{'id':'r1','url':'https://alfa.example/jobs','text':'Alfa Srl\nCerchiamo freelance WordPress.','original':True}]))
        self.payload={'task':schema.READ,'result_ids':['r1'],'evidence':evidence}
        _,connection,_=self.request()
        body=json.loads(connection.request.call_args.kwargs['body'])
        wire=json.loads(body['messages'][1]['content']);block=wire['evidence'][0]
        self.assertNotIn('text',block);self.assertIn('Cerchiamo freelance WordPress.',block['segments'].values())
        self.assertEqual(body['response_format']['json_schema']['schema'],schema.wire_schema(schema.READ))
        self.assertIn('text',self.payload['evidence'][0]) # canonical source remains local

    def test_http_errors_have_safe_codes_and_no_response_body(self):
        for status in (400,401,403,404,408,429,500,502,503,504):
            with self.subTest(status=status),self.assertRaises(ai_provider.ProviderError) as caught:
                self.request(status=status,raw=b'secret provider prose')
            self.assertEqual(str(caught.exception),'provider_http_'+str(status))
            self.assertEqual(caught.exception.retryable,status in (408,429,500,502,503,504))

    def test_incomplete_refused_filtered_and_tool_outputs_keep_usage(self):
        for finish,refusal,expected in [('length',None,'truncated'),('stop','private text','refusal'),('content_filter',None,'filtered'),('tool_calls',None,'unexpected_finish')]:
            data=copy.deepcopy(self.data);data['choices'][0].update(finish_reason=finish)
            data['choices'][0]['message']['refusal']=refusal
            with self.subTest(finish=finish,refusal=bool(refusal)),self.assertRaises(ai_provider.ProviderError) as caught:self.request(data=data)
            self.assertEqual(str(caught.exception),'provider_response_'+expected)
            self.assertEqual(caught.exception.usage['output_tokens'],60)
            self.assertFalse(caught.exception.retryable)

    def test_empty_output_and_missing_choices_are_errors(self):
        for data in ({'choices':[],'usage':self.data['usage']},{'choices':[{'finish_reason':'stop','message':{'content':None}}]},[]):
            with self.subTest(data=data),self.assertRaises(ai_provider.ProviderError):self.request(data=data)

    def test_bad_json_and_oversized_response_are_bounded(self):
        for raw,code in [(b'not JSON','invalid_json'),(b'x'*1_048_577,'too_large')]:
            with self.subTest(code=code),self.assertRaisesRegex(ai_provider.ProviderError,'provider_response_'+code):self.request(raw=raw)

    def test_missing_usage_stays_unknown(self):
        data=copy.deepcopy(self.data);data.pop('usage')
        result,_,_=self.request(data=data);self.assertEqual(result['usage'],{})

    def test_malformed_token_counts_not_treated_as_actual_usage(self):
        data=copy.deepcopy(self.data);data['usage']={'prompt_tokens':True,'completion_tokens':-1,'total_tokens':'160'}
        result,_,_=self.request(data=data);self.assertEqual(result['usage'],{})

    def test_local_and_other_models_do_not_receive_openai_reasoning_setting(self):
        self.cfg['model']='other-configured-model'
        _,connection,_=self.request()
        self.assertNotIn('reasoning_effort',json.loads(connection.request.call_args.kwargs['body']))

    def test_sol_medium_reasoning_structured_output_and_total_completion_cap(self):
        self.cfg.update(model='gpt-6.1-sol',max_output_tokens=4096)
        result,connection,_=self.request()
        body=json.loads(connection.request.call_args.kwargs['body'])
        self.assertEqual(body['model'],'gpt-6.1-sol')
        self.assertEqual(body['reasoning_effort'],'medium')
        self.assertEqual(body['max_completion_tokens'],4096)
        self.assertEqual(body['response_format']['type'],'json_schema')
        for key in ('temperature','top_p','tools','max_tokens','service_tier'):
            self.assertNotIn(key,body)
        self.assertFalse(body['store'])
        # Reasoning tokens are included in completion usage, not added twice.
        self.assertEqual(result['usage']['output_tokens'],60)
        self.assertEqual(result['usage']['reasoning_tokens'],10)

    def test_sol_reasoning_setting_is_not_sent_to_other_hosts(self):
        self.cfg.update(model='gpt-6.1-sol',endpoint='https://provider.example/v1/chat/completions')
        _,connection,_=self.request()
        self.assertNotIn('reasoning_effort',json.loads(connection.request.call_args.kwargs['body']))

    def test_worker_error_envelope_is_safe_and_preserves_usage(self):
        pipe=Mock()
        with patch.object(ai_provider,'_request',side_effect=ai_provider.ProviderError('provider_response_truncated',{'output_tokens':60})):
            ai_provider._worker(pipe,self.cfg,self.payload)
        self.assertEqual(pipe.send.call_args.args[0],{'error':'provider_response_truncated','provider_error':True,'usage':{'output_tokens':60},'retryable':False})
        pipe.close.assert_called_once()

if __name__=='__main__':unittest.main()
