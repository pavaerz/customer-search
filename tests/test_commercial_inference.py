import copy
import json
from datetime import datetime,timezone,timedelta
import unittest
from unittest.mock import patch
from sales.db import now,digest
from sales.research_rules import qualify,validate_signals
from sales.research_analysis import LocalResearcher
from sales.commercial_inference import declared_condition
from test_research import sample


def inference_sample():
    identity=sample()[0]
    texts=[
        'Alfa lancia un nuovo marchio di arredi e apre la vendita diretta ai consumatori privati in Italia.',
        'Il nostro sito e il catalogo sono riservati esclusivamente ai rivenditori autorizzati. La consultazione richiede il codice del rivenditore.',
    ]
    docs=[{'id':digest(t),'url':'https://alfa.example/'+str(i),'text':t,'official':True,'status':200,
           'published_at':now()[:10] if i==0 else None,'checked_at':now(),'content_hash':digest(t)} for i,t in enumerate(texts)]
    signals,errors=validate_signals([{'document_id':d['id'],'quote':d['text'],'kind':'event' if i==0 else 'condition'} for i,d in enumerate(docs)],docs)
    assert not errors
    ids=[s['id'] for s in signals]
    proposal={**sample()[3],'support_ids':ids,'project':'website','budget_signal_id':'',
              'why':'Nuovo pubblico privato; il catalogo e sito esistenti sono riservati ai rivenditori.',
              'proposal':'Sito pubblico completo per il nuovo marchio e il catalogo destinato ai privati.'}
    review={**sample()[4],'support_ids':ids,'inference':{
        'event_id':ids[0],'condition_id':ids[1],'relationship':'incompatible_audience',
        'reason':'Il nuovo pubblico privato è distinto dai rivenditori autorizzati che accedono al canale esistente.',
        'full_project_reason':'Occorre una presenza pubblica completa del nuovo marchio con catalogo e percorso di contatto per i privati.',
        'small_fix_reason':'Una traduzione o pagina dentro il portale riservato non rende accessibile il catalogo al nuovo pubblico.',
    }}
    return identity,docs,signals,proposal,review


