"""Replay saved C44 originals; observes controls, never fabricates AI decisions."""
import gzip
import hashlib
import json
from pathlib import Path

from sales.agent6 import evidence, response_channels
from sales.commercial.identity import establish
from sales.commercial.entity_scope import profile
from sales.extract import Document
from sales.db import digest


def main():
    root=Path(__file__).resolve().parents[1]
    fixture=root/'tests/fixtures/ai_first/campaign44/originals.json.gz'
    rows=[]
    for item in json.loads(gzip.decompress(fixture.read_bytes())):
        page=item['page']
        doc={'id':digest(page['html']),'text':Document(page['html']).text}
        packet=evidence.packet(page,doc)
        identity=establish([page])
        owner=bool(identity.get('identity_status')=='verified' and not identity.get('identity_conflicts') and not profile(page)['multi_subject'])
        controls=response_channels.collect(page,packet['units'][0],identity,owner)
        rows.append({'url':page['url'],'source_campaign':item['source_campaign'],
                     'html_sha256':hashlib.sha256(page['html'].encode()).hexdigest(),
                     'resolved_name':identity.get('name'),'identity_status':identity.get('identity_status'),
                     'observed_channels':controls,
                     'commercial_decision':'NOT_EVALUATED',
                     'note':'Controls observed in a saved original, not live availability or commercial qualification.'})
    result={'mode':'offline_saved_originals','paid_calls':0,'submissions':0,
            'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),
            'originals':len(rows),'channels':sum(len(r['observed_channels']) for r in rows),
            'rows':rows,
            'limits':['No new AI inference. No conversion or commercial-precision measurement.',
                      'Application controls on course pages are not freelance opportunities.',
                      'webbes.it brand is corroborated by its visible self-identification, not truncated from SEO metadata.']}
    destination=root/'implementation-report/commercial-objective/response-channels-replay.json'
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('mode','originals','channels','paid_calls','submissions')}))


if __name__=='__main__':
    main()
