"""Descriptive precision of ranked proposals, using explicit manual reviews.

Never turn missing reviews into successes, or remove a proposal from the cohort
because its review demoted it. These are operational metrics, not a held-out
benchmark or a probability of winning a client.
"""
import json


def proposed_reviews(store, campaign_id=None):
    where=' AND a.campaign_id=?' if campaign_id is not None else ''
    with store.connect() as c:
        rows=c.execute('''SELECT a.id,a.entity_id,a.score,a.body,r.verdict,
          (SELECT json_extract(d.details,'$.acquisition_provider')
           FROM discovery_candidates d WHERE d.assessment_id=a.id
           AND json_extract(d.details,'$.acquisition_provider') IS NOT NULL
           ORDER BY d.id LIMIT 1) provider
          FROM research_assessments a LEFT JOIN research_reviews r ON r.id=(
            SELECT max(x.id) FROM research_reviews x WHERE x.assessment_id=a.id)
          WHERE (a.status='qualified' OR json_extract(a.body,'$.original_status')='qualified')
          AND coalesce(json_extract(a.body,'$.campaign_only'),0)=0'''+where,
          (campaign_id,) if campaign_id is not None else ()).fetchall()
    result=[]
    for row in rows:
        item=dict(row);body=json.loads(item.pop('body'))
        item['strategy']=body.get('origin_strategy',body.get('strategy','unknown'))
        result.append(item)
    return result


def ranked_quality(rows):
    # Keep the latest proposed dossier per company, then use the same priority
    # ordering as the UI. Return IDs so the measured cohort is inspectable.
    unique={}
    for row in sorted(rows,key=lambda r:r['id'],reverse=True):
        unique.setdefault(row['entity_id'],row)
    ranked=sorted(unique.values(),key=lambda r:(r['score'],r['id']),reverse=True)
    result={'ranked_samples':{},'precision_method':'Ultima proposta per azienda, ordinata per priorità e ID decrescenti. Revisioni manuali; falsi positivi conservati. Non è un benchmark indipendente.'}
    for k in (10,20):
        cohort=ranked[:k]
        reviewed=[r for r in cohort if r['verdict'] in ('confirmed','false_positive')]
        confirmed=sum(r['verdict']=='confirmed' for r in reviewed)
        sufficient=len(cohort)==k and len(reviewed)==k
        result['precision_at_'+str(k)]=round(100*confirmed/k,1) if sufficient else None
        result['ranked_samples'][str(k)]={'target':k,'available':len(cohort),'reviewed':len(reviewed),
            'confirmed':confirmed,'false_positives':len(reviewed)-confirmed,'complete':sufficient,
            'assessment_ids':[r['id'] for r in cohort]}
    return result
