'use strict';
(() => {
  let data = null;
  let fingerprint = '';
  let configLoaded = false;
  let refreshing = false;
  const dirty = new Set();
  const categories = {A:'A · Richiesta di progetto', B:'B · Agenzia cerca freelance', C:'C · Collaborazione professionale'};
  const statuses = {new:'Da valutare', saved:'Salvata', discarded:'Scartata', contacted:'Contattata'};
  const el = id => document.getElementById(id);
  const h = escapeHtml;
  const date = value => value ? new Date(value).toLocaleDateString('it-IT') : 'Non dichiarata';
  const link = (url, label) => `<a href="${safeUrl(url)}" target="_blank" rel="noopener noreferrer">${h(label)} ↗</a>`;
  const field = (label, value) => `<div><dt>${h(label)}</dt><dd>${h(value || 'Non dichiarato')}</dd></div>`;

  function card(i) {
    return `<details class="opp-card" data-id="${i.id}"><summary><span><small>${i.selection_error?'ESCLUSA · non è un annuncio':i.published?h(categories[i.category]):'PAGINA DA VERIFICARE · data assente'} · ${h(statuses[i.status])}</small><strong>${h(i.title)}</strong><small>${h(i.source)} · Pubblicazione: ${date(i.published)}</small></span><b class="opp-rating">${i.score}<small>/100</small></b></summary>
      <section class="selection-panel"><div class="selection-kicker">${i.selection_error?'SELEZIONE ERRATA · SCHEDA ESCLUSA':i.published?'RISCONTRO NELLA PAGINA ORIGINALE':'ATTUALITÀ NON VERIFICATA · POSSIBILE COLLABORAZIONE'}</div><p>${h(i.selection_error || i.evidence)}</p>${link(i.url,'Apri la richiesta originale')}<p class="field-note">${h(i.verification)} il ${date(i.verified_at)}. Disponibilità effettiva da confermare.</p></section>
      <div class="opp-body"><dl class="opp-facts">${field('Committente',i.company)}${field('Località',i.location)}${field('Modalità',i.mode)}${field('Budget / compenso riportato',i.budget)}${field('Tecnologie rilevate',i.technologies.join(', '))}${field('Tipo di progetto',i.project_type)}${field('Fonte della data',i.date_source)}</dl>
      <details><summary>Contenuto della richiesta letto sulla fonte</summary><p class="opp-description">${h(i.description)}</p></details>
      <details><summary>Come è stato calcolato il punteggio</summary><p>Valutazione automatica, non probabilità di ottenere il lavoro.</p><ul>${Object.entries(i.score_details).map(([k,v])=>`<li>${h(k)}: +${v}</li>`).join('')}</ul><p>Il totale finale applica i limiti per data assente o annuncio vecchio.</p></details>
      <ul class="opp-limitations">${i.limitations.map(v=>`<li>${h(v)}</li>`).join('')}</ul>
      ${i.sources.length>1?`<p>Stessa richiesta trovata anche su: ${i.sources.map(url=>link(url,new URL(url).hostname)).join(' · ')}</p>`:''}
      <label>Note personali<textarea name="notes" rows="3" maxlength="10000">${h(i.notes)}</textarea></label>
      <div class="email-actions"><button class="secondary" data-opp="saved" ${i.selection_error?'disabled':''}>Salva opportunità</button><button class="secondary" data-opp="contacted">Segna contattata</button><button class="secondary" data-opp="discarded">Scarta</button>${!i.selection_error && ['discarded','contacted'].includes(i.status)?'<button class="secondary" data-opp="new">Rimetti da valutare</button>':''}<button class="secondary" data-opp="notes">Salva note e bozza</button></div>
      <div class="opp-application"><button class="primary" data-opp="draft" ${i.selection_error?'disabled':''}>${i.draft?'Rigenera':'Genera'} bozza di candidatura</button><p class="field-note">Bozza modificabile. Nessun invio automatico: scegli tu il canale indicato nell’annuncio.</p><label>Testo della candidatura<textarea name="draft" rows="9" maxlength="18000" placeholder="Premi Genera bozza per iniziare">${h(i.draft)}</textarea></label><button class="secondary" data-opp="copy">Copia testo</button></div></div></details>`;
  }

  function render(force = false) {
    if (!data) return;
    el('opp-progress').textContent = data.job.message;
    el('opp-search').disabled = data.job.running || !state;
    el('opp-stop').disabled = !data.job.running;
    el('opp-week').textContent = `${data.weekly_recent}/10 nell’ultima settimana: richieste trovate negli ultimi 7 giorni, pubblicate da non più di 30 giorni, con pagina originale letta e non scartate. È un obiettivo sperimentale, non una garanzia.`;
    if (!configLoaded) {
      const form = el('opp-config');
      form.elements.queries.value = data.config.queries.join('\n');
      form.elements.batch_size.value = data.config.batch_size;
      form.elements.provider.value = data.config.provider;
      form.elements.time_range.value = data.config.time_range;
      configLoaded = true;
    }
    const source = el('opp-source').value;
    const sources = [...new Set(data.items.map(i=>i.source))].sort();
    el('opp-source').innerHTML = '<option value="">Tutte</option>' + sources.map(s=>`<option value="${h(s)}">${h(s)}</option>`).join('');
    el('opp-source').value = sources.includes(source) ? source : '';
    const days = el('opp-date').value;
    const today = Date.now();
    const items = data.items.filter(i=>
      (!el('opp-category').value || i.category === el('opp-category').value) &&
      i.score >= Number(el('opp-score').value) &&
      (!el('opp-source').value || i.source === el('opp-source').value) &&
      (!days || (days === 'unknown' ? !i.published : i.published && today - Date.parse(i.published) <= Number(days)*86400000)) &&
      (el('opp-status').value === 'all' || (el('opp-status').value === 'active' ? ['new','saved'].includes(i.status) : i.status === el('opp-status').value))
    ).sort((a,b)=>el('opp-sort').value === 'date' ? (b.published || '').localeCompare(a.published || '') || b.score-a.score : b.score-a.score || (b.published || '').localeCompare(a.published || ''));
    el('opp-count').textContent = `${items.length} schede mostrate · ${data.items.length} pagine archiviate`;
    const next = JSON.stringify(items);
    if (!dirty.size && (force || next !== fingerprint)) {
      const open = [...el('opp-results').querySelectorAll('details.opp-card[open]')].map(e=>e.dataset.id);
      el('opp-results').innerHTML = items.length ? items.map(card).join('') : '<div class="empty-state"><h3>Nessun annuncio recente con questi filtri.</h3><p>Le pagine senza data non dimostrano una ricerca attuale e sono escluse dalla vista iniziale. Puoi consultarle scegliendo “Pagine senza data · da verificare”. I motivi di esclusione delle ricerche sono nello storico.</p></div>';
      el('opp-results').querySelectorAll('.opp-card').forEach(e=>e.open=open.includes(e.dataset.id));
      fingerprint = next;
    }
    el('opp-history').innerHTML = data.runs.length ? data.runs.map(r=>`<details><summary>${date(r.started)} · ${h(r.status)} · ${r.summary.added || 0} nuove / ${r.summary.duplicates || 0} già presenti</summary><p>${r.summary.checked || 0} pagine controllate</p>${r.summary.validation?`<p>${h(r.summary.validation)}</p>`:''}<ul>${(r.summary.queries || []).map(q=>`<li>${h(q.query)} · ${q.returned} risultati</li>`).join('')}${Object.entries(r.summary.rejected || {}).map(([reason,n])=>`<li>${n} · ${h(reason)}</li>`).join('')}${(r.summary.rejected_details || []).map(e=>`<li>${link(e.url,e.url)}: ${h(e.reason)}</li>`).join('')}${(r.summary.errors || []).map(e=>`<li>${h(e.url || 'Motore')}: ${h(e.reason)}</li>`).join('')}</ul></details>`).join('') : '<p>Nessuna ricerca eseguita.</p>';
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      const response = await fetch('/api/opportunities');
      if (!response.ok) throw new Error('Impossibile caricare le opportunità.');
      data = await response.json();
      render();
    } catch (error) { el('opp-progress').textContent = error.message; }
    finally { refreshing = false; }
  }
  window.refreshOpportunities = refresh;
  ['opp-category','opp-score','opp-date','opp-source','opp-status','opp-sort'].forEach(id=>el(id).addEventListener('change',()=>{
    if (dirty.size) { toast('Salva le note o la bozza prima di applicare i filtri.'); return; }
    render(true);
  }));
  el('opp-config').addEventListener('submit',async event=>{
    event.preventDefault();
    try {
      const form = event.currentTarget;
      await api('/api/opportunities/config',{queries:form.elements.queries.value.split('\n').map(s=>s.trim()).filter(Boolean),batch_size:Number(form.elements.batch_size.value),provider:form.elements.provider.value,time_range:form.elements.time_range.value});
      toast('Configurazione salvata. Sarà usata dal prossimo avvio.');
      await refresh();
    } catch(error) { toast(error.message,true); }
  });
  el('opp-search').addEventListener('click',async()=>{
    try { el('opp-search').disabled = true; await api('/api/opportunities/search'); await refresh(); }
    catch(error) { toast(error.message,true); el('opp-search').disabled = false; }
  });
  el('opp-stop').addEventListener('click',async()=>{
    try { await api('/api/opportunities/stop'); el('opp-progress').textContent='Arresto richiesto; attendo la richiesta di rete in corso.'; }
    catch(error) { toast(error.message,true); }
  });
  el('opp-results').addEventListener('input',event=>{
    const card = event.target.closest('.opp-card');
    if (card) dirty.add(card.dataset.id);
  });
  el('opp-results').addEventListener('click',async event=>{
    const button = event.target.closest('[data-opp]');
    if (!button) return;
    const card = button.closest('.opp-card');
    const action = button.dataset.opp;
    button.disabled = true;
    try {
      const body = {notes:card.querySelector('[name=notes]').value,draft:card.querySelector('[name=draft]').value};
      if (action === 'copy') { await navigator.clipboard.writeText(body.draft); toast('Testo copiato. Nessuna candidatura inviata.'); return; }
      if (action === 'draft') body.generate_draft = true;
      else if (action !== 'notes') body.status = action;
      const result = await api('/api/opportunities/'+card.dataset.id,body);
      card.querySelector('[name=draft]').value = result.draft;
      dirty.delete(card.dataset.id);
      toast(action === 'draft' ? 'Bozza pronta da rivedere.' : 'Modifiche salvate.');
      await refresh();
    } catch(error) { toast(error.message,true); }
    finally { button.disabled = false; }
  });
  window.addEventListener('beforeunload',event=>{if(dirty.size){event.preventDefault();event.returnValue='';}});
  setInterval(()=>{if(!el('opportunities-page').hidden) refresh();},2500);
})();
