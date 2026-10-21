# Approfondimenti reali successivi alla Campagna 52

Originali acquisiti con `CompanyWeb` e le protezioni dell'app, il 20 ottobre 2026 UTC / 21 ottobre in Italia. Nessuna nuova campagna nell'app.

- `originals.json.gz`: tre annunci singoli ApriamoInsieme, ricavati dalle schede della raccolta già incontrata nella 52. Sono proposte di cofondazione, non commesse pagate dimostrate.
- `sinfonia-page.json.gz`: pagina ufficiale corrente delle candidature spontanee di Sinfonialab, individuata con una query limitata al dominio già verificato. Non dimostra l'apertura della precedente posizione freelance.
- `receipts.json.gz`: input effettivi e tre risposte AI del primo passaggio, allora invalide. Conservati senza correggere gli output: servono a riprodurre i difetti di validazione, non a dichiarare risultati commerciali.

I test confrontano selezione precedente e nuova sullo stesso JobPosting: la frase che esclude lo stipendio deve restare insieme alle condizioni del round e al ruolo tecnico, entro 3.000 byte, con intervalli e hash originali. Le schede correlate e il riassunto automatico della piattaforma non entrano nella descrizione dell'annuncio.

Le verifiche geografiche richiedono citazioni nella proprietà del medesimo annuncio `applicantLocationRequirements` di tipo Country. Un indirizzo dell'editore o un codice IT altrove non sono sufficienti.

Le risposte simulate nei test di coda sono esplicitamente doppioni offline del protocollo, non opportunità reali. Ricevute live, costi e revisione separata: `implementation-report/commercial-objective/followup53/`.
