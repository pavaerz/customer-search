"""Synthetic original documents; no network and no claim of real leads.

Exercise canonical validation and commercial decisions together, rather than
trusting model labels or bypassing attribution with prequalified records.
"""
import unittest
from test_agent6 import TEXT, source, output, identity, evaluated
from sales.agent6 import schema, qualification as q, commercial_roles as roles


class Attribution(unittest.TestCase):
    def test_non_company_identity_withheld_but_other_proofs_survive(self):
        for name in ('Unioncamere Piemonte', 'Regione Lombardia', 'M.I.A. Lombardia', 'Emilia-Romagna'):
            src=source(name+'\nNew products announced.')
            p,o=output(src,'COMPANY_SIGNAL',{'entity':name,'signal':'New products announced.'})
            a=schema.validate(o,p)['analyses'][0]
            self.assertEqual([f['field'] for f in a['facts']],['signal'])
            self.assertEqual(a['identity_issues'][0]['code'],'non_company_identity')
            b=q.evaluate(src,a,p['evidence'],'NEWS',{})
            self.assertFalse(b['identity_verified'])
            self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))

    def test_supplier_service_is_not_saved_as_client_request(self):
        src=source('Alfa Srl\nWe offer WordPress development for your business.')
        b=evaluated(src,'SUPPLIER_OFFER',fields={'entity':'Alfa Srl','request':'We offer WordPress development for your business.'})
        self.assertEqual(b['state'],'REJECTED')
        self.assertFalse(any(f['field']=='request' for f in b['facts']))
        self.assertEqual(b['withheld_evidence'][0]['url'],src['url'])
        self.assertEqual(b['actor_attribution']['subject']['role'],'SUPPLIER')

    def test_searching_for_clients_is_not_buying_freelance_services(self):
        request='We are looking for new clients for freelance WordPress development. Remote from Italy.'
        src=source('Alfa Srl\nPosted 2 days ago\n'+request)
        b=evaluated(src,fields={'entity':'Alfa Srl','request':request,'technical':'WordPress','contract':'freelance','geography':'Remote from Italy.'})
        self.assertEqual(b['state'],'NEEDS_REVIEW')
        self.assertEqual(b['actor_attribution']['subject']['role'],'SUPPLIER')
        self.assertFalse(any(f['field']=='request' for f in b['facts']))

    def test_agency_can_sell_services_and_seek_freelancers(self):
        b=evaluated(source(TEXT+'\nWe are a digital agency. We offer websites.'),'AGENCY_PARTNERSHIP')
        self.assertEqual(b['state'],'POTENTIAL')
        self.assertEqual(b['actor_attribution']['subject']['role'],'BUYER')
        self.assertEqual(b['actor_attribution']['organization']['role'],'AGENCY')
        self.assertTrue(any(f['field']=='request' for f in b['facts']))

    def test_flow_does_not_make_a_company_a_startup(self):
        p,o=output();a=schema.validate(o,p)['analyses'][0]
        b=q.evaluate(source(),a,p['evidence'],'STARTUPS',identity())
        self.assertEqual(b['actor_attribution']['organization']['role'],'UNKNOWN')

    def test_publisher_and_subject_are_distinct(self):
        src=source(TEXT,url='https://news.example/article',editorial=True)
        p,o=output(src);a=schema.validate(o,p)['analyses'][0]
        b=q.evaluate(src,a,p['evidence'],'NEWS',{'name':'News Publishing','identity_status':'verified','website':'https://news.example'})
        self.assertEqual(b['actor_attribution']['source']['role'],'PUBLISHER')
        self.assertEqual(b['actor_attribution']['subject']['name'],'Alfa Srl')
        self.assertFalse(b['identity_verified'])
        self.assertNotIn(b['state'],('VERIFIED','POTENTIAL'))

    def test_refusal_is_not_a_buyer_and_snippet_is_not_self_description(self):
        src=source('We are a digital agency.',original=False)
        facts=[{'field':'request','quote':'We offer WordPress services; no freelancers.'}]
        b=roles.inspect(src,'SUPPLIER_OFFER',facts,identity(),True,'Alfa Srl')
        self.assertEqual(b['subject']['role'],'SUPPLIER')
        self.assertEqual(b['organization']['role'],'UNKNOWN')
        self.assertEqual(len(b['withheld']),1)

    def test_own_declared_budget_preserved_and_unknown_never_estimated(self):
        b=evaluated();self.assertEqual(b['budget']['amount'],4000)
        self.assertEqual(b['budget']['basis'],'declared_on_verified_owner_source')
        b=evaluated(source(TEXT.replace('Budget: €4000 fixed price','Funding: €5000000')))
        self.assertEqual(b['budget']['kind'],'UNKNOWN');self.assertIsNone(b['budget']['amount'])

    def test_unverified_owner_cannot_supply_budget(self):
        self.assertEqual(evaluated(ident=False)['budget']['kind'],'UNKNOWN')

    def test_other_company_budget_neither_rewards_nor_rejects_buyer(self):
        src=source(TEXT.replace('Budget: €4000 fixed price','Client Beta Srl\nBudget: €500 fixed price'))
        b=evaluated(src)
        self.assertEqual(b['budget']['kind'],'UNKNOWN')
        self.assertIsNotNone(b['budget_uncertainty'])
        self.assertNotIn('budget_below_minimum',b['counterevidence'])
        self.assertEqual(b['state'],'VERIFIED')

    def test_actual_low_budget_rejects_with_matching_counterevidence(self):
        b=evaluated(source(TEXT.replace('€4000','€500')))
        self.assertEqual(b['state'],'REJECTED')
        self.assertIn('budget_below_minimum',b['counterevidence'])

    def test_existing_target_exclusion_applies_to_verified_subject_only(self):
        # The reader obtains this structured finding from the existing,
        # separately tested own-company legal/size detector.
        excluded={'code':'large_company','reason':'Gruppo documentato fuori target','url':'https://alfa.example/careers'}
        b=evaluated(source(target_exclusion=excluded))
        self.assertEqual(b['state'],'REJECTED')
        self.assertEqual(b['counterevidence'],['large_company'])
        b=evaluated(source(target_exclusion=excluded),ident=False)
        self.assertNotEqual(b['state'],'REJECTED')

    def test_italian_and_english_number_formats_keep_declared_value(self):
        for amount,value in [('4.000',4000),('4,000',4000),('4.000,50',4000.5),('4,000.50',4000.5),('4000,50',4000.5),('4000.50',4000.5)]:
            with self.subTest(amount=amount):
                b=evaluated(source(TEXT.replace('€4000','€'+amount)))
                self.assertEqual(b['budget']['amount'],value)
                self.assertEqual(b['state'],'VERIFIED')
        self.assertEqual(q.money('Budget: €4,00,0 fixed price')['kind'],'UNKNOWN')


