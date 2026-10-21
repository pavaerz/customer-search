"""Explicit human quality audits, separate from preferences and CRM outcomes."""
from datetime import datetime,timezone,timedelta

KINDS={'quality_confirmed','false_positive'}


def latest(store):
    with store.connect() as c:
        rows=c.execute("SELECT f.*,r.request_key FROM agent6_feedback f JOIN agent6_records r ON r.id=f.record_id WHERE f.kind IN ('quality_confirmed','false_positive') ORDER BY f.id").fetchall()
    return {r['request_key']:dict(r) for r in rows}


def summary(store,at=None):
    at=at or datetime.now(timezone.utc)
    rows=list(latest(store).values())
    confirmed=sum(r['kind']=='quality_confirmed' for r in rows)
    cutoff=(at-timedelta(days=7)).isoformat()
    week=[r for r in rows if cutoff<=r['created_at']<=at.isoformat()]
    return {'reviewed_requests':len(rows),'confirmed':confirmed,'false_positives':len(rows)-confirmed,
            'observed_precision':confirmed/len(rows) if rows else None,'sample_sufficient':len(rows)>=20,
            'confirmed_reviews_last_7_days':sum(r['kind']=='quality_confirmed' for r in week),
            'weekly_target':5,'basis':'explicit_manual_review_of_qualification_not_conversion_or_random_sample',
            'note':'Le revisioni confermate nella settimana non dimostrano da sole cinque nuove opportunità ogni settimana. Preferenze, contatti e vendite non sostituiscono la revisione delle prove.'}
