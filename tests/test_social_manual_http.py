"""Loopback HTTP only; previews never create campaigns or invoke providers."""
from unittest.mock import patch
import test_commercial44_http as base


class SocialPreviewHttp(base.RecommendationHttp44):
    def test_manual_links_preview_is_read_only_and_requires_request_protection(self):
        filters={'mode':'extended','commercial_engines':['SOCIAL'],'regions':['Veneto'],
                 'social_urls':['https://www.instagram.com/p/Example/?igsh=discard-me']}
        body={'filters':filters};path='/api/agent6/preview'
        for headers in ({'X-CSRF-Token':'bad'},{'Origin':'https://evil.test'},{'Host':'evil.test'}):
            self.assertEqual(self.request(path,body,headers)[0],403)
        with self.store.connect() as c:
            before=c.execute('SELECT count(*) FROM campaigns').fetchone()[0]
        with patch('sales.agent6.research.acquire',side_effect=AssertionError('Preview is not research')),patch(
                'sales.agent6.ai.infer',side_effect=AssertionError('Preview is not inference')):
            status,result=self.request(path,body)
        self.assertEqual(status,200)
        self.assertEqual(result['social_urls'],['https://www.instagram.com/p/Example/'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM campaigns').fetchone()[0],before)
            self.assertEqual(c.execute('SELECT count(*) FROM research_tasks').fetchone()[0],0)

    def test_manual_links_invalid_input_is_rejected_before_start(self):
        for urls in (['https://127.0.0.1/p/internal'],['https://instagram.com/p/a%22ORsecret'],
                     ['https://linkedin.com/company/alfa'],['https://instagram.com/p/a/']*21):
            status,_=self.request('/api/agent6/preview',{'filters':{
                'commercial_engines':['SOCIAL'],'regions':['Veneto'],'social_urls':urls}})
            self.assertEqual(status,400)
