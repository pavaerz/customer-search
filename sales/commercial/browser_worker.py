"""Private subprocess entrypoint for bounded commercial browser inspection.

Input is supplied only by browser.review through an owned temporary file. No
HTTP endpoint accepts this payload; no transport bypass exists here.
"""
import json
import sys
import time
from pathlib import Path

from sales.db import Store
from .browser import _review
from .resources import Budget, BudgetExceeded, _context


def main():
    payload=json.load(sys.stdin);store=Store(Path(payload['store']))
    from sales import heavy
    heavy.DATA=store.path.parent
    def emit(kind, **value):
        print(json.dumps({'type':kind,**value}),flush=True)
    # The child uses the same database ledger, campaign generation and quotas.
    # No Store.init, settings changes, runtime lease or extra browser reservation.
    value=payload.get('budget');token=None
    if value:
        budget=Budget(store,{'id':value['cid'],'generation':value['generation']},value['engine'],value['limits'])
        budget.deadline=value['deadline'];budget.task_id=value.get('task_id');token=_context.set(budget)
    def check():
        if time.monotonic()>=payload['deadline']:raise TimeoutError('Budget temporale complessivo del browser raggiunto')
    try:
        result=_review(store,payload['pages'],check=check,max_pages=payload['max_pages'],
                       capture=payload['capture'],limits=payload['limits'],
                       checkpoint=lambda result:emit('checkpoint',result=result))
        emit('result',result=result)
    except BudgetExceeded as exc:emit('error',resource=exc.resource,message=str(exc))
    except InterruptedError as exc:emit('error',message=str(exc))
    finally:
        if token is not None:_context.reset(token)


if __name__=='__main__':main()
