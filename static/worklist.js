/* Commercial worklist uses saved evidence only. Research starts explicitly. */
'use strict';
let agent7Mode='WORKLIST',agent7View='ready',agent7Search='',agent7Flow='',agent7SearchTimer;
let agent8Filters={};
const agent8Types={OPPORTUNITA_IMPRENDITORIALE:'Cofounder / partecipazione imprenditoriale',DEMANDA_ESPLICITA:'Richiesta esplicita',COLLABORAZIONE_AGENZIA:'Collaborazione con agenzia',OPPORTUNITA_PROATTIVA:'Opportunità proattiva',SEGNALE_INDIRETTO:'Segnale da verificare',NON_QUALIFICATA:'Non qualificata'};
const agent7Views={ready:'Da contattare',verified:'Verificate',potential:'Potenziali',promising:'Promettenti da verificare',review:'Da approfondire',resolved:'Approfondimenti conclusi',new:'Nuove piste',contacted:'Contattati',replied:'Risposte ricevute',proposal:'Preventivi',won:'Clienti acquisiti',lost:'Perse',excluded:'Eliminate'};
const agent7ResearchRender=renderAgent6,agent7ResearchLoad=loadAgent6,agent7ResearchUpdate=updateResearchState;
function agent7ModeSwitch(){return `<nav class="agent7-modes" aria-label="Modalità di lavoro"><button data-agent7-mode="WORKLIST" aria-pressed="${agent7Mode==='WORKLIST'}">Opportunità e contatti</button><button data-agent7-mode="RESEARCH" aria-pressed="${agent7Mode==='RESEARCH'}">Ricerca clienti</button></nav>`}
renderAgent6=function(){
 if(agent7Mode==='RESEARCH'){agent7ResearchRender();$('#agent6-root').insertAdjacentHTML('afterbegin',agent7ModeSwitch());return}
 $('#main').innerHTML=`<section id="agent6-root">${agent7ModeSwitch()}
 <header class="agent6-header"><div><span class="eyebrow">CUSTOMERSEARCH 9.2.1 · LA TUA WORKLIST</span><h1>Chi contattare oggi</h1><p>Richieste, collaborazioni e opportunità proattive, con prove, contatti e prossimi passi.</p></div><div class="agent6-utilities"><button class="quiet" data-agent6="intelligence">Strategie e risultati</button><button class="quiet" data-agent6="legacy">Storico ricerche</button></div></header>
 <div id="agent7-running" role="status">${agent7Running()}</div>
 <div class="agent7-tabs" role="group" aria-label="Stato delle opportunità">${Object.entries(agent7Views).filter(([k])=>['ready','promising','review','new','contacted'].includes(k)).map(([k,v])=>`<button data-agent7-view="${k}" aria-pressed="${agent7View===k}">${v} <span data-agent7-count="${k}">—</span></button>`).join('')}</div>
 <div class="agent7-filters panel"><label>Cerca azienda o sito<input id="agent7-search" type="search" maxlength="200" placeholder="Nome o dominio" value="${esc(agent7Search)}"></label><label>Categoria<select id="agent7-flow"><option value="">Tutte le categorie</option>${Object.entries(S.agent6_flows).map(([k,v])=>`<option value="${k}" ${agent7Flow===k?'selected':''}>${esc(v)}</option>`).join('')}</select></label><label>Vista<select id="agent7-view">${Object.entries(agent7Views).map(([k,v])=>`<option value="${k}" ${agent7View===k?'selected':''}>${v}</option>`).join('')}</select></label><p class="small muted">Tutte le campagne · Una scheda per azienda. Le singole richieste restano nel dossier e possono avere stati diversi. Aprire questa vista non consuma crediti.</p></div>
 <details class="panel"><summary>Filtra per progetto, territorio e verifica</summary><div class="agent7-filters">
 <label>Tipo di opportunità<select data-agent8-filter="type"><option value="">Tutti i tipi</option>${Object.entries(agent8Types).map(([k,v])=>`<option value="${k}" ${agent8Filters.type===k?'selected':''}>${v}</option>`).join('')}</select></label>
 <label>Priorità<select data-agent8-filter="priority"><option value="">Tutte</option>${Object.entries({high:'Alta',medium:'Media',low:'Bassa'}).map(([k,v])=>`<option value="${k}" ${agent8Filters.priority===k?'selected':''}>${v}</option>`).join('')}</select></label>
 ${Object.entries({region:'Territorio',sector:'Settore',source:'Sito della fonte'}).map(([k,v])=>`<label>${v}<input data-agent8-filter="${k}" maxlength="120" value="${esc(agent8Filters[k]||'')}"></label>`).join('')}
 <div class="agent9-filter-flags"><label><input type="checkbox" data-agent8-filter="complete" ${agent8Filters.complete==='1'?'checked':''}> Verifica completata</label>
 <label><input type="checkbox" data-agent8-filter="contact" ${agent8Filters.contact==='1'?'checked':''}> Con contatto pubblico</label>
 <label><input type="checkbox" data-agent8-filter="contacted" ${agent8Filters.contacted==='1'?'checked':''}> Già contattata</label></div>
 </div></details><div id="agent6-results" aria-live="polite" aria-busy="true"><p>Caricamento delle opportunità salvate…</p></div><div id="agent6-intelligence"></div></section>`;
 loadAgent6()
};
function agent7Running(){return S.campaign?.running?'<p class="agent7-running">Una ricerca è in corso. <button class="quiet" data-agent7-mode="RESEARCH">Vedi avanzamento e controlli</button></p>':''}
updateResearchState=function(before){
 if(agent7Mode!=='WORKLIST'||!$('#agent7-running'))return agent7ResearchUpdate(before);
 $('#agent7-running').innerHTML=agent7Running();
 if(JSON.stringify(S.campaign)!==JSON.stringify(before.campaign))loadAgent6()
};
loadAgent6=async function(){
 if(agent7Mode!=='WORKLIST')return agent7ResearchLoad();
 clearTimeout(agent7SearchTimer);
 const seq=++agent6Request,host=$('#agent6-results');if(!host)return;
 host.setAttribute('aria-busy','true');
 try{
  const data=await api('/agent6/worklist?'+new URLSearchParams({view:agent7View,q:agent7Search,flow:agent7Flow,offset:agent6Offset,group:'company',...agent8Filters}));
  if(seq!==agent6Request||agent7Mode!=='WORKLIST'||!host.isConnected)return;
  for(const [key,count] of Object.entries(data.counts)){const el=$(`[data-agent7-count="${key}"]`);if(el)el.textContent=count;const option=$(`#agent7-view option[value="${key}"]`);if(option)option.textContent=agent7Views[key]+' · '+count}
  const count=data.total?`${data.total} ${data.total===1?'azienda':'aziende'} · ${agent6Offset+1}–${Math.min(data.total,agent6Offset+data.items.length)}`:'Nessuna opportunità in questa vista';
  host.innerHTML=`<div class="agent6-panel-heading"><h2>${agent7Views[agent7View]}</h2><p class="small muted">${count}</p></div>`+
   (data.items.map(agent7Card).join('')||`<section class="agent6-empty"><h3>${agent7View==='ready'?'Nessuna proposta pronta da contattare':'Nessuna scheda in questo gruppo'}</h3><p>${data.counts.review||data.counts.new?'Ci sono piste da approfondire: consulta le fonti e le informazioni mancanti.':'Qui compariranno le proposte sostenute dalle fonti. I semplici URL trovati restano nella ricerca.'}</p><button data-agent7-mode="RESEARCH">Vai alla ricerca clienti</button></section>`)+
   (data.total>25?`<div class="actions"><button data-agent6="prev" ${agent6Offset?'':'disabled'}>Precedenti</button><button data-agent6="next" ${agent6Offset+data.items.length<data.total?'':'disabled'}>Successive</button></div>`:'');
 }catch(e){if(seq===agent6Request&&host.isConnected)host.textContent=e.message}
 finally{if(seq===agent6Request&&host.isConnected)host.setAttribute('aria-busy','false')}
};
function agent7Card(r){
 const b=r.body,w=r.worklist,contacted=['contacted','replied','proposal','won'].includes(w.bucket);
 const proof=b.evidence_level|| (b.original?'ORIGINAL_READ':'SNIPPET_ONLY');
 const proofLabel={SNIPPET_ONLY:'Solo indizio indicizzato',ORIGINAL_READ:'Fonte originale consultata',ORIGINAL_VERIFIED:'Verifica sulla fonte originale',CROSS_VERIFIED:'Riscontri su più fonti',WEBSITE_AUDIT_VERIFIED:'Audit del sito e ipotesi commerciale verificati'}[proof]||'Prove da verificare';
 const proactive=(b.automatic_opportunity_type||b.opportunity_type)==='OPPORTUNITA_PROATTIVA';
 const need=proactive?'<strong>Proposta proattiva</strong><p>L’azienda non ha dichiarato di cercare un fornitore. La proposta nasce dai problemi osservati sul sito; interesse e budget restano da confermare.</p>':w.request?`<strong>Cosa cerca</strong><p>${esc(w.request)}</p>`:w.signal?`<strong>Segnale da verificare</strong><p>${esc(w.signal)}</p>`:'<p>Richiesta commerciale ancora da verificare.</p>';
 return `<article class="panel agent6-card agent7-card ${contacted?'is-contacted':''}">
 <div class="tags"><span class="tag agent6-state-${esc(r.state.toLowerCase())}">${esc(b.research_resolution?'Approfondimento concluso':b.verification_hold?'Verifica non conclusa':b.decision_engine==='ai_first_1'?({INTERESTING:'Interessante da contattare',NOT_INTERESTING:'Non pertinente',NEEDS_RESEARCH:'Da approfondire'}[b.decision]||'Verifica da completare'):(agent6Labels[r.state]||r.state))}</span>${!['VERIFIED','POTENTIAL'].includes(r.state)&&w.label!==(agent6Labels[r.state]||r.state)?`<span class="tag">${esc(w.label)}</span>`:''}${b.flows.map(f=>`<span class="tag">${esc(agent6FlowLabel(f)||f)}</span>`).join('')}</div>
 <h3>${esc(b.entity_name||'Committente da identificare')}</h3>${b.official_domain?link(b.official_domain,b.official_domain):''}
 <p class="small">${esc(b.opportunity_type_label||'Tipo da verificare')} · ${esc(b.region||b.identity?.region||'Territorio da verificare')} · ${esc(b.sector||'Settore da verificare')}</p>
 ${b.service?`<p><strong>${b.research_resolution?'Ambito analizzato:':'Servizio proponibile:'}</strong> ${esc(({website:'Sito aziendale',ecommerce:'E-commerce',webapp:'Applicazione web'})[b.service]||b.service)}</p>`:''}
 <div class="agent7-need">${need}</div>${r.company_dossier?.signals.length>1?`<p class="small">${r.company_dossier.signals.length} richieste o segnali collegati a questa azienda. Apri il dossier per consultarli separatamente.</p>`:''}<p class="reason"><strong>Valutazione</strong> ${esc(b.reason)}</p>${agentFollowupResolution(b.research_resolution,r.id)}${b.later_analysis_failure?'<p class="small">Una nuova interpretazione AI dello stesso originale non è stata validata. È conservata la precedente valutazione verificata, con la sua data di consultazione.</p>':''}
 ${w.warning?`<p class="agent7-warning"><strong>Da ricontrollare:</strong> ${esc(w.warning)}</p>`:''}
 <dl class="agent7-facts"><div><dt>Fonte e affidabilità</dt><dd>${link(w.source,'Consulta la fonte')}<br>${esc(proofLabel)} · Identità ${b.identity_verified?'verificata':'da verificare'}${w.secondary_source?`<br>${link(w.secondary_source,'Seconda fonte')}`:''}</dd></div>
 <div><dt>Data e contatto</dt><dd>${b.freshness?.status==='STANDING_INVITATION'?'Invito permanente · incarichi da confermare':`Richiesta: ${w.date?esc(w.date):'data non verificata'}`}<br>Consultata: ${w.checked_at?dt(w.checked_at):'non ancora'}<br>${w.contacts.length?w.contacts.map(agentResponseChannel).join('<br>'):(b.observed_owner_contacts||[]).length?'Canale per questa richiesta da confermare':'Contatto pubblico da verificare'}</dd></div></dl>${agentObservedContacts(b)}
 <p><strong>Prossimo passo:</strong> ${esc(w.next_action)}</p>
 ${Object.keys(b.manual_corrections||{}).length?'<p class="small">Valutazione corretta manualmente; prove e qualifica automatica conservate.</p>':''}${b.research_resolution?'':agent921Alignment(b)+agent8SourceContext(b)+agent91Completion(b)+agent9Assessment(b)}${b.website_audit?agent8Audit(b.website_audit):''}
 <div class="actions"><button data-agent6="dossier" data-id="${r.id}">Prove e dossier</button>${!w.excluded&&!contacted&&w.bucket!=='resolved'?`<button class="primary" data-agent7-contact="${r.id}">Conferma contatto</button>`:''}${!w.excluded&&['VERIFIED','POTENTIAL'].includes(r.state)?`<button data-agent6="save" data-id="${r.id}">Salva nei contatti</button>`:''}<button data-agent6="review" data-id="${r.id}">Registra esito</button><button data-agent8-correct="${r.id}">Correggi valutazione</button>${!w.excluded?`<button class="quiet" data-agent7-delete="${r.id}">Elimina proposta</button>`:''}</div><div id="agent6-detail-${r.id}"></div></article>`
}
function agentFollowupResolution(resolution,hostId){
 if(!resolution)return '';
 return `<div class="agent7-need"><strong>${esc(resolution.label)}</strong>${resolution.terminal_records.map(r=>`<p>${esc(r.reason)}<br>${link(r.url,'Fonte dell’approfondimento')} · <button class="quiet" data-agent8-related="${r.id}" data-host="${hostId}">Leggi la valutazione finale</button></p>`).join('')}<p class="small">${esc(resolution.limit)} La valutazione iniziale resta conservata.</p></div>`;
}
function agentResponseChannel(c){
 const labels={email:'Email',phone:'Telefono',contact_form:'Modulo sulla pagina',form:'Modulo sulla pagina',application_link:'Link per candidarsi'};
 const value=['application_link','contact_form','form'].includes(c.type)?link(c.value,labels[c.type]):`${esc(labels[c.type]||'Recapito')}: ${esc(c.value)}`;
 return `${value}${c.url?' · '+link(c.url,'Fonte del contatto'):''}${c.attribution==='observed_owner_response_control'?'<br><span class="small muted">Canale indicato dalla fonte · nessun invio effettuato</span>':''}`;
}
function agentObservedContacts(b){
 const contacts=b.observed_owner_contacts||[];
 if(!contacts.length)return '';
 return `<div class="agent7-observed-contacts"><strong>Recapito generale pubblicato dall’azienda</strong>${contacts.map(c=>`<p>${agentResponseChannel(c)}${c.checked_at?' · Consultato: '+esc(c.checked_at.slice(0,10)):''}</p>`).join('')}<p class="small muted">Presente nella fonte originale. Uso per questa candidatura e ricezione dei messaggi da confermare; nessun invio effettuato.</p></div>`;
}
function agent9Assessment(b){
 const labels={company_fit:'Compatibilità',website_need:'Problemi del sito',evidence_strength:'Solidità delle prove',contactability:'Contatto',freshness:'Attualità',commercial_relevance:'Ragione commerciale',buying_intent:'Intenzione di acquisto'};
 const values={INTERESTING:'Interessante',NOT_INTERESTING:'Non pertinente',NEEDS_RESEARCH:'Da approfondire',HIGH:'Alta',MEDIUM:'Media',LOW:'Bassa',SUPPORTED:'Sostenuta dalle prove',NOT_COMPATIBLE:'Non compatibile',UNKNOWN:'Non dimostrata',SIGNIFICANT_OBSERVATIONS:'Rilievi significativi',LIMITED_OBSERVATIONS:'Rilievi limitati',CORROBORATED:'Riscontri coerenti',PARTIAL:'Parziale',PUBLIC_CHANNEL:'Canale pubblico verificato',RECENT:'Recente',STALE:'Datata',TO_VERIFY:'Da verificare',DECLARED_REQUEST:'Richiesta esplicita verificata'};
 const a=b.website_audit,issues=(a?.observations||[]).filter(o=>['ISSUE','ASSESSMENT'].includes(o.status)&&o.severity==='major').slice(0,4);
 return `${a&&a.browser_status!=='COMPLETE'?'<p class="agent9-audit-warning"><strong>Audit incompleto.</strong> Alcuni controlli non sono stati completati. Questo non dimostra un difetto del sito.</p>':''}${issues.length?`<div class="agent7-need"><strong>Problemi osservati da approfondire</strong><ul>${issues.map(o=>`<li>${esc(o.impact||o.action)} · ${link(o.evidence.url,'Prova')}</li>`).join('')}</ul></div>`:''}${b.proposed_scope?`<p><strong>Proposta da discutere:</strong> ${esc(b.proposed_scope)}</p>`:''}${b.commercial_dimensions?`<details class="agent8-audit"><summary>Motivazioni e limiti della valutazione</summary><p class="small">Le dimensioni descrivono le prove disponibili, non la probabilità di ottenere il cliente.</p>${Object.entries(b.commercial_dimensions).map(([k,v])=>`<p><strong>${esc(labels[k]||k)} · ${esc(values[v.value]||v.value)}</strong><br>${esc(v.reason)}${v.uncertainty?`<br><span class="small muted">${esc(v.uncertainty)}</span>`:''}${v.evidence?.length?`<br>${v.evidence.map(e=>link(e.url,'Fonte')).join(' · ')}`:''}</p>`).join('')}</details>`:''}`;
}
function agent8Audit(a){
 const issues=a.observations.filter(o=>['ISSUE','ASSESSMENT'].includes(o.status));
 const labels={http_status:'Risposta della pagina',https:'Connessione HTTPS',title:'Titolo della pagina',meta_description:'Descrizione per i motori',canonical:'URL canonico',viewport:'Impostazione mobile',h1:'Titolo principale',structured_data:'Dati strutturati',images_without_alt:'Descrizioni delle immagini',broken_commercial_path:'Percorso commerciale interrotto',mobile_content:'Contenuti su telefono',desktop_content:'Contenuti su desktop',horizontal_overflow:'Contenuti fuori larghezza',obstructed_controls:'Comandi coperti',responsive:'Adattamento mobile',form_delivery:'Invio dei moduli',performance:'Prestazioni',site_creation_date:'Data di realizzazione',complete_link_coverage:'Verifica di tutti i collegamenti'};
 const scores={TECHNICAL_ISSUES:'Problemi tecnici',CONTENT_AND_STRUCTURE:'Contenuti e struttura',COMMERCIAL_OPPORTUNITY:'Ipotesi di progetto',BUSINESS_FIT:'Compatibilità commerciale',EVIDENCE_CONFIDENCE:'Copertura dei controlli'};
 return `<details class="agent8-audit"><summary>Audit del sito · ${issues.length} osservazioni · ${a.pages.length} pagine controllate</summary><p class="small">Controlli limitati alle pagine indicate. Non misurato non significa difettoso. Gli indicatori non stimano la probabilità di vendita.</p>${Object.entries(a.scores||{}).map(([k,v])=>`<p class="small"><strong>${esc(scores[k]||k)}:</strong> ${v.score==null?'da valutare':esc(v.score)+'/100'}</p>`).join('')}${issues.map(o=>`<p><strong>${esc(labels[o.code]||o.code)}</strong> · ${esc(({minor:'limitato',moderate:'moderato',major:'rilevante'})[o.severity]||o.severity)}<br>${esc(o.impact||o.action)}<br>${esc(o.observation_type||'Controllo tecnico')}<br>${link(o.evidence.url,'Pagina osservata')} · ${esc(o.evidence.method)} · ${dt(o.evidence.checked_at)}</p>`).join('')}${a.controls?.length?`<details><summary>Copertura dei controlli</summary><p class="small">Un controllo non eseguito o bloccato non dimostra un difetto.</p>${a.controls.map(c=>`<p class="small"><strong>${esc(labels[c.code]||c.code)}</strong> · ${esc(({PASS:'Eseguito',FAIL_OBSERVED:'Problema osservato',NOT_TESTED:'Non eseguito',BLOCKED:'Accesso bloccato',PARTIAL:'Parziale',INCONCLUSIVE:'Non conclusivo'})[c.status]||c.status)} · livello ${c.level}<br>${c.source?link(c.source,'Fonte'):''} · ${dt(c.checked_at)}</p>`).join('')}</details>`:''}${(a.external_solutions||[]).length?`<h4>Soluzioni esterne collegate dal sito</h4>${a.external_solutions.map(x=>`<p>${link(x.url,x.label)} · ${x.access?.content_read?'pagina consultata, adeguatezza da valutare':'contenuto non verificato'}<br>${link(x.source_url,'Pagina che contiene il collegamento')}</p>`).join('')}`:''}<p><strong>Non misurato:</strong> ${esc([...new Set(a.observations.filter(o=>o.status==='UNKNOWN').map(o=>labels[o.code]||o.code))].join(', '))}</p></details>`
}
function agent8SourceContext(b){
 const s=b.social_source||b.social_origin,n=b.news_correlation;let result='';
 const exclusions={excluded_legal_form:'Forma societaria esclusa',public_administration:'Pubblica amministrazione',large_group:'Grande gruppo'};
 for(const item of b.commercial_exclusions||[])result+=`<p><strong>Fuori dai criteri: ${esc(exclusions[item.code]||item.code)}</strong><br>${esc(item.quote)} · ${link(item.url,'Prova riferita al titolare')}</p>`;
 const terms={EQUITY_ONLY:'Compenso esclusivamente in quote: non è una commessa retribuita.',UNPAID:'Collaborazione dichiarata gratuita.',COFOUNDER_ROLE:'Ruolo di cofondatore: condizioni di retribuzione da chiarire.',CONTRADICTORY_TERMS:'Condizioni economiche contraddittorie: serve un chiarimento.',PAID_CONTRACT:'Contratto retribuito dichiarato; l’importo resta quello eventualmente documentato.'}[b.engagement?.status];
 if(terms)result+=`<p class="small"><strong>Condizioni:</strong> ${terms}</p>`;
 const fit={SUITABLE_FOR_AUDIT:'Attività, territorio e contatto compatibili con un approfondimento commerciale; capacità di spesa non stimata.',LOW_PRIORITY:'Compatibilità commerciale bassa per il target configurato.',NOT_SUITABLE:'Azienda o situazione fuori dai criteri commerciali.',INSUFFICIENT_EVIDENCE:'Compatibilità commerciale ancora da verificare.'}[b.commercial_fit?.status];
 if(fit)result+=`<p class="small"><strong>Compatibilità:</strong> ${fit}</p>`;

 if(s){
  const label={INDEXED_ONLY_ACCESS_POLICY:'Solo indizio indicizzato: il post non è stato letto.',ORIGINAL_UNAVAILABLE:'Post originale non consultabile.',PUBLIC_POST_AUTHOR_OR_SCOPE_UNVERIFIED:'Pagina consultata, ma autore o testo del post non isolati con certezza.',PUBLIC_POST_READ:'Post pubblico originale consultato.'}[s.status]||'Verifica del post incompleta.';
  const requests=(b.facts||[]).filter(f=>f.field==='request'&&f.original&&f.url===s.url);
  const attribution=s.official_identity_link?.verified
   ?s.official_identity_link.relationship==='person_post_referenced_by_company'
    ?'Il sito ufficiale dell’azienda rimanda a questo specifico post. Il ruolo professionale dell’autore nell’azienda resta da verificare.'
    :'Il sito ufficiale rimanda al profilo autore o all’annuncio specifico: collegamento aziendale verificato.'
   :'Attribuzione all’azienda non verificata attraverso un riferimento ufficiale.';
  result+=`<details><summary>Verifica della fonte social</summary><p>${label}</p><p><strong>Piattaforma:</strong> ${esc(s.platform||'Da verificare')}<br><strong>Autore indicato dal post:</strong> ${esc(s.author_name||'Non verificato')}${s.author_profile?' · '+link(s.author_profile,'Profilo o annuncio originale'):''}${s.subject_name?'<br><strong>Azienda o soggetto della richiesta:</strong> '+esc(s.subject_name):''}</p><p>${link(s.url,'Fonte del post')}${s.published_at?' · Pubblicazione: '+esc(s.published_at):' · Data non verificata'}</p>${requests.map(f=>`<blockquote>${esc(f.quote)}</blockquote>`).join('')}${s.reposted?'<p>Contenuto ripubblicato: non dimostra una richiesta di chi lo condivide.</p>':''}<p>${attribution}</p></details>`;
 }
 if(n)result+=`<details><summary>Evento aziendale e verifica del sito</summary><p>${n.identity_linked?'Azienda protagonista collegata al sito ufficiale.':'Collegamento tra azienda protagonista e sito ancora da verificare.'}</p><p>Pubblicazione: ${esc(n.published_at||'non verificata')} · Data dell’evento: ${esc(n.event_date||'non verificata')}</p><p>${n.event_current?'Fonte recente; la notizia non equivale a una richiesta di acquisto.':'La fonte non dimostra un evento attuale.'}</p>${n.source_url?link(n.source_url,'Notizia originale'):''}${n.relation?`<p><strong>Ipotesi commerciale:</strong> ${esc(n.relation)}</p>`:''}</details>`;
 return result;
}
document.addEventListener('change',e=>{const k=e.target.dataset.agent8Filter;if(!k)return;agent8Filters[k]=e.target.type==='checkbox'?(e.target.checked?'1':''):e.target.value;agent6Offset=0;loadAgent6()});
document.addEventListener('click',async e=>{
 const mode=e.target.closest('[data-agent7-mode]'),tab=e.target.closest('[data-agent7-view]');
 if(mode){agent7Mode=mode.dataset.agent7Mode;agent6Offset=0;agent6Request++;renderAgent6();return}
 if(tab){agent7View=tab.dataset.agent7View;$('#agent7-view').value=agent7View;agent6Offset=0;for(const b of document.querySelectorAll('[data-agent7-view]'))b.setAttribute('aria-pressed',String(b===tab));loadAgent6();return}
 const action=e.target.closest('[data-agent7-contact],[data-agent7-delete]');if(!action)return;
 action.disabled=true;
 try{const id=action.dataset.agent7Contact||action.dataset.agent7Delete;await api(`/agent6/records/${id}/feedback`,{kind:action.dataset.agent7Contact?'contacted':'not_interesting',note:''});toast(action.dataset.agent7Contact?'Contatto registrato. Nessun messaggio inviato.':'Proposta eliminata. L’azienda non verrà riproposta.');await loadAgent6()}
 catch(error){toast(error.message)}finally{action.disabled=false}
});
document.addEventListener('input',e=>{if(e.target.id==='agent7-search'){agent7Search=e.target.value;agent6Offset=0;clearTimeout(agent7SearchTimer);agent7SearchTimer=setTimeout(()=>{if(agent7Mode==='WORKLIST')loadAgent6()},250)}});
document.addEventListener('change',e=>{if(e.target.id==='agent7-view'){agent7View=e.target.value;agent6Offset=0;for(const b of document.querySelectorAll('[data-agent7-view]'))b.setAttribute('aria-pressed',String(b.dataset.agent7View===agent7View));loadAgent6()}if(e.target.id==='agent7-flow'){agent7Flow=e.target.value;agent6Offset=0;loadAgent6()}});

