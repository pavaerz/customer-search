"""Frozen identity/triage replay, not a new campaign or a qualification run."""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sales.agent6.site_identity import resolve
from sales.commercial.target_fit import evaluate, source_role
from sales.extract import parse_page

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/agent91/campaign40.json.gz'


def report():
    raw = FIXTURE.read_bytes()
    saved = json.loads(gzip.decompress(raw))
    rows = []
    for case in saved['cases']:
        pages, identity, provenance = resolve(case['pages'], case['url'])
        first = next(p for p in case['pages'] if p['url'] == case['url'])
        parsed = parse_page(first)
        role = source_role(first['url'], parsed['title'], parsed['text'])
        fit = evaluate(identity, pages, {'eligible': identity.get('region') in ('Veneto', 'Lombardia', 'Piemonte', 'Toscana', 'Emilia-Romagna')})
        old = case['observed']
        rows.append({
            'record_id': case['record_id'], 'task_id': case['task_id'], 'url': case['url'],
            'before': {'name': old['identity']['name'], 'identity_status': old['identity']['identity_status'],
                       'region': old['identity'].get('region'), 'audit_allowed': old['commercial_fit']['audit_allowed'],
                       'reasons': old['commercial_fit']['reasons'], 'historical_state': old['state']},
            'after': {'name': identity['name'], 'identity_status': identity['identity_status'],
                      'region': identity.get('region'), 'source_role': role, 'audit_allowed': fit['audit_allowed'],
                      'reasons': fit['reasons'], 'location_evidence': identity.get('location_evidence', []),
                      'relationship_verified': provenance['relationship_verified']},
            'interpretation': 'Ammesso allo screening; bisogno e difetti ancora da verificare.' if fit['audit_allowed'] else
                              'Fonte esclusa dagli audit aziendali; nessun committente dedotto dal suo contenuto.'})
    return {'mode': 'offline_saved_evidence', 'campaign_id': 40,
            'fixture_sha256': hashlib.sha256(raw).hexdigest(), 'cases': rows,
            'new_ai_calls': 0, 'new_serper_calls': 0, 'new_browser_measurements': 0,
            'production_writes': 0, 'new_qualifications': 0,
            'limits': ['Tre regressioni selezionate, non un campione commerciale rappresentativo.',
                       'La disponibilità delle pagine non è stata ricontrollata sul web.',
                       'Nessuna misura dei risparmi futuri o delle conversioni.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    args = parser.parse_args()
    content = json.dumps(report(), ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(content)
    else:
        print(content)
