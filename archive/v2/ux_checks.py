"""Conservative layout signals, not an aesthetic rating or accessibility certification."""
MEASURE = r'''() => {
 const visible = e => {const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)>0;};
 const scale = Math.min(1,window.visualViewport?.scale || 1);
 const blocks = [...document.querySelectorAll('main p, article p, main li, body p')].filter(e=>visible(e)&&!e.closest('footer,nav,[role=dialog]')&&e.innerText.trim().length>=40);
 const small = blocks.filter(e=>parseFloat(getComputedStyle(e).fontSize)*scale<14);
 const links = [...document.querySelectorAll('header a,nav a,header button,nav button')].filter(e=>visible(e)&&e.innerText.trim());
 const smallTargets=links.filter(e=>{const r=e.getBoundingClientRect();return r.width*scale<24&&r.height*scale<24;});
 const d=document.documentElement;
 const overflow = ['hidden','clip'].includes(getComputedStyle(d).overflowX)||['hidden','clip'].includes(getComputedStyle(document.body).overflowX)?0:d.scrollWidth-d.clientWidth;
 const clipped = blocks.filter(e=>{const r=e.getBoundingClientRect();return r.right>d.clientWidth+20||r.left < -20;});
 return {scale, layoutWidth:d.clientWidth, viewportWidth:(window.visualViewport?.width || d.clientWidth)*scale, textChars:document.body.innerText.trim().length, overflow, clipped:clipped.length, small:small.length, smallChars:small.reduce((n,e)=>n+e.innerText.length,0), blocks:blocks.length,
 targets:smallTargets.length, nav:links.length, samples:small.slice(0,2).map(e=>e.innerText.trim().slice(0,100))};
}'''


def evaluate_pair(first, second, device, incomplete=False):
    if incomplete:
        return []
    findings = []
    if all(m.get('viewportWidth', 9999) <= 450 and m.get('layoutWidth', 0) >= 700
           and m.get('scale', 1) < .7 and m.get('textChars', 0) >= 200
           for m in (first, second)):
        findings.append({'code':'desktop_scaled_mobile', 'text':f'{device}: il browser riduce una pagina larga almeno 700 px per farla entrare sul telefono. I contenuti vengono rimpiccioliti invece di adattarsi alla larghezza disponibile.', 'severity':3})
    if min(first['overflow'], second['overflow']) > 20 and min(first['clipped'], second['clipped']) >= 1:
        findings.append({'code':'text_overflow', 'text':f'{device}: alcuni blocchi di testo superano il bordo dello schermo, rendendo più scomoda la lettura.', 'severity':3})
    if min(first['targets'], second['targets']) >= 4:
        findings.append({'code':'small_navigation', 'text':f'{device}: almeno quattro collegamenti del menu hanno un’area molto piccola nel controllo. È un indizio da verificare nell’uso del menu.', 'severity':1})
    return findings


def qualifies(findings):
    # One repeated, concrete reading problem is enough; tiny menu targets alone are not.
    codes = {f['code'] for f in findings}
    return bool({'text_overflow','desktop_scaled_mobile'} & codes)