function agent8CompanyDossier(d,hostId=d.id){
 const assessment=agentFollowupResolution(d.research_resolution,hostId)+agentCommercialAssessment(d.body);
 const c=d.company_dossier;if(!c)return assessment;
 return assessment+`<details class="panel" open><summary>Azienda · ${c.signals.length} richieste o segnali · ${c.flows.map(agent6FlowLabel).map(esc).join(', ')}</summary>
 <p class="small">Le prove sono raccolte insieme; ogni richiesta mantiene la propria valutazione. Un collegamento non dimostra un nuovo bisogno.</p>
 ${c.signals.map(s=>`<p><strong>${esc(s.title||'Segnale aziendale')}</strong> · ${esc(agent6Labels[s.saved_state]||s.saved_state)}<br>${esc(s.reason||'Da valutare')}<br>${link(s.url,'Fonte del segnale')} · Campagne ${s.campaigns.join(', ')}${s.record_id!==d.id?` · <button class="quiet" data-agent8-related="${s.record_id}" data-host="${hostId}">Apri questa valutazione</button>`:''}</p>`).join('')}
 <details><summary>Perché queste schede appartengono alla stessa azienda</summary>${c.links.map(l=>`<p class="small">Scheda ${l.record_id} · ${esc(({same_verified_official_domain:'Stesso dominio ufficiale verificato',same_published_legal_id:'Stessa partita IVA pubblicata nelle fonti ufficiali',conflicting_legal_identities_same_domain:'Dati societari in conflitto: collegamento limitato',unresolved_subject_no_company_merge:'Identità irrisolta: nessuna fusione aziendale'})[l.basis]||l.basis)}<br>${esc(l.domain||'Dominio non verificato')}${l.legal_id?' · '+esc(l.legal_id):''}${l.proofs.map(p=>` · ${link(p.url,'Prova societaria')}`).join('')}</p>`).join('')}</details>
 ${d.correction_history?.length?`<details><summary>Correzioni manuali (${d.correction_history.length})</summary>${d.correction_history.map(a=>`<p>${dt(a.created_at)} · ${esc(a.note)}<br>${Object.entries(a.changes).map(([k,v])=>`${esc(k)}: ${esc(v||'valore automatico ripristinato')}`).join(' · ')}</p>`).join('')}</details>`:''}</details>`
}

