# Bandi: confronto automatico dei requisiti

La sezione Bandi resta separata da ricerca clienti e CRM. Il pulsante **Ricerca bandi** salva il profilo, aggiorna le fonti ufficiali e analizza le misure, incluse quelle già raccolte nella sessione precedente.

Ogni scheda mostra uno degli esiti:

- **Requisiti soddisfatti**: regole estratte e revisionate, fonti aggiornate oggi, sportello attivo e nessun requisito o documento irrisolto. Confronto con i dati dichiarati, non concessione del contributo.
- **Escluso per il tuo profilo**: almeno una condizione necessaria non soddisfatta, oppure sportello chiuso, con citazione e fonte.
- **Mi serve un tuo dato**: domanda specifica legata a un requisito, senza chiedere di interpretare il bando. Salvataggio del profilo o delle risposte ricalcola gli esiti.
- **Analisi non conclusa**: problemi di lettura, condizioni complesse non rappresentabili, fonti discordanti o interpretazione locale non convalidata. Non viene attribuita compatibilità positiva.

Le schede precedenti, prive di documenti completi, sono indicate come **Da analizzare**. Non vengono promosse automaticamente. La scheda ON esistente è stata aggiornata con il riscontro ufficiale che esclude le ditte individuali.

## Come funziona

Il client HTTP protetto legge la scheda e i collegamenti a requisiti, FAQ, normativa e allegati. Il lettore PDF locale (`pypdf`) conserva testo e provenienza; PDF senza testo, cifrati o oltre i limiti tecnici vengono segnalati. Nessuna disattivazione dei controlli sui certificati o sulle reti private.

Il modello Qwen locale estrae condizioni strutturate e le rivede sul testo. Ogni citazione deve esistere nel documento; campi e operatori devono essere validi e coerenti con il contenuto della citazione. Il vocabolario dei campi è ristretto a quelli menzionati nel documento, per evitare requisiti inventati. La decisione finale usa confronti deterministici (forme giuridiche, territori, ATECO, date, importi, dati dichiarati). Assenza di un dato non equivale a requisito soddisfatto. Condizioni OR tra campi, eccezioni o composizioni societarie complesse bloccano la conclusione positiva.

Le dichiarazioni aggiuntive sono legate al testo e all’impronta della fonte, modificabili nelle schede. Una variazione della fonte richiede una nuova conferma. Regime fiscale e altri dati personali non vengono dedotti dalla P.IVA. Il controllo P.IVA è solo formale. Nessun profilo è inviato a servizi esterni: l’analisi avviene localmente.

Copertura: cataloghi Invitalia, Regione Veneto e CCIAA Padova secondo il territorio dichiarato; approfondimenti ufficiali collegati, inclusi Gazzetta Ufficiale, EUR-Lex e MIMIT. Non è una copertura esaustiva di tutti gli incentivi italiani. Due livelli di collegamenti, fino a 12 documenti per misura, PDF fino a 8 MB / 80 pagine / 300.000 caratteri: raggiungere un limite impedisce l’esito positivo. Nessun esito positivo quando il modello non è disponibile o la revisione fallisce. Un’esclusione testuale inequivocabile può essere dimostrata anche senza modello.

## Dati, sicurezza e avvio

Avvio invariato: `.venv/bin/python app.py`, poi http://127.0.0.1:8765. Dipendenze: `pip install -r requirements.txt` nell’ambiente virtuale. Per il modello locale vedere README e `scripts/setup_ollama.py`.

Nessuna modifica distruttiva allo schema. Campi aggiunti nel profilo JSON; fonti, regole e valutazione nelle schede. Gli endpoint applicano Host/Origin/CSRF. Stop invalida il token del worker prima di terminarlo e conserva i risultati precedenti. Il profilo aggiornato viene confrontato con le prove conservate; dopo il cambio di giorno occorre aggiornare le fonti per concludere positivamente.

Backup precedente: `data/backups/20261013T200223003514Z`; migrazione ripetibile e ripristino verificati su copia (`migration-grant-eligibility.json`).

## Verifica del 13 ottobre 2026

- Caso reale ON: esclusione della ditta individuale dimostrata nelle FAQ ufficiali (`grant-eligibility-pilot.json`). Gli allegati non necessari a dimostrare tale esclusione non costituiscono prova di una valutazione completa per altre forme giuridiche.
- Modello locale: dopo due prove conservative fallite, restrizione dei campi al testo e controlli semantici; caso sintetico minimo correttamente estratto, revisionato e confrontato (`grant-model-check.json`). Il caso sintetico non è un bando reale né una prova di accuratezza generale.
- Test su citazioni inventate, requisiti mancanti, importi ignoti, scadenze discordanti, fonti obsolete, OR, esclusioni con deroghe, domande e correzione delle risposte, PDF e sicurezza.
- Browser a 390 e 1440 px: salvataggio, avvio/Stop, risposta e ricalcolo, filtri, nessun overflow o errore JavaScript. Dati di collaudo soltanto in database temporanei.

L’ente resta responsabile della valutazione della domanda. L’app confronta i requisiti documentati; non garantisce fondi, approvazione o valutazioni discrezionali sul progetto.
