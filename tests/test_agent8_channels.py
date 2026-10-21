"""Five public channels with read-only compatibility for saved LinkedIn data."""
import unittest
import test_agent6_campaign32 as support
from sales.agent6 import FLOWS,flow_label,memory
from sales.agent6.api import listing,preview
from sales.agent6.strategies import brief
from sales.agent6.learning import strategy_id
from sales.commercial.catalog import options
from sales.db import encode,now


class Channels(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
    def tearDown(self):self.base.tearDown()

    def test_exact_five_channels_and_distinct_briefs(self):
        self.assertEqual(set(FLOWS),{'AZIENDE','AGENCIES','SOCIAL','STARTUPS','NEWS'})
        briefs=[brief(f,['Veneto','Toscana'],0) for f in FLOWS]
        self.assertEqual(len({b['goal'] for b in briefs}),5)
        self.assertEqual(flow_label('LINKEDIN'),'Social')
        for f in FLOWS:
            p=preview(self.base.store,{**self.base.filters,'commercial_engines':[f]})
            self.assertEqual(list(p['flows']),[f])

    def test_social_search_rotates_platform_without_private_access(self):
        self.assertEqual(brief('SOCIAL',[],0)['focus_platform'],'linkedin.com')
        b=brief('SOCIAL',[],1)
        self.assertEqual(b['focus_platform'],'instagram.com')
        self.assertIn('Do not automate login',b['query_constraints'])
        for host in ('bsky.app','mastodon.social','instagram.com'):
            self.assertIn(':social:',strategy_id('site:'+host+' cerco wordpress','SOCIAL'))

    def test_proactive_queries_use_shared_territories_and_respect_selected_regions(self):
        from sales.agent6 import proactive,commercial_policy
        def query(text):return {**support.query(text),'strategy':proactive.STRATEGY}
        for city,region in [('Brescia','Lombardia'),('Udine','Friuli-Venezia Giulia'),('Rovigo','Veneto'),('Lucca','Toscana')]:
            self.assertTrue(commercial_policy.assess_query(query('aziende serramenti '+city+' sito ufficiale'),'AZIENDE',[region])['allowed'])
        for text in ('aziende serramenti Napoli sito ufficiale','aziende serramenti -Veneto sito ufficiale',
                     'aziende serramenti sito ufficiale (Veneto OR Italia)'):
            self.assertFalse(commercial_policy.assess_query(query(text),'AZIENDE')['allowed'])
        self.assertEqual(commercial_policy.assess_query(query('produttori Lombardia sito ufficiale'),'AZIENDE',['Veneto'])['reason'],
                         'proactive_territory_outside_campaign')

    def test_legacy_alias_keeps_budget_but_cannot_duplicate_a_channel(self):
        f={**self.base.filters,'commercial_engines':['LINKEDIN']}
        old,limits=options(f)
        new,new_limits=options({**f,'commercial_engines':['SOCIAL']})
        self.assertEqual(old,['LINKEDIN']);self.assertEqual(new,['SOCIAL'])
        self.assertEqual(limits,new_limits)
        with self.assertRaises(ValueError):options({**f,'commercial_engines':['SOCIAL','LINKEDIN']})

    def test_social_filters_and_memory_read_legacy_without_rewriting_it(self):
        store,campaign=self.base.store,self.base.c
        memory.event(store,campaign,'LINKEDIN','query',memory.normalized('site:linkedin.com cerco wordpress'),
                     {'query':'site:linkedin.com cerco wordpress','results':1,'strategy':'old social'})
        body={'flows':['LINKEDIN'],'state':'DISCOVERED','url':'https://www.linkedin.com/posts/synthetic','original':False}
        with store.connect() as c:
            c.execute('INSERT INTO agent6_records(campaign_id,flow,request_key,state,body,updated_at) VALUES (?,?,?,?,?,?)',
                      (campaign['id'],'LINKEDIN','legacy-social','DISCOVERED',encode(body),now()))
        self.assertEqual(listing(store,{'flow':'SOCIAL'})['total'],1)
        self.assertEqual(listing(store,{'flow':'LINKEDIN'})['total'],1)
        self.assertTrue(memory.seen_query(store,'SOCIAL','site:linkedin.com cerco wordpress'))
        hist=memory.history(store,'SOCIAL')
        self.assertEqual(len(hist['recent_queries']),1)
        self.assertEqual(hist['strategy_groups'][0]['flow'],'SOCIAL')
        self.assertEqual(strategy_id('cerco wordpress','SOCIAL'),strategy_id('cerco wordpress','LINKEDIN'))
        with store.connect() as c:
            self.assertEqual(c.execute('SELECT flow FROM agent6_records').fetchone()[0],'LINKEDIN')
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')


if __name__=='__main__':unittest.main()
