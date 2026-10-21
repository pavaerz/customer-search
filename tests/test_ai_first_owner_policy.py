"""Explicit user exclusions; no budget inference or model accuracy claims."""
import json
import unittest
from unittest.mock import patch

import test_ai_first as harness
from sales.agent6.owner_policy import exclusions
from sales.agent6 import decision


def page(text,name='Alfa Srl',organization=None):
    markup='<title>'+name+'</title><h1>'+name+'</h1><p>'+text+'</p>'
    if organization:markup+='<script type="application/ld+json">'+json.dumps(organization)+'</script>'
    return {'url':'https://alfa.example/','html':markup,'checked_at':harness.DATE,'status':200}


def identity(name='Alfa Srl'):
    return {'name':name,'website':'https://alfa.example/','identity_status':'verified'}


class OwnerExclusions(unittest.TestCase):
    def test_verified_legal_form_not_wellness_word_or_customer(self):
        p=page('Realizziamo sistemi digitali.','Alfa S.p.A.')
        self.assertEqual(exclusions([p],identity('Alfa S.p.A.'),True)[0]['code'],'excluded_legal_form')
        self.assertEqual(exclusions([p],identity('Alfa S.p.A.'),False),[])
        self.assertEqual(exclusions([page('Il nostro centro wellness SPA.')],identity(),True),[])
        self.assertEqual(exclusions([page('Lavoriamo per il cliente Beta S.p.A.')],identity(),True),[])
        self.assertEqual(exclusions([page('Centro benessere','DAY SPA')],identity('DAY SPA'),True),[])

    def test_public_owner_or_government_schema_not_customer_mention(self):
        self.assertEqual(exclusions([page('Servizi pubblici.','Comune di Padova')],
                                    identity('Comune di Padova'),True)[0]['code'],'public_administration')
        self.assertEqual(exclusions([page('Il Comune di Padova è un nostro cliente.')],identity(),True),[])
        for company in ('Regione Software Srl','RegioneViva','Ministero del Design Srl'):
            self.assertEqual(exclusions([page('Servizi digitali',company)],identity(company),True),[])
        org={'@type':'GovernmentOrganization','url':'https://alfa.example/','name':'Alfa Srl'}
        self.assertEqual(exclusions([page('Servizio pubblico',organization=org)],identity(),True)[0]['code'],'public_administration')
        org['url']='https://other.example/'
        self.assertEqual(exclusions([page('Un nostro cliente',organization=org)],identity(),True),[])

    def test_large_group_only_owner_self_description(self):
        p=page('Siamo un gruppo multinazionale con sedi in tutto il mondo.')
        self.assertEqual(exclusions([p],identity(),True)[0]['code'],'large_group')
        for text in ('Siamo fornitori del gruppo multinazionale Beta.',
                     'Il nostro investitore è una multinazionale.',
                     'Produciamo per clienti del gruppo multinazionale Beta.',
                     'Siamo una piccola azienda con 5 dipendenti.'):
            self.assertEqual(exclusions([page(text)],identity(),True),[],text)

    def test_evidence_is_visible_and_blocks_promotion_without_inventing_budget(self):
        p=harness.payload();proof=exclusions([page('Siamo una multinazionale.')],identity(),True)
        p.update(policy_exclusion=True,commercial_exclusions=proof)
        with self.assertRaisesRegex(ValueError,'commercial_policy_exclusion'):
            decision.validate(harness.response(p),p)
        out=harness.response(p);out.update(decision='NOT_INTERESTING',reason='Fuori dai criteri: titolare multinazionale.')
        out,_=decision.validate(out,p)
        record=decision.materialize({'url':'https://alfa.example/','checked_at':harness.DATE,'original':True},
                                    out,p['evidence'],p,'AGENCIES')
        self.assertEqual(record['commercial_exclusions'],proof)
        self.assertIsNone(record['budget']['amount'])
        self.assertEqual(record['decision'],'NOT_INTERESTING')


class ReadPath(unittest.TestCase):
    def test_original_reader_passes_owner_policy_to_model_and_dossier(self):
        base=harness.IntegratedPath();base.setUp()
        try:
            original=page(harness.TEXT+'\nSiamo una multinazionale.')
            base.w.enqueue('candidate','AGENCIES',{'url':original['url']},'owner-policy')
            with base.store.connect() as db:
                row=db.execute("SELECT * FROM research_tasks WHERE fingerprint='owner-policy'").fetchone()
                task={**dict(row),'payload':json.loads(row['payload'])}
            observed=[]
            def model(p,cfg,check):
                observed.append(p)
                out=harness.response(p);out.update(decision='NOT_INTERESTING',reason='Grande gruppo escluso.')
                return {'output':out,'usage':{}}
            with patch('sales.agent6.research.CompanyWeb.get',return_value=original),patch(
                    'sales.agent6.research.identity_from',return_value=identity()),patch(
                    'sales.agent6.ai.infer',side_effect=model):
                base.w.execute(task,lambda:None)
            self.assertTrue(observed[0]['policy_exclusion'])
            self.assertEqual(observed[0]['commercial_exclusions'][0]['code'],'large_group')
            with base.store.connect() as db:
                b=json.loads(db.execute('SELECT body FROM agent6_records ORDER BY id DESC').fetchone()[0])
            self.assertEqual(b['decision'],'NOT_INTERESTING')
            self.assertEqual(b['commercial_exclusions'][0]['code'],'large_group')
        finally:base.tearDown()