function agentCommercialAssessment(b){
 const a=b?.commercial_assessment;if(!a)return '';
 const labels={REQUESTING_EXTERNAL:'Cerca un professionista esterno',ACCEPTING_EXTERNAL:'Accetta collaborazioni esterne',SUPPLYING_SERVICES:'Propone i propri servizi',EMPLOYEE_ONLY:'Cerca esclusivamente dipendenti',TRAINING:'Formazione o corsi',COMPLETED_PROJECT:'Progetto già concluso',COMPANY_ACTIVITY:'Attività aziendale osservata',UNKNOWN:'Da verificare',FULL_PROJECT:'Progetto completo',COLLABORATION:'Collaborazione professionale',SMALL_TASK:'Piccolo intervento',CHECKED_ADEQUATE:'Soluzione esistente ritenuta adeguata',CHECKED_GAP:'Lacuna individuata nella soluzione esaminata',NOT_CHECKED:'Soluzione esistente da verificare'};
 const references=[...new Set([...(a.intent_facts||[]),...(a.scope_facts||[]),...(a.solution_facts||[])])].map(i=>b.facts?.[i]).filter(Boolean);
 return `<details class="agent8-assessment"><summary>Come è stata valutata l’opportunità</summary>
 ${b.verification_hold?`<p class="agent7-warning"><strong>Verifica non conclusa.</strong> La valutazione AI è conservata, ma il controllo richiesto non permette uno scarto commerciale definitivo. Questa scheda non è pronta da contattare.</p><p><strong>Da verificare:</strong> ${esc(b.verification_coverage?.question||b.next_verification||'Controllo funzionale del sito')}<br><strong>Interpretazione AI precedente:</strong> ${esc(b.ai_decision?.reason||'Non disponibile')}</p>`:''}
 <p class="small">Interpretazione AI delle prove consultate: non garantisce un incarico né un budget disponibile.</p>
 <p><strong>Situazione:</strong> ${esc(labels[a.intent]||'Da verificare')}<br><strong>Lavoro proponibile:</strong> ${esc(labels[a.scope]||'Da verificare')}<br><strong>Soluzione digitale:</strong> ${esc(labels[a.existing_solution]||'Da verificare')}</p>
 <p>${esc(a.interpretation)}</p>
 ${references.map(f=>`<blockquote>${esc(f.quote)}<footer>${link(f.url,'Prova originale')}</footer></blockquote>`).join('')}
 ${(a.objections||[]).length?`<p><strong>Obiezioni e limiti da valutare:</strong> ${esc(a.objections.join(' · '))}</p>`:''}
 ${(b.unattributed_contacts||[]).length?'<p class="small">Alcuni recapiti presenti nelle fonti non sono stati attribuiti al committente. Non sono proposti come canali di contatto.</p>':''}</details>`;
}

