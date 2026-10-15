import unittest
from site_audit import seo_report,parse_pagespeed
import app
class SiteAuditTest(unittest.TestCase):
    def test_real_scores_and_missing_scores_are_distinct(self):
        result=parse_pagespeed({'lighthouseResult':{'categories':{'performance':{'score':0},'seo':{'score':None}},'audits':{}}},'mobile','https://example.org/')
        self.assertEqual(result['scores'],{'performance':0})
        self.assertEqual(parse_pagespeed({},'mobile','https://example.org/')['status'],'unavailable')
        self.assertEqual(parse_pagespeed({'lighthouseResult':{'runtimeError':{'code':'error'},'categories':{'seo':{'score':1}}}},'mobile','x')['status'],'unavailable')
    def test_seo_signals_do_not_invent_geo_score(self):
        r=seo_report('<title>Servizi</title><h1>Produzione</h1><meta name="robots" content="noindex"><script type="application/ld+json">{"@type":"Organization"}</script>','https://example.org')
        self.assertEqual(r['geo_aeo']['structured_types'],['Organization'])
        self.assertNotIn('score',r['geo_aeo'])
        self.assertEqual(r['checks'][3]['status'],'da approfondire')
    def test_old_small_font_reason_is_not_presented_as_a_defect(self):
        f={'kind':'Usabilità · layout','qualifies':True,'incomplete':False,'text':'testo piccolo','ux_findings':[{'code':'small_text','text':'testo piccolo'}]}
        self.assertEqual(app.redesign_reason({'findings':[f]}),'')
