# Campagna 45: discovery osservata

`discovery.json` è un estratto delle metriche della Campagna 45, conclusa il
20 ottobre 2026. Conserva le sei query eseguite, i conteggi osservati, i 14 URL
con le decisioni registrate e i limiti AI. L'hash del file di provenienza è
incluso. Non contiene credenziali, HTML inventato o opportunità sintetiche.

`test_objective_campaign45.py` usa questi input per verificare la preparazione
delle query e l'esclusione delle pagine-indice. Le prove di scheduling usano
invece task sintetici su database temporanei: riproducono la distribuzione
due flussi con sette URL e tre flussi con query vuote, non risultati commerciali.
Nessuna API, inferenza o pagina esterna viene consultata.

Il replay non misura quanti risultati otterrebbero le query modificate. Gli
esiti storici della Campagna 45 restano invariati.

`news-originals.json.gz` conserva sei HTML pubblici già acquisiti nei task
7426–7431: URL, data di consultazione, stato e contenuto. Non sono stati
riscaricati. Il replay `test_objective_source_context45.py` verifica la selezione
di testo e link, non simula nuove opportunità. SHA-256 del fixture:
`c242abe67dd61ff75526c1d9ff6423cd2c98237ceb9874a476c65a4f199792e3`.

Stesso evento non implica stesso contenuto: alcune pagine nominano aziende
diverse. Il fixture non attribuisce a queste aziende un bisogno digitale.

`owner-original.json.gz` è l'HTML pubblico già salvato nel task 7440, sul sito
Rechsteiner. Il replay dei nomi usa anche le citazioni/decisione della scheda
1212 in `partial-browser.json`. Verifica il collegamento esplicito tra marchio
e titolare, senza nuove inferenze o promozioni commerciali.