const agent8CorrectionOptions={opportunity_type:agent8Types,priority:{high:'Alta',medium:'Media',low:'Bassa'},relevance:{relevant:'Pertinente',irrelevant:'Non pertinente',uncertain:'Da approfondire'},commercial_fit:{high:'Alta',medium:'Media',low:'Bassa',unknown:'Sconosciuta'}};
function agent8RelatedProof(d){const b=d.body;return `<h4>Valutazione selezionata: ${esc(b.title||b.entity_name||'Richiesta da verificare')}</h4><p>${esc(agent6Labels[d.state]||d.state)} · ${esc(b.reason||'')}</p><p class="small">${link(b.url,'Fonte di questa richiesta')} · Consultata ${dt(b.checked_at)}</p>${(b.facts||[]).map(f=>`<p><strong>${esc(agent6Fields[f.field]||f.field)}</strong> · ${f.original?'Originale':'Indizio indicizzato'}<br>${esc(f.quote)}<br>${link(f.url,'Prova')} · ${f.document_start!=null?`caratteri ${f.document_start}–${f.document_end}`:'posizione non disponibile'}</p>`).join('')}<p><strong>Controprove:</strong> ${esc((b.counterevidence||[]).join(', ')||'Nessuna registrata: non implica assenza di rischi.')}</p>`}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-agent8-correct],[data-agent8-correction-save],[data-agent8-related]');if(!b)return;
 b.disabled=true;
 try{
  if(b.dataset.agent8Related){
   const d=await api('/agent6/records/'+b.dataset.agent8Related),host=$('#agent6-detail-'+b.dataset.host);
   host.innerHTML=agent8RelatedProof(d)+agent8CompanyDossier(d,b.dataset.host)+`<button data-agent6="review" data-id="${d.id}">Registra esito per questa richiesta</button><button data-agent8-correct="${d.id}">Correggi questa valutazione</button>${String(d.id)!==b.dataset.host?`<div id="agent6-detail-${d.id}"></div>`:''}`;return
  }
  const id=b.dataset.agent8Correct||b.dataset.agent8CorrectionSave;
  if(b.dataset.agent8Correct){
   const d=await api('/agent6/records/'+id),current=d.manual_corrections||{};
   $('#agent6-detail-'+id).innerHTML=`<div class="panel"><h4>Correggi la valutazione commerciale</h4><p class="small">Le correzioni non modificano le prove, non promuovono il candidato e non registrano un contatto. Per eliminarlo usa Elimina proposta.</p><div class="agent7-filters">${Object.entries({opportunity_type:'Tipo di opportunità',priority:'Priorità',relevance:'Pertinenza',commercial_fit:'Compatibilità commerciale'}).map(([k,label])=>`<label>${label}<select id="agent8-edit-${k}-${id}"><option value="">Mantieni valutazione automatica</option>${Object.entries(agent8CorrectionOptions[k]).map(([v,text])=>`<option value="${v}" ${current[k]?.value===v?'selected':''}>${text}</option>`).join('')}</select></label>`).join('')}</div><label>Motivazione<textarea id="agent8-edit-note-${id}" maxlength="2000" required></textarea></label><button data-agent8-correction-save="${id}">Salva correzioni</button></div>`;
  }else{
   const changes=Object.fromEntries(Object.keys(agent8CorrectionOptions).map(k=>[k,$(`#agent8-edit-${k}-${id}`).value||null]));
   await api(`/agent6/records/${id}/corrections`,{changes,note:$('#agent8-edit-note-'+id).value});toast('Correzioni salvate. Prove e storico conservati.');await loadAgent6()
  }
 }catch(error){toast(error.message)}finally{b.disabled=false}
});

