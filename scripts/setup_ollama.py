"""Explicit, free local installation. app.py never downloads a runtime or a model."""
import hashlib,os,platform,subprocess,sys,tarfile,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sales.config import ROOT
from sales.local_model import ensure_local_model
VERSION='0.40.3'
URL=f'https://github.com/ollama/ollama/releases/download/v{VERSION}/ollama-darwin.tgz'
SHA256='a2d1d906a2c8febd9cb18f5c183854d0a6db5dc522940d68b0c0ed048e8dfdea'

def main():
 if platform.system()!='Darwin' or platform.machine()!='arm64':raise SystemExit('Installazione automatica predisposta per Mac Apple Silicon; sugli altri sistemi installa Ollama dal sito ufficiale.')
 folder=ROOT/'.runtime/ollama';binary=folder/'ollama';folder.mkdir(parents=True,exist_ok=True)
 if not binary.exists():
  archive=folder.parent/'ollama-darwin.tgz';h=hashlib.sha256();size=0
  try:
   with urllib.request.urlopen(URL,timeout=60) as source,archive.open('wb') as out:
    while data:=source.read(1024*1024):
     size+=len(data)
     if size>512*1024*1024:raise ValueError('Archivio oltre la dimensione attesa')
     out.write(data);h.update(data)
   if h.hexdigest()!=SHA256:raise ValueError('Hash del runtime non corrispondente: installazione fermata')
   with tarfile.open(archive) as bundle:bundle.extractall(folder,filter='data')
  finally:archive.unlink(missing_ok=True)
 status=ensure_local_model()
 if not status['available']:raise SystemExit(status['reason'])
 if 'qwen2.5:7b' not in status['models']:
  subprocess.run([str(binary),'pull','qwen2.5:7b'],env={**os.environ,'OLLAMA_HOST':'127.0.0.1:11434','OLLAMA_NO_CLOUD':'1'},check=True)
 print('Ollama locale pronto: qwen2.5:7b. Nessun servizio cloud abilitato.')
if __name__=='__main__':main()
