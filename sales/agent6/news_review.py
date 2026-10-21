"""Grounded relation between a business event and a whole-site opportunity."""
import json
from . import website_review

TASK='NEWS_OPPORTUNITY_REVIEW_8'
SYSTEM=website_review.SYSTEM+(' Additionally connect the cited company event to specific measured commercial journeys. '
 'Do not treat an opening, funding, expansion, press publication or a missing language as an order for a site. '
 'Consider available counterevidence; unverified external systems are unknown, not a mandatory gate for a full new site. If the event is already represented '
 'or translation/a new page would suffice, choose LIMITED_FIX or NO_OPPORTUNITY. '
 'An unrelated bad website is not evidence that the news caused this need. Missing publication/currentness or '
 'unsupported event-to-gap relation means NEEDS_REVIEW. Event_date UNKNOWN must remain unknown.')


def schema():
    from .schema import obj,TEXT,arr
    return obj({**website_review.schema()['properties'],'event_ids':arr(TEXT,1),
        'event_relation':TEXT,'existing_solution_check':TEXT})


def validate(raw,payload):
    from .schema import ValidationError
    value=json.loads(raw) if isinstance(raw,str) else raw
    if not isinstance(value,dict) or set(value)!=set(schema()['properties']):raise ValidationError('invalid_news_review_shape')
    core={k:value[k] for k in website_review.schema()['properties']}
    website_review.validate(core,payload)
    if type(value['event_ids'])!=list or len(value['event_ids'])>1 or any(type(x)!=str for x in value['event_ids']):raise ValidationError('invalid_news_event_ids')
    if not set(value['event_ids'])<={e['id'] for e in payload.get('events',[])}:raise ValidationError('unknown_news_event')
    for key in ('event_relation','existing_solution_check'):
        if type(value[key])!=str or len(value[key])>1200:raise ValidationError('invalid_news_relation')
    if value['decision']=='COMPLETE_PROJECT':
        if not value['event_ids'] or not value['event_relation'].strip() or not payload.get('event_current'):
            raise ValidationError('unverified_event_relation_or_currentness')
    return value,[]


def payload(report,fit,identity,context,current):
    from sales.db import digest
    p=website_review.payload(report,fit,identity);f=context['event']
    p.update(task=TASK,event_current=current,events=[{
        'id':digest(context['document']['id']+f['quote'])[:24],'subject':context['subject'],
        'url':f['url'],'quote':f['quote'],'published_at':context['published_at'],
        'event_date':context.get('event_date'),'checked_at':context['checked_at']}])
    # The observed offering and sampled pages can contradict the hypothesis;
    # lack of an unvisited feature is not proof of its absence.
    p['existing_solution_scope']={'pages':report['pages'],'complete_site_coverage':False,
        'counterevidence':fit.get('counterevidence',[])[:3]}
    return p
