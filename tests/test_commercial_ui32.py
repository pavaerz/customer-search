"""Offline presentation regression; no server, provider, AI or production data."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is required for frontend rendering tests')
class CommercialPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path('static/commercial.js').read_text()
        harness = r'''
const vm=require('vm');
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const context={settingsView:()=>{},campaignActions:()=>'',renderMain:()=>{},updateResearchState:()=>{},runCampaignAction:()=>{},document:{addEventListener:()=>{}},esc:escape,dt:v=>v||'Data non disponibile',link:(u,t)=>'<a href="'+escape(u)+'">'+escape(t)+'</a>'};
vm.createContext(context);vm.runInContext('var campaignActions,renderMain,updateResearchState,runCampaignAction,settingsView;',context);vm.runInContext(SOURCE,context);
function render(expression){return vm.runInContext(expression,context)}
const verified={state:'VERIFIED',body:{engine:'AGENCIES',company:'Alfa',skills:['WordPress'],contract:'external',verified_proof:{subject:'Alfa',quote:'Cerchiamo sviluppatori WordPress freelance.',url:'https://alfa.example/collabora',collaboration_type:'external',temporal_limits:'Disponibilità non confermata',status:'verified_request'},verification:{status:'complete',currentness:'standing_invitation',availability_verified:false,checks:{identity:true,attributable_request:true,compatible_relationship:true}},commercial_intent:{commercial_role:'FREELANCE_BUYER',requester:'publisher',work_recipient:'external_professional'}}};
context.item=verified;
const proof=render('commercialQualification(item,true)');
context.item={state:'VERIFIED',body:{engine:'AGENCIES'}};
const historical=render('commercialQualification(item)');
context.item={state:'NEEDS_REVIEW',body:{engine:'FREELANCE',commercial_intent:{commercial_role:'BUYER',request_clause:'<img src=x onerror=alert(1)>',negations:[{quote:'Non collaboriamo con freelance.'}],contradictions:[{positive:'Cerchiamo sviluppatori freelance.',negative:'Non collaboriamo con freelance.'}]},verification:{status:'contradictory'}}};
const contradiction=render('commercialQualification(item,true)');
context.body={engine:'WEBSITE_REBUILD',screening:{status:'incomplete'},browser:{executed:false,outcome:'budget_deferred',limits:['Quota browser esaurita']}};
const deferred=render('commercialWebsiteSummary(body)');
context.body={engine:'WEBSITE_REBUILD',screening:{status:'negative'},evidence:[],browser:{completed:false,outcome:'partial',resources_closed:true,worker_reaped:true,elapsed_ms:1200,total_limit_ms:1500,pages:[{url:'https://alfa.example'}],levels:{HTTP:{status:'available'},DOM:{status:'partial'},BROWSER_ADVANCED:{status:'not_requested'}},diagnostics:[{phase:'dom',status:'timeout',elapsed_ms:1000,limit_ms:1000,error:'<script>broken()</script>'}]}};
const partial=render('commercialWebsiteSummary(body)+commercialBrowserDiagnostics(body)');
context.body={url:'https://linkedin.com/jobs/view/freelance-python-at-alfa-123',social:{indexed_job:{company_candidate:'Alfa',role_candidate:'Freelance Python',contract_hint:'external',contract:null,published_at:null,skills_hint:['Python'],commercial_compatibility:null}}};
const linkedin=render('commercialIndexedJob(body)');
console.log(JSON.stringify({proof,historical,contradiction,deferred,partial,linkedin}));
'''.replace('SOURCE', json.dumps(source), 1)
        run = subprocess.run([shutil.which('node')], input=harness, text=True, capture_output=True, check=True)
        cls.views = json.loads(run.stdout)

    def test_verified_source_subject_relation_and_availability_distinct(self):
        html=self.views['proof']
        for text in ('Alfa','Cerchiamo sviluppatori WordPress freelance.','Fonte originale','Collaborazione esterna','Invito continuativo osservato','Non confermata direttamente','Chi pagherebbe: Non identificato'):
            self.assertIn(text,html)

    def test_historical_verification_is_not_invented(self):
        html=self.views['historical']
        self.assertIn('Non registrata in questa valutazione storica',html)
        self.assertIn('Soggetto non registrato',html)
        self.assertNotIn('Identità: verificata',html)

    def test_contradictory_evidence_retained_and_escaped(self):
        html=self.views['contradiction']
        self.assertIn('Non collaboriamo con freelance.',html)
        self.assertIn('Cerchiamo sviluppatori freelance.',html)
        self.assertIn('Prove contraddittorie',html)
        self.assertNotIn('<img',html)
        self.assertIn('&lt;img',html)

    def test_budget_deferred_is_neither_inspected_nor_site_defect(self):
        html=self.views['deferred']
        self.assertIn('Non eseguito',html)
        self.assertIn('quota browser esaurita',html)
        self.assertIn('Nessun problema tecnico dimostrato',html)

    def test_indexed_contract_hint_does_not_become_verified_contract_or_date(self):
        html=self.views['linkedin']
        self.assertIn('Alfa',html)
        self.assertIn('Freelance Python',html)
        self.assertIn('Contratto verificato:</strong> Sconosciuto',html)
        self.assertIn('Indizio nel titolo:</strong> Collaborazione esterna',html)
        self.assertIn('Data verificata:</strong> Data non disponibile',html)
        self.assertIn('non dalla lettura dell’annuncio originale',html)

    def test_browser_levels_limits_and_cleanup_are_visible(self):
        html=self.views['partial']
        for text in ('Parziale / incompleto','Livello 1 · HTTP','Livello 2 · DOM','Livello 3 · Browser avanzato','Non richiesto','limite 1000 ms','Limite complessivo: 1500 ms','Chiusura risorse: confermata','Processo terminato e raccolto','gli errori non sono difetti attribuiti al sito'):
            self.assertIn(text,html)
        self.assertNotIn('<script>',html)


if __name__=='__main__':unittest.main()
