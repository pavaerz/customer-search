'use strict';
let state = null;
let view = 'draft';
let demo = false;
let filter = '';
let outcomeFilter = '';
const outcomeLabels = {awaiting:'In attesa', replied:'Ha risposto', interested:'Interessato', declined:'Non interessato', customer:'Cliente', do_not_contact:'Non ricontattare'};
let lastFingerprint = '';
let toastTimer;
const editing = new Set();
const $ = (selector) => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = url => /^https?:\/\//i.test(url) ? escapeHtml(url) : '#';

function toast(message, error = false) {
  $('#toast').textContent = message;
  $('#toast').className = 'toast' + (error ? ' error' : '');
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, error ? 10000 : 5000);
}

async function api(path, body = {}) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json', 'X-CSRF-Token':state.csrf}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Operazione non completata.');
  return result;
}

const demoLead = {
  id:'demo', name:'Laboratorio Esempio · Scheda dimostrativa', domain:'esempio.invalid', url:'https://esempio.invalid', email:'info@esempio.invalid', email_source:'https://esempio.invalid/contatti',
  status:'draft', findings:[{kind:'Esempio di osservazione', text:'Qui comparirà un problema rilevato sul sito, con il link alla pagina controllata. Questo è un esempio, non un sito analizzato.', source:'https://esempio.invalid'}],
  subject:'Un’osservazione sul vostro sito', body:'Buongiorno,\n\nsono Diego Pavanello e realizzo siti web.\n\nQui troverai un testo personalizzato con le osservazioni raccolte durante la visita al sito. Potrai modificarlo prima di inviarlo.\n\nVi va di parlarne?\n\nDiego Pavanello\nhttps://designerdimontagna.it\nFront-end-Designer', error:''
};