class WebApps(unittest.TestCase):
    constraints=('Limited single workflow MVP for bookings. No sensitive data; authentication and access control. '
                 'No external integrations. Maintenance included and agreed.')

    def decision(self,constraints):
        request='We are looking for a freelance frontend developer to build our complete web app. Remote from Italy.'
        src=source('Alfa Srl\nPosted 2 days ago\n'+request+'\n'+constraints,title='Frontend web app')
        fields={'entity':'Alfa Srl','request':request,'technical':'frontend developer','contract':'freelance','geography':'Remote from Italy.'}
        if constraints:fields['feasibility']=constraints
        return evaluated(src,fields=fields)

    def test_bounded_application_can_complete_qualification(self):
        b=self.decision(self.constraints)
        self.assertEqual(b['state'],'VERIFIED')
        self.assertEqual(b['feasibility']['status'],'BOUNDED')
        self.assertEqual(b['budget']['kind'],'UNKNOWN')
        self.assertTrue(b['feasibility']['proofs'])

    def test_each_unknown_critical_constraint_prevents_promotion(self):
        for remove in ('Limited single workflow MVP for bookings.','No sensitive data; authentication and access control.',
                       'No external integrations.','Maintenance included and agreed.'):
            with self.subTest(remove=remove):
                b=self.decision(self.constraints.replace(remove,''))
                self.assertEqual(b['state'],'NEEDS_REVIEW')
                self.assertIn('feasibility',b['missing'])

    def test_explicit_critical_risk_overrides_generic_reassurance(self):
        b=self.decision(self.constraints+' Includes medical records and a 24/7 SLA.')
        self.assertEqual(b['state'],'NEEDS_REVIEW')
        self.assertEqual(b['feasibility']['status'],'RISKY')
        self.assertEqual(b['feasibility']['risk_quote'],'medical records')

    def test_snippet_constraints_do_not_prove_feasibility(self):
        result=roles.webapp_feasibility([{'field':'feasibility','quote':self.constraints,'url':'https://alfa.example','original':False}])
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['proofs'],[])

    def test_negated_security_or_maintenance_is_not_positive_evidence(self):
        for text in (self.constraints.replace('authentication and access control','authentication not required'),
                     self.constraints.replace('Maintenance included and agreed','Maintenance not included or planned')):
            b=self.decision(text)
            self.assertEqual(b['state'],'NEEDS_REVIEW')
            self.assertIn('feasibility',b['missing'])
