import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sales.db import Store, now
from sales.linked_sites import referenced_sites
from sales.company_investigation import linked_brand_solutions
from sales.research_analysis import ResearchWeb, LocalResearcher, inspect_candidate


class LinkedSitesTests(unittest.TestCase):
    def test_context_can_cross_layout_divs_but_not_semantic_sections(self):
        html='<div><div><p>Visita il nostro <strong>sito dedicato</strong>!</p></div><a href="https://external.example/">Scopri di più</a></div>'
        self.assertEqual(referenced_sites(html), ['https://external.example/'])
        self.assertEqual(referenced_sites(html.replace('<div><p>', '<section><p>').replace('</p></div>', '</p></section>')), [])

    def test_ambiguous_destinations_credits_partners_hidden_and_large_context_are_ignored(self):
        link='<a href="https://external.example/">Scopri di più</a>'
        for html in (
            '<div>Visita il nostro sito dedicato!'+link+'<a href="https://other.example/">Altro</a></div>',
            '<div>Visita il sito del nostro partner!'+link+'</div>',
            '<footer>Visita il nostro sito dedicato!'+link+'</footer>',
            '<div hidden>Visita il nostro sito dedicato!'+link+'</div>',
            '<blockquote>Visita il nostro sito dedicato!'+link+'</blockquote>',
            '<main><p>Visita il nostro sito dedicato!</p>'+link+'</main>',
            '<div>Visita il nostro sito dedicato!'+'x'*1100+link+'</div>',
            '<div><script>Visita il nostro sito dedicato!</script>'+link+'</div>',
            '<div>Visita il nostro sito dedicato!<section>'+link+'</section></div>',
        ):
            with self.subTest(html=html[:80]): self.assertEqual(referenced_sites(html), [])

    def test_identity_and_blocked_domain_checks_still_apply(self):
        identity={'name':'Alfa Srl','identity_status':'verified','website':'https://alfa.example/'}
        page={'url':identity['website'],'html':'<div>Visita il nostro sito dedicato!<a href="https://external.example/">Scopri</a></div>'}
        self.assertEqual(linked_brand_solutions([page],identity),['https://external.example/'])
        self.assertEqual(linked_brand_solutions([page],{**identity,'identity_status':'unknown'}),[])
        self.assertEqual(linked_brand_solutions([{**page,'url':'https://publisher.example/'}],identity),[])
        self.assertEqual(linked_brand_solutions([{**page,'html':page['html'].replace('external.example','facebook.com')}],identity),[])

    def inspect(self, failure=False, cancel=False, many=False):
        seen=[];analyzed=[]
        legal='<title>Alfa Srl</title><p>Via Roma 1, 35100 Padova (PD)</p><p>P.IVA 12345678901</p><a href="mailto:info@alfa.example">info@alfa.example</a>'
        def read(web,url):
            seen.append(url)
            html='<title>Alfa Srl</title><p>Produciamo impianti</p><a href="/contatti">Contatti</a>'
            if url.endswith('/contatti'):
                html=legal+''.join('<section><p>Visita il nostro sito dedicato!</p><a href="https://external%d.example/">Scopri</a></section>'%i for i in range(4 if many else 1))
            elif 'external' in url:
                if cancel:raise InterruptedError('stop')
                if failure:raise ValueError('robots disallows')
                url='https://destination.example/';html='<title>Soluzione dedicata</title><p>Catalogo dei prodotti</p>'
            return {'url':url,'html':html,'status':200,'checked_at':now()}
        def analyze(owner,identity,docs,coverage):
            analyzed.extend(docs)
            return [],{},{},[]
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'isolated.sqlite3');store.init()
            with patch.object(ResearchWeb,'get',read),patch.object(LocalResearcher,'analyze',analyze):
                result=inspect_candidate(store,{'url':'https://alfa.example/','strategy':'companies'},lambda:None)
        return result,seen,analyzed

    def test_real_inspector_reads_solution_after_contact_identity_and_retains_redirect_provenance(self):
        result,seen,docs=self.inspect()
        self.assertIn('https://external0.example/',seen)
        external=next(d for d in docs if d['url']=='https://destination.example/')
        self.assertEqual(external['role'],'linked_solution');self.assertFalse(external['official'])
        self.assertNotEqual(result['assessment']['status'],'qualified')

    def test_failed_solution_is_incomplete_and_stop_propagates(self):
        result,_,_=self.inspect(failure=True)
        self.assertFalse(result['assessment']['coverage']['solutions'])
        self.assertNotEqual(result['assessment']['status'],'qualified')
        with self.assertRaises(InterruptedError):self.inspect(cancel=True)

    def test_external_inspection_remains_bounded_and_reports_missing_coverage(self):
        result,seen,_=self.inspect(many=True)
        self.assertEqual(sum('external' in u for u in seen),3)
        self.assertFalse(result['assessment']['coverage']['solutions'])


if __name__=='__main__':unittest.main()
