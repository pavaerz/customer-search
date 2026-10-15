"""Screen an entire saved Google result set without making new search requests.

This measures company identification, NOT opportunity precision. Uses the same
protected page reader and triage as the app; business state stays in a private copy.
"""
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from contextlib import closing
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sales.db import Store, digest, domain, now
from sales.research_analysis import ResearchWeb, LocalResearcher
from sales.research_triage import triage

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/cycle50/2026-10-14T10-15-46.907683+00-00'


def run():
    baseline = json.loads((SOURCE / 'report.json').read_text())
    items = {}
    for query in baseline['queries']:
        if 'azienda contatti' not in query['query']:
            continue
        for item in query.get('results', []):
            items.setdefault(domain(item['url']), {**item, 'query': query['query']})
    dest = ROOT / 'data/company-screening' / now().replace(':', '-')
    dest.mkdir(parents=True, mode=0o700)
    (dest / 'pages').mkdir(mode=0o700)
    with closing(sqlite3.connect(Store().path)) as src, closing(sqlite3.connect(dest / 'pilot.sqlite3')) as dst:
        src.backup(dst)
    os.chmod(dest / 'pilot.sqlite3', 0o600)
    store = Store(dest / 'pilot.sqlite3')
    report = {'started_at': now(), 'source': str(SOURCE.relative_to(ROOT)),
              'directory': str(dest.relative_to(ROOT)), 'search_requests': 0,
              'sample': list(items.values()), 'cases': [], 'reads': [],
              'limitation': 'Company-identification diagnostic on one sector; not a qualification or independent precision benchmark.'}
    original = ResearchWeb.get

    def capture(web, url, refresh=False):
        page = original(web, url, refresh)
        filename = digest(url) + '.json'
        (dest / 'pages' / filename).write_text(json.dumps(page, ensure_ascii=False))
        report['reads'].append({'url': url, 'status': page['status'], 'capture': filename})
        return page

    def save():
        (dest / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        (ROOT / 'docs/pilot50-existing-companies.json').write_text(json.dumps({
            'directory': str(dest.relative_to(ROOT)), 'examined': len(report['cases']),
            'sample': len(items), 'finished_at': report.get('finished_at'),
            'company_ready': sum(c.get('result', {}).get('details', {}).get('company_ready', False) for c in report['cases']),
            'search_requests': 0, 'limitation': report['limitation']}, ensure_ascii=False, indent=2))

    print(dest, flush=True)
    save()
    with patch.object(ResearchWeb, 'get', capture), patch.object(LocalResearcher, 'call', side_effect=AssertionError('No inference in identification screening')):
        for item in items.values():
            start = time.monotonic()
            case = {'url': item['url'], 'query': item['query']}
            try:
                case['result'] = triage(store, {'url': item['url'], 'strategy': 'companies', 'company_stage': 'identify',
                    'provider': 'Google via Serper — risultati già acquisiti',
                    'filters': {'target': 'b2b', 'regions': ['Veneto', 'Lombardia', 'Piemonte', 'Toscana'],
                                'projects': ['website'], 'groups': ['direct']}}, lambda: None)
            except Exception as exc:
                case['error'] = str(exc)[:600]
            case['seconds'] = round(time.monotonic() - start, 2)
            report['cases'].append(case)
            save()
            print(json.dumps({'n': len(report['cases']), 'url': item['url'], 'state': case.get('result', {}).get('state'),
                              'ready': case.get('result', {}).get('details', {}).get('company_ready'),
                              'error': case.get('error')}, ensure_ascii=False), flush=True)
    report['finished_at'] = now()
    save()


if __name__ == '__main__':
    run()
