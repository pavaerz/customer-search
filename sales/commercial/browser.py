"""Bounded, read-only mobile/desktop rendering with existing network protections."""
import time,re
import json, os, signal, subprocess, sys, tempfile
from pathlib import Path
from contextvars import copy_context
from urllib.parse import urlsplit
from urllib.parse import urljoin
from sales.operation_outcomes import safe_error
from sales.db import digest,now
from sales.providers import PublicWeb
from sales.safe_proxy import SafeProxy
from sales.heavy import heavy_slot
from sales.content_policy import require_non_pdf,skip_pdf
from .resources import reserve,BudgetExceeded,timeout

MEASURE="""() => {
 const visibleText=()=>{const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node,count=0;while((node=walker.nextNode())&&count++<1500){const e=node.parentElement;if(e&&!['SCRIPT','STYLE','NOSCRIPT'].includes(e.tagName)&&node.textContent.trim().length>20&&e.checkVisibility?.({checkOpacity:true,checkVisibilityCSS:true}))return true}return false};
 const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'&&(!e.checkVisibility||e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))};
 const blocks=[...document.querySelectorAll('main p,main h1,main h2,article p,section p')].filter(e=>visible(e)&&e.innerText.trim().length>30);
 const clipped=blocks.filter(e=>{const r=e.getBoundingClientRect();return r.left>=innerWidth||r.right>innerWidth*1.3||(['hidden','clip'].includes(getComputedStyle(e).overflowY)&&e.scrollHeight>e.clientHeight+10)});
 const blocked=[...document.querySelectorAll('a,button')].filter(e=>{if(!visible(e))return false;const r=e.getBoundingClientRect();if(r.top<0||r.top>innerHeight||r.left<0||r.right>innerWidth)return false;const top=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return top&&!e.contains(top)&&!top.contains(e)});
 const typography=e=>{const s=getComputedStyle(e);return {tag:e.tagName,text:e.innerText.trim().slice(0,180),font_size:parseFloat(s.fontSize),font_weight:s.fontWeight,color:s.color}};
 const hierarchy={headings:[...document.querySelectorAll('main h1,main h2,article h1,article h2,h1')].filter(visible).slice(0,6).map(typography),paragraphs:[...document.querySelectorAll('main p,article p,section p')].filter(e=>visible(e)&&e.innerText.trim().length>60).slice(0,3).map(typography)};
 return {width:innerWidth,overflow:document.documentElement.scrollWidth-innerWidth,blocks:blocks.length,clipped:clipped.length,
 typography:hierarchy,
 links:[...document.querySelectorAll('a[href]')].filter(visible).map(e=>e.href),
 headings:[...document.querySelectorAll('h1,h2')].filter(visible).map(e=>e.innerText.trim()).slice(0,20),
 blocked:blocked.length, navigation:[...document.querySelectorAll('nav a')].filter(visible).length,
 contactLinks:[...document.querySelectorAll('a[href]')].filter(visible).filter(e=>/contatt|contact|preventiv/i.test(e.innerText+' '+e.pathname)).map(e=>e.href),
 offerLinks:[...document.querySelectorAll('a[href]')].filter(visible).filter(e=>/prodott|serviz|catalog/i.test(e.innerText+' '+e.pathname)).map(e=>e.href),
 visible_content:visibleText()||[...document.images].some(visible),
 fonts_loaded:!document.fonts||document.fonts.status==='loaded',title:document.title,meta_viewport:document.querySelector('meta[name=viewport]')?.content||null,text:document.body.innerText.trim().length};
}"""

def error_code(exc,phase):
    text=str(exc).lower()
    if getattr(exc,'code',None)=='excluded_pdf':return 'excluded_pdf'
    if 'robots' in text:return 'robots'
    if 'certificate' in text or 'ssl' in text or 'tls' in text:return 'tls_error'
    if isinstance(exc,TimeoutError) or 'timeout' in text or 'timed out' in text or 'temporale' in text:
        return 'navigation_timeout' if phase=='navigation' else 'rendering_timeout' if phase in ('rendering','resource') else phase+'_timeout'
    return 'navigation_error' if phase=='navigation' else 'access_error'


def _review(store,pages,check=lambda:None,max_pages=3,capture=True,limits=None,checkpoint=lambda value:None):
    """Synchronous worker boundary; Playwright and resource routes are asynchronous."""
    import asyncio
    return asyncio.run(_review_async(store,pages,check,max_pages,capture,limits,checkpoint))


