"""Actual Chromium, local fixture only: text in hidden DOM is not visual proof."""
from test_commercial_browser36 import Browser36

class Browser40(Browser36):
    def test_invisible_dom_is_unvalidated_not_site_defect(self):
        result=self.render('<style>body{opacity:0}</style><main><p>Contenuto aziendale presente nel DOM ma completamente invisibile nel rendering.</p></main>')
        self.assertFalse(result['completed']);self.assertEqual(result['findings'],[])
        self.assertTrue(all(s['reliability']=='UNVALIDATED' for s in result.get('screenshots',[])))
