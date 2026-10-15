"""Start an already installed local runtime; never download or call a cloud model."""
import os,subprocess,time
from .config import ROOT
from .providers import api_json

def ensure_local_model():
    url='http://127.0.0.1:11434/api/tags'
    try:return {'available':True,'models':[m['name'] for m in api_json(url,timeout=2).get('models',[])]}
    except Exception:pass
    binary=ROOT/'.runtime/ollama/ollama'
    if not binary.exists():return {'available':False,'reason':'Ollama non installato; leggi README.md'}
    runtime=ROOT/'.runtime';log=runtime/'ollama.log'
    env={**os.environ,'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_MODELS':str(runtime/'models'),'OLLAMA_NO_CLOUD':'1','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1'}
    with log.open('ab') as output:
        process=subprocess.Popen([str(binary),'serve'],env=env,stdout=output,stderr=output,start_new_session=True)
    log.chmod(0o600)
    for _ in range(30):
        if process.poll() is not None:break
        try:return {'available':True,'models':[m['name'] for m in api_json(url,timeout=.5).get('models',[])]}
        except Exception:time.sleep(.1)
    return {'available':False,'reason':'Servizio locale non avviato; consulta .runtime/ollama.log'}
