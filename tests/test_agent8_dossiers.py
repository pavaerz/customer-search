"""Offline cross-channel identity, human corrections and historical integrity."""
import copy,json,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import test_agent6 as original
import test_agent6_campaign32 as support
from sales.agent6 import memory,api,entities,annotations
from sales.agent6.worklist import listing
from sales.db import digest,encode

DATE='2026-10-19T12:00:00Z'


def legal(body,number='IT12345678903'):
    b=copy.deepcopy(body);host=b['official_domain']
    b['identity']={**b.get('identity',{}),'legal_id':number,'legal_id_conflicts':[],
        'source_url':host,'legal_id_evidence':[{'legal_id':number,'url':host+'/contatti',
        'original':True,'checked_at':DATE,'content_hash':'saved-page-hash',
        'method':'owned_legal_text','quote':'Partita IVA: '+number}]}
    return b


class Dossiers(unittest.TestCase):
    def setUp(self):
        self.base=support.Campaign32Fix();self.base.setUp()
        self.store,self.c,self.rs=self.base.store,self.base.c,self.base.rs
        self.at=datetime(2026,10,19,14,tzinfo=timezone.utc)
    def tearDown(self):self.base.tearDown()
    def save(self,body=None,flow='AGENCIES',**kw):return memory.save_record(self.store,self.c,flow,{**(body or original.evaluated()),**kw})
    def view(self,**kw):return listing(self.store,{'group':'company',**kw},at=self.at)

    def test_one_company_three_flows_distinct_requests_and_originals_preserved(self):
        ids=[self.save(flow=f,url=f'https://alfa.example/{i}') for i,f in enumerate(('AZIENDE','AGENCIES','SOCIAL'))]
        with self.store.connect() as c:before='\n'.join(c.iterdump())
        with patch('socket.create_connection',side_effect=AssertionError('No network')):
            result=self.view();self.assertEqual(result['total'],1)
            self.assertEqual(result['counts']['ready'],1)
            d=api.dossier(self.store,ids[0])['company_dossier']
        self.assertEqual(len(d['signals']),3);self.assertEqual(d['flows'],['AGENCIES','AZIENDE','SOCIAL'])
        self.assertEqual({p['record_id'] for p in d['evidence']},set(ids))
        self.assertEqual({l['basis'] for l in d['links']},{'same_verified_official_domain'})
        with self.store.connect() as c:self.assertEqual('\n'.join(c.iterdump()),before)

    def test_namesakes_without_shared_domain_or_proven_vat_never_merge(self):
        self.save();self.save(url='https://other.example/job',official_domain='https://other.example',entity_key=digest('other'))
        self.assertEqual(self.view()['total'],2)

    def test_same_vat_on_owned_originals_links_two_domains_not_publisher(self):
        a=legal(original.evaluated());first=self.save(a)
        second=self.save(legal({**a,'url':'https://alfabrand.example/jobs','official_domain':'https://alfabrand.example','entity_key':digest('brand')}),flow='SOCIAL')
        self.assertEqual(self.view()['total'],1)
        self.assertEqual(len(api.dossier(self.store,second)['company_dossier']['domains']),2)
        # A search snippet/third-party article repeating a VAT is not an alias proof.
        bad=legal({**a,'url':'https://publisher.example/jobs','official_domain':'https://publisher.example','entity_key':digest('publisher')})
        bad['identity']['legal_id_evidence'][0]['url']='https://alfa.example/contatti'
        self.save(bad);self.assertEqual(self.view()['total'],2)
        memory.feedback(self.store,first,'not_interesting')
        self.assertEqual(self.view(view='excluded')['total'],1)
        self.assertEqual(self.view()['total'],1)

    def test_conflicting_vat_prevents_domain_bridge(self):
        a=legal(original.evaluated());self.save(a)
        self.save(legal({**a,'url':'https://alfa.example/new-tenant'},'IT98765432103'))
        self.save(url='https://alfa.example/no-legal-proof')
        self.assertEqual(self.view()['total'],3)
        self.assertEqual(entities.vat('IT98765432103'),'IT98765432103')

    def test_invalid_vat_or_model_identity_does_not_join_distinct_domains(self):
        self.save(legal(original.evaluated(),'IT12345678901'))
        self.save(legal({**original.evaluated(),'url':'https://other.example/jobs','official_domain':'https://other.example','entity_key':'other'},'IT12345678901'))
        self.assertEqual(self.view()['total'],2)
        self.assertIsNone(entities.vat('IT00000000000'))

    def test_new_alias_cannot_bypass_explicit_exclusion_or_contact_memory(self):
        first=self.save(legal(original.evaluated()))
        memory.feedback(self.store,first,'not_interesting')
        alias=legal({**original.evaluated(),'url':'https://brand.example/job','official_domain':'https://brand.example','entity_key':'brand'})
        second=self.save(alias)
        self.assertTrue(api.dossier(self.store,second)['body']['suppressed'])
        self.assertEqual(self.view()['total'],0)
        memory.feedback(self.store,first,'restore');memory.feedback(self.store,first,'contacted')
        third=self.save(legal({**alias,'url':'https://third.example/job','official_domain':'https://third.example','entity_key':'third'}))
        self.assertEqual(api.dossier(self.store,third)['state'],'REJECTED')
        self.assertIn('già contattata',api.dossier(self.store,third)['body']['reason'])

    def test_shared_company_memory_contains_all_channels_without_merging_facts(self):
        self.save(flow='AZIENDE');self.save(flow='SOCIAL',url='https://alfa.example/post')
        companies=memory.history(self.store,'AGENCIES')['shared_companies']
        self.assertEqual(len(companies),1);self.assertEqual(companies[0]['request_count'],2)
        self.assertEqual(companies[0]['flows'],['AZIENDE','SOCIAL'])
        self.assertTrue(all('record_id' in f for f in companies[0]['evidence']))

    def test_crm_keeps_project_service_and_blocks_alias_outreach_after_contact(self):
        first=self.save(legal({**original.evaluated(),'service':'ecommerce'}))
        second=self.save(legal({**original.evaluated(),'url':'https://brand.example/job','official_domain':'https://brand.example','entity_key':'brand'}))
        pid=api.save_contact(self.store,first)['prospect_id']
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT service FROM prospects WHERE id=?',(pid,)).fetchone()[0],'ecommerce')
            c.execute("UPDATE prospects SET stage='contacted',notes='Manual note retained' WHERE id=?",(pid,))
        with self.assertRaisesRegex(ValueError,'già contattata'):api.save_contact(self.store,second)
        self.assertEqual(api.save_contact(self.store,first)['prospect_id'],pid)
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM prospects').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT notes FROM prospects WHERE id=?',(pid,)).fetchone()[0],'Manual note retained')

    def test_identity_extractor_retains_owned_vat_proof_not_web_agency_credit(self):
        from sales.research_analysis import identity_from
        from test_agent8_proactive import pages,ROOT
        page=pages()[ROOT];page['html']=page['html'].replace('12345678901','12345678903')
        page['html']+='<aside>Realizzato da Other Agency Srl - Partita IVA: 98765432103</aside>'
        identity=identity_from([page]);self.assertEqual(identity['legal_id'],'IT12345678903')
        self.assertTrue(identity['legal_id_evidence']);self.assertEqual(identity['legal_id_conflicts'],[])
        self.assertTrue(all(p['content_hash']==digest(page['html']) for p in identity['legal_id_evidence']))

    def test_social_host_or_unverified_name_not_a_company_anchor(self):
        a=original.evaluated()
        for i in range(2):self.save({**a,'url':f'https://linkedin.com/posts/{i}','official_domain':'https://linkedin.com','entity_key':'social'},flow='SOCIAL')
        self.assertEqual(self.view()['total'],2)

    def test_company_view_keeps_request_contact_history_and_stable_counts(self):
        first=self.save();second=self.save(url='https://alfa.example/role-two')
        memory.feedback(self.store,first,'contacted')
        self.assertEqual(self.view()['total'],0)
        review=self.view(view='review');contacted=self.view(view='contacted')
        self.assertEqual(review['items'][0]['id'],second);self.assertEqual(contacted['items'][0]['id'],first)
        self.assertEqual(review['counts'],contacted['counts'])
        self.assertIsNone(review['items'][0]['feedback'])

    def test_corrections_do_not_modify_qualification_evidence_crm_or_budget(self):
        rid=self.save(state='NEEDS_REVIEW',original=False,identity_verified=False)
        before=api.dossier(self.store,rid)
        with self.store.connect() as c:filters=c.execute('SELECT filters FROM campaigns').fetchone()[0]
        annotations.save(self.store,rid,{'opportunity_type':'DEMANDA_ESPLICITA','priority':'high','commercial_fit':'high'},'Valutazione personale, identità ancora da verificare.')
        self.assertEqual(self.view()['total'],0)
        row=self.view(view='review',priority='high')['items'][0]
        self.assertEqual(row['state'],'NEEDS_REVIEW');self.assertFalse(row['body']['verification_dimensions']['declared_demand'])
        after=api.dossier(self.store,rid)
        self.assertEqual(after['body'],before['body']);self.assertEqual(after['revisions'],before['revisions'])
        with self.store.connect() as c:
            self.assertEqual(c.execute('SELECT filters FROM campaigns').fetchone()[0],filters)
            self.assertEqual(c.execute('SELECT count(*) FROM prospects').fetchone()[0],0)

    def test_annotation_follows_same_request_not_another_role_and_can_be_reset(self):
        rid=self.save();other=self.save(url='https://alfa.example/other')
        annotations.save(self.store,rid,{'relevance':'irrelevant'},'Fuori dal mio ambito.')
        self.assertEqual(self.view(view='review')['items'][0]['id'],rid)
        self.assertEqual(self.view()['items'][0]['id'],other)
        self.rs.stop(self.c['id']);self.rs.paused(self.c['id']);self.c=self.rs.create(self.base.filters)
        newer=self.save();self.assertIn('relevance',api.dossier(self.store,newer)['manual_corrections'])
        annotations.save(self.store,newer,{'relevance':None},'Rivalutazione dopo nuove prove.')
        self.assertEqual(api.dossier(self.store,newer)['manual_corrections'],{})
        self.assertEqual(len(api.dossier(self.store,newer)['correction_history']),2)

    def test_annotation_validation_and_repeatable_additive_migration(self):
        rid=self.save()
        for changes,note in [({'state':'VERIFIED'},'No'),({'priority':{}},'No'),({'priority':'urgent'},'No'),({'priority':'high'},'')]:
            with self.assertRaises(ValueError):annotations.save(self.store,rid,changes,note)
        annotations.save(self.store,rid,{'priority':'low'},'Manual review')
        with self.store.connect() as c:
            before=c.execute('SELECT body FROM agent6_records WHERE id=?',(rid,)).fetchone()[0]
            annotations.migrate(c);annotations.migrate(c)
            self.assertEqual(c.execute('SELECT body FROM agent6_records WHERE id=?',(rid,)).fetchone()[0],before)
            self.assertEqual(c.execute('SELECT count(*) FROM agent8_annotations').fetchone()[0],1)

    def test_corrections_affect_planner_only_after_distinct_sample_threshold(self):
        query='agenzia cerca freelance WordPress Veneto'
        for i in range(3):
            rid=self.save(url=f'https://alfa.example/job-{i}',query=query,strategy='external_collaboration')
            memory.event(self.store,self.c,'AGENCIES','query',str(i),{'query':query+f' {i}','strategy':'external_collaboration','results':1})
            annotations.save(self.store,rid,{'relevance':'irrelevant'},'Servizio fuori ambito confermato dalla lettura.')
            annotations.save(self.store,rid,{'relevance':'irrelevant'},'Conferma, non una seconda azienda.')
            h=memory.history(self.store,'AGENCIES');learn=h['manual_corrections'][0]
            self.assertEqual(learn['reviewed_requests'],i+1)
            self.assertEqual(learn['priority_adjustment'],-1 if i==2 else 0)
        family=next(g for g in h['strategy_groups'] if g.get('annotation_adjustment'))
        self.assertEqual(family['annotation_adjustment'],-1)
        chosen=memory.choose([{'query':query,'strategy':'external_collaboration'},{'query':'agenzia cerca progetto ecommerce Veneto','strategy':'project'}],h,1,0)
        self.assertEqual(chosen['strategy'],'project')


if __name__=='__main__':unittest.main()
