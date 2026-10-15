import unittest
from unittest.mock import Mock, patch
import app
from mobile_review import incomplete_result


class LoadingTest(unittest.TestCase):
    def test_incomplete_reasons_remain_retryable_and_not_qualified(self):
        for message, expected in [('Tempo di caricamento esaurito','timeout'),
                                  ('Budget di caricamento raggiunto','load_budget'),
                                  ('Errore del browser','browser_error'),
                                  ('Risorsa non caricata','resource_error'),
                                  ('Richiesta dinamica non eseguita','dynamic_request'),
                                  ('Contenuto della pagina insufficiente','empty_page')]:
            review = incomplete_result(message)
            self.assertFalse(review['qualifies'])
            self.assertTrue(review['incomplete'])
            self.assertEqual(app.incomplete_reason(review), expected)
            self.assertIn(expected, app.RETRY_REASONS)

    def test_deadline_records_timeout_and_cleans_up_child(self):
        child = Mock(pid=12345)
        with patch.object(app.subprocess,'Popen',return_value=child), patch.object(app,'check_search_stop'), patch.object(app.os,'killpg') as kill:
            self.assertIsNone(app.inspect_with_deadline('https://fixture.invalid', timeout=-1))
            self.assertEqual(app.ANALYSIS_LOCAL.reason,'timeout')
            kill.assert_called_once_with(12345, app.signal.SIGKILL)
            child.communicate.assert_called_once()

    def test_default_analysis_has_no_deadline_and_stop_still_cleans_up(self):
        child=Mock(pid=12345)
        child.communicate.side_effect=[app.subprocess.TimeoutExpired('inspect', .25), ('', '')]
        with patch.object(app.subprocess,'Popen',return_value=child), patch.object(app,'check_search_stop',side_effect=[None, app.SearchStopped()]), patch.object(app.os,'killpg') as kill:
            with self.assertRaises(app.SearchStopped):
                app.inspect_with_deadline('https://fixture.invalid')
            kill.assert_called_once_with(12345,app.signal.SIGKILL)
            self.assertEqual(child.communicate.call_args_list[0].kwargs,{'timeout':.25})
