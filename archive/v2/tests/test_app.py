import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import app


class AppTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(app.os.environ, {'SERPER_API_KEY': '', 'SEARXNG_URL': ''})
        self.env.start()
        app.STOP_SEARCH.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.data = patch.object(app, 'DATA', Path(self.temp.name))
        self.db = patch.object(app, 'DB', Path(self.temp.name) / 'test.sqlite3')
        self.data.start()
        self.db.start()
        app.init()
        self.mobile = patch('mobile_review.review_mobile', return_value=None)
        self.mobile.start()
        self.audit = patch.object(app,'technical_report',return_value={'pagespeed':[]})
        self.audit.start()

    def tearDown(self):
        self.audit.stop()
        self.mobile.stop()
        self.env.stop()
        app.STOP_SEARCH.clear()
        self.db.stop()
        self.data.stop()
        self.temp.cleanup()

    def lead(self, domain='example.org', email='info@example.org'):
        with app.db() as conn:
            return conn.execute('INSERT INTO leads(domain,name,url,email,email_source,findings,subject,body,created) VALUES(?,?,?,?,?,?,?,?,?)', (domain, 'Test', 'https://' + domain, email, 'https://' + domain, '[]', 'Oggetto', 'Testo', app.today())).lastrowid

    def status(self, lead_id):
        with app.db() as conn:
            return conn.execute('SELECT status FROM leads WHERE id=?', (lead_id,)).fetchone()[0]

    def test_manual_gmail_claim_and_confirmation(self):
        lead = self.lead()
        from urllib.parse import urlsplit, parse_qs
        query = parse_qs(urlsplit(app.prepare_gmail(lead)).query)
        self.assertEqual(query['to'], ['info@example.org'])
        self.assertEqual(query['body'], ['Testo'])
        self.assertEqual(self.status(lead), 'gmail_pending')
        with self.assertRaises(ValueError):
            app.prepare_gmail(lead)
        other = self.lead('other.org')
        with self.assertRaises(ValueError):
            app.prepare_gmail(other)
        app.confirm_gmail(lead)
        self.assertEqual(self.status(lead), 'sent')
        with self.assertRaises(ValueError):
            app.prepare_gmail(other)
        with self.assertRaises(ValueError):
            app.confirm_gmail(other)

    def test_contacted_company_alias_is_suppressed(self):
        first = self.lead()
        alias = self.lead('alias.org', 'sales@alias.org')
        unrelated = self.lead('unrelated.org', 'info@unrelated.org')
        with app.db() as c:
            c.execute("UPDATE leads SET vat='01114601006' WHERE id IN (?,?)", (first, alias))
            c.execute("INSERT INTO search_candidates(domain,item,status,retry_after) VALUES ('alias.org','{}','retry',9999999999)")
        app.prepare_gmail(first)
        with self.assertRaises(ValueError):
            app.prepare_gmail(alias)
        app.confirm_gmail(first)
        self.assertEqual(self.status(alias), 'excluded')
        self.assertEqual(self.status(unrelated), 'draft')
        self.assertEqual(app.deferred_candidates(), 0)
        with app.db() as c:
            self.assertTrue(app.company_match(c, {'domain':'third.org', 'email':'new@third.org', 'vat':'01114601006'}))
            # Removing a card must never remove the previous-contact evidence.
            c.execute("UPDATE leads SET status='deleted' WHERE id=?", (first,))
        with app.db() as c:
            other = dict(c.execute('SELECT * FROM leads WHERE id=?', (alias,)).fetchone())
            self.assertTrue(app.company_match(c, other, contacted_only=True))
        self.assertEqual(app.cache_candidates([{'url':'https://example.org/'}]), 0)

    def test_startup_removes_existing_contacted_aliases_from_proposals(self):
        sent = self.lead()
        alias = self.lead('alias.org', 'INFO@example.org')
        unrelated = self.lead('unrelated.org', 'info@unrelated.org')
        with app.db() as c:
            c.execute("UPDATE leads SET status='sent',sent_at='2026-10-01' WHERE id=?", (sent,))
            c.execute("INSERT INTO search_candidates(domain,item) VALUES ('alias.org','{}')")
        app.init()
        self.assertEqual(self.status(alias), 'excluded')
        self.assertEqual(self.status(sent), 'sent')
        self.assertEqual(self.status(unrelated), 'draft')
        self.assertEqual(app.pending_candidates(), 0)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT sent_at FROM leads WHERE id=?', (sent,)).fetchone()[0], '2026-10-01')

    def test_practical_observation_names_broken_contact_link(self):
        lead = {'domain':'example.org', 'findings':[{'kind':'Link interrotto', 'label':'Contatti', 'source':'https://example.org/contatti'}]}
        _, body = app.draft(lead, app.settings())
        self.assertNotIn('“Contatti”', body)
        self.assertNotIn('pagina non trovata', body)
        self.assertIn('capire le vostre esigenze', body)
        self.assertNotIn('HTTP', body)
        page = app.Page('<a href="/contatti"><span>Contatti</span></a>')
        self.assertEqual(page.link_labels['/contatti'], 'Contatti')

    def test_mobile_preview_alone_does_not_claim_a_defect(self):
        lead = {'domain':'example.org', 'findings':[{'kind':'Mobile · controllo','overflow_confirmed':False}]}
        self.assertEqual(app.practical_observation(lead), '')
        lead['findings'][0]['overflow_confirmed'] = True
        self.assertIn('larghezza dello schermo', app.practical_observation(lead))

    def test_personalized_email_requires_a_concrete_observation(self):
        lead = {'domain':'example.org', 'findings':[{'kind':'Risorse','source':'https://example.org'}]}
        self.assertEqual(app.practical_observation(lead), '')
        lead['findings'] = [{'kind':'Connessione','source':'http://example.org/'}]
        _, body = app.draft(lead, app.settings())
        self.assertNotIn('senza una connessione protetta', body)
        self.assertNotIn('ripensare il sito da zero', body)
        self.assertNotIn('vulnerabilità', body)
        lead['findings'] = [{'kind':'Mobile · controllo','overflow_confirmed':True,'incomplete':True}]
        self.assertEqual(app.practical_observation(lead), '')
        lead['findings'] = [{'kind':'Immagine non disponibile','verified':False}]
        self.assertEqual(app.practical_observation(lead), '')

    def test_stalled_analysis_has_deadline_and_stop(self):
        import subprocess
        import sys
        import time
        original = subprocess.Popen
        processes = []
        def stalled(*args, **kwargs):
            process = original([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
            processes.append(process)
            return process
        with patch.object(app.subprocess, 'Popen', side_effect=stalled):
            start = time.monotonic()
            self.assertIsNone(app.inspect_with_deadline('https://example.org', timeout=.2))
            self.assertLess(time.monotonic() - start, 3)
            self.assertIsNotNone(processes[-1].poll())
            app.STOP_SEARCH.set()
            with self.assertRaises(app.SearchStopped):
                app.inspect_with_deadline('https://example.org')
            self.assertIsNotNone(processes[-1].poll())

    def test_three_parallel_analyses_and_reason_totals(self):
        import time
        candidates = [{'url':f'https://parallel{i}.it/'} for i in range(6)]
        app.cache_candidates(candidates)
        barrier = threading.Barrier(3)
        lock = threading.Lock()
        active = peak = 0
        def inspect(url):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait(timeout=3)
            time.sleep(.02)
            with lock: active -= 1
            app.ANALYSIS_LOCAL.reason = 'no_email'
            return None
        with patch.object(app, 'inspect_with_deadline', side_effect=inspect), patch.object(app, 'remaining_searches', return_value=0):
            app.search_worker()
        self.assertEqual(peak, 3)
        self.assertEqual(app.JOB['checked'], 6)
        self.assertEqual(app.JOB['counts']['no_email'], 6)
        self.assertEqual(app.pending_candidates(), 0)

    def test_template_save_and_explicit_apply_preserve_sent_and_pending(self):
        draft_id = self.lead()
        sent = self.lead('sent.org', 'sent@example.org')
        pending = self.lead('pending.org', 'pending@example.org')
        with app.db() as c:
            c.execute("UPDATE leads SET status='sent' WHERE id=?", (sent,))
            c.execute("UPDATE leads SET status='gmail_pending' WHERE id=?", (pending,))
        app.save_settings({'template_subject':'Idea per {sito}', 'template_body':'Ciao {sito}, sono {nome}. {firma} {mio_sito}'})
        with app.db() as c:
            self.assertEqual(c.execute('SELECT body FROM leads WHERE id=?',(draft_id,)).fetchone()[0], 'Testo')
        self.assertEqual(app.apply_template_to_drafts(), 1)
        with app.db() as c:
            self.assertIn('Ciao example.org, sono Diego Pavanello.', c.execute('SELECT body FROM leads WHERE id=?',(draft_id,)).fetchone()[0])
            self.assertEqual(c.execute('SELECT body FROM leads WHERE id=?',(sent,)).fetchone()[0], 'Testo')
            self.assertEqual(c.execute('SELECT body FROM leads WHERE id=?',(pending,)).fetchone()[0], 'Testo')

    def test_search_plan_rotates_without_losing_combinations(self):
        plans = app.search_plan()
        self.assertEqual(len(plans), len(set(plans)))
        self.assertEqual(len(plans), sum(len(cities) for _,cities in app.SEARCH_AREAS)*len(app.BUSINESS_SECTORS))
        self.assertEqual(len({p[0] for p in plans[:12]}), 12)
        self.assertGreater(len({p[1] for p in plans[:12]}), 1)

    def test_query_results_count_only_fresh_domains_and_keep_origin(self):
        plan = app.search_plan()[0]
        items = [{'url':'https://company.it/'}]*2
        self.assertEqual(app.cache_candidates(items, plan), 1)
        self.assertEqual(app.cache_candidates(items, plan), 0)
        stats = app.search_performance()
        self.assertEqual((stats['requests'],stats['returned'],stats['fresh']), (2,4,1))
        with app.db() as c:
            row = c.execute('SELECT query_key FROM search_candidates').fetchone()
        self.assertEqual(row[0], app.query_key(plan))

    def test_focus_rotation_allocates_eighty_percent_to_requested_regions(self):
        regions = []
        for _ in range(20):
            chosen = app.choose_query()
            regions.append(app.focus_region(chosen))
            app.cache_candidates([], chosen)
        for region in app.FOCUS_CITIES:
            self.assertEqual(regions.count(region), 4)
        self.assertEqual(regions.count('Altre zone'), 4)

    def test_saved_draft_updates_original_query_performance(self):
        app.cache_candidates([{'url':'https://origin.it/'}], app.search_plan()[0])
        lead = {'domain':'origin.it','name':'Origin','url':'https://origin.it/', 'email':'info@origin.it', 'email_source':'https://origin.it/', 'findings':[]}
        with patch.object(app,'inspect_with_deadline',return_value=lead), patch.object(app,'remaining_searches',return_value=0):
            app.search_worker()
        stats = app.search_performance()
        self.assertEqual((stats['checked'],stats['drafts']), (1,1))
        self.assertEqual(stats['best'][0]['city'], app.search_plan()[0][1])

    def test_technical_errors_alone_no_longer_select_site(self):
        def page(url):
            if url.endswith('robots.txt'): return 404,'',url
            return 200,'<title>Example SRL</title><p>Example S.r.l. info@example.org</p><a href="/missing">Missing</a>',url
        with patch.object(app,'public_page',side_effect=page), patch.object(app.time,'sleep'):
            lead = app.inspect_site('http://example.org/')
        self.assertIsNone(lead)
        self.assertIn(app.INSPECTION_REASON, app.RETRY_REASONS)

    def test_finance_lookup_saves_source_without_altering_email(self):
        from company_finance import valid_vat
        vat=next('1234567890'+str(n) for n in range(10) if valid_vat('1234567890'+str(n)))
        lead=self.lead()
        with app.db() as c: c.execute('UPDATE leads SET vat=? WHERE id=?',(vat,lead))
        def page(url):
            if url.endswith('robots.txt'):return 404,'',url
            return 200,f'<p>Partita IVA {vat}</p><p>Utile netto 2024: euro 120.000,00</p>',url
        with patch.object(app,'search_web',return_value={'results':[{'url':'https://source.example/report'}]}), patch.object(app,'public_page',side_effect=page),patch.object(app.time,'sleep'):
            result=app.lookup_finance(lead)
        self.assertEqual(result['status'],'reported')
        self.assertEqual(result['record']['amount_eur'],120000)
        self.assertEqual(result['record']['source'],'https://source.example/report')
        with app.db() as c: self.assertEqual(c.execute('SELECT body FROM leads WHERE id=?',(lead,)).fetchone()[0],'Testo')

    def test_outcome_does_not_change_send_history_or_allow_resend(self):
        lead=self.lead()
        with self.assertRaises(ValueError): app.save_outcome(lead,'interested','')
        with app.db() as c: c.execute("UPDATE leads SET status='sent',sent_at='2026-10-07',message_id='original' WHERE id=?",(lead,))
        app.save_outcome(lead,'interested','Vorrebbe parlarne la prossima settimana')
        with app.db() as c: row=c.execute('SELECT * FROM leads WHERE id=?',(lead,)).fetchone()
        self.assertEqual(row['outcome'],'interested')
        self.assertEqual(row['status'],'sent')
        self.assertEqual(row['sent_at'],'2026-10-07')
        self.assertEqual(row['message_id'],'original')
        with self.assertRaises(ValueError): app.prepare_gmail(lead)
        with self.assertRaises(ValueError): app.save_outcome(lead,'invented','')
        with self.assertRaises(ValueError): app.save_outcome(lead,'customer','x'*3001)

    def test_unavailable_candidate_retries_once_after_one_day(self):
        app.cache_candidates([{'url':'https://retry.it/'}])
        with patch.object(app,'inspect_with_deadline',return_value=None),patch.object(app,'remaining_searches',return_value=0):
            app.search_worker()
            self.assertEqual(app.pending_candidates(),0)
            self.assertEqual(app.deferred_candidates(),1)
            with app.db() as c:
                row=c.execute('SELECT * FROM search_candidates').fetchone()
                self.assertEqual(row['attempts'],1)
                self.assertEqual(row['last_reason'],'unavailable')
                c.execute('UPDATE search_candidates SET retry_after=0')
            self.assertEqual(app.pending_candidates(),1)
            app.search_worker()
        with app.db() as c:
            row=c.execute('SELECT * FROM search_candidates').fetchone()
            self.assertEqual(row['status'],'done')
            self.assertEqual(row['attempts'],2)
        self.assertEqual(app.deferred_candidates(),0)

    def test_public_contacts_do_not_include_scripts(self):
        page = app.Page('<script>const email="private@example.org"</script><p>info@example.org</p><a href="mailto:hello@example.org?subject=hi">Email</a>')
        self.assertEqual(page.contacts(), ['hello@example.org', 'info@example.org'])

    def test_private_addresses_rejected_before_connection(self):
        with patch.object(app.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]), patch.object(app.socket, 'create_connection') as connect:
            with self.assertRaises(ValueError):
                app.public_page('http://private.example/')
            connect.assert_not_called()

    def test_email_header_injection_rejected(self):
        for email, subject in [('ok@example.org\r\nBcc: bad@example.org', 'Hi'), ('ok@example.org', 'Hello\nBcc: bad@example.org')]:
            with self.assertRaises(ValueError):
                app.validate_message(email, subject, 'Body')

    def test_observations_have_evidence_and_email_source(self):
        def page(url):
            if url.endswith('robots.txt'):
                return 200, 'User-agent: *\nAllow: /', url
            if url.endswith('/contatti'):
                return 200, '<p>info@example.org</p>', url
            if url.endswith('/missing'):
                return 404, 'Not found', url
            return 200, '<title>Attività</title><p>Attività S.r.l.</p><a href="/contatti">Contatti</a><a href="/missing">Servizi</a>', url
        finding = {'kind':'Usabilità · layout','qualifies':True,'incomplete':False,'source':'https://example.org/','checked_at':'2026-10-07','text':'Testo fuori schermo'}
        with patch.object(app, 'public_page', side_effect=page), patch.object(app.time, 'sleep'), patch.object(app,'technical_report',return_value={'url':'https://example.org/','checked_at':'2026-10-09','pagespeed':[{'strategy':'mobile','status':'ok','scores':{'seo':70},'fetch_time':'2026-10-09'}]}):
            result = app.inspect_site('https://example.org/')
        self.assertEqual(result['email_source'], 'https://example.org/contatti')
        self.assertEqual(len(result['findings']), 1)
        self.assertTrue(all(f['source'] and f['checked_at'] for f in result['findings']))

    def test_branded_provider_mailbox_requires_contact_page(self):
        root = 'https://edilferorani.it/'
        def page(url):
            if url.endswith('robots.txt'):
                return 404, '', url
            if url.endswith('contatti.php'):
                return 200, '<p>Edilferorani Srl - edilferorani@tiscali.it</p>', url
            return 200, '<p>Edilferorani Srl</p><a href="prodotti1">Uno</a><a href="prodotti2">Due</a><a href="prodotti3">Tre</a><a href="contatti.php">Contatti</a>', url
        finding = {'kind':'Usabilità · layout','qualifies':True,'incomplete':False}
        with patch.object(app, 'public_page', side_effect=page), patch.object(app.time, 'sleep'), patch.object(app,'technical_report',return_value={'url':'https://example.org/','checked_at':'2026-10-09','pagespeed':[{'strategy':'mobile','status':'ok','scores':{'seo':70},'fetch_time':'2026-10-09'}]}):
            lead = app.inspect_site(root)
        self.assertEqual(lead['email'], 'edilferorani@tiscali.it')
        self.assertEqual(lead['email_source'], root + 'contatti.php')
        for email, source in [
            ('designer@gmail.com', root + 'contatti.php'),
            ('edilferorani@agency.it', root + 'contatti.php'),
            ('edilferorani@gmail.com', root),
            ('edilferorani@gmail.com', 'https://other.it/contatti'),
        ]:
            self.assertFalse(app.branded_public_mailbox(email, source, root))

    def test_robots_disallow_skips_homepage(self):
        with patch.object(app, 'public_page', return_value=(200, 'User-agent: *\nDisallow: /', 'https://example.org/robots.txt')) as fetch:
            with self.assertRaises(ValueError):
                app.inspect_site('https://example.org/')
            self.assertEqual(fetch.call_count, 1)

    def test_missing_contact_does_not_generate_a_lead(self):
        def page(url):
            return (404, '', url) if url.endswith('robots.txt') else (200, '<title>No contact</title>', url)
        with patch.object(app, 'public_page', side_effect=page), patch.object(app.time, 'sleep'):
            self.assertIsNone(app.inspect_site('https://example.org/'))

    def test_draft_uses_real_profile_and_findings(self):
        subject, body = app.draft({'domain':'example.org', 'url':'https://example.org', 'findings':[{'kind':'Link interrotto','text':'Il link /servizi restituisce 404.'}]}, app.settings())
        self.assertIn('example.org', subject)
        self.assertNotIn('Ho anche trovato', body)
        self.assertNotIn('404', body)
        self.assertIn('Diego Pavanello', body)
        self.assertIn('designerdimontagna.it', body)
        self.assertNotIn('https://designerdimontagna.it', body)
        self.assertIn('Front-end Designer', body)

    def test_redesign_template_uses_specific_topics_without_inventing_defects(self):
        _, body = app.draft({'domain':'example.org', 'findings':[], 'context':[
            {'text':'Serramenti in legno su misura', 'source':'https://example.org/serramenti'},
            {'text':'Restauro delle persiane', 'source':'https://example.org/restauro'}]}, app.settings())
        self.assertNotIn('Serramenti in legno su misura', body)
        self.assertNotIn('Restauro delle persiane', body)
        self.assertIn('Credo ci siano diversi aspetti', body)
        self.assertIn('capire le vostre esigenze', body)
        self.assertNotIn('non funziona', body)

    def test_context_keeps_complete_headings_and_ignores_cookie_notices(self):
        page = app.Page('<h2>Serramenti <strong>su misura</strong></h2><h2>Gestisci il consenso cookie</h2><h2>Chi siamo</h2>')
        self.assertEqual(app.page_context(page, 'https://example.org/'), [
            {'text':'Serramenti su misura', 'source':'https://example.org/'}])

    def test_uncertain_signals_do_not_become_broken_site_claims(self):
        for kind in ('Risorse', 'Mobile · da verificare', 'Connessione'):
            _, body = app.draft({'domain':'example.org','findings':[{'kind':kind,'text':'HTTP viewport audit HTTPS'}]}, app.settings())
            for jargon in ('HTTP', 'viewport', 'audit', 'meta tag'):
                self.assertNotIn(jargon, body)
            self.assertNotIn('non si apre', body)
            self.assertNotIn('non funziona', body)

    def test_business_filter_excludes_directories_not_real_company(self):
        self.assertFalse(app.business_result({'url':'https://it.kompass.com/azienda'}))
        self.assertFalse(app.business_result({'url':'https://example.org/', 'title':'Elenco aziende metalmeccaniche'}))
        self.assertTrue(app.business_result({'url':'https://example.org/', 'title':'Rossi lavorazioni metalmeccaniche'}))

    def test_public_entities_and_srl_markers(self):
        for url, title in [('https://www.comune.capraia-e-limite.fi.it','Home'), ('https://example.it','Sito istituzionale del Comune di Capraia e Limite'), ('https://istruzione.gov.it','Home')]:
            self.assertFalse(app.business_result({'url':url,'title':title}))
        for name in ['Rossi S.r.l.', 'Rossi SRL', 'Rossi S.R.L.S.', 'società a responsabilità limitata']:
            self.assertTrue(app.is_srl(name))
        self.assertFalse(app.is_srl('Rossi S.p.A.'))

    def test_geographic_plan_stays_in_requested_order(self):
        plan = app.search_plan()
        order = [area for area, _ in app.SEARCH_AREAS]
        positions = [order.index(area) for _, _, area in plan]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(plan[0][2], 'Veneto')
        self.assertEqual(plan[-1][2], 'Centro Italia')

    def test_public_draft_is_excluded_and_quotes_removed(self):
        first = self.lead('comune.esempio.it')
        second = self.lead('azienda.it')
        with app.db() as c:
            c.execute('UPDATE leads SET body=? WHERE id=?', ('Testo personale.\n\nMi sono soffermato in particolare su «Servizi». Partirei proprio da questi contenuti.\n\nFirma personale.', second))
        app.refresh_generated_drafts()
        self.assertEqual(self.status(first), 'excluded')
        with app.db() as c:
            body = c.execute('SELECT body FROM leads WHERE id=?', (second,)).fetchone()[0]
        self.assertEqual(body, 'Testo personale.\n\nFirma personale.')

    def test_draft_migration_preserves_manual_edits_and_sent_mail(self):
        ids = [self.lead(f'company{i}.it') for i in range(3)]
        with app.db() as c:
            for lead_id in ids:
                row = dict(c.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone())
                row['findings'] = []
                subject, body = app.legacy_draft(row, app.settings())
                c.execute('UPDATE leads SET subject=?,body=? WHERE id=?', (subject,body,lead_id))
            c.execute("UPDATE leads SET body='Testo modificato da Diego' WHERE id=?", (ids[1],))
            c.execute("UPDATE leads SET status='sent' WHERE id=?", (ids[2],))
        self.assertEqual(app.refresh_generated_drafts(), 1)
        self.assertEqual(app.refresh_generated_drafts(), 0)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT body FROM leads WHERE id=?',(ids[1],)).fetchone()[0], 'Testo modificato da Diego')
            self.assertTrue(c.execute('SELECT subject FROM leads WHERE id=?',(ids[2],)).fetchone()[0].startswith('Un paio'))

    def test_double_click_only_sends_once(self):
        lead_id = self.lead()
        entered, release = threading.Event(), threading.Event()
        errors = []
        def send(*args, **kwargs):
            entered.set()
            release.wait(3)
            return {'id':'gmail-123'}
        def first():
            try:
                app.send_lead(lead_id)
            except Exception as exc:
                errors.append(exc)
        with patch.object(app, 'token_read', return_value={'access_token':'token'}), patch.object(app, 'access_token', return_value='token'), patch.object(app, 'api_json', side_effect=send) as api:
            thread = threading.Thread(target=first)
            thread.start()
            self.assertTrue(entered.wait(3))
            try:
                with self.assertRaises(ValueError):
                    app.send_lead(lead_id)
            finally:
                release.set()
                thread.join(5)
            self.assertFalse(errors)
            self.assertEqual(api.call_count, 1)
            self.assertEqual(self.status(lead_id), 'sent')

    def test_timeout_during_send_blocks_retry(self):
        lead_id = self.lead()
        with patch.object(app, 'token_read', return_value={'access_token':'token'}), patch.object(app, 'access_token', return_value='token'), patch.object(app, 'api_json', side_effect=TimeoutError()):
            with self.assertRaises(ValueError):
                app.send_lead(lead_id)
        self.assertEqual(self.status(lead_id), 'uncertain')
        with self.assertRaises(ValueError):
            app.send_lead(lead_id)

    def test_explicit_gmail_rejection_preserves_draft(self):
        lead_id = self.lead()
        with patch.object(app, 'token_read', return_value={'access_token':'token'}), patch.object(app, 'access_token', return_value='token'), patch.object(app, 'api_json', side_effect=HTTPError('url', 403, 'Forbidden', {}, None)):
            with self.assertRaises(ValueError):
                app.send_lead(lead_id)
        self.assertEqual(self.status(lead_id), 'draft')

    def test_same_recipient_on_other_site_cannot_be_sent_twice(self):
        first = self.lead()
        second = self.lead('other.org')
        with app.db() as conn:
            conn.execute("UPDATE leads SET status='sent' WHERE id=?", (first,))
        with self.assertRaisesRegex(ValueError, 'già stato contattato'):
            app.send_lead(second)

    def test_deleted_drafts_still_count_toward_daily_limit(self):
        lead_id = self.lead()
        with app.db() as conn:
            conn.execute("UPDATE leads SET status='deleted' WHERE id=?", (lead_id,))
        self.assertEqual(app.count_today(), 1)

    def test_restart_marks_interrupted_send_uncertain(self):
        lead_id = self.lead()
        with app.db() as conn:
            conn.execute("UPDATE leads SET status='sending' WHERE id=?", (lead_id,))
        app.init()
        self.assertEqual(self.status(lead_id), 'uncertain')

    def test_search_saves_at_most_twenty_real_candidates(self):
        candidates = [{'url': f'https://site{i}.it/'} for i in range(25)]
        def inspect(url):
            domain = app.hostname(url)
            return {'domain': domain, 'name': domain, 'url': url, 'email': 'info@' + domain,
                    'email_source': url, 'findings': [{'text': 'Osservazione verificata', 'source': url}]}
        with patch.dict(app.os.environ, {'TAVILY_API_KEY':'test'}), patch.object(app, 'api_json', return_value={'results': candidates}), patch.object(app, 'inspect_with_deadline', side_effect=inspect), patch.object(app.time, 'sleep'):
            app.search_worker()
        self.assertEqual(app.count_today(), 20)
        with app.db() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM leads WHERE status='draft'").fetchone()[0], 20)

    def test_second_run_collects_another_twenty_from_saved_queue(self):
        candidates = [{'url': f'https://batch{i}.it/'} for i in range(40)]
        def inspect(url):
            domain = app.hostname(url)
            return {'domain':domain,'name':domain,'url':url,'email':'info@'+domain,
                    'email_source':url,'findings':[{'text':'Verificato','source':url}]}
        with patch.dict(app.os.environ, {'TAVILY_API_KEY':'test'}), patch.object(app, 'api_json', return_value={'results':candidates}) as api, patch.object(app, 'inspect_with_deadline', side_effect=inspect), patch.object(app.time, 'sleep'):
            app.search_worker()
            self.assertEqual(app.count_today(), 20)
            self.assertEqual(app.pending_candidates(), 20)
            app.search_worker()
            self.assertEqual(app.count_today(), 40)
            self.assertEqual(app.JOB['added'], 20)
            self.assertEqual(app.pending_candidates(), 0)
            self.assertEqual(api.call_count, 1)

    def test_stop_keeps_candidate_pending(self):
        app.cache_candidates([{'url':'https://candidate.it/'}])
        def interrupt(url):
            app.STOP_SEARCH.set()
            return None
        with patch.object(app, 'inspect_with_deadline', side_effect=interrupt):
            app.search_worker()
        self.assertEqual(app.pending_candidates(), 1)
        self.assertEqual(app.JOB['added'], 0)

    def test_search_does_not_invent_candidates_to_fill_quota(self):
        with patch.dict(app.os.environ, {'TAVILY_API_KEY':'test'}), patch.object(app, 'api_json', return_value={'results': [{'url':'https://site.it/'}]}), patch.object(app, 'inspect_with_deadline', return_value=None), patch.object(app.time, 'sleep'):
            app.search_worker()
        self.assertEqual(app.count_today(), 0)
        self.assertIn('meno di 20', app.JOB['message'])

    def test_tavily_basic_request_and_persistent_daily_cap(self):
        with patch.dict(app.os.environ, {'TAVILY_API_KEY':'test-only'}), patch.object(app, 'api_json', return_value={'results': []}) as api:
            for _ in range(30):
                app.search_web('attività italiane')
            args, kwargs = api.call_args
            self.assertEqual(args[0], 'https://api.tavily.com/search')
            self.assertEqual(args[1]['search_depth'], 'basic')
            self.assertFalse(args[1]['auto_parameters'])
            self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-only')
            app.init()
            with self.assertRaises(app.SearchLimitError):
                app.search_web('non deve partire')
            self.assertEqual(api.call_count, 30)

    def test_failed_tavily_request_still_counts(self):
        with patch.dict(app.os.environ, {'TAVILY_API_KEY':'test-only'}), patch.object(app, 'api_json', side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):
                app.search_web('test')
        self.assertEqual(app.search_usage(), 1)

    def test_serper_fallback_normalizes_results_and_counts_separately(self):
        with app.db() as c:
            c.execute('INSERT INTO search_usage VALUES (?,30)', (app.today(),))
        with patch.dict(app.os.environ, {'TAVILY_API_KEY':'test', 'SERPER_API_KEY':'test-serper'}), patch.object(app, 'api_json', return_value={'organic':[{'link':'https://azienda.it','title':'Azienda Srl','snippet':'Servizi'}]}) as api:
            result = app.search_web('azienda srl Veneto')
        self.assertEqual(result['results'][0]['url'], 'https://azienda.it')
        self.assertEqual(api.call_args.args[0], 'https://google.serper.dev/search')
        self.assertEqual(api.call_args.args[1]['num'], 10)
        self.assertEqual(app.serper_usage(), (1, 1))
        self.assertEqual(app.search_usage(), 30)

    def test_serper_total_cap_survives_restart(self):
        with app.db() as c:
            c.execute('INSERT INTO serper_usage VALUES (?,2400)', ('2020-01-01',))
        app.init()
        with patch.object(app, 'api_json') as api:
            with self.assertRaises(app.SearchLimitError):
                app.serper_search('test')
            api.assert_not_called()

    def test_serper_daily_cap_blocks_network(self):
        with app.db() as c:
            c.execute('INSERT INTO serper_usage VALUES (?,100)', (app.today(),))
        with patch.object(app, 'api_json') as api:
            with self.assertRaises(app.SearchLimitError):
                app.serper_search('test')
            api.assert_not_called()

    def test_searxng_first_does_not_spend_api_credits(self):
        app.SEARXNG_STATUS['retry_after'] = 0
        with patch.dict(app.os.environ, {'SEARXNG_URL':'http://127.0.0.1:8888'}), patch.object(app, 'api_json', return_value={'results':[{'url':'https://example.it','title':'Azienda'}]}) as api:
            result = app.search_web('azienda srl')
        self.assertTrue(result['results'])
        self.assertTrue(api.call_args.args[0].startswith('http://127.0.0.1:8888/search?'))
        self.assertEqual(app.search_usage(), 0)
        self.assertEqual(app.serper_usage(), (0,0))
        self.assertEqual(app.searxng_usage(), 1)

    def test_searxng_failure_falls_back_to_tavily(self):
        app.save_settings({'allow_api_fallback':True})
        app.SEARXNG_STATUS['retry_after'] = 0
        with patch.dict(app.os.environ, {'SEARXNG_URL':'http://127.0.0.1:8888', 'TAVILY_API_KEY':'test'}), patch.object(app, 'api_json', side_effect=[OSError('offline'), {'results':[]}]) as api:
            app.search_web('azienda srl')
        self.assertEqual(api.call_count, 2)
        self.assertEqual(app.search_usage(), 1)
        app.SEARXNG_STATUS['retry_after'] = 0

    def test_searxng_only_never_consumes_api_credits(self):
        app.SEARXNG_STATUS['retry_after'] = 0
        with patch.dict(app.os.environ, {'SEARXNG_URL':'http://127.0.0.1:8888', 'TAVILY_API_KEY':'test', 'SERPER_API_KEY':'test'}), patch.object(app, 'searxng_search', side_effect=OSError('offline')), patch.object(app, 'tavily_search') as tavily, patch.object(app, 'serper_search') as serper:
            with self.assertRaises(app.SearchLimitError):
                app.search_web('azienda')
            tavily.assert_not_called()
            serper.assert_not_called()
        app.SEARXNG_STATUS['retry_after'] = 0
        with patch.dict(app.os.environ, {'SEARXNG_URL':'http://127.0.0.1:8888'}), patch.object(app, 'searxng_search', return_value={'results':[]}), patch.object(app, 'tavily_search') as tavily:
            self.assertEqual(app.search_web('azienda'), {'results':[]})
            tavily.assert_not_called()

    def test_monthly_limit_blocks_network_and_ignores_previous_month(self):
        with patch.object(app, 'today', return_value='2026-10-15'):
            with app.db() as c:
                c.execute('INSERT INTO search_usage VALUES (?,?)', ('2026-09-30', 30))
                c.execute('INSERT INTO search_usage VALUES (?,?)', ('2026-10-01', 929))
            with patch.dict(app.os.environ, {'TAVILY_API_KEY':'test'}), patch.object(app, 'api_json', return_value={'results':[]}) as api:
                app.search_web('ultima richiesta disponibile')
                with self.assertRaises(app.SearchLimitError):
                    app.search_web('non deve partire')
                self.assertEqual(api.call_count, 1)
                self.assertEqual(app.monthly_search_usage(), 930)

    def test_stop_prevents_next_search_and_preserves_drafts(self):
        lead_id = self.lead()
        app.JOB['running'] = True
        app.stop_search()
        with patch.object(app, 'api_json') as api:
            with self.assertRaises(app.SearchStopped):
                app.search_web('non deve partire')
            api.assert_not_called()
        app.search_worker()
        self.assertFalse(app.JOB['running'])
        self.assertFalse(app.JOB['stopping'])
        self.assertEqual(self.status(lead_id), 'draft')
        self.assertEqual(app.search_usage(), 0)

    def test_restart_disables_legacy_automatic_search(self):
        app.save_settings({'daily': True})
        app.init()
        self.assertFalse(app.settings()['daily'])


    def test_geographic_scope_excludes_old_queue_and_southern_addresses(self):
        plans = app.search_plan()
        self.assertTrue(any(p[1]=='Roma' for p in plans))
        self.assertTrue(any(p[1]=='Bologna' for p in plans))
        self.assertFalse(any(p[1] in ('Napoli','Ancona','Pesaro','Perugia','Terni') for p in plans))
        for address in ('60100 Ancona', '61121 Pesaro', '06100 Perugia', '05100 Terni'):
            self.assertTrue(app.outside_search_area(address))
        self.assertFalse(app.outside_search_area('50100 Firenze'))
        self.assertTrue(app.outside_search_area('Sede: Via Roma 1, 80100 Napoli'))
        self.assertTrue(app.outside_search_area('09100 Cagliari'))
        self.assertFalse(app.outside_search_area('00100 Roma'))
        self.assertFalse(app.outside_search_area('Mario Napoli, 20100 Milano'))
        with app.db() as c:
            c.execute("INSERT INTO search_candidates(domain,item,query_key) VALUES (?,?,?)", ('south.it','{}',app.query_key((app.BUSINESS_SECTORS[0],'Napoli','Sud e isole'))))
        app.cache_candidates([{'url':'https://north.it/'}], plans[0])
        self.assertEqual(app.exclude_outside_candidates(),1)
        self.assertEqual(app.pending_candidates(),1)
        self.assertEqual(app.cache_candidates([{'url':'https://napoli.it/','content':'80100 Napoli'}],plans[0]),0)

    def test_good_lighthouse_scores_are_not_selected(self):
        def page(url):
            if url.endswith('robots.txt'): return 404, '', url
            return 200, '<title>Example Srl</title><p>Example S.r.l. info@example.org</p>', url
        with patch.object(app,'public_page',side_effect=page), patch.object(app.time,'sleep'), patch.object(app,'technical_report',return_value={'pagespeed':[{'strategy':v,'status':'ok','scores':dict.fromkeys(('performance','seo','accessibility','best-practices'),100)} for v in ('mobile','desktop')]}):
            lead = app.inspect_site('https://example.org/')
        self.assertIsNone(lead)
        self.assertEqual(app.INSPECTION_REASON,'no_issue')

    def test_layout_recovery_is_once_only_and_preserves_exclusions(self):
        with app.db() as c:
            for domain, status, reason in [('layout.it','done','no_issue'),('browser.it','retry','resource_error'),('mail.it','done','no_email'),('excluded.it','dismissed','outside_area')]:
                c.execute('INSERT INTO search_candidates(domain,item,status,last_reason,retry_after) VALUES (?,?,?,?,?)',(domain,'{}',status,reason,9999999999))
        self.assertEqual(app.recover_layout_candidates(),2)
        self.assertEqual(app.pending_candidates(),2)
        self.assertEqual(app.recover_layout_candidates(),0)


    def test_unassessed_draft_is_rechecked_without_rewriting_email(self):
        lead_id = self.lead()
        with app.db() as c:
            c.execute('UPDATE leads SET findings=? WHERE id=?',(json.dumps([{'kind':'Opportunità commerciale'}]),lead_id))
        self.assertEqual(app.stage_unassessed_drafts(),1)
        self.assertEqual(self.status(lead_id),'review_pending')
        with patch.object(app,'inspect_with_deadline',return_value=None):
            self.assertEqual(app.reassess_pending_drafts(),0)
        self.assertEqual(self.status(lead_id),'review_pending')
        finding={'kind':'Usabilità · layout','qualifies':True,'incomplete':False,'text':'Testo fuori schermo'}
        with patch.object(app,'inspect_with_deadline',return_value={'findings':[finding]}):
            self.assertEqual(app.reassess_pending_drafts(),1)
        self.assertEqual(self.status(lead_id),'draft')
        with app.db() as c:
            self.assertEqual(c.execute('SELECT body FROM leads WHERE id=?',(lead_id,)).fetchone()[0],'Testo')


    def test_selection_uses_lighthouse_even_when_layout_fails(self):
        def page(url):
            if url.endswith('robots.txt'):return 404,'',url
            return 200,'<title>Example Srl</title><p>Example S.r.l. info@example.org</p>',url
        report={'url':'https://example.org/','checked_at':'2026-10-09','pagespeed':[{'strategy':'mobile','status':'ok','scores':{'performance':72,'seo':100}}]}
        with patch.object(app,'public_page',side_effect=page),patch.object(app.time,'sleep'),patch.object(app,'technical_report',return_value=report),patch('mobile_review.review_mobile',side_effect=AssertionError('Layout must not run')):
            lead=app.inspect_site('https://example.org/')
        self.assertIsNotNone(lead)
        self.assertEqual(lead['site_audit'],report)
        self.assertIn('72/100',lead['findings'][0]['text'])

    def test_technical_recovery_preserves_excluded_and_contacted_sites(self):
        with app.db() as c:
            for domain,status,reason in [('retrytechnical.it','done','dynamic_request'),('missingmail.it','done','no_email'),('south.it','dismissed','outside_area')]:
                c.execute('INSERT INTO search_candidates(domain,item,status,last_reason) VALUES (?,?,?,?)',(domain,'{}',status,reason))
        self.assertEqual(app.recover_technical_candidates(),1)
        self.assertEqual(app.recover_technical_candidates(),0)
        self.assertEqual(app.pending_candidates(),1)



if __name__ == '__main__':
    unittest.main()
