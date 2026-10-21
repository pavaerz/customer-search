import sys,os,socket,sqlite3
from pathlib import Path
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[2]
def audit(event,args):
 if event=='open':
  path,mode,flags=args
  if isinstance(path,(str,bytes,os.PathLike)) and (flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)):
   p=Path(os.fsdecode(path)).resolve()
   if p.is_relative_to(ROOT/'data') or p.is_relative_to(ROOT/'.runtime') or p==ROOT/'.env':raise PermissionError('Test isolation: production writes forbidden')
 if event in ('os.remove','os.rmdir','os.rename'):
  for path in args[:2]:
   if isinstance(path,(str,bytes,os.PathLike)) and Path(os.fsdecode(path)).resolve().is_relative_to(ROOT/'data'):raise PermissionError('Test isolation: production mutation forbidden')
 if event=='socket.connect':
  address=args[1]
  if not isinstance(address,tuple) or address[0] not in ('127.0.0.1','::1','localhost') or address[1] in (8765,8888,11434):raise PermissionError('Test isolation: external/production network forbidden')
 if event=='sqlite3.connect':
  path=str(args[0])
  if path.startswith('file:'):path=unquote(urlsplit(path).path)
  if path not in (':memory:','') and Path(path).resolve().is_relative_to(ROOT/'data'):raise PermissionError('Test isolation: production database forbidden')
sys.addaudithook(audit)
