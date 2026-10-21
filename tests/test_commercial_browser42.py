"""Local real Chromium only; no claim about historical external audit success."""
import test_commercial_browser41 as previous
class Browser42(previous.Browser41):
 def test_large_nested_dom_remains_measurable(self):
  html='<main><h1>Produzione italiana di componenti tecnici</h1>'+''.join('<section><div><p>Produciamo componenti metallici per aziende industriali con lavorazioni documentate.</p></div></section>' for _ in range(600))+'</main>'
  r=self.render(body=html);self.assertTrue(r['completed'],r);self.assertEqual(len(r['independent_measurements']),2)
 def test_timeout_diagnostics_have_dependencies(self):
  r=self.render('<script src="/slow.js"></script>');self.assertFalse(r['completed']);self.assertTrue(any('pending_dependencies' in d for d in r['diagnostics'] if d.get('error')));self.assertEqual(r['findings'],[])
