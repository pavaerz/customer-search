"""Local Lighthouse selection. One browser at a time, cancellable, no total deadline."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from site_audit import parse_pagespeed, seo_report
from sales.safe_proxy import SafeProxy
from sales.heavy import heavy_slot

CATEGORIES = {'performance':'Prestazioni', 'seo':'SEO', 'accessibility':'Accessibilità', 'best-practices':'Buone pratiche'}
SCORE_THRESHOLD = 90
CACHE_SECONDS = 86400


def unavailable(strategy, message):
    return {'strategy':strategy,'status':'unavailable','source':'Lighthouse locale','message':message}


def runtime_paths():
    home=Path.home()
    def version(path):
        match=re.search(r'/v(\d+)\.(\d+)\.(\d+)/',str(path))
        return tuple(map(int,match.groups())) if match else (0,0,0)
    nodes=sorted(home.glob('.nvm/versions/node/v*/bin/node'), key=version, reverse=True)
    node=os.getenv('LIGHTHOUSE_NODE') or next((str(p) for p in nodes if version(p)>=(22,19,0)),shutil.which('node') or '')
    clis=sorted(home.glob('.npm/_npx/*/node_modules/lighthouse/cli/index.js'),key=lambda p:p.stat().st_mtime,reverse=True)
    cli=os.getenv('LIGHTHOUSE_CLI') or (str(clis[0]) if clis else '')
    chrome=os.getenv('CHROME_PATH') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    return node,cli,chrome


def cache_key(url,strategy):
    return hashlib.sha256(url.encode()).hexdigest()[:24]+'-'+strategy


def valid_report(raw,url):
    final=urlsplit(raw.get('finalDisplayedUrl') or raw.get('finalUrl',''))
    expected=urlsplit(url)
    if final.scheme not in ('https','http') or (final.hostname or '').removeprefix('www.') != (expected.hostname or '').removeprefix('www.'):
        return False
    if raw.get('runtimeError'): return False
    audits=raw.get('audits',{})
    if audits.get('http-status-code',{}).get('score') == 0: return False
    return bool(raw.get('categories'))


def local_lighthouse(url,strategy,data_dir,check_stop):
    if strategy not in ('mobile','desktop'): raise ValueError('Dispositivo non valido')
    check_stop()
    node,cli,chrome=runtime_paths()
    if not all(p and Path(p).is_file() for p in (node,cli,chrome)):
        return unavailable(strategy,'Lighthouse locale non configurato: servono Node recente, Lighthouse e Chrome.')
    folder=Path(data_dir)/'site-reviews'; folder.mkdir(parents=True,exist_ok=True)
    key=cache_key(url,strategy); destination=folder/('lighthouse-'+key+'.json')
    def read_cached():
        try:
            if time.time()-destination.stat().st_mtime>CACHE_SECONDS:return None
            raw=json.loads(destination.read_text())
            return raw if valid_report(raw,url) else None
        except (OSError,ValueError):return None
    raw=read_cached()
    if raw is None:
        with heavy_slot(check_stop), (folder/'lighthouse.lock').open('a') as lock:
            while True:
                check_stop()
                try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError: time.sleep(.2)
            raw=read_cached()
            if raw is None:
                with tempfile.TemporaryDirectory(prefix='lighthouse-',dir=data_dir) as temp, SafeProxy() as proxy:
                    profile=Path(temp)/'chrome'; output=Path(temp)/'report.json'
                    browser=process=None
                    try:
                        # Own Chrome explicitly: it stays in the inspector's process group,
                        # so Stop kills Chrome as well as the Python and Node processes.
                        browser=subprocess.Popen([chrome,'--headless','--no-first-run','--no-default-browser-check',
                            '--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',
                            '--user-data-dir='+str(profile),'--proxy-server='+proxy.url,'--proxy-bypass-list=<-loopback>','--disable-quic','--force-webrtc-ip-handling-policy=disable_non_proxied_udp','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                        port_file=profile/'DevToolsActivePort'
                        startup_deadline=time.monotonic()+30
                        while not port_file.exists():
                            if time.monotonic()>startup_deadline:return unavailable(strategy,'Avvio Chrome scaduto: controllo da ripetere.')
                            check_stop()
                            if browser.poll() is not None:return unavailable(strategy,'Chrome non è riuscito ad avviarsi.')
                            time.sleep(.1)
                        port=port_file.read_text().splitlines()[0]
                        command=[node,cli,url,'--port='+port,'--output=json','--output-path='+str(output),
                                 '--quiet','--locale=it','--only-categories='+','.join(CATEGORIES)]
                        if strategy=='desktop':command.append('--preset=desktop')
                        process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                        audit_deadline=time.monotonic()+120
                        while process.poll() is None:
                            if time.monotonic()>audit_deadline:return unavailable(strategy,'Timeout tecnico Lighthouse: nessun punteggio assegnato.')
                            check_stop();time.sleep(.2)
                        if process.returncode or not output.exists():
                            return unavailable(strategy,'Lighthouse non ha completato il test. Nessun punteggio assegnato.')
                        raw=json.loads(output.read_text())
                        if not valid_report(raw,url):
                            return unavailable(strategy,'Pagina di errore, redirect fuori dominio o test non valido: nessun punteggio utilizzato.')
                        output.replace(destination)
                    except (OSError,ValueError):
                        return unavailable(strategy,'Errore di avvio o lettura del report Lighthouse.')
                    finally:
                        for child in (process,browser):
                            if child is not None:
                                if child.poll() is None:child.terminate()
                                try:child.wait(timeout=5)
                                except subprocess.TimeoutExpired:child.kill();child.wait()
    result=parse_pagespeed({'lighthouseResult':raw},strategy,url)
    result.update(source='Lighthouse locale',report_url='/site-reviews/'+destination.name,
                  note='Test locale di laboratorio, non PageSpeed remoto né dati degli utenti reali. Cache 24 ore; valori soggetti a variazioni.')
    return result


def technical_report(url,html,data_dir,check_stop):
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'url':url,'seo':seo_report(html,url),
            'selection_policy':{'version':'lighthouse-v1','threshold':SCORE_THRESHOLD,'categories':list(CATEGORIES)},
            'pagespeed':[]}
    for strategy in ('mobile','desktop'):
        check_stop()
        report['pagespeed'].append(local_lighthouse(url,strategy,data_dir,check_stop))
    report['completed_at']=time.time()
    report['selection_findings']=selection_evidence(report)
    return report


def selection_evidence(report):
    findings=[]
    for result in report.get('pagespeed',[]):
        if result.get('status')!='ok':continue
        below=[]
        for category,label in CATEGORIES.items():
            value=result.get('scores',{}).get(category)
            if isinstance(value,(int,float)) and not isinstance(value,bool) and 0<=value<SCORE_THRESHOLD:
                below.append(f'{label} {value}/100')
        if below:
            device='Mobile' if result.get('strategy')=='mobile' else 'Desktop'
            findings.append({'kind':'SEO · Lighthouse','qualifies':True,
                             'text':f"{device}: {', '.join(below)}. Sotto la soglia di selezione {SCORE_THRESHOLD}/100; opportunità di ottimizzazione tecnica, non giudizio sul design.",
                             'source':report.get('url',''),'checked_at':result.get('fetch_time') or report.get('checked_at'),
                             'report_url':result.get('report_url')})
    return findings
