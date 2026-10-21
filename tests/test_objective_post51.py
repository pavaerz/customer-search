"""C51 saved originals only: select boundaries and failed re-analysis."""
import copy,json,unittest
from pathlib import Path
from sales.extract import Document
from sales.agent6.worklist import current_original
from sales.commercial.geography import resolve_location
SAVED=json.loads((Path(__file__).parent/'fixtures/ai_first/campaign50/internetimage51.json').read_text())

class SelectExtraction(unittest.TestCase):
    def test_real_original_separates_province_from_next_option_without_guessing(self):
        page=SAVED['tasks'][0]['original_page']
        text=Document(page['html']).text
        self.assertNotIn('PadovaImpiegato',text)
        line=next(l for l in text.splitlines() if 'in provincia di Padova' in l)
        self.assertEqual(resolve_location(line)['region'],'Veneto')
        self.assertNotIn('Impiegato',line)
        self.assertIn('Collaborazioni con Professionisti e Aziende con Partita IVA (Sviluppo, Design, SEO, ADS, CRM)',text)

    def test_options_and_groups_have_boundaries_but_inline_word_fragments_do_not(self):
        d=Document('<select><optgroup label="roles"><option>Padova</option><option>Impiegato</option></optgroup></select><p>Woo<strong>Commerce</strong></p>')
        self.assertEqual(d.text,'Padova\nImpiegato\nWooCommerce')
        self.assertEqual(resolve_location('PadovaImpiegato')['region'],None)
        self.assertEqual(resolve_location('Kenya')['region'],None)

class FailedReanalysis(unittest.TestCase):
    def setUp(self):self.rows=sorted(copy.deepcopy(SAVED['records']),key=lambda r:r['id'],reverse=True)

    def test_actual_identical_cached_original_preserves_valid_review_without_writes(self):
        row,failure=current_original(self.rows)
        self.assertEqual(row['id'],1354)
        self.assertEqual(failure['record_id'],1473)
        self.assertEqual(row['body']['checked_at'],'2026-10-20T07:35:34.071550+00:00')
        self.assertEqual(self.rows,sorted(SAVED['records'],key=lambda r:r['id'],reverse=True))

    def test_changed_original_new_observation_or_completed_negative_supersedes(self):
        for kind in ('documents','date','negative','unknown'):
            self.setUp();b=self.rows[0]['body']
            if kind=='documents':b['documents'][0]['document_id']='different-original'
            if kind=='date':b['checked_at']='2026-10-21T00:00:00+00:00'
            if kind=='negative':b.update(validation_status='ACCEPTED',technical_error=None,decision='NOT_INTERESTING')
            if kind=='unknown':b['documents']=[]
            row,failure=current_original(self.rows)
            self.assertEqual(row['id'],1473,kind);self.assertIsNone(failure)

    def test_manual_exclusion_still_overrides_preserved_original(self):
        import test_ai_first as harness
        from sales.agent6 import memory
        from sales.agent6.worklist import listing
        from datetime import datetime,timezone
        b=harness.IntegratedPath();b.setUp();self.addCleanup(b.tearDown)
        first=memory.save_record(b.store,b.c,'AGENCIES',self.rows[1]['body'])
        b.rs.stop(b.c['id']);b.rs.paused(b.c['id']);c=b.rs.create(b.filters)
        second=memory.save_record(b.store,c,'AGENCIES',self.rows[0]['body'])
        at=datetime(2026,10,21,tzinfo=timezone.utc)
        result=listing(b.store,{'view':'ready'},at=at)
        self.assertEqual(result['total'],1);self.assertEqual(result['items'][0]['id'],first)
        self.assertEqual(result['items'][0]['body']['later_analysis_failure']['record_id'],second)
        memory.feedback(b.store,second,'not_interesting','Manual user exclusion')
        self.assertEqual(listing(b.store,{'view':'ready'},at=at)['total'],0)
        self.assertEqual(listing(b.store,{'view':'excluded'},at=at)['total'],1)

class LearningPreservation(unittest.TestCase):
    setUp=FailedReanalysis.setUp
    def test_same_original_failure_keeps_commercial_memory_and_technical_error(self):
        from sales.agent6.learning import summarize
        records={r['id']:r['body'] for r in self.rows};events=[]
        for row in self.rows:
            b=row['body'];events.append({'id':row['id'],'flow':'AGENCIES','campaign_id':row['campaign_id'],
              'kind':'decision','body':{'record_id':row['id'],'request_key':row['request_key'],
              'query':'Veneto agenzia collabora sviluppatori freelance','domain':'internetimage.it',
              'state':row['state'],'original':True,'technical_error':b.get('technical_error')}})
        for n in range(3):events.append({'id':9000+n,'flow':'AGENCIES','campaign_id':n,'kind':'query',
            'body':{'query':'Veneto agenzia collabora sviluppatori freelance','results':1}})
        pending=copy.deepcopy(events[0]);pending['id']-=.5
        pending['body'].update(technical_error=None,state='NEEDS_REVIEW')
        events.append(pending) # Earlier pending event must not erase old proof either.
        groups=summarize(events,[],records)
        self.assertEqual(sum(g['relevant'] for g in groups),1)
        self.assertEqual(sum(g['technical_errors'] for g in groups),1)
        self.assertEqual(sum(g['verified_rejections'] for g in groups),0)
        records[self.rows[0]['id']]['documents']=[]
        groups=summarize(events,[],records)
        self.assertEqual(sum(g['relevant'] for g in groups),0)
