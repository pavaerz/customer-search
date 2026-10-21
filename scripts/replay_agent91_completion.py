"""Recheck a saved promising dossier; no database, network or new AI output."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.replay_agent91 import load, replay_case
from sales.agent6 import commercial_policy


def report():
    case=next(c for c in load()['cases'] if c['record']['id']==369)
    body=replay_case(case)
    direction=commercial_policy.investigation(body)
    return {'mode':'offline_replay_not_new_campaign','source_campaign':39,'record_id':369,
        'url':body['url'],'source_checked_at':body['checked_at'],
        'name':body['entity_name'],'identity_verified':body['identity_verified'],
        'state':body['state'],'missing':body['missing'],
        'resolved_requirements':body['requirement_resolution'],
        'collaboration_geography':body['collaboration_geography'],
        'current_availability':body['completion_queue']['current_availability'],
        'project_budget':body['budget'],'completion':body['completion_queue'],
        'next_check':direction,
        'proposed_query_not_executed':commercial_policy.verification_query(body,direction['goal']) if direction['allowed'] else None,
        'new_ai_calls':0,'new_serper_calls':0,'production_writes':0,
        'limits':['Saved source, not a new verification of current availability.',
            'An ongoing invitation is not proof of an open assignment, project scope or budget.',
            'The missing currentness check is queued, not completed or simulated.',
            'Campaign 40 had no queued targeted follow-up searches: scheduler protection alone does not explain its zero qualified results.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    value=json.dumps(report(),ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(value+'\n')
    else:print(value)
