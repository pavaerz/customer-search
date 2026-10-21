"""Opt-in evaluation of frozen originals. No search, campaign, CRM or messaging.

Without --execute this only checks inputs and prints the proposed limits.
Do not pass --execute without the user's explicit authorization for this run.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

from sales.agent6 import decision, grounding
from sales.agent6.schema import ValidationError
from sales.commercial.ai import validate_config
from sales.commercial.ai_provider import infer, ProviderError
from sales.commercial.token_count import estimate

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'implementation-report/commercial-objective/validation-inputs'
RESULT=ROOT/'implementation-report/commercial-objective/VALIDATION-AI-01.json'
MAX_CALLS=20
MAX_COST=0.50
# Rates retained from C44's recorded configuration, not a provider invoice.
CONFIG=validate_config({'enabled':True,'provider':'REMOTE','model':'gpt-5.4-mini',
    'endpoint':'https://api.openai.com/v1/chat/completions','mode':'shadow',
    'timeout':60,'max_input_tokens':8192,'max_output_tokens':1500,
    'max_calls_per_campaign':MAX_CALLS,'max_calls_per_engine':MAX_CALLS,
    'max_calls_per_candidate':2,'max_estimated_cost':MAX_COST,'max_retries':0,
    'input_cost_per_million':0.75,'output_cost_per_million':4.50})
REPAIRABLE={'unknown_or_ambiguous_segment','unsupported_actor','unknown_assessment_fact'}


def load_inputs(directory=DIRECTORY,config=CONFIG):
    manifest=json.loads((directory/'MANIFEST.json').read_text())
    records=[]
    for row in manifest['sources']:
        name=row['payload_file']
        if Path(name).name!=name:
            raise ValueError('Input path outside manifest directory')
        raw=(directory/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['payload_sha256']:
            raise ValueError('Prepared input hash mismatch')
        item=json.loads(raw);p=item['payload']
        if any(k in p for k in ('review','expected','allowed','positive_means')):
            raise ValueError('Review label in model input')
        if p['task']!=decision.TASK or estimate(p,config)['tokens']>config['max_input_tokens']:
            raise ValueError('Invalid task or input limit exceeded')
        if item['wire_payload']!=grounding.provider_payload(p):
            raise ValueError('Prepared wire payload mismatch')
        records.append({'id':row['id'],'flow':row['flow'],'url':row['url'],
                        'review':row['review'],'payload':p})
    if not records or len(records)>config['max_calls_per_campaign'] or len({r['id'] for r in records})!=len(records):
        raise ValueError('Invalid evaluation sample')
    return records


def metrics(records,result):
    answers={r['id']:r for r in result['results']}
    positives={r['id'] for r in records if r['review']['expected']=='INTERESTING'}
    promoted={key for key,r in answers.items() if (r.get('output') or {}).get('decision')=='INTERESTING'}
    valid={key for key,r in answers.items() if r.get('output')}
    return {'source_count':len(records),'attempted_sources':len(answers),'valid_decisions':len(valid),
            'known_positive_invitations':len(positives),'recognized_positive_invitations':len(promoted & positives),
            'promoted_outside_positive_labels':len(promoted-positives),
            'positive_invitations_not_recovered':[
                {'id':key,'reason':answers[key]['status'] if key in answers else 'not_attempted',
                 'decision':(answers.get(key,{}).get('output') or {}).get('decision')} for key in sorted(positives-promoted)],
            'agreement_on_valid_decisions':sum(
                r['id'] in valid and answers[r['id']]['output']['decision'] in r['review']['allowed'] for r in records),
            'basis':'Agreement with saved-source review labels; independent review of new outputs still required.',
            'social_originals_evaluated':0}


def evaluate(records,provider,save,check=lambda:None,config=CONFIG):
    """Serial accounting; reserve before dispatch; one bounded semantic repair."""
    config=validate_config(config)
    max_calls=config['max_calls_per_campaign']
    max_cost=config['max_estimated_cost']
    if config['provider']=='REMOTE' and any(config[k] is None for k in ('input_cost_per_million','output_cost_per_million')):
        raise ValueError('Missing evaluation rates')
    result={'mode':'frozen_original_ai_evaluation','status':'running','attempts':[],
            'results':[],'reserved_estimated_usd':0.0,'usage_estimated_usd':0.0,
            'provider_reported_cost_usd':None,'serper_calls':0,'messages_sent':0,
            'production_campaigns_created':0,'max_calls':max_calls,'max_estimated_usd':max_cost,
            'model':config['model'],'provider':config['provider'],
            'configuration':config,
            'system_prompt_sha256':hashlib.sha256(decision.SYSTEM.encode()).hexdigest(),
            'input_hashes':{r['id']:hashlib.sha256(json.dumps(r['payload'],sort_keys=True,ensure_ascii=False).encode()).hexdigest() for r in records},
            'rates_basis':'Explicit evaluation configuration, not provider invoice',
            'limits':['Not a discovery campaign; no new websites or social originals fetched.',
                      'Purposive sample with two positive agency invitations; not market precision.',
                      'Actual current jobs, compensation and conversion are not established.']}
    reservation=(config['max_input_tokens']*config['input_cost_per_million']+
                 config['max_output_tokens']*config['output_cost_per_million'])/1_000_000
    try:
        for record in records:
            payload=copy.deepcopy(record['payload'])
            answer={'id':record['id'],'url':record['url'],'status':'not_attempted','output':None}
            for attempt in (1,2):
                check()
                if len(result['attempts'])>=max_calls or result['reserved_estimated_usd']+reservation>max_cost+1e-12:
                    result['status']='budget_reached';break
                if estimate(payload,config)['tokens']>config['max_input_tokens']:
                    answer['repair_skipped']='input_limit';break
                receipt={'id':record['id'],'attempt':attempt,'status':'reserved','usage':{},
                         'reserved_estimated_usd':reservation}
                result['attempts'].append(receipt)
                result['reserved_estimated_usd']+=reservation
                answer['status']='attempting'
                if answer not in result['results']:
                    result['results'].append(answer)
                save(result)  # A crash after this point is a possible paid call.
                try:
                    response=provider(payload,config,check)
                    receipt['model_output']=response.get('output')
                    usage=response.get('usage') or {}
                    receipt['usage']={k:v for k,v in usage.items() if k in ('input_tokens','output_tokens','total_tokens','reasoning_tokens','cached_input_tokens') and type(v) is int and v>=0}
                    if (receipt['usage'].get('input_tokens',0)>config['max_input_tokens'] or
                            receipt['usage'].get('output_tokens',0)>config['max_output_tokens']):
                        raise ProviderError('token_limit')
                    out,_=decision.validate(response.get('output'),payload)
                    receipt['status']='valid';answer.update(status='valid',output=out)
                    source={'url':record['url'],'original':True,'checked_at':payload['observed_at']}
                    body=decision.materialize(source,out,payload['evidence'],payload,record['flow'])
                    answer['contact_projection']=decision.projection(body)
                    answer['facts']=body['facts']
                except ValidationError as exc:
                    receipt.update(status='invalid',error=str(exc))
                    answer.update(status='invalid',error=str(exc))
                except (ValueError,TypeError,KeyError) as exc:
                    # ProviderError is sanitized; arbitrary prose is never logged.
                    code=str(exc) if isinstance(exc,ProviderError) else type(exc).__name__
                    receipt.update(status='provider_error',error=code)
                    answer.update(status='provider_error',error=code)
                    if isinstance(exc,ProviderError) and exc.usage:
                        receipt['usage']={k:v for k,v in exc.usage.items() if k in ('input_tokens','output_tokens','total_tokens','reasoning_tokens','cached_input_tokens') and type(v) is int and v>=0}
                    if code in ('provider_http_400','provider_http_401','provider_http_403','provider_http_404','provider_http_429','remote_api_key_missing','token_limit'):
                        result['status']='provider_blocked'
                except RuntimeError:
                    receipt.update(status='provider_error',error='provider_worker_failed')
                    answer.update(status='provider_error',error='provider_worker_failed')
                    result['status']='provider_blocked'
                except TimeoutError:
                    receipt.update(status='timeout',error='provider_timeout')
                    answer.update(status='timeout',error='provider_timeout')
                usage=receipt['usage']
                result['usage_estimated_usd']+=(usage.get('input_tokens',0)*config['input_cost_per_million']+
                                               usage.get('output_tokens',0)*config['output_cost_per_million'])/1_000_000
                save(result)
                if receipt['status']=='valid' or attempt==2 or receipt.get('error') not in REPAIRABLE:
                    break
                payload={**payload,'repair':{'code':receipt['error'],
                    'instruction':'Reassess using only supplied segment IDs and complete evidenced names. '
                    'Fact indices start at zero. Do not upgrade commercial interest to make validation pass.'}}
            if result['status'] in ('budget_reached','provider_blocked'):
                break
        if result['status']=='running':
            result['status']='completed'
    except (KeyboardInterrupt,InterruptedError):
        result['status']='stopped'
        if result['attempts'] and result['attempts'][-1]['status']=='reserved':
            result['attempts'][-1]['status']='interrupted_charge_unknown'
            result['results'][-1]['status']='stopped'
    finally:
        result['usage_missing_attempts']=sum(not all(k in r['usage'] for k in ('input_tokens','output_tokens')) for r in result['attempts'])
        result['usage_cost_complete']=result['usage_missing_attempts']==0
        result['metrics']=metrics(records,result)
        save(result)
    return result


def main(config=CONFIG,result_path=RESULT):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true',help='Consume paid AI only after explicit user authorization.')
    args=parser.parse_args()
    config=validate_config(config)
    records=load_inputs(config=config)
    reservation=(config['max_input_tokens']*config['input_cost_per_million']+
                 config['max_output_tokens']*config['output_cost_per_million'])/1_000_000
    if not args.execute:
        print(json.dumps({'status':'prepared_no_calls','originals':len(records),
                          'model':config['model'],'max_calls':config['max_calls_per_campaign'],
                          'max_estimated_usd':config['max_estimated_cost'],
                          'max_input_tokens':config['max_input_tokens'],
                          'max_output_tokens_including_reasoning':config['max_output_tokens'],
                          'maximum_single_call_reservation_usd':reservation,
                          'full_sample_single_pass_reservation_usd':reservation*len(records),
                          'all_calls_reservation_usd':reservation*config['max_calls_per_campaign'],
                          'input_estimates':{r['id']:estimate(r['payload'],config) for r in records},
                          'serper_calls':0,'authorization_required':True}))
        return
    if not os.environ.get('CUSTOMERSEARCH_AI_API_KEY','').strip():
        raise SystemExit('Chiave API assente. Nessuna chiamata eseguita.')
    # Never rerun an interrupted evaluation automatically: reservations must be reviewed.
    with result_path.open('x') as file:
        result_path.chmod(0o600)
        file.write('{"status":"reserved_not_started"}\n')
    def save(result):
        partial=result_path.with_suffix('.partial')
        with partial.open('w') as file:
            partial.chmod(0o600)
            json.dump(result,file,ensure_ascii=False,indent=2)
        partial.replace(result_path)
    result=evaluate(records,infer,save,config=config)
    print(json.dumps({'status':result['status'],'calls':len(result['attempts']),
                      'reserved_estimated_usd':result['reserved_estimated_usd']}))


if __name__=='__main__':
    main()
