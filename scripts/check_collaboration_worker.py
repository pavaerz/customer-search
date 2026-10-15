"""Offline integration replay: recorded search -> real worker -> persisted contact.

One explicitly selected positive case, not a precision or acquisition-rate test.
Only provider input, page acquisition, inference and further search scheduling
are replaced. Production database/configuration are never opened.
"""
import hashlib
import json
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sales.db import Store, now
from sales.research_store import ResearchStore
from sales.research_funnel import Funnel
from sales.discovery_planner import Planner
from sales.research_analysis import ResearchWeb, LocalResearcher
from sales import research_worker as worker


def main():
    source = ROOT / 'data/benchmarks50/allowed-regions-demand.json'
    searches = ROOT / 'data/benchmarks50/direct-demand-evaluation2.json'
    target = 'https://www.adriasonline.it/lavora-con-noi/'
    case = next(c for c in json.loads(source.read_text())['cases'] if c['payload']['url'] == target)
    query, item = next((q['query'], r) for q in json.loads(searches.read_text())['queries']
                       for r in q['results'] if r['url'] == target)
    pages = {p['url']: p for p in case['captures']}
    reads = []

    def page_get(web, url, refresh=False):
        reads.append(url)
        if url not in pages:
            raise AssertionError('Missing frozen original: ' + url)
        return pages[url]

    with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
        store = Store(Path(directory) / 'replay.sqlite3')
        store.init(); store.configure({'provider': 'serper'})
        rs = ResearchStore(store)
        campaign = rs.create({'regions': ['Emilia-Romagna'], 'groups': ['agencies'], 'projects': ['website']})
        cid = campaign['id']
        Planner(rs).offer_query(campaign, 'partner', {'query': query, 'page': 1, 'period': '', 'region': 'Emilia-Romagna'})
        rs.event(cid, 'frontier_initialized', 'Frozen single-result integration cohort.')
        stack.enter_context(patch.object(Planner, 'tick', return_value=0))
        provider = stack.enter_context(patch('sales.serper_provider.search', return_value=({'results': [item]}, True)))
        stack.enter_context(patch.object(ResearchWeb, 'get', page_get))
        stack.enter_context(patch.object(LocalResearcher, 'call', side_effect=AssertionError('No inference in replay')))
        stack.enter_context(patch('socket.create_connection', side_effect=AssertionError('No network in replay')))
        triage = worker.triage

        def stop_after_read(*args):
            result = triage(*args)
            rs.stop(cid)
            return result

        with patch.object(worker, 'triage', stop_after_read):
            worker.run(store.path, cid, campaign['generation'])
        assert rs.campaign(cid)['status'] == 'stopping'
        assert rs.campaign(cid)['promising'] == 0, 'Late result promoted after Stop'
        rs.paused(cid)
        resumed = rs.resume(cid)
        worker.run(store.path, cid, resumed['generation'])
        current = rs.campaign(cid)
        listing = Funnel(rs).listing({'campaign': cid, 'company_only': 1, 'state': 'promising'})
        assert current['status'] == 'exhausted', current['message']
        assert current['qualified'] == 0
        assert current['promising'] == listing['total'] == 1
        assert listing['group_counts'] == {'agencies': 1}
        candidate = listing['items'][0]
        evidence = candidate['details']['collaboration']
        contacts = candidate['details']['identity']['contacts']
        assert evidence['url'] == target and evidence['budget'] is None
        assert any(c['type'] == 'email' and c['value'] == 'info@adriasonline.it' for c in contacts)
        assert candidate['details']['query'] == query
        with store.connect() as connection:
            assert connection.execute('SELECT count(*) FROM research_assessments').fetchone()[0] == 0
            assert connection.execute("SELECT count(*) FROM research_tasks WHERE kind='verify'").fetchone()[0] == 0
            assert connection.execute('SELECT count(*) FROM api_usage').fetchone()[0] == 0
        assert provider.call_count == 1, 'Resume repeated the completed search'
        # Reopen through the same listing used by the HTTP API: no in-memory state.
        reopened = Funnel(ResearchStore(Store(store.path))).listing({'campaign': cid, 'company_only': 1, 'state': 'promising'})
        assert reopened['items'][0]['id'] == candidate['id']
        report = {'checked_at': now(), 'sample_size': 1,
                  'scope': 'Selected positive integration regression, not an unbiased quality sample.',
                  'originals_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'searches_sha256': hashlib.sha256(searches.read_bytes()).hexdigest(),
                  'source': target, 'promising': 1, 'qualified': 0,
                  'public_email': 'info@adriasonline.it', 'category': 'agencies',
                  'checks': ['search lineage retained', 'late promotion refused after Stop',
                             'resume without repeated search', 'one persisted company',
                             'public contact and literal request retained', 'no heavy verification scheduled',
                             'unknown budget preserved', 'survives database reopen'],
                  'api_requests': 0, 'model_calls': 0, 'production_data_modified': False,
                  'frozen_page_reads': len(reads)}
    (ROOT / 'docs/worker50-collaboration.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