function agent91Completion(b){
 const c=b.completion_queue;if(!c)return '';
 const names={entity:'Identità aziendale',official_domain:'Sito ufficiale',request:'Invito o richiesta',technical:'Ambito tecnico',contract:'Rapporto di collaborazione',contact:'Contatto pubblico',publication:'Data e attualità',geography:'Compatibilità territoriale',scope:'Perimetro del progetto',feasibility:'Fattibilità',closed:'Disponibilità ancora aperta',budget:'Budget dichiarato',contract_terms:'Condizioni della collaborazione'};
 const label=x=>esc(names[x]||x);
 return `<details class="agent8-audit" ${c.promising&&c.phase!=='qualified'?'open':''}><summary>${c.phase==='qualified'?'Qualifica completata · prove e limiti':c.promising?'Pista promettente · verifiche da completare':'Stato delle verifiche'}</summary><p><strong>Riscontri disponibili:</strong> ${c.completed_checks.length?c.completed_checks.map(label).join(', '):'Nessuno ancora verificato'}</p>${b.hypothesis?`<p><strong>Ipotesi da verificare:</strong> ${esc(b.hypothesis)}</p>`:''}<p><strong>Limiti:</strong> ${c.missing_checks.length?c.missing_checks.map(label).join(', '):'Consulta le prove e la copertura nel dossier.'}</p>${c.optional_unknowns?.length?`<p class="small"><strong>Non dichiarato, non obbligatorio:</strong> ${c.optional_unknowns.map(label).join(', ')}.</p>`:''}${b.kind==='AGENCY_PARTNERSHIP'?'<p class="small">Invito a collaborare: incarico attivo, compenso e volume di lavoro non confermati. Non è un contratto acquisito.</p>':''}${c.current_availability==='UNKNOWN'?'<p class="small">Disponibilità attuale non confermata. Il contatto pubblico non garantisce una commessa.</p>':''}${c.blocked_reason?`<p class="small">Verifica bloccata: ${esc(c.blocked_reason)}</p>`:''}</details>`;
}

