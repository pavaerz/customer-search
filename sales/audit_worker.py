"""Isolated Lighthouse subprocess; parent owns and cancels the whole process group."""
import json
import sys
from .config import DATA
from technical_audit import technical_report
if __name__=='__main__':
    url=sys.argv[1]
    print(json.dumps(technical_report(url,'',DATA,lambda:None)),flush=True)
