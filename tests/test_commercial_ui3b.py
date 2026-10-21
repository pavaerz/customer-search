"""3B presentation checks: synthetic Node VM, no provider or browser network."""
import json,shutil,subprocess,unittest
from pathlib import Path

@unittest.skipUnless(shutil.which('node'),'Node needed for isolated presentation checks')
class AIUI3BTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=Path('static/commercial.js').read_text()
        harness=r'''
const vm=require('vm');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const context={campaignActions:()=>'',renderMain:()=>{},updateResearchState:()=>{},runCampaignAction:()=>{},settingsView:()=>{},document:{addEventListener:()=>{}},esc,S:{settings:{},campaign:{id:1,ai:{estimated_cost:null,reported_cost:null,calls:2,errors:1,fallbacks:1}}}};
vm.createContext(context);vm.runInContext('var campaignActions,renderMain,updateResearchState,runCampaignAction,settingsView;',context);vm.runInContext(SOURCE,context);
const render=s=>vm.runInContext(s,context);
const disabled=render('commercialAISettings()');
context.item={state:'NEEDS_REVIEW',ai_assessment:{mode:'shadow',provider:'MOCK',model:'<img src=x onerror=alert(1)>',status:'completed',output:{commercial_intent:'UNKNOWN',explanation:'<script>evil()</script>',supporting_evidence:[{id:'EVIDENCE_1',quote:'<img src=x>'}],missing_evidence:['<b>Unknown</b>'],recommended_action:'REVIEW'},differences:['<svg onload=evil()>']}};
const assessment=render('commercialAIView(item)');
context.item.ai_assessment.fallback=true;context.item.ai_assessment.error='<img src=x>';const fallback=render('commercialAIView(item)');
context.item={state:'VERIFIED'};const absent=render('commercialAIView(item)');
context.S.campaign.ai={estimated_cost:0,reported_cost:0,calls:0};const zero=render('commercialAIUsage()');
context.S.settings.commercial_ai={enabled:true,provider:'LOCAL',model:'<img src=x>',endpoint:'http://127.0.0.1:11434/api/chat'};const local=render('commercialAISettings()');
console.log(JSON.stringify({disabled,assessment,fallback,absent,zero,local}));
'''.replace('SOURCE',json.dumps(source),1)
        run=subprocess.run([shutil.which('node')],input=harness,text=True,capture_output=True);assert run.returncode==0,run.stderr;cls.views=json.loads(run.stdout)
    def test_disabled_default_no_secret_field(self):
        html=self.views['disabled'];self.assertIn('value="DISABLED" selected',html);self.assertNotIn('name="enabled" type="checkbox" checked',html)
        self.assertNotRegex(html,r'name="(?:api_key|token|password|secret)"');self.assertIn('nessuna inferenza parte salvando',html)
    def test_unknown_cost_not_zero(self):
        self.assertIn('Costo stimato: non disponibile',self.views['disabled']);self.assertIn('Costo dichiarato: non disponibile',self.views['disabled'])
        self.assertIn('Costo stimato: 0',self.views['zero']);self.assertIn('Costo dichiarato: 0',self.views['zero'])
    def test_shadow_official_state_distinct(self):
        html=self.views['assessment'];self.assertIn('Valutazione AI · Shadow',html);self.assertIn('Decisione ufficiale:</strong> Da verificare',html)
        self.assertIn('Risposta simulata',html);self.assertIn('Il parere AI non cambia questo stato',html);self.assertIn('Evidenze e differenze',html)
    def test_untrusted_output_escaped(self):
        for name in ('assessment','fallback','local'):
            html=self.views[name];self.assertNotIn('<img',html);self.assertNotIn('<script>',html);self.assertNotIn('<svg',html);self.assertIn('&lt;',html)
    def test_fallback_and_absence_explicit(self):
        self.assertIn('Fallback deterministico attivo',self.views['fallback']);self.assertEqual(self.views['absent'],'')
    def test_local_configuration_requires_no_download_and_keeps_shadow(self):
        self.assertIn('value="LOCAL" selected',self.views['local']);self.assertIn('nessuna installazione o download automatico',self.views['local']);self.assertIn('value="shadow"',self.views['local'])