function agent921Alignment(b){
 const a=b.commercial_alignment;if(!a)return '';
 const arrangement={PAID_DEVELOPMENT_OPPORTUNITY:'Sviluppo remunerato dichiarato',FREELANCE_COLLABORATION:'Collaborazione freelance · compenso da concordare',TECHNICAL_COFOUNDER_OPPORTUNITY:'Ruolo da cofounder · condizioni da chiarire',EQUITY_ONLY_OPPORTUNITY:'Solo equity · non è una commessa remunerata',UNCLEAR_ARRANGEMENT:'Accordo economico da chiarire',UNPAID_COLLABORATION:'Collaborazione dichiarata non retribuita',MIXED_COMPENSATION:'Compenso misto dichiarato · termini da verificare'};
 const affinity={HIGH_AFFINITY:'Alta affinità',POSSIBLE_AFFINITY:'Affinità possibile',UNKNOWN_AFFINITY:'Competenze da approfondire',CLEARLY_UNRELATED:'Attività non pertinente'};
 const levels={HIGH:'Alta',MEDIUM:'Media',LOW:'Bassa',SUPPORTED:'Sostenuto dalle prove',TO_EXPLORE:'Da approfondire',PARTIAL:'Parziali',UNKNOWN:'Non dimostrato'};
 return `<dl class="agent7-facts"><div><dt>Interesse commerciale</dt><dd>${esc(levels[a.COMMERCIAL_INTEREST]||a.COMMERCIAL_INTEREST)}<br>${esc(affinity[a.affinity.value])}</dd></div><div><dt>Solidità delle prove</dt><dd>${esc(levels[a.EVIDENCE_CONFIDENCE]||a.EVIDENCE_CONFIDENCE)}</dd></div><div><dt>Possibilità di contatto</dt><dd>${a.READY_FOR_OUTREACH?'Qualificata · canale pubblico disponibile':a.CONTACT_AVAILABLE?'Contatto disponibile · qualifica da completare':(b.observed_owner_contacts||[]).length?'Recapito generale disponibile · canale per questa richiesta da confermare':'Contatto pubblico mancante · qualifica indipendente'}</dd></div></dl><p class="small"><strong>Tipo di rapporto:</strong> ${esc(arrangement[a.arrangement]||a.arrangement)}</p>${agent921Startup(a.startup_profile)}${b.proposal_type==='COMPLETE_NEW_WEBSITE'?'<p><strong>Proposta:</strong> nuovo sito completo, da discutere con l’azienda. Nessuna richiesta di acquisto presunta.</p>':''}${['TECHNICAL_COFOUNDER_OPPORTUNITY','EQUITY_ONLY_OPPORTUNITY'].includes(a.arrangement)?'<p class="small">Opportunità imprenditoriale separata dalle commesse. Equity senza valore monetario attribuito; prodotto, founder, clienti, investimenti e impegno restano sconosciuti se non documentati.</p>':''}`;
}

function agent921Startup(profile){
 if(!profile)return '';
 const labels={idea:'Idea',problem:'Problema affrontato',product:'Prodotto previsto',stage:'Fase',founders:'Founder',business_model:'Modello di business',users_customers:'Utenti o clienti',investment:'Investimenti',commitment:'Impegno richiesto'};
 return `<details class="agent8-audit"><summary>Progetto imprenditoriale · dati disponibili</summary>${Object.entries(profile).map(([k,v])=>`<p><strong>${esc(labels[k]||k)}:</strong> ${v.status==='DOCUMENTED'?v.evidence.map(f=>`${esc(f.quote)} · ${link(f.url,'Fonte')}`).join('<br>'):'Non dichiarato nelle prove raccolte'}</p>`).join('')}</details>`;
}