class InferenceTests(unittest.TestCase):
    def test_privacy_authority_address_does_not_erase_owned_company_location(self):
        from sales.research_analysis import identity_from
        schema={'@type':'Organization','url':'https://alfa.example/','legalName':'Alfa Srl',
                'vatID':'12345678901','address':{'streetAddress':'Via Cherso 21','postalCode':'31045','addressLocality':'Motta di Livenza','addressRegion':'TV','addressCountry':'IT'}}
        home={'url':'https://alfa.example/','status':200,'checked_at':now(),'html':'<script type="application/ld+json">'+json.dumps(schema)+'</script><p>info@alfa.example</p>'}
        privacy={'url':'https://alfa.example/privacy','status':200,'checked_at':now(),'html':'<p>Garante per la protezione dei dati personali</p><p>Piazza Venezia 11 — 00187 Roma</p>'}
        self.assertEqual(identity_from([home,privacy])['region'],'Veneto')
    def test_google_query_excludes_only_unreadable_socials_and_preserves_lookup(self):
        from sales.discovery_planner import searchable_query
        query='"nuovo marchio" arredamento'
        prepared=searchable_query({'query':query})
        for host in ('facebook.com','instagram.com','youtube.com','paginegialle.it','firmania.it'):
            self.assertIn('-site:'+host,prepared)
        self.assertEqual(searchable_query({'query':prepared}),prepared)
        self.assertEqual(searchable_query({'query':query,'subject':'Alfa Srl'}),query)
        scoped='site:alfa.example nuovo marchio'
        self.assertEqual(searchable_query({'query':scoped}),scoped)
    def test_province_before_postcode_remains_geographic_evidence(self):
        from sales.research_rules import region_of
        self.assertEqual(region_of('Via Flaminia km 58.00 Civita Castellana VT 01033 Seguici sui social'),'Lazio')
        self.assertIsNone(region_of('Via Roma 12, 80100 Napoli'))
    def test_inference_can_pass_without_request_or_declared_defect(self):
        args=inference_sample();a=qualify(*args)
        self.assertEqual({s['kind'] for s in args[2]},{'event','condition'})
        self.assertEqual(a['status'],'qualified')
        self.assertEqual(a['need_inference']['type'],'inference')
        self.assertIsNone(a['budget']);self.assertEqual(a['score_detail']['Compatibilità economica documentata']['points'],0)

    def test_missing_relation_or_alternative_check_never_qualifies(self):
        for field in ('inference','existing_solution_checked','small_fix_sufficient'):
            args=inference_sample();args[4].pop(field)
            self.assertNotEqual(qualify(*args)['status'],'qualified')
        for field in ('reason','full_project_reason','small_fix_reason'):
            args=inference_sample();args[4]['inference'][field]=''
            self.assertNotEqual(qualify(*args)['status'],'qualified')

    def test_stale_future_or_undated_event_not_promoted(self):
        for date in (None,'2000-01-01','2099-01-01'):
            args=inference_sample();args[2][0]['published_at']=date
            self.assertNotEqual(qualify(*args)['status'],'qualified')

    def test_condition_alone_or_email_catalogue_and_translation_are_insufficient(self):
        for text in ('Gli ordini possono essere inviati tramite email.',
                     'Gli ordini dei clienti privati si ricevono solo via email.',
                     'Il sito è soltanto in italiano.',
                     'Produciamo esclusivamente arredi artigianali.',
                     'Il catalogo comprende i nostri prodotti. Solo qualità italiana.'):
            args=inference_sample();args[2][1]['quote']=text;args[1][1]['text']=text
            self.assertFalse(declared_condition(text))
            self.assertNotEqual(qualify(*args)['status'],'qualified')
        args=inference_sample();args[2][:]=args[2][1:]
        self.assertNotEqual(qualify(*args)['status'],'qualified')

    def test_forged_unscoped_or_republished_evidence_cannot_support_relation(self):
        for mutation in ('forged','unscoped','namesake','same_event','missing_ref','wrong_condition'):
            args=inference_sample()
            if mutation=='forged':args[1][1]['text']='Testo diverso, senza condizione commerciale.'
            if mutation=='unscoped':args[1][0]['official']=False
            if mutation=='namesake':args[1][0].update(official=False,scoped_to_subject='Azienda Beta')
            if mutation=='same_event':args[2][1]['event_key']=args[2][0]['event_key']
            if mutation=='missing_ref':args[4]['support_ids']=args[4]['support_ids'][:1]
            if mutation=='wrong_condition':args[4]['inference']['condition_id']='inventato'
            self.assertNotEqual(qualify(*args)['status'],'qualified',mutation)

    def test_coverage_contact_scope_and_feasibility_gates_still_apply(self):
        for mutation in ('coverage','contact','scope','risk','technical'):
            args=inference_sample()
            if mutation=='coverage':args[3]['checked_sections'].remove('solutions')
            if mutation=='contact':args[0]['contacts']=[]
            if mutation=='scope':args[3]['scope']='small_change'
            if mutation=='risk':args[3]['critical_unknowns']=['Dati sanitari e integrazione critica non delimitati']
            limits=['Pagina necessaria: HTTP 503'] if mutation=='technical' else []
            self.assertNotEqual(qualify(*args,limits=limits)['status'],'qualified',mutation)

    def test_analysis_reaches_correlation_for_event_plus_condition(self):
        identity,docs,signals,proposal,review=inference_sample()
        calls=[]
        def answer(task,data,schema):
            calls.append(data)
            if 'existing_solution_ids' in schema['properties']:return {'existing_solution_ids':[]}
            if 'units' in data:
                return {'claims':[{'unit_id':data['units'][0]['id'],'kind':'event' if data['document_id']==docs[0]['id'] else 'condition'}]}
            if 'proposal' in data:
                self.assertIn('inference',schema['required'])
                return review
            return proposal
        with patch.object(LocalResearcher,'call',side_effect=answer):
            s,p,v,limits=LocalResearcher(None).analyze(identity,docs,dict.fromkeys(('identity','offer','contact','solutions'),True))
        self.assertEqual(len(calls),5)
        self.assertFalse(limits)
        self.assertEqual(qualify(identity,docs,s,p,v)['status'],'qualified')

    def test_event_with_existing_offer_is_evaluated_without_explicit_request(self):
        identity,docs,signals,proposal,review=inference_sample()
        docs[1]['text']='Le collezioni del nuovo marchio sono già disponibili sul sito pubblico con schede e contatti.'
        calls=[]
        def answer(task,data,schema):
            calls.append(data)
            if 'existing_solution_ids' in schema['properties']:return {'existing_solution_ids':[]}
            if 'units' in data:
                return {'claims':[{'unit_id':data['units'][0]['id'],'kind':'event' if data['document_id']==docs[0]['id'] else 'counterevidence'}]}
            return {**proposal,'project':'none','support_ids':[]}
        with patch.object(LocalResearcher,'call',side_effect=answer):
            s,p,v,limits=LocalResearcher(None).analyze(identity,docs,dict.fromkeys(('identity','offer','contact','solutions'),True))
        self.assertEqual(len(calls),4)
        self.assertEqual(qualify(identity,docs,s,p,v)['status'],'rejected')