function emailPreview(body) {
  const website = state?.settings?.website || '';
  const label = website.replace(/^https?:\/\//i, '').replace(/\/$/, '');
  return body.split('\n').map(line => website && /^https?:\/\//i.test(website) && [website, label].includes(line.trim())
    ? `<strong><a href="${safeUrl(website)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a></strong>`
    : line.trim() === `Vi lascio il mio sito: ${label}` && website ? `Vi lascio il mio sito: <a href="${safeUrl(website)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>` : escapeHtml(line)).join('\n');
}

function financePanel(lead) {
  const f = lead.finance;
  const record = f?.record;
  return `<h4>AZIENDA E DATI ECONOMICI</h4><p>${lead.vat ? 'P. IVA rilevata nel sito: ' + escapeHtml(lead.vat) : 'Partita IVA ancora da verificare'}</p>${record ? `<p><strong>Utile netto ${record.year}: ${new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(record.amount_eur)}</strong></p><a href="${safeUrl(record.source)}" target="_blank" rel="noopener noreferrer">${escapeHtml(record.source_type)} ↗</a><p>${escapeHtml(record.evidence)}</p>` : ''}<p>${escapeHtml(f?.message || 'Nessun dato economico verificato. La ricerca usa le quote dei motori già configurati; non acquista bilanci.')}</p><button class="secondary" data-action="finance" ${demo ? 'disabled' : ''}>${f ? 'Ricontrolla dati economici' : 'Cerca utile pubblico'}</button>`;
}

function auditPanel(lead) {
  const audit=lead.site_audit;
  const metricNames={'largest-contentful-paint':'LCP · contenuto principale','cumulative-layout-shift':'CLS · stabilità visiva','total-blocking-time':'TBT · blocco del browser','first-contentful-paint':'FCP · primo contenuto','speed-index':'Speed Index'};
  const scoreNames={performance:'Prestazioni',accessibility:'Accessibilità',seo:'SEO', 'best-practices':'Buone pratiche'};
  const result = !audit?.checked_at ? '<p>Analisi non ancora eseguita.</p>' : `
    <p>Controllato il ${escapeHtml(new Date(audit.checked_at).toLocaleString('it-IT'))} · homepage</p>
    <h4>PAGESPEED / LIGHTHOUSE</h4>${audit.pagespeed_service?.some(p=>p.status==='unavailable')?'<p>Servizio Google PageSpeed non disponibile per questo test. Gli eventuali punteggi sotto provengono da Lighthouse locale.</p>':''}
    ${(audit.pagespeed || []).map(p=>`<div class="finding"><strong>${p.strategy==='mobile'?'Mobile':'Desktop'} · ${escapeHtml(p.source || 'Google PageSpeed')}</strong>${p.status==='ok'?`<div class="audit-scores">${Object.entries(p.scores).map(([k,v])=>`<span class="${v>=90?'score-good':v>=50?'score-warn':'score-poor'}"><b>${v}/100</b> ${escapeHtml(scoreNames[k] || k)} · ${v>=90?'buono':v>=50?'da migliorare':'scarso'}</span>`).join('')}</div><p>${Object.entries(p.metrics).map(([k,v])=>`${escapeHtml(metricNames[k] || k)}: ${escapeHtml(v)}`).join(' · ')}</p><p>${p.fetch_time?'Test del '+escapeHtml(new Date(p.fetch_time).toLocaleString('it-IT'))+'. ':''}${escapeHtml(p.note)}</p>${p.issues.map(i=>`<p>• ${escapeHtml(i.title)} ${escapeHtml(i.detail)}</p>`).join('')}<a href="${safeUrl(p.report_url?.startsWith('/site-reviews/') ? location.origin+p.report_url : p.report_url)}" target="_blank" rel="noopener noreferrer">${p.source==='Lighthouse locale'?'Apri report Lighthouse JSON':'Apri PageSpeed'} ↗</a>`:`<p>${escapeHtml(p.message)}</p>`}</div>`).join('')}
    <h4>SEO · RISCONTRI TECNICI</h4><p>${escapeHtml(audit.seo?.scope)}</p>
    ${(audit.seo?.checks || []).map(c=>`<div class="finding"><strong>${escapeHtml(c.label)} · ${escapeHtml(c.status)}</strong><p>${escapeHtml(c.detail)}</p></div>`).join('')}
    <h4>GEO / AEO · CONTENUTI PER I MOTORI AI</h4>${audit.seo?.geo_aeo?.coverage?`<p><strong>${audit.seo.geo_aeo.coverage.present}/${audit.seo.geo_aeo.coverage.total} segnali tecnici presenti</strong> · ${escapeHtml(audit.seo.geo_aeo.coverage.label)}</p>${audit.seo.geo_aeo.content_checks.map(c=>`<p>${c.present?'✓':'—'} ${escapeHtml(c.label)}</p>`).join('')}`:''}<p>${escapeHtml(audit.seo?.geo_aeo?.summary)}</p>
    <p>Tipi di dati strutturati JSON-LD: ${escapeHtml(audit.seo?.geo_aeo?.structured_types?.join(', ') || 'nessuno rilevato')}. Blocchi JSON-LD non validi: ${audit.seo?.geo_aeo?.invalid_jsonld || 0}.</p>
    <p>${escapeHtml(audit.seo?.geo_aeo?.note)}</p>`;
  return `<section class="audit-panel"><h3>Valutazione del sito</h3>${result}<button class="secondary" data-action="audit" ${demo?'disabled':''}>${audit?.checked_at?'Aggiorna analisi (cache 1 ora)':'Analizza SEO, GEO/AEO e Lighthouse'}</button></section>`;
}

function card(lead) {
  const sent = lead.status === 'sent';
  const labels = {draft:'Da rivedere', sent:'Inviata', sending:'Invio in corso', uncertain:'Da verificare in Gmail', gmail_pending:'Invio da confermare'};
  const editable = lead.status === 'draft';
  const reason = lead.selection_reason || 'In attesa di una selezione basata sui punteggi SEO / Lighthouse.';
  const reasonTitle = lead.needs_review || !lead.selection_reason ? 'Analisi tecnica da aggiornare' : 'Selezionata per i punteggi SEO / Lighthouse';
  return `<details class="lead" data-id="${lead.id}"><summary><span class="site-avatar">${escapeHtml(lead.domain.slice(0,2).toUpperCase())}</span><span class="lead-title"><strong>${escapeHtml(lead.name)}</strong><small>${escapeHtml(lead.domain)} · ${lead.findings.length} osservazion${lead.findings.length === 1 ? 'e' : 'i'}</small><span class="selection-preview"><b>${escapeHtml(reasonTitle)}</b> · ${escapeHtml(reason)}</span></span><span class="tag ${sent ? 'sent' : ''}">${lead.status === 'draft' && lead.needs_review ? 'Da valutare' : labels[lead.status] || 'Da verificare'}</span><span class="chevron">⌄</span></summary><section class="selection-panel"><span class="selection-kicker">PERCHÉ QUESTA AZIENDA</span><h3>${escapeHtml(reasonTitle)}</h3><p>${escapeHtml(reason)}</p><a href="${safeUrl(lead.url)}" target="_blank" rel="noopener noreferrer">Apri il sito dell’azienda ↗</a></section><div class="lead-detail"><div class="email-panel"><div class="email-view">${editable ? '<button class="editor-open" data-action="edit">✎ Apri l’editor e scrivi il tuo messaggio</button>' : ''}<div class="email-meta">A <a href="mailto:${escapeHtml(lead.email)}">${escapeHtml(lead.email)}</a></div><h3 class="subject">${escapeHtml(lead.subject)}</h3><pre class="email-body">${emailPreview(lead.body)}</pre></div><div class="edit-container"></div>${sent ? `<div class="outcome-panel"><strong>${escapeHtml(outcomeLabels[lead.outcome] || "Esito non registrato")}</strong>${lead.outcome_note ? `<p>${escapeHtml(lead.outcome_note)}</p>` : ""}<button class="secondary" data-action="outcome-edit">Aggiorna esito</button></div>` : ""}${lead.error ? `<p class="error-note">${escapeHtml(lead.error)}</p>` : ''}<div class="email-actions">${editable ? `<button class="delete" data-action="delete">Elimina</button><button class="secondary" data-action="edit">✎ Modifica email</button><button class="primary" data-action="send" ${demo ? 'disabled' : ''}>Apri in Gmail ↗</button>` : lead.status === 'gmail_pending' ? `<span class="field-note">Completa l’invio in Gmail, poi conferma qui. Controlla la posta inviata prima di qualsiasi nuovo invio.</span><button class="primary" data-action="confirm">Ho inviato da Gmail</button>` : `<span class="field-note">${sent ? 'Inviata da pavanello93@gmail.com · ' + escapeHtml(new Date(lead.sent_at).toLocaleString('it-IT')) : 'Invio bloccato per evitare messaggi duplicati.'}</span>`}</div></div><aside class="evidence"><h4>CONTENUTI LETTI SUL SITO</h4>${(lead.context || []).length ? (lead.context || []).map(c => `<div class="finding"><strong>${escapeHtml(c.text)}</strong><p><a href="${safeUrl(c.source)}" target="_blank" rel="noopener noreferrer">Pagina di origine ↗</a></p></div>`).join('') : '<p>Per questa scheda sono disponibili solo il titolo e i controlli già salvati.</p>'}${lead.findings.map(f => `<div class="finding"><strong>${escapeHtml(f.kind)}</strong><p>${escapeHtml(f.text)}</p><a href="${safeUrl(f.source)}" target="_blank" rel="noopener noreferrer">Apri la pagina ↗</a>${f.checked_at ? `<p>Verificato il ${escapeHtml(new Date(f.checked_at).toLocaleString('it-IT'))}</p>` : ''}</div>`).join('')}${auditPanel(lead)}${financePanel(lead)}<h4>CONTATTO PUBBLICO</h4><a href="${safeUrl(lead.email_source)}" target="_blank" rel="noopener noreferrer">Pagina dove è stata trovata l’email ↗</a><p>Controlli sulle pagine pubbliche e, quando disponibile, controllo a larghezza smartphone. I caricamenti parziali richiedono una verifica manuale.</p><p>L’email pubblica non equivale al consenso alle comunicazioni commerciali.</p></aside></div></details>`;
}

function renderQuotas(providers) {
  if (!providers) return null;
  const local = providers.searxng || {configured:false};
  const t = providers.tavily;
  const s = providers.serper;
  const tLeft = Math.max(0, 930 - t.month);
  const sLeft = Math.max(0, 2400 - s.total);
  const available = (t.configured ? Math.max(0, Math.min(30 - t.today, tLeft)) : 0)
    + (s.configured ? Math.max(0, Math.min(100 - s.today, sLeft)) : 0);
  const number = value => value.toLocaleString('it-IT');
  const bar = (id, used, total) => {
    const el = $(id);
    el.max = total;
    el.value = Math.min(total, Math.max(0, used));
    el.classList.toggle('quota-exhausted', used >= total);
    el.setAttribute('aria-valuetext', `${number(used)} utilizzate su ${number(total)}`);
  };
  $('#searches-today').textContent = number((local.today || 0) + t.today + s.today);
  $('#searxng-day-count').textContent = local.configured ? `${number(local.today || 0)} effettuate · ${local.status || ''}` : 'Non collegato';
  $('#searches-reserve').textContent = `${number(available)} richieste API ancora disponibili oggi${local.configured ? ' · SearXNG senza crediti API' : ''}`;
  $('#tavily-day-count').textContent = t.configured ? `${t.today} / 30 usate` : 'Non collegato';
  $('#serper-day-count').textContent = s.configured ? `${s.today} / 100 usate` : 'Non collegato';
  bar('#tavily-day-progress', t.today, 30);
  bar('#serper-day-progress', s.today, 100);
  $('#quota-day-note').textContent = available === 0 ? (local.configured ? 'Quote API esaurite; puoi continuare con SearXNG locale.' : state.search_configured ? 'Quota disponibile esaurita. Controlla i budget dei motori.' : 'Collega un motore dalle impostazioni per iniziare.')
    : 'Barre = richieste usate. Ogni richiesta può trovare più siti.';
  if (local.configured && !state.settings.allow_api_fallback) {
    $('#searches-reserve').textContent = 'Solo SearXNG · Tavily e Serper disattivati per le nuove ricerche';
    $('#quota-day-note').textContent = 'I contatori includono le richieste precedenti di oggi. Docker deve essere aperto.';
  }
  return local.configured ? null : available;
}

function render(force = false) {
  if (!state) return;
  const drafts = state.leads.filter(l => l.status !== 'sent');
  const sent = state.leads.filter(l => l.status === 'sent');
  const searchesLeft = renderQuotas(state.search_providers);
  $('#draft-count').textContent = drafts.filter(l => l.status === 'draft').length;
  $('#sent-count').textContent = sent.length;
  $('#outcome-filter-label').hidden = view !== 'sent';
  const responses = sent.filter(l => ['replied','interested','declined','customer'].includes(l.outcome)).length;
  $('#outcome-summary').textContent = `${sent.length} invii registrati · ${responses} risposte segnalate · ${sent.filter(l=>l.outcome==='interested').length} interessati · ${sent.filter(l=>l.outcome==='customer').length} clienti. Esiti aggiornati da te, senza lettura automatica di Gmail.`;
  $('#nav-count').textContent = drafts.length;
  $('#gmail-status').textContent = state.gmail.connected ? 'Gmail collegato' : 'Gmail da collegare';
  $('#gmail-dot').classList.toggle('connected', state.gmail.connected);
  $('#schedule-label').textContent = 'Ricerca manuale · Decidi tu quando iniziare';
  $('#search').disabled = state.job.running || (state.search_configured && searchesLeft === 0 && !state.pending_candidates);
  $('#search').title = searchesLeft === 0 && state.search_configured && !state.pending_candidates ? 'Budget di ricerca disponibile esaurito.' : '';
  $('#stop-search').disabled = !state.job.running || state.job.stopping;
  $('#stop-search').textContent = state.job.stopping ? 'Arresto in corso…' : 'Stop ricerca';
  $('#search').innerHTML = state.job.running ? '<span class="spinner"></span> Ricerca in corso…' : '<span>✳</span> Avvia ricerca <span>↗</span>';
  $('#search-status').textContent = state.job.running ? `${state.job.added} nuove aziende · ${state.job.checked} controllate · test SEO/Lighthouse in corso` : '';
  const items = (demo ? [demoLead] : view === 'sent' ? sent : drafts).filter(l => view !== 'sent' || !outcomeFilter || l.outcome === outcomeFilter).filter(l => `${l.name} ${l.domain} ${l.email}`.toLowerCase().includes(filter.toLowerCase()));
  $('#list-count').textContent = items.length;
  const fingerprint = JSON.stringify([items, demo, view, filter]);
  if (editing.size || (!force && fingerprint === lastFingerprint)) return;
  const open = [...document.querySelectorAll('.lead[open]')].map(el => el.dataset.id);
  lastFingerprint = fingerprint;
  if (items.length) {
    $('#leads').innerHTML = (demo ? '<div class="demo-banner">Anteprima dimostrativa · Nessun sito reale analizzato e nessuna email inviabile. <button class="secondary" id="exit-demo">Chiudi anteprima</button></div>' : '') + items.map(card).join('');
    document.querySelectorAll('.lead').forEach(el => { el.open = open.includes(el.dataset.id) || demo; });
  } else {
    const title = filter ? 'Nessun risultato' : view === 'sent' ? 'Le prossime conversazioni iniziano qui.' : 'La tua prossima collaborazione è là fuori.';
    const text = filter ? 'Prova a cercare un altro sito o indirizzo email.' : view === 'sent' ? 'Le email che invii compariranno qui, con data e testo del messaggio.' : 'Avvia la ricerca: visiteremo siti di imprese, produttori e fornitori in tutta Italia e raccoglieremo qui le bozze da rivedere.';
    $('#leads').innerHTML = `<div class="empty-state"><span class="empty-icon">${view === 'sent' ? '↗' : '⌕'}</span><h3>${title}</h3><p>${text}</p>${!filter && view !== 'sent' ? '<button class="secondary" id="show-demo">Guarda come sarà una scheda ↗</button>' : ''}</div>`;
  }
}

async function refresh() {
  const response = await fetch('/api/state');
  if (!response.ok) throw new Error('Impossibile caricare i dati. Ricarica la pagina.');
  state = await response.json();
  render();
}

function openSettings() {
  if (!state) return;
  const form = $('#settings-form');
  form.elements.allow_api_fallback.checked = !!state.settings.allow_api_fallback;
  ['name','website','signature','template_subject','template_body'].forEach(key => { form.elements[key].value = state.settings[key]; });
  $('#gmail-connect').textContent = state.gmail.connected ? 'Scollega Gmail' : 'Collega Gmail ↗';
  $('#gmail-help').textContent = state.gmail.connected ? 'Account autorizzato per l’invio. Scollegare rimuove le credenziali salvate da questa app.' : 'Accesso tramite Google. L’app richiede il permesso di invio, senza leggere la tua casella.';
  $('#config-status').textContent = `Ricerca: ${state.search_configured ? 'chiave configurata' : 'chiave Tavily o Serper mancante'} · Google: ${state.gmail.configured ? 'client configurato' : 'credenziali OAuth mancanti'}`;
  const providers = state.search_providers;
  if (providers) $('#config-status').textContent += ` · Tavily: ${providers.tavily.today}/30 oggi, ${providers.tavily.month}/930 mese · Serper: ${providers.serper.configured ? providers.serper.today + '/100 oggi, ' + providers.serper.total + '/2400 complessive' : 'non configurato'}`;
  updateTemplatePreview();
  $('#settings-dialog').showModal();
}

function updateTemplatePreview() {
  const f = $('#settings-form').elements;
  const values = {sito:'azienda-esempio.it', nome:f.name.value, firma:f.signature.value.replace('Front-end-Designer','Front-end Designer'), mio_sito:f.website.value.replace(/^https?:\/\//i,'').replace(/\/+$/,'')};
  const render = text => text.replace(/\{(sito|nome|firma|mio_sito)\}/g, (_, key) => values[key]);
  $('#template-preview-subject').textContent = render(f.template_subject.value);
  $('#template-preview-body').textContent = render(f.template_body.value);
}
$('#settings-form').addEventListener('input', updateTemplatePreview);

$('#settings-open').addEventListener('click', openSettings);
$('#gmail-shortcut').addEventListener('click', openSettings);
$('#settings-close').addEventListener('click', () => $('#settings-dialog').close());
$('#settings-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.target;
  try {
    const apply = event.submitter?.name === 'apply_template';
    if (apply && !window.confirm('Sostituire il testo di tutte le bozze, incluse quelle modificate a mano?')) return;
    const result = await api('/api/settings', {name:form.elements.name.value.trim(), website:form.elements.website.value.trim(), signature:form.elements.signature.value.trim(), template_subject:form.elements.template_subject.value, template_body:form.elements.template_body.value, apply_template:apply, allow_api_fallback:form.elements.allow_api_fallback.checked});
    await refresh();
    $('#settings-dialog').close();
    toast(apply ? `Template applicato a ${result.updated} bozze.` : 'Impostazioni salvate per le nuove bozze.');
  } catch (err) { toast(err.message, true); }
});
$('#gmail-connect').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    if (state.gmail.connected) {
      await api('/api/gmail/disconnect');
      await refresh();
      $('#settings-dialog').close();
      toast('Gmail scollegato da questa app.');
    } else {
      const result = await api('/api/gmail/connect');
      window.location.assign(result.url);
    }
  } catch (err) { toast(err.message, true); }
  finally { button.disabled = false; }
});
$('#stop-search').addEventListener('click', async () => {
  $('#stop-search').disabled = true;
  try { await api('/api/search/stop'); await refresh(); }
  catch (err) { toast(err.message, true); await refresh().catch(() => {}); }
});
$('#search').addEventListener('click', async () => {
  if (!state) return;
  if (!state.search_configured || !state.settings.website) { openSettings(); toast('Completa la configurazione della ricerca per trovare siti reali.'); return; }
  demo = false;
  try { await api('/api/search'); await refresh(); } catch (err) { toast(err.message, true); }
});
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
  if (editing.size) { toast('Salva o annulla le modifiche prima di cambiare vista.'); return; }
  view = button.dataset.view;
  demo = false;
  document.querySelectorAll('[data-view]').forEach(el => el.classList.toggle('active', el === button));
  $('#companies-page').hidden = view === 'opportunities';
  $('#opportunities-page').hidden = view !== 'opportunities';
  $('#breadcrumb').textContent = view === 'sent' ? 'Email inviate' : view === 'opportunities' ? 'Opportunità' : 'Aziende';
  if (view === 'opportunities') { window.refreshOpportunities?.(); return; }
  $('#list-title').innerHTML = (view === 'sent' ? 'Email inviate' : 'Aziende da contattare') + ' <span id="list-count">0</span>';
  $('#list-caption').textContent = view === 'sent' ? 'MESSAGGI INVIATI' : 'BOZZE DA RIVEDERE';
  render(true);
}));
$('#filter').addEventListener('input', event => { filter = event.target.value; render(); });
$('#leads').addEventListener('click', async event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.id === 'show-demo' || button.id === 'exit-demo') { demo = button.id === 'show-demo'; render(true); return; }
  const element = button.closest('.lead');
  if (!element) return;
  const lead = demo ? demoLead : state.leads.find(l => String(l.id) === element.dataset.id);
  const action = button.dataset.action;
  if (action === 'audit') {
    button.disabled=true; button.textContent='Analisi in corso…';
    try { await api(`/api/leads/${lead.id}/audit`); await refresh(); render(true); toast('Risultati salvati nella scheda.'); }
    catch(err) { toast(err.message,true); button.disabled=false; button.textContent='Riprova analisi'; }
    return;
  }
  if (action === 'outcome-edit') {
    if (editing.size) { toast('Salva o annulla prima la modifica aperta.'); return; }
    editing.add(lead.id);
    element.querySelector('.edit-container').innerHTML = `<form class="outcome-form"><label>Esito<select name="outcome">${Object.entries(outcomeLabels).map(([key,label])=>`<option value="${key}" ${lead.outcome === key ? 'selected' : ''}>${label}</option>`).join('')}</select></label><label>Note<textarea name="note" rows="4" maxlength="3000">${escapeHtml(lead.outcome_note || '')}</textarea></label><div class="email-actions"><button type="button" class="secondary" data-action="cancel">Annulla</button><button class="primary" type="submit">Salva esito</button></div><p class="field-note">Registra soltanto l’esito: non invia email né avvia ricontatti.</p></form>`;
    element.querySelector('select').focus();
    return;
  }
  if (action === 'edit') {
    if (editing.size) { toast('Salva o annulla la modifica già aperta.'); return; }
    editing.add(lead.id);
    element.querySelector('.email-view').hidden = true;
    element.querySelector('.email-actions').hidden = true;
    element.querySelector('.edit-container').innerHTML = `<form class="edit-form"><label>Destinatario<input name="email" type="email" value="${escapeHtml(lead.email)}" required></label><label>Oggetto<input name="subject" value="${escapeHtml(lead.subject)}" maxlength="250" required></label><label>Messaggio<textarea class="message-editor" name="body" rows="17" maxlength="20000" spellcheck="true" lang="it" required>${escapeHtml(lead.body)}</textarea></label><div class="editor-info"><span>Modifica liberamente il testo. L’invio usa la versione salvata.</span><span class="editor-count">${lead.body.length} / 20.000</span></div><details class="editor-preview"><summary>Anteprima dell’email</summary><div class="email-body">${emailPreview(lead.body)}</div></details><div class="email-actions"><button type="button" class="secondary" data-action="cancel">Annulla</button><button type="submit" class="primary">Salva modifiche</button></div></form>`;
    element.querySelector('textarea').focus();
    return;
  }
  if (action === 'cancel') { editing.delete(lead.id); render(true); return; }
  if (demo) { demo = false; toast('Anteprima chiusa. Nessun dato reale modificato.'); render(true); return; }
  let gmailWindow = null;
  if (action === 'send') {
    gmailWindow = window.open('about:blank', '_blank');
    if (!gmailWindow) { toast('Consenti le finestre popup per aprire Gmail.', true); return; }
    gmailWindow.opener = null;
  }
  button.disabled = true;
  try {
    const result = await api(`/api/leads/${lead.id}/${action === 'send' ? 'compose' : action}`);
    if (gmailWindow) gmailWindow.location.href = result.url;
    toast(action === 'finance' ? 'Ricerca economica completata: consulta la fonte nella scheda.' : action === 'send' ? 'Completa l’invio in Gmail, poi premi “Ho inviato da Gmail”.' : action === 'confirm' ? 'Invio registrato sulla tua conferma.' : 'Bozza eliminata. Il sito non verrà proposto nuovamente.');
    await refresh();
  } catch (err) { if (gmailWindow) gmailWindow.close(); toast(err.message, true); await refresh().catch(() => {}); }
  finally { button.disabled = false; }
});
$('#leads').addEventListener('input', event => {
  if (event.target.name !== 'body') return;
  const form = event.target.closest('.edit-form');
  if (!form) return;
  form.querySelector('.editor-count').textContent = `${event.target.value.length} / 20.000`;
  form.querySelector('.editor-preview .email-body').innerHTML = emailPreview(event.target.value);
});
$('#leads').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.target;
  const id = form.closest('.lead').dataset.id;
  if (form.classList.contains('outcome-form')) {
    const button = form.querySelector('[type=submit]'); button.disabled = true;
    try {
      await api(`/api/leads/${id}/outcome`, {outcome:form.elements.outcome.value,note:form.elements.note.value});
      editing.delete(Number(id)); await refresh(); render(true); toast('Esito registrato.');
    } catch (err) { button.disabled = false; toast(err.message,true); }
    return;
  }
  const values = {email:form.elements.email.value.trim(), subject:form.elements.subject.value.trim(), body:form.elements.body.value};
  const button = form.querySelector('[type=submit]');
  button.disabled = true;
  try {
    if (demo) { Object.assign(demoLead, values); editing.delete('demo'); }
    else { await api(`/api/leads/${id}/edit`, values); editing.delete(Number(id)); await refresh(); }
    render(true);
    toast(demo ? 'Anteprima aggiornata.' : 'Bozza aggiornata.');
  } catch (err) { toast(err.message, true); button.disabled = false; }
});
window.addEventListener('beforeunload', event => { if (editing.size) { event.preventDefault(); event.returnValue = ''; } });
async function poll() {
  try { await refresh(); } catch (err) { toast(err.message, true); }
  setTimeout(poll, state?.job.running ? 2000 : 10000);
}
poll();
if (new URLSearchParams(location.search).get('gmail') === 'connected') {
  toast('Gmail collegato: pavanello93@gmail.com.');
  history.replaceState({}, '', '/');
}

$('#outcome-filter').addEventListener('change', event => { if (editing.size) { event.target.value=outcomeFilter; toast('Salva o annulla prima la modifica.'); return; } outcomeFilter=event.target.value; render(true); });
