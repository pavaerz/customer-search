"""Bounded render analysis. All page traffic uses the public-IP-pinned fetcher."""
import asyncio
import json
import hashlib
from datetime import datetime
from urllib.parse import urlsplit, urljoin
from zoneinfo import ZoneInfo
from ux_checks import MEASURE, evaluate_pair, qualifies

TRACKERS = ('google-analytics.com', 'googletagmanager.com', 'doubleclick.net', 'connect.facebook.net')


def tracker_url(url):
    host = (urlsplit(url).hostname or '').lower()
    return any(host == domain or host.endswith('.' + domain) for domain in TRACKERS)


def optional_request(req):
    if req.resource_type == 'media' or urlsplit(req.url).path.lower() == '/favicon.ico':
        return True
    if tracker_url(req.url):
        return True
    parsed = urlsplit(req.url)
    host = (parsed.hostname or '').lower()
    # CAPTCHA background calls do not validate the site's text layout.
    # Do not execute them or treat their absence as evidence about form usability.
    return (req.method == 'POST'
            and host in ('www.google.com', 'www.recaptcha.net')
            and parsed.path in ('/recaptcha/api2/reload', '/recaptcha/api2/clr',
                                '/recaptcha/enterprise/reload', '/recaptcha/enterprise/clr'))


def incomplete_result(reason):
    return {'kind':'Usabilità · layout', 'qualifies':False, 'incomplete':True,
            'ux_findings':[], 'incomplete_reasons':[reason]}


def review_mobile(url, html, data_dir, fetch, check_stop, capture=False):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return incomplete_result('Browser non disponibile')

    async def run():
        state = {'requests':0, 'bytes':0, 'pending':0, 'failures':set()}
        slots = asyncio.Semaphore(4)
        cache = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel='chrome', headless=True)
            try:
                context = await browser.new_context(viewport={'width':390, 'height':780}, device_scale_factor=1,
                    is_mobile=True, has_touch=True, service_workers='block', accept_downloads=False)
                await context.route_web_socket('**/*', lambda ws: ws.close())
                async def route_request(route):
                    req=route.request
                    check_stop()
                    if optional_request(req):
                        return await route.abort()
                    if req.method != 'GET':
                        state['failures'].add('Richiesta dinamica non eseguita')
                        return await route.abort()
                    state['pending'] += 1
                    try:
                        if req.url == url and req.resource_type == 'document':
                            return await route.fulfill(status=200, body=html, content_type='text/html; charset=utf-8')
                        async with slots:
                            check_stop()
                            if req.url not in cache:
                                if state['requests'] >= 150 or state['bytes'] > 20_000_000:
                                    state['failures'].add('Budget di caricamento raggiunto')
                                    return await route.abort()
                                state['requests'] += 1
                                cache[req.url] = await asyncio.to_thread(fetch, req.url)
                                state['bytes'] += len(cache[req.url][1])
                            code, raw, mime, final = cache[req.url]
                        if code != 200:
                            state['failures'].add('Risorsa non disponibile')
                        if final != req.url:
                            cache[final]=(code,raw,mime,final)
                            # Importing the validated final stylesheet creates a new routed
                            # request (native redirect hops can bypass Playwright routing).
                            if req.resource_type == 'stylesheet':
                                return await route.fulfill(status=200, content_type='text/css',
                                                           body='@import url(' + json.dumps(final) + ');')
                            if req.resource_type in ('script','document') and urljoin(final,'.') != urljoin(req.url,'.'):
                                state['failures'].add('Redirect con percorso delle risorse differente')
                        await route.fulfill(status=code,body=raw,headers={'Content-Type':mime})
                    except Exception:
                        state['failures'].add('Risorsa non caricata')
                        await route.abort()
                    finally:
                        state['pending'] -= 1
                await context.route('**/*', route_request)
                page=await context.new_page()
                page.on('requestfailed', lambda req: state['failures'].add('Risorsa rifiutata dal browser') if not optional_request(req) else None)
                page.on('dialog', lambda dialog: dialog.dismiss())
                await page.goto(url,wait_until='domcontentloaded',timeout=0)
                async def settle():
                    quiet = 0
                    while quiet < 3:
                        check_stop()
                        await page.wait_for_timeout(200)
                        quiet = quiet + 1 if state['pending'] == 0 else 0
                await settle()
                if len((await page.locator('body').inner_text(timeout=2000)).strip())<40:
                    return incomplete_result('Contenuto della pagina insufficiente')
                findings=[]
                screenshots=[]
                capture_id=hashlib.sha256((url+datetime.now(ZoneInfo('Europe/Rome')).isoformat()).encode()).hexdigest()[:24]
                structure=[]
                for width,device in ((390,'Telefono (390 px)'),(1366,'Schermo ampio (1366 px)')):
                    await page.set_viewport_size({'width':width,'height':780})
                    await settle()
                    if capture:
                        folder=data_dir / 'site-reviews'
                        folder.mkdir(parents=True,exist_ok=True)
                        name=capture_id + f'-{width}.png'
                        await page.screenshot(path=str(folder / name), full_page=False, timeout=0)
                        screenshots.append({'width':width,'path':'/site-reviews/'+name})
                        structure.append(await page.evaluate("""() => ({width:innerWidth,
                            headings:[...document.querySelectorAll('h1,h2,h3')].filter(e=>e.getBoundingClientRect().height>0).slice(0,15).map(e=>({tag:e.tagName,text:e.innerText.trim(),size:getComputedStyle(e).fontSize})),
                            actions:[...document.querySelectorAll('a,button')].filter(e=>{let r=e.getBoundingClientRect();return r.height>0&&r.top>=0&&r.top<innerHeight&&/contatt|preventiv|richied|scopri|servizi|prodott/i.test(e.innerText)}).slice(0,12).map(e=>e.innerText.trim())})"""))
                    first=await page.evaluate(MEASURE)
                    await page.wait_for_timeout(400)
                    second=await page.evaluate(MEASURE)
                    findings.extend(evaluate_pair(first,second,device,bool(state['failures'])))
                if state['pending']:
                    state['failures'].add('Risorse ancora in caricamento')
                incomplete=bool(state['failures'])
                if incomplete: findings=[]
                return {'kind':'Usabilità · layout', 'text':' '.join(f['text'] for f in findings) or ('Controllo incompleto: non è un giudizio sul sito.' if incomplete else 'Nessun problema di layout sufficiente confermato.'),
                    'screenshots':screenshots,'structure':structure,
                    'source':url,'ux_findings':findings,'qualifies':qualifies(findings),'incomplete':incomplete,
                    'incomplete_reasons':sorted(state['failures']), 'resource_requests':state['requests'],
                    'method':'Misure di layout nel browser; stile grafico da valutare manualmente.',
                    'checked_at':datetime.now(ZoneInfo('Europe/Rome')).isoformat()}
            finally:
                await browser.close()
    try:
        return asyncio.run(run())
    except Exception as exc:
        check_stop()
        return incomplete_result('Tempo di caricamento esaurito' if type(exc).__name__ == 'TimeoutError' else 'Errore del browser')
