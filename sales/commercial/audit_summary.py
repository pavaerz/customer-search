"""Describe retained browser observations without certifying partial rendering."""
def coverage(browser):
    rows=[]
    for page in browser.get('pages',[]):
        m=page.get('measurements') or {};observed=[]
        if m.get('text_excerpt'):observed.append('Testo DOM acquisito')
        if m.get('visible_content'):observed.append('Contenuto visibile osservato')
        if m.get('fonts_loaded'):observed.append('Font caricati al momento della misura')
        if page.get('complete'):observed.append('Verifica rendering del viewport completata')
        rows.append({'url':page.get('url'),'viewport':page.get('viewport'),
                     'observed':observed,'rendering_verified':bool(page.get('complete')),
                     'missing':[] if page.get('complete') else ['Rendering stabile e dipendenze non completamente verificati']})
    return {'completed':bool(browser.get('completed')),'viewports':rows,
            'failure_codes':browser.get('failure_codes',[]),
            'limits':browser.get('limits',[]),
            'missing':[] if browser.get('completed') else ['Audit complessivo non completato; nessun difetto deducibile dagli errori'],
            'resource_requests':browser.get('resource_requests'),
            'document_reused':any(d.get('wait_until')=='reuse_pending_document' for d in browser.get('diagnostics',[]))}
