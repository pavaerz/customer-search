'use strict';
// Grants have their own profile, worker and results; customer campaigns stay separate.
let grantData=null,grantMeta=null,grantDraft=null,grantBusy=false,grantSequence=0,grantFilter='all';
const previousGrantRender=renderMain;
renderMain=function(){if(view==='grants'){renderGrants();return}previousGrantRender()};
function grantOptions(values,current){return values.map(([key,label])=>`<option value="${esc(key)}" ${key===current?'selected':''}>${esc(label)}</option>`).join('')}
async function renderGrants(){
 const seq=++grantSequence;
 $('#main').innerHTML='<p role="status">Caricamento dello spazio Bandi…</p>';
 try{
  [grantMeta,grantData]=await Promise.all([api('/grants/profile'),api('/grants')]);
  if(view!=='grants'||seq!==grantSequence)return;
  const p=grantDraft||grantMeta.profile;
  const field=(key,label,type='text',hint='')=>`<label>${label}<input name="${key}" type="${type}" value="${esc(p[key])}" maxlength="500" ${hint?`placeholder="${esc(hint)}"`:''}></label>`;
  $('#main').innerHTML=`<div class="heading"><div><h1>Bandi per la tua attività</h1><p>Incentivi e contributi pubblici, in uno spazio separato dalla ricerca clienti.</p></div><div class="actions"><button class="primary" id="grant-start">Ricerca bandi</button><button id="grant-stop" hidden>Ferma ricerca</button></div></div>
  <details class="panel grant-profile" ${!p.activity?'open':''}><summary>Il tuo profilo attività <span class="muted small">· dati dichiarati da te</span></summary><form id="grant-profile-form"><p class="muted">La partita IVA viene controllata solo nel formato. Indica il regime fiscale che conosci: non viene ricavato automaticamente.</p><div class="grant-fields">
  ${field('name','Nome attività')}${field('vat','Partita IVA (facoltativa)','text','11 cifre')}${field('ateco','Codice ATECO','text','Es. 62.10.00')}
  <label>Forma giuridica<select name="legal_form">${grantOptions(Object.entries(grantMeta.forms),p.legal_form)}</select></label>
  <label>Regime fiscale dichiarato<select name="tax_regime">${grantOptions(Object.entries(grantMeta.regimes),p.tax_regime)}</select></label>
  ${field('started_on','Data di apertura / costituzione','date')}${field('birth_date','Data di nascita (per bandi con limiti di età)','date')}
  <label>Dimensione dell’impresa<select name="company_size">${grantOptions([['unknown','Non indicata'],['micro','Microimpresa'],['small','Piccola impresa'],['medium','Media impresa'],['large','Grande impresa']],p.company_size)}</select></label>
  <label>Condizione lavorativa<select name="employment_status">${grantOptions([['unknown','Non indicata'],['self_employed','Lavoratore autonomo'],['employed','Dipendente'],['unemployed','Disoccupato'],['inactive','Inattivo']],p.employment_status)}</select></label>
  ${[['registered','Iscrizione al Registro Imprese'],['chamber_fees','Diritto camerale in regola'],['durc','Regolarità contributiva'],['startup','Iscrizione come startup innovativa']].map(([key,label])=>`<label>${label}<select name="${key}">${grantOptions([['unknown','Non indicato'],['yes','Sì'],['no','No'],...(key==='durc'?[['not_applicable','Non applicabile']]:[])],p[key])}</select></label>`).join('')}
  ${field('investment_amount','Investimento previsto (€)','number')}
  <label>Regione dell’investimento<select name="investment_region">${grantOptions([['','Non indicata'],...grantMeta.regions.map(x=>[x,x])],p.investment_region)}</select></label>
  <label>Regione della sede<select name="region">${grantOptions(grantMeta.regions.map(x=>[x,x]),p.region)}</select></label>${field('province','Provincia','text','Es. Padova')}
  <label class="grant-wide">La tua attività<textarea name="activity" maxlength="500" required placeholder="Es. sviluppo siti web ed e-commerce">${esc(p.activity)}</textarea></label>
  <label class="grant-wide">Cosa vorresti finanziare<textarea name="investment" maxlength="500" placeholder="Es. attrezzature, software o formazione">${esc(p.investment)}</textarea></label></div>
  <div class="actions"><button type="submit">Salva profilo</button><span class="small muted" id="grant-save-status">I dati rimangono in locale.</span></div></form></details>
  <div class="panel grant-coverage"><strong>Fonti disponibili</strong><p>Incentivi nazionali Invitalia; bandi della Regione Veneto per sedi in Veneto; Camera di Commercio di Padova per la provincia di Padova. Per le altre regioni, al momento, solo la fonte nazionale.</p><p class="small muted">Il motore legge requisiti e documenti ufficiali e li confronta con il profilo. Ti mostra condizioni soddisfatte, motivi di esclusione e domande precise quando manca un tuo dato. La decisione sulla domanda spetta all’ente.</p><div class="grant-source-links">${grantMeta.sources.map(([name,url])=>link(url,name)).join('')}</div></div>
  <div id="grant-progress" role="status" aria-live="polite"></div><section id="grant-results" aria-label="Bandi individuati"></section>`;
  updateGrantResults();
 }catch(e){if(view==='grants'&&seq===grantSequence)$('#main').innerHTML=`<div class="panel"><h2>Impossibile caricare i bandi</h2><p>${esc(e.message)}</p><button data-view="grants">Riprova</button></div>`}
}
const grantStatuses={compatible:'Requisiti soddisfatti',excluded:'Escluso per il tuo profilo',needs_data:'Mi serve un tuo dato',source_incomplete:'Analisi non conclusa',not_analyzed:'Da analizzare'};
function grantCard(i){
 const b=i.body,ev=b.eligibility||{},status=ev.status||b.status;
 const quotes=(rows)=>rows?.length?rows.map(x=>`<blockquote>${esc(x)}</blockquote>`).join(''):'<p class="muted">Informazione non individuata nella pagina.</p>';
 const fixedQuestions=[...new Map((ev.questions||[]).filter(q=>q.field!=='declaration').map(q=>[q.field,q])).values()];
 const declarations=(ev.questions||[]).filter(q=>q.field==='declaration');
 return `<article class="card grant-card grant-${esc(status)}"><div class="tags"><span class="tag">${esc(grantStatuses[status]||'Analisi in corso')}</span></div><h2>${esc(i.title)}</h2><p class="grant-verdict">${esc(ev.reason||b.reason)}</p><p>${link(i.url,'Fonte ufficiale')} · <span class="small muted">Consultata il ${dt(i.checked_at)}</span></p>
 ${status==='needs_data'?`<div class="grant-questions"><h3>Per completare il confronto</h3>${fixedQuestions.map(q=>`<p>${esc(q.question)} <button class="quiet" data-grant-field="${esc(q.field)}">Completa questo dato</button></p>`).join('')}${declarations.length?`<form data-grant-answers>${declarations.map(q=>`<label>${esc(q.question)}<select name="${esc(q.key)}">${grantOptions([['unknown','Non lo so ancora'],['yes','Sì'],['no','No']],'unknown')}</select></label>`).join('')}<button type="submit">Rispondi e ricalcola</button></form>`:''}</div>`:''}
 <details><summary>Come ho verificato i requisiti${ev.checks?.length?' · '+ev.checks.length+' controlli':''}</summary>
 ${(ev.checks||[]).map(c=>`<div class="grant-check"><strong>${esc({pass:'Soddisfatto',fail:'Non soddisfatto',missing:'Dato mancante',blocked:'Analisi incompleta',unknown:'Non accertato'}[c.result]||c.result)} · ${esc(c.label)}</strong><p>${esc(c.detail)}</p><blockquote>${esc(c.quote)}</blockquote>${link(c.url,'Leggi il requisito nella fonte')}</div>`).join('')||'<p>Avvia Ricerca bandi per analizzare questa scheda con il nuovo motore.</p>'}
 ${ev.blockers?.length?`<h3>Cosa impedisce di concludere l’analisi</h3><ul>${ev.blockers.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
 <h3>Scadenza e apertura · estratti</h3>${quotes(b.deadlines)}<h3>Agevolazione · estratti</h3>${quotes(b.benefit)}
 ${b.documents?.length?`<h3>Documenti consultati</h3><ul>${b.documents.map(d=>`<li>${link(d.url,d.title)} · ${dt(d.checked_at)}</li>`).join('')}</ul>`:''}
 ${(ev.declarations||[]).some(q=>q.value!=='unknown')?`<h3>Le tue risposte · modificabili</h3><form data-grant-answers>${ev.declarations.map(q=>`<label>${esc(q.question)}<select name="${esc(q.key)}">${grantOptions([['unknown','Non lo so ancora'],['yes','Sì'],['no','No']],q.value)}</select></label>`).join('')}<button type="submit">Aggiorna risposte</button></form>`:''}
 <p class="small muted">${esc(ev.basis||'')}</p></details></article>`;
}
function updateGrantResults(){
 if(view!=='grants'||!$('#grant-results'))return;
 const {run,items,tasks,errors}=grantData,running=run?.state==='running';
 $('#grant-start').disabled=grantBusy||running;$('#grant-stop').hidden=!running;$('#grant-stop').disabled=grantBusy;
 const labels={running:'Ricerca e verifica in corso',completed:'Ricerca completata',partial:'Ricerca parziale',stopped:'Ricerca fermata',error:'Ricerca interrotta'};
 $('#grant-progress').innerHTML=run?`<div class="panel"><strong>${esc(labels[run.state]||run.state)}</strong><p>${esc(run.message)}</p><span class="small muted">${(tasks.done||0)+(tasks.failed||0)} pagine esaminate · ${items.length} misure raccolte · avvio ${dt(run.created_at)}</span></div>`:'';
 const shown=items.filter(i=>grantFilter==='all'||i.body.status===grantFilter||(grantFilter==='source_incomplete'&&i.body.status==='not_analyzed'));
 const counts=Object.fromEntries(Object.keys(grantStatuses).map(s=>[s,items.filter(i=>i.body.status===s).length]));
 const openIds=[...document.querySelectorAll('#grant-results details[open]')].map(d=>d.closest('article')?.dataset.grantId);
 $('#grant-results').innerHTML=`<div class="sectionhead"><h2>Esito del confronto con il tuo profilo</h2></div><nav class="grant-filters" aria-label="Esiti dei bandi">${[['all','Tutti',items.length],['compatible','Requisiti soddisfatti',counts.compatible],['needs_data','Dati mancanti',counts.needs_data],['excluded','Esclusi',counts.excluded],['source_incomplete','Analisi incomplete',counts.source_incomplete+counts.not_analyzed]].map(([value,label,count])=>`<button data-grant-filter="${value}" aria-pressed="${grantFilter===value}" class="${grantFilter===value?'active':''}">${label} <span>${count}</span></button>`).join('')}</nav>${shown.length?`<div class="cards">${shown.sort((a,b)=>['compatible','needs_data','source_incomplete','not_analyzed','excluded'].indexOf(a.body.status)-['compatible','needs_data','source_incomplete','not_analyzed','excluded'].indexOf(b.body.status)).map(i=>grantCard(i).replace('<article ',`<article data-grant-id="${i.id}" `)).join('')}</div>`:`<div class="panel"><h3>${running?'Lettura e confronto dei requisiti…':'Nessun bando in questa vista'}</h3><p>${run?'Le schede compaiono dopo l’analisi delle fonti; nessun bando viene dichiarato compatibile se i controlli non sono completi.':'Completa il profilo e premi Ricerca bandi.'}</p></div>`}${errors.length?`<details class="panel"><summary>${errors.length} pagine non leggibili</summary>${errors.map(e=>`<p>${link(e.url,e.url)}<br><span class="muted">${esc(e.error)}</span></p>`).join('')}</details>`:''}`;
 for(const id of openIds)if(id)document.querySelector(`[data-grant-id="${id}"] details`)?.setAttribute('open','');
}

async function saveGrantProfile(){
 const form=$('#grant-profile-form');if(!form.checkValidity()){form.closest('details').open=true;form.reportValidity();throw new Error('Completa la descrizione della tua attività')}
 const p=await api('/grants/profile',Object.fromEntries(new FormData(form)));grantMeta.profile=p;grantDraft=null;$('#grant-save-status').textContent='Profilo salvato · confronti aggiornati';grantData=await api('/grants');updateGrantResults();
}
document.addEventListener('input',e=>{if(e.target.closest('#grant-profile-form')){grantDraft=Object.fromEntries(new FormData($('#grant-profile-form')));$('#grant-save-status').textContent='Modifiche da salvare'}});
document.addEventListener('submit',async e=>{if(e.target.id!=='grant-profile-form')return;e.preventDefault();if(grantBusy)return;grantBusy=true;try{await saveGrantProfile();toast('Profilo attività salvato')}catch(error){toast(error.message)}finally{grantBusy=false;updateGrantResults()}});
document.addEventListener('click',async e=>{
 const filter=e.target.closest('[data-grant-filter]');if(filter){grantFilter=filter.dataset.grantFilter;updateGrantResults();return}
 const field=e.target.closest('[data-grant-field]');if(field){$('.grant-profile').open=true;const input=document.querySelector(`#grant-profile-form [name="${field.dataset.grantField}"]`);input?.focus();input?.scrollIntoView({block:'center',behavior:'smooth'});return}
 const button=e.target.closest('#grant-start,#grant-stop');if(!button||grantBusy)return;
 grantBusy=true;button.disabled=true;
 try{if(button.id==='grant-start'){await saveGrantProfile();grantData=await api('/grants/start',{})}else grantData=await api('/grants/stop',{});updateGrantResults()}
 catch(error){toast(error.message)}finally{grantBusy=false;updateGrantResults()}
});
let grantPolling=false;
setInterval(async()=>{if(view!=='grants'||grantBusy||grantPolling||document.activeElement?.closest('[data-grant-answers]')||grantData?.run?.state!=='running')return;grantPolling=true;try{grantData=await api('/grants');updateGrantResults()}catch(error){if($('#grant-progress'))$('#grant-progress').textContent='Connessione interrotta: nuovo tentativo in corso.'}finally{grantPolling=false}},2000);

document.addEventListener('submit',async e=>{if(!e.target.matches('[data-grant-answers]'))return;e.preventDefault();if(grantBusy)return;grantBusy=true;try{grantData=await api('/grants/answers',{answers:Object.fromEntries(new FormData(e.target))});toast('Risposte salvate, confronto aggiornato')}catch(error){toast(error.message)}finally{grantBusy=false;updateGrantResults()}});
