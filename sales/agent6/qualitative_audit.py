"""Bounded HTML observations: assess sampled content/paths, never invent aesthetics."""
from collections import defaultdict
import re
from urllib.parse import urljoin, urlsplit
from sales.extract import Document
from sales.db import digest
from .source_access import inspect


def observations(pages):
    out = []
    for page in pages:
        if page.get('purpose') == 'external_solution' or not inspect(page)['content_read']:
            continue
        doc = Document(page.get('html', ''))
        text = doc.text
        def add(code, kind, dimension, value, explanation):
            out.append({'id': digest(str([page['url'], code, value]))[:24], 'code': code,
                'status': 'ASSESSMENT', 'severity': 'major', 'dimension': dimension,
                'observation_type': kind, 'certainty': 'GROUNDED_ASSESSMENT',
                'measurement_status': 'OBSERVED', 'journey': 'commercial_navigation',
                'evidence': {'url': page['url'], 'checked_at': page.get('checked_at'),
                    'content_hash': digest(page.get('html', '')), 'method': 'sampled_html_structure',
                    'value': value},
                'impact': explanation, 'action': 'Valutare una nuova architettura dei contenuti e dei percorsi; non prova una richiesta di acquisto.'})
        offers = list(re.finditer(r'\b(?:servizi|prodotti|lavorazioni|soluzioni|services|products)\b', text, re.I))
        # More than a missing H1: a long offering document without any section
        # headings. The scope is the acquired HTML, not the rendered whole site.
        if len(text) >= 1800 and len(offers) >= 3 and len(doc.headings) <= 1:
            add('undifferentiated_offering', 'CONTENT_ASSESSMENT', 'CONTENT_AND_STRUCTURE',
                {'characters': len(text), 'headings': doc.headings,
                 'excerpts': [text[max(0,m.start()-45):m.end()+90] for m in offers[:3]]},
                'Nel documento acquisito la presentazione estesa dell’offerta non è suddivisa in sezioni con titoli: servizi e prodotti risultano difficili da distinguere nella struttura dei contenuti.')
        targets = defaultdict(set)
        for link in doc.links:
            label = ' '.join(link['text'].lower().split())
            url = urljoin(page['url'], link['url'])
            if urlsplit(url).scheme in ('http', 'https') and re.fullmatch(r'scopri|scopri di più|leggi|leggi tutto|clicca qui|read more|learn more', label):
                targets[label].add(url)
        ambiguous = {k: sorted(v) for k,v in targets.items() if len(v) >= 4}
        if ambiguous:
            add('indistinguishable_navigation', 'OBSERVED_UX_ISSUE', 'NAVIGATION',
                {'link_labels_and_destinations': ambiguous},
                'Almeno quattro destinazioni hanno lo stesso testo di collegamento generico. Le etichette, lette isolatamente, non permettono di distinguere il percorso verso i diversi contenuti.')
    return out


def design_observations(pages, browser):
    """A narrow design assessment grounded in rendered computed styles.

    Equal styles do not prove illegibility: spacing and other visual cues may
    distinguish sections. This observation alone cannot justify a full project.
    """
    out=[]
    for row in (browser or {}).get('pages',[]):
        if not row.get('complete') or row.get('scope')!='rendered':
            continue
        page=next((p for p in pages if p['url']==row['url'] and p.get('purpose')!='external_solution'),None)
        styles=row.get('measurements',{}).get('typography',{})
        headings=styles.get('headings',[]);paragraphs=styles.get('paragraphs',[])
        if not page or not headings or not paragraphs:
            continue
        same=[h for h in headings if h.get('text') and h.get('font_size') and any(
            p.get('font_size') and abs(h['font_size']-p['font_size'])<.5
            and h.get('font_weight')==p.get('font_weight') and h.get('color')==p.get('color')
            for p in paragraphs)]
        if not same:
            continue
        value={'headings':same,'paragraphs':paragraphs,'viewport':row.get('viewport')}
        out.append({'id':digest(str([row['url'],'typographic_hierarchy',value]))[:24],
            'code':'typographic_hierarchy','status':'ASSESSMENT','severity':'moderate','dimension':'VISUAL_HIERARCHY',
            'observation_type':'DESIGN_ASSESSMENT','certainty':'GROUNDED_ASSESSMENT','measurement_status':'OBSERVED',
            'journey':'content_hierarchy','evidence':{'url':row['url'],'checked_at':row.get('checked_at') or page.get('checked_at'),
                'content_hash':digest(page.get('html','')),'method':'browser_computed_styles','value':value},
            'impact':'Nel viewport misurato alcuni titoli hanno dimensione, peso e colore uguali al testo. La gerarchia tipografica è poco differenziata; spaziatura e altre indicazioni visive vanno considerate separatamente.',
            'action':'Valutazione qualitativa della gerarchia; non dimostra da sola la necessità di un rifacimento completo.'})
    return out
