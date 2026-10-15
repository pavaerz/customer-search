# Pulizia risultati e navigazione — 13 ottobre 2026

Intervento richiesto esplicitamente dall’utente: rimuovere i risultati precedenti e semplificare il menu, con icone distinte.

## Navigazione

Tre destinazioni: **Ricerca**, **Contatti**, **Impostazioni**. Icone uniche (lente, persone, regolazioni) e una sola voce principale attiva. Aziende e Privati sono filtri nella Ricerca. Contatti contiene Bacheca, Elenco e Statistiche. La cronologia è accessibile nei dettagli della Ricerca. Archivio e Storico non occupano più voci separate del menu.

## Dati

Backup verificato: `data/backups/20261013T175007605903Z/`. Server e worker fermati prima della pulizia; operazione transazionale con verifica dei riferimenti.

Rimosse dalle viste operative 21 schede, 132 record precedenti, 25 esecuzioni storiche e una campagna sospesa con 819 attività in coda. Prove, audit, interazioni, note e dati originali sono conservati sia nel backup sia nell’archivio interno `workspace_archive`, non esposto dalle API dell’app. L’operazione non equivale a una cancellazione definitiva dei dati personali.

Conservate identità, categorie manuali, aziende già contattate, esclusioni e proposte eliminate. I contatti dell’archivio precedente sono trasferiti nella memoria prima della pulizia. La reimportazione automatica dei risultati precedenti è disabilitata dopo un reset, anche al riavvio. Configurazioni, credenziali e contatori dei provider invariati. Le nuove campagne restano utilizzabili normalmente.

La procedura amministrativa è in `scripts/reset_results.py`; richiede un backup verificato e rifiuta campagne attive. Non è una nuova azione automatica o un pulsante distruttivo nell’interfaccia. Per ripristinare l’intero stato precedente, a server fermo si può ripristinare il database dal backup verificato; il ripristino totale sostituirebbe gli eventuali nuovi dati successivi al reset.

## Verifica

147 test Python superati, inclusi sei nuovi casi: archiviazione completa, memoria commerciale, mancata reimportazione dopo riavvio, blocco durante ricerca attiva, nuove campagne dopo reset e rollback su riferimenti inattesi.

Test browser su 48 combinazioni di otto viste e sei larghezze (320–1920 px), menu con esattamente tre icone distinte e una voce attiva, dossier desktop/mobile, mouse e touch, filtri, salvataggi e gestione degli errori. Nessun errore JavaScript nei casi verificati. App reale riavviata: schede, campagne, archivio visibile e contatori a zero. Nessuna ricerca commerciale o email avviata dal collaudo.

Conteggi e verifica SQLite in [WORKSPACE-RESET-4.0.json](WORKSPACE-RESET-4.0.json).