def adaptive_phase_limit(base_ms,pending_resources,remaining_ms,explicit=False):
    """Borrow from unused total time only for a live resource backlog."""
    if explicit or not pending_resources:return max(1,min(base_ms,remaining_ms))
    return max(1,min(base_ms*2,remaining_ms//3))

def rendering_phase_limit(base_ms,pending_resources,remaining_ms,explicit=False,remaining_views=1):
    """Spend the existing total deadline on queued work, retaining other views.

    Explicit phase limits remain hard limits. No request/resource quota changes
    and no retry: the same authorized resource reads are allowed to finish.
    """
    if explicit or not pending_resources:return max(1,min(base_ms,remaining_ms))
    reserve=min(2500,max(0,remaining_ms//5))
    return max(1,(remaining_ms-reserve)//max(1,remaining_views))


def audit_state(report):
    if not report or report.get('executed') is False:return 'NOT_EXECUTED'
    if report.get('completed'):return 'COMPLETE'
    if report.get('pages'):return 'PARTIAL'
    if any('timeout' in str(c) for c in report.get('failure_codes',[])) or 'timeout' in report.get('outcome',''):return 'TIMEOUT'
    return 'BLOCKED' if report.get('outcome') in ('robots','access_error','tls_error') else 'FAILED'


async def _review_async(store,pages,check,max_pages,capture,limits,checkpoint):
    import asyncio
    import threading
    from contextvars import ContextVar
    from playwright.async_api import async_playwright

    check()
    for p in pages:require_non_pdf(p)
    limits=limits or {};started=time.monotonic();deadline=started+limits.get('browser_total_seconds',120)
    from .audit_policy import resource_role,finish
    requested=limits.get('browser_audit_level','DEEP')
    if requested not in ('BASIC','STANDARD','DEEP'):raise ValueError('Livello audit non valido')
    if requested!='DEEP':max_pages=1
    result={'completed':False,'outcome':'access_error','findings':[],'links':[],'pages':[],
            'dom_checkpoints':[],'screenshots':[],'limits':[],'diagnostics':[],
            'path_checks':[],'resources_closed':False}
    failures=set();page_failures=set();requests=0;total_bytes=0;cache={};failed_resources={};context=None;browser=None
    noncritical_requests=0
    phase='startup';current_url='';current_width=None;budget_failures=[]
    phase_limits={'startup':limits.get('browser_startup_timeout_ms',15000),
                  'navigation':limits.get('browser_timeout_ms',20000),
                  'rendering':limits.get('browser_render_timeout_ms',5000),
                  'dom':limits.get('browser_render_timeout_ms',5000),
                  'evidence':limits.get('browser_evidence_timeout_ms',2500),
                  'cleanup':limits.get('browser_cleanup_timeout_ms',800)}
    phase_deadline=min(deadline,started+phase_limits['startup']/1000)
    advanced=limits.get('browser_advanced',True) and requested!='BASIC'
    result['requested_level']=requested;result['ignored_resources']=[]
    result['levels']={'HTTP':{'status':'available','pages':len(pages)},
                      'DOM':{'status':'unavailable'},
                      'BROWSER_ADVANCED':{'status':'unavailable' if advanced else 'not_requested'}}
    resource_deadline=ContextVar('browser_resource_deadline',default=deadline)
    cancelled=threading.Event();route_tasks=set();fetch_tasks={};active_reads=0
    max_concurrent=max(1,min(4,int(limits.get('browser_resource_concurrency',4))))
    from .browser_queue import ResourceSlots
    slots=ResourceSlots(max_concurrent);origin_locks={}
    result['resource_concurrency_limit']=max_concurrent;result['peak_resource_reads']=0
    def guard():
        check()
        if budget_failures:raise budget_failures[0]
        if time.monotonic()>=deadline:raise TimeoutError('Budget temporale del controllo browser raggiunto')
    def resource_guard():
        guard()
        if cancelled.is_set():raise InterruptedError('Chiusura del controllo browser')
        if time.monotonic()>=resource_deadline.get():raise TimeoutError('Timeout della singola risorsa browser')
    def milliseconds(cap):
        guard()
        return max(1,min(cap,timeout(max(.001,min(deadline,phase_deadline)-time.monotonic()))*1000))
    def diagnose(kind,status,begin=None,exc=None,url=None,**extra):
        # Resources have independent concurrent lifetimes. A single mutable
        # active_resource marker would race and incorrectly kill the whole page.
        if kind in phase_limits:
            if status=='started':result['active_phase']={'name':kind,'started_at':begin or started,'limit_ms':phase_limits[kind],'url':url or current_url}
            elif status in ('completed','incomplete','partial','blocked') and result.get('active_phase',{}).get('name')==kind:result.pop('active_phase',None)
        result['diagnostics'].append({'phase':kind,'status':status,'url':url or current_url,
            'viewport':current_width,'elapsed_ms':round((time.monotonic()-(begin or started))*1000),
            'limit_ms':min(phase_limits.get(kind,limits.get('browser_resource_timeout_ms',3000)),max(0,round((deadline-(begin or started))*1000))),
            'error':(safe_error(exc) or type(exc).__name__+': '+kind) if exc is not None else None,
            **({'code':error_code(exc,kind),'message':safe_error(exc) or type(exc).__name__+': '+kind} if exc is not None else {}),**extra})
        checkpoint(result)
    def failure(exc,kind,url=None,**details):
        marker=result.get('active_phase',{})
        begin=marker.get('started_at') if marker.get('name')==kind else time.monotonic()
        message=safe_error(exc) or type(exc).__name__+': '+kind
        details.setdefault('pending_dependencies',[getattr(t,'cs_resource',{}) for t in route_tasks])
        if details.get('role')!='FORM':
            failures.add(message)
            # A resource/script failure persists for the loaded document. A
            # timed-out measurement invalidates that viewport, not every later
            # viewport even after its dependencies have actually settled.
            if kind=='resource' or details.get('dependency'):page_failures.add(message)
        else:result.setdefault('unverified_features',[]).append({'feature':'form','url':url,'reason':message,'affects_rendering':False})
        diagnose(kind,'incomplete',begin=details.pop('begin',begin),exc=exc,url=url,**details)
    async def measure(page,early=False):
        condition="document.body && (document.body.innerText.trim().length || document.querySelector('a[href]'))" if early else 'document.body'
        script="() => { if (!("+condition+")) return false; const value=("+MEASURE+")(); value.text_excerpt=document.body.innerText.slice(0,20000); value.ready_state=document.readyState; return value; }"
        handle=await page.wait_for_function(script,timeout=milliseconds(phase_limits['dom']))
        try:return await handle.json_value()
        finally:await handle.dispose()
    def save_page(source,width,measurements,complete,scope):
        row={'url':source['url'],'final_url':measurements.pop('_final_url',source['url']),
             'checked_at':now(),'viewport':width,'measurements':measurements,'complete':complete,'scope':scope}
        index=next((i for i,p in enumerate(result['pages']) if p['url']==source['url'] and p['viewport']==width),None)
        if index is None:result['pages'].append(row)
        else:result['pages'][index]=row
        result['links']+=measurements.get('links',[])
        result['levels']['DOM']['status']='partial'
        checkpoint(result)
    try:
        web=PublicWeb(store,resource_guard);web.allow_binary=True
        web.request_timeout=lambda:max(.001,min(limits.get('browser_resource_timeout_ms',3000)/1000,resource_deadline.get()-time.monotonic(),deadline-time.monotonic()))
        # Shared robots cache and crawl delay remain serialized per origin.
        # Network reads themselves run concurrently after policy authorization.
        original_policy=web.policy
        def protected_policy(url):
            parts=urlsplit(url);origin=(parts.scheme,parts.netloc)
            lock=origin_locks.setdefault(origin,threading.Lock())
            # Politeness/robots authorization is not download time. Its wait
            # stays bounded by the enclosing phase and total supervisor budget.
            begin=time.monotonic();resource_deadline.set(deadline)
            while not lock.acquire(timeout=.025):resource_guard()
            try:
                resource_guard();original_policy(url)
                diagnose('resource_policy','completed',begin,url=url,wait_ms=round((time.monotonic()-begin)*1000))
            finally:
                lock.release()
                resource_deadline.set(min(deadline,time.monotonic()+limits.get('browser_resource_timeout_ms',3000)/1000))
        web.policy=protected_policy
        async def fetch(url,resource_type):
            nonlocal requests,total_bytes,active_reads,noncritical_requests
            queued=time.monotonic()
            async with slots.acquire(resource_type):
                guard()
                # Reserve part of the unchanged total for CSS/JS/fonts. Never
                # fake a successful render when omitted media affects it: this
                # remains an explicit crawler limit with unvalidated measures.
                maximum=limits.get('browser_max_resources',60)
                noncritical=resource_type not in ('document','stylesheet','script','font')
                if noncritical and noncritical_requests>=max(1,int(maximum*.7)):
                    raise ValueError('Riserva risorse per dipendenze essenziali: rendering parziale')
                if requests>=limits.get('browser_max_resources',60) or total_bytes>12000000:raise ValueError('Budget risorse raggiunto')
                requests+=1;active_reads+=1
                if noncritical:noncritical_requests+=1
                result['peak_resource_reads']=max(result['peak_resource_reads'],active_reads)
                begin=time.monotonic();token=resource_deadline.set(min(deadline,begin+limits.get('browser_resource_timeout_ms',3000)/1000))
                diagnose('resource','started',begin,url=url,resource_type=resource_type,queue_wait_ms=round((begin-queued)*1000))
                try:
                    # asyncio copies the ledger and per-resource deadline to the
                    # thread. Never run blocking DNS/robots/socket I/O in a route.
                    p=await asyncio.to_thread(web._raw,url);guard();require_non_pdf(p)
                    total_bytes+=len(p.get('body',b''));cache[url]=p
                    return p
                finally:resource_deadline.reset(token);active_reads-=1
        originals={p['url']:p for p in pages};folder=store.path.parent/'site-reviews'
        diagnose('startup','started',started)
        with heavy_slot(guard),SafeProxy() as proxy:
          async with async_playwright() as pw:
            begin=time.monotonic();phase_deadline=min(deadline,begin+phase_limits['startup']/1000)
            try:
                result['owned_driver_pid']=pw._impl_obj._connection._transport._proc.pid;checkpoint(result)
            except AttributeError:pass
            browser=await pw.chromium.launch(channel='chrome',headless=True,timeout=milliseconds(phase_limits['startup']),
                proxy={'server':proxy.url,'bypass':'<-loopback>'},
                args=['--disable-quic','--force-webrtc-ip-handling-policy=disable_non_proxied_udp'])
            diagnose('startup','completed',begin)
            try:
                session=await browser.new_browser_cdp_session()
                result['owned_browser_pids']=[int(x['id']) for x in (await session.send('SystemInfo.getProcessInfo'))['processInfo']]
                await session.detach();checkpoint(result)
            except Exception:pass
            try:
                context=await browser.new_context(service_workers='block',accept_downloads=False)
                async def block_websocket(ws):
                    failures.add('WebSocket dinamico non eseguito: comportamento non verificato')
                    diagnose('resource','blocked',url=ws.url,resource_type='websocket');await ws.close()
                await context.route_web_socket('**/*',block_websocket)
                async def route_handler(route):
                    task=asyncio.current_task();route_tasks.add(task)
                    req=route.request;begin=time.monotonic()
                    role=resource_role(req.url,req.resource_type,pages[0]['url'])
                    task.cs_resource={'url':req.url,'role':role,'type':req.resource_type}
                    async def abort():
                        try:await route.abort()
                        except Exception:pass  # page may already have closed
                    try:
                        if role in ('TRACKING','OPTIONAL'):
                            result['ignored_resources'].append({'url':req.url,'role':role,'reason':'Nonessential analytics/media; interaction outside audit scope'})
                            diagnose('resource','intentionally_omitted',begin,url=req.url,resource_type=req.resource_type,role=role)
                            await abort();return
                        if req.method!='GET' or req.resource_type in ('eventsource','websocket'):
                            failures.add('Operazione dinamica o flusso continuo non eseguito')
                            diagnose('resource','blocked',begin,url=req.url,resource_type=req.resource_type)
                            await abort();return
                        guard();require_non_pdf(req.url)
                        if req.url in failed_resources:
                            if role!='FORM':failures.add(failed_resources[req.url]);page_failures.add(failed_resources[req.url])
                            diagnose('resource','not_retried',begin,url=req.url,resource_type=req.resource_type,role=role,reason=failed_resources[req.url]);await abort();return
                        if req.url in originals:
                            p=originals[req.url];await route.fulfill(status=p.get('status',200),body=p['html'],content_type='text/html');return
                        if req.url not in cache:
                            if req.url not in fetch_tasks:fetch_tasks[req.url]=asyncio.create_task(fetch(req.url,req.resource_type))
                            await asyncio.shield(fetch_tasks[req.url])
                        require_non_pdf(cache[req.url]);p=cache[req.url]
                        if p['status']!=200:raise ValueError('Risorsa non disponibile: HTTP '+str(p['status']))
                        if p['url']!=req.url:
                            require_non_pdf(p['url']);cache[p['url']]=p
                            old=urlsplit(req.url);final=urlsplit(p['url'])
                            same_base=(old.scheme,old.netloc,old.path.rsplit('/',1)[0])==(final.scheme,final.netloc,final.path.rsplit('/',1)[0])
                            if req.resource_type=='document' or not same_base:raise ValueError('Redirect verificato via HTTP, base del documento/risorsa non renderizzata: '+p['url'])
                            diagnose('resource','completed',begin,url=req.url,resource_type=req.resource_type,final_url=p['url'],redirect_method='validated_body_same_base')
                        await route.fulfill(status=p['status'],body=p.get('body',p.get('html','')),content_type=p.get('content_type','text/plain'))
                        diagnose('resource','completed',begin,url=req.url,resource_type=req.resource_type)
                    except (InterruptedError,BudgetExceeded) as exc:
                        if not cancelled.is_set():budget_failures.append(exc)
                        await abort()
                    except Exception as exc:
                        if getattr(exc,'code',None)=='excluded_pdf':
                            from sales.content_policy import note_pdf
                            note_pdf(req.url)
                        failed_resources[req.url]=safe_error(exc);failure(exc,'resource',req.url,begin=begin,resource_type=req.resource_type,role=role);await abort()
                    finally:route_tasks.discard(task)
                # The async Playwright dispatcher runs callbacks in its own task.
                # Explicitly propagate the ledger to the callback's asyncio task.
                resource_context=copy_context()
                async def dispatch(route):
                    return await asyncio.create_task(route_handler(route),context=resource_context.copy())
                await context.route('**/*',dispatch)
                page=await context.new_page();page.on('dialog',lambda dialog:dialog.dismiss())
                page.on('pageerror',lambda error:failure(error,'rendering',dependency=True))
                ordered=pages[:1]
                for pattern in (r'contatt|contact|preventiv',r'prodott|serviz|catalog'):
                    selected=next((p for p in pages[1:] if re.search(pattern,urlsplit(p['url']).path,re.I) and p not in ordered),None)
                    if selected:ordered.append(selected)
                ordered+=[p for p in pages if p not in ordered]
                def viewports(source):
                    widths=(390,) if requested=='BASIC' else (390,1366)
                    if 'browser_viewports' in limits:widths=tuple(w for w in widths if w in limits['browser_viewports'].get(source['url'],[]))
                    return widths
                remaining_views=sum(len(viewports(source)) for source in ordered[:max_pages])
                for source in ordered[:max_pages]:
                    current_url=source['url'];guard()
                    for width in viewports(source):
                        remaining_views-=1
                        # Re-navigating while requests are pending aborts their
                        # routes and executes scripts twice. Resize the same
                        # document; keep its failures and remeasure readiness.
                        reuse=width==1366 and not page.is_closed() and page.url==source['url']
                        if not reuse:page_failures.clear()
                        current_width=width;guard();phase='navigation';begin=time.monotonic();navigation_ok=False
                        phase_deadline=min(deadline,begin+phase_limits['navigation']/1000);diagnose(phase,'started',begin)
                        try:
                            await page.set_viewport_size({'width':width,'height':844})
                            response=None if reuse else await page.goto(source['url'],wait_until='commit',timeout=milliseconds(phase_limits['navigation']))
                            if response and response.status>=400:raise ValueError('Navigazione HTTP '+str(response.status))
                            navigation_ok=True;diagnose(phase,'completed',begin,final_url=page.url,wait_until='reuse_pending_document' if reuse else 'commit')
                        except (InterruptedError,BudgetExceeded):raise
                        except Exception as exc:failure(exc,phase)
                        if not navigation_ok:continue
                        # Save useful DOM BEFORE fonts, stylesheets, images and
                        # async scripts finish. This checkpoint is evidence only,
                        # never a layout defect measured from an unstyled page.
                        phase='dom';begin=time.monotonic();phase_limits['dom']=adaptive_phase_limit(limits.get('browser_render_timeout_ms',5000),len(route_tasks),max(1,int((deadline-begin)*1000)), 'browser_render_timeout_ms' in limits);phase_deadline=min(deadline,begin+phase_limits['dom']/1000)
                        diagnose(phase,'started',begin,stage='early')
                        try:
                            early=await measure(page,early=True);early['_final_url']=page.url
                            save_page(source,width,early,False,'early_dom')
                            result['dom_checkpoints'].append({'url':source['url'],'viewport':width,'elapsed_ms':round((time.monotonic()-started)*1000),
                                'scope':'early_dom','text_excerpt':early.get('text_excerpt',''),'pending_resources':len(route_tasks),
                                'ready_state':early.get('ready_state'),'layout_evidence':False})
                            diagnose(phase,'completed',begin,stage='early',pending_resources=len(route_tasks))
                        except (InterruptedError,BudgetExceeded):raise
                        except Exception as exc:
                            if error_code(exc,'dom')=='dom_timeout':
                                # This optional checkpoint is not the rendered
                                # measurement. Keep the timeout visible; require
                                # successful readiness and final measurements.
                                diagnose('dom','incomplete',begin,exc=exc,stage='early',affects_completion=False)
                            else:failure(exc,'dom')
                        phase='rendering';begin=time.monotonic();phase_limits['rendering']=rendering_phase_limit(limits.get('browser_render_timeout_ms',5000),len(route_tasks),max(1,int((deadline-begin)*1000)), 'browser_render_timeout_ms' in limits,remaining_views+1);phase_deadline=min(deadline,begin+phase_limits['rendering']/1000)
                        ready=False;diagnose(phase,'started',begin)
                        try:
                            while True:
                                guard()
                                if page_failures and not route_tasks:
                                    raise ValueError('Dipendenze non disponibili: readiness non certificabile; attesa aggiuntiva omessa')
                                settled=await asyncio.wait_for(page.evaluate("() => !!document.body && document.readyState === 'complete' && (!document.fonts || document.fonts.status === 'loaded')"),timeout=milliseconds(phase_limits['rendering'])/1000)
                                critical=[t for t in route_tasks if getattr(t,'cs_resource',{}).get('role')!='FORM']
                                if settled and not critical:break
                                if time.monotonic()>=phase_deadline:
                                    diagnose('rendering','pending_dependencies',begin,ready_state=await page.evaluate('document.readyState'),pending=[getattr(t,'cs_resource',{}) for t in route_tasks],fonts_loaded=await page.evaluate("!document.fonts || document.fonts.status==='loaded'"))
                                    raise TimeoutError('Timeout risorse della fase rendering')
                                await asyncio.sleep(.025)
                            ready=True;diagnose(phase,'completed',begin,wait_until='rendered_resources_settled')
                        except (InterruptedError,BudgetExceeded):raise
                        except Exception as exc:failure(exc,phase)
                        phase='dom';begin=time.monotonic();phase_limits['dom']=adaptive_phase_limit(limits.get('browser_render_timeout_ms',5000),len(route_tasks),max(1,int((deadline-begin)*1000)), 'browser_render_timeout_ms' in limits);phase_deadline=min(deadline,begin+phase_limits['dom']/1000)
                        diagnose(phase,'started',begin,stage='rendered')
                        try:
                            one=await measure(page)
                            if advanced:await page.wait_for_timeout(min(100,milliseconds(100)))
                            guard();two=await measure(page) if advanced else one
                            diagnose('dom','completed',begin,stage='rendered')
                        except (InterruptedError,BudgetExceeded):raise
                        except Exception as exc:failure(exc,'dom');continue
                        if two['text']==0 and not two['links']:
                            failures.add('Nessun contenuto del sito acquisito');continue
                        complete=navigation_ok and ready and not page_failures
                        if not two.get('visible_content',False):
                            failures.add('Nessun contenuto visibile validato; il testo DOM non dimostra il rendering.');complete=False
                        if min(one['text'],two['text'])<40:failures.add('Contenuto renderizzato insufficiente');complete=False
                        two['_final_url']=page.url;save_page(source,width,two,complete,'rendered' if complete else 'partial_dom')
                        if complete and advanced:
                            if one['clipped']>=2 and two['clipped']>=2:
                                result['findings'].append({'code':'mobile_content' if width==390 else 'desktop_content','severity':'major','url':source['url'],'quote':f"A {width} px, {two['clipped']} blocchi tagliati/fuori larghezza in due misure.",'viewport':width})
                            elif min(one['overflow'],two['overflow'])>100:
                                result['findings'].append({'code':'horizontal_overflow','severity':'moderate','url':source['url'],'quote':f"Overflow di {two['overflow']} px su schermo da {width} px.",'viewport':width})
                            if min(one['blocked'],two['blocked'])>=2:result['findings'].append({'code':'obstructed_controls','severity':'major','url':source['url'],'quote':f"{two['blocked']} controlli coperti da altri elementi a {width} px, in due misure.",'viewport':width})
                        if capture and requested!='BASIC' and two.get('fonts_loaded',False):
                            phase='evidence';begin=time.monotonic();phase_deadline=min(deadline,begin+phase_limits['evidence']/1000);diagnose(phase,'started',begin)
                            try:
                                folder.mkdir(exist_ok=True);name='commercial-'+digest(source['url']+str(width)+now())[:24]+'.png'
                                await page.screenshot(path=str(folder/name),timeout=milliseconds(2000),animations='disabled')
                                result['screenshots'].append({'url':source['url'],'viewport':width,'path':'/site-reviews/'+name,'reliability':'CONFIRMED' if complete else 'UNVALIDATED'});diagnose('evidence','completed',begin)
                            except (InterruptedError,BudgetExceeded):raise
                            except Exception as exc:failure(exc,phase)
                result['links']=list(dict.fromkeys(result['links']));phase='evidence';begin=time.monotonic();phase_deadline=min(deadline,begin+phase_limits['evidence']/1000);diagnose('evidence','started',begin)
                paths=[]
                for row in result['pages']:
                    for key in ('contactLinks','offerLinks'):paths+=row['measurements'].get(key,[])
                for url in (list(dict.fromkeys(paths))[:max_pages] if advanced and requested=='DEEP' else []):
                    if skip_pdf(url) or urlsplit(url).netloc!=urlsplit(pages[0]['url']).netloc:continue
                    guard()
                    try:
                        p=originals[url] if url in originals else cache.get(url)
                        if p is None:p=await fetch(url,'path_check')
                        status=p['status'];result['path_checks'].append({'url':url,'status':status})
                        if status in (404,410):
                            kind='contact' if re.search(r'contatt|contact|preventiv',urlsplit(url).path,re.I) else 'offer'
                            result['findings'].append({'code':'broken_'+kind,'severity':'major','url':url,'quote':f'Destinazione collegata nel rendering: HTTP {status}.'})
                        elif status!=200:failures.add('Percorso non verificabile: HTTP '+str(status))
                    except (InterruptedError,BudgetExceeded):raise
                    except Exception as exc:failure(exc,phase,url)
                diagnose('evidence','completed' if not failures else 'partial',begin)
                result['completed']=not failures and bool(result['pages']) and all(p['complete'] for p in result['pages'])
            finally:
                phase='cleanup';begin=time.monotonic();diagnose('cleanup','started',begin);cancelled.set()
                for task in route_tasks|set(fetch_tasks.values()):
                    if not task.done():task.cancel()
                await asyncio.gather(*route_tasks,*fetch_tasks.values(),return_exceptions=True)
                try:
                    if context:await context.close()
                finally:
                    await browser.close();result['resources_closed']=True;diagnose('cleanup','completed',begin)
    except (InterruptedError,BudgetExceeded):raise
    except Exception as exc:failure(exc,phase)
    result['levels']['DOM']['status']='completed' if result['pages'] and all(p['complete'] for p in result['pages']) else 'partial' if result['pages'] else 'unavailable'
    if advanced:result['levels']['BROWSER_ADVANCED']['status']='completed' if result['completed'] else 'partial' if result['pages'] else 'unavailable'
    result['limits']=sorted(failures);result['completed']=bool(result['completed'] and not failures)
    result['resource_requests']=requests;result['resource_bytes']=total_bytes
    result['elapsed_ms']=round((time.monotonic()-started)*1000)
    codes=[d.get('code') for d in result['diagnostics'] if d.get('code') and d.get('affects_completion') is not False]
    result['failure_codes']=list(dict.fromkeys(codes))
    result['outcome']='completed' if result['completed'] else 'partial' if result['pages'] else next((c for c in codes if c in ('navigation_timeout','rendering_timeout','tls_error','robots')),'access_error')
    from .audit_policy import retain_independent_findings
    retain_independent_findings(result)
    if not result['completed']:result['findings']=[]
    finish(result,requested,capture)
    result['audit_state']=audit_state(result)
    return result


def _launch_worker(source, output, errors):
    """Own a new process group: a stuck renderer or DNS cannot own the worker."""
    return subprocess.Popen([sys.executable, '-m', 'sales.commercial.browser_worker'],
                            stdin=source, stdout=output, stderr=errors,
                            start_new_session=True, close_fds=True)


def _terminate_owned(proc, browser_pids=(), cleanup_seconds=.4):
    """Stop only this inspection's descendants, including Chromium's own group.

    Chromium may start a separate process group, so killing only the Python
    worker group is insufficient. Snapshot descendants before orphaning them.
    """
    owned={proc.pid};errors=[];cleanup_deadline=time.monotonic()+max(.01,cleanup_seconds)
    try:
        rows=subprocess.run(['/bin/ps','-axo','pid=,ppid='],capture_output=True,text=True,timeout=max(.01,min(.15,cleanup_seconds/3))).stdout
        pairs=[tuple(map(int,line.split())) for line in rows.splitlines() if len(line.split())==2]
        for _ in range(12):
            newer={pid for pid,ppid in pairs if ppid in owned}
            if newer<=owned:break
            owned|=newer
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    # CDP supplied PIDs are corroborated descendants, never arbitrary input.
    owned|={int(pid) for pid in browser_pids if int(pid)>1}
    for pid in sorted(owned,reverse=True):
        if pid==os.getpid():continue
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass
        except OSError as exc:errors.append({'pid':pid,'operation':'kill','error':str(exc)})
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    except OSError as exc:errors.append({'pid':proc.pid,'operation':'killpg','error':str(exc)})
    try:proc.wait(timeout=max(.001,min(.1,cleanup_deadline-time.monotonic())))
    except subprocess.TimeoutExpired:pass
    def alive(pid):
        try:os.kill(pid,0);return True
        except ProcessLookupError:return False
        except PermissionError:return True  # unknown is never reported as gone
    remaining=sorted(pid for pid in owned if alive(pid))
    while remaining and time.monotonic()<cleanup_deadline:
        time.sleep(min(.01,max(.001,cleanup_deadline-time.monotonic())))
        proc.poll();remaining=[pid for pid in remaining if alive(pid)]
    return proc.poll() is not None and not remaining, sorted(owned), {'signal_errors':errors,'remaining_pids':remaining}



def review(store,pages,check=lambda:None,max_pages=3,capture=True,limits=None):
    """Bounded public entrypoint. No credentials, config mutation or AI in child.

    The supervisor owns the time budget, cancellation and browser reservation.
    The subprocess reinstalls the same persisted resource ledger for HTTP reads.
    Incremental checkpoints retain trustworthy DOM if teardown is forced.
    """
    from .resources import _context
    check()
    for page in pages:require_non_pdf(page)
    limits=dict(limits or {});started=time.monotonic()
    total=max(.001,float(timeout(limits.get('browser_total_seconds',120))))
    cleanup=min(.8,max(.4,total*.2));deadline=started+total;work_deadline=deadline-cleanup
    budget=_context.get()
    payload={'store':str(store.path),'pages':pages,'max_pages':max_pages,'capture':capture,
             'limits':{**limits,'browser_total_seconds':max(.01,total-cleanup)},
             'deadline':work_deadline,
             'budget':({'cid':budget.cid,'generation':budget.generation,'engine':budget.engine,
                        'limits':budget.limits,'task_id':getattr(budget,'task_id',None),'deadline':getattr(budget,'deadline',work_deadline)} if budget else None)}
    result={'completed':False,'outcome':'access_error','findings':[],'links':[],'pages':[],
            'screenshots':[],'limits':[],'diagnostics':[],'path_checks':[],
            'resources_closed':False,'levels':{'HTTP':{'status':'available','pages':len(pages)},
            'DOM':{'status':'unavailable'},'BROWSER_ADVANCED':{'status':'unavailable'}}}
    if total<=cleanup+.05:
        result.update(outcome='inspection_timeout',termination_reason='insufficient_time',resources_closed=True,
                      worker_reaped=True,total_limit_ms=round(total*1000),elapsed_ms=round((time.monotonic()-started)*1000),
                      limits=['Tempo residuo insufficiente per avvio e chiusura sicuri: browser non avviato.'])
        result['audit_state']=audit_state(result)
        return result
    if budget:budget.browser_slot()
    else:reserve('browser_runs')
    proc=None;complete_message=False;reason=None;pending_error=None;observed=[]
    with tempfile.TemporaryDirectory(prefix='customersearch-browser-') as folder:
        source_path=Path(folder)/'input.json';source_path.write_text(json.dumps(payload))
        with source_path.open('rb') as source,(Path(folder)/'events').open('wb') as output,(Path(folder)/'events').open('rb') as events,(Path(folder)/'stderr').open('w+b') as errors:
            proc=_launch_worker(source,output,errors)
            position=0;buffer=b''
            def receive():
                nonlocal result,position,buffer,complete_message,pending_error
                events.seek(position);chunk=events.read();position+=len(chunk);buffer+=chunk
                lines=buffer.split(b'\n');buffer=lines.pop()
                for line in lines:
                    if not line:continue
                    try:message=json.loads(line)
                    except (ValueError,UnicodeError):continue
                    if message.get('type') in ('checkpoint','result'):result=message['result']
                    if message.get('type')=='result':complete_message=True
                    if message.get('type')=='error':
                        pending_error=BudgetExceeded(message['resource']) if message.get('resource') else InterruptedError(message.get('message','Controllo interrotto'))
            try:
                while True:
                    check();receive()
                    if proc.poll() is not None:receive();break
                    if time.monotonic()>=work_deadline:reason='inspection_timeout';break
                    for marker in ('active_resource','active_phase'):
                        active=result.get(marker,{})
                        # Socket timeout and supervisor otherwise race at exactly
                        # the same instant. Allow the resource handler to record
                        # its failure and abort the route; the enclosing phase
                        # and overall hard deadlines still apply without grace.
                        grace=.25  # allow the awaited timeout to checkpoint; total deadline is unchanged
                        if active and time.monotonic()>=active['started_at']+active['limit_ms']/1000+grace:
                            reason=error_code(TimeoutError(),active['name']);break
                    if reason:break
                    time.sleep(min(.025,max(.001,work_deadline-time.monotonic())))
            except (InterruptedError,BudgetExceeded) as exc:reason='cancelled';pending_error=exc
            finally:
                cleanup_started=time.monotonic()
                if proc.poll() is None or not result.get('resources_closed'):
                    reaped,observed,cleanup_details=_terminate_owned(proc,[*result.get('owned_browser_pids',()),*([result['owned_driver_pid']] if result.get('owned_driver_pid') else [])],min(cleanup,max(.01,deadline-time.monotonic())))
                    # Kill may have followed a checkpoint; keep its evidence, never claims.
                    receive()
                    result['forced_cleanup']=True
                    result['resources_closed']=reaped
                    result['diagnostics'].append({'phase':'cleanup','status':'completed' if reaped else 'incomplete',
                        'elapsed_ms':round((time.monotonic()-cleanup_started)*1000),'limit_ms':round(cleanup*1000),
                        'error':None if reaped else 'Risorse non confermate chiuse','forced':True,**cleanup_details})
                result['worker_reaped']=proc.poll() is not None
                result['owned_process_ids']=observed
            if budget:budget.browser_finished(isinstance(pending_error,InterruptedError) and result.get('resources_closed',False))
            if pending_error:raise pending_error
    if not result.get('resources_closed') or not result.get('worker_reaped'):
        reason='cleanup_error'
    if reason or not complete_message:
        from .audit_policy import retain_independent_findings
        retain_independent_findings(result)
        result['completed']=False;result['findings']=[]
        result['termination_reason']=reason or 'worker_exit'
        result.setdefault('failure_codes',[]).append(reason or 'worker_exit')
        result['outcome']='partial' if result.get('pages') else reason or 'access_error'
        result.setdefault('limits',[]).append('Ispezione interrotta al limite temporale della fase o del controllo; nessun difetto del sito dedotto.' if reason else 'Processo browser terminato senza una valutazione completa.')
        result.setdefault('diagnostics',[]).append({'phase':'inspection','status':'incomplete','code':reason or 'worker_exit',
            'elapsed_ms':round((time.monotonic()-started)*1000),'limit_ms':round(total*1000),'error':result['limits'][-1]})
        result['levels']['DOM']['status']='partial' if result.get('pages') else 'unavailable'
        result['levels']['BROWSER_ADVANCED']['status']=('partial' if result.get('pages') else 'unavailable') if limits.get('browser_advanced',True) else 'not_requested'
    result['elapsed_ms']=round((time.monotonic()-started)*1000)
    result['total_limit_ms']=round(total*1000)
    result['inspection_level']='BROWSER_ADVANCED' if limits.get('browser_advanced',True) else 'DOM'
    from .audit_policy import finish
    finish(result,limits.get('browser_audit_level','DEEP'),capture)
    result['audit_state']=audit_state(result)
    return result
