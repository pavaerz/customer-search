# Campagna 41: input congelati per il replay 9.2

`campaign41.json.gz` contiene i record storici 781 (NHW Consulting) e 756
(Punto Infissi), i payload dei task con l’HTML originale, la risposta AI già
validata per NHW, le query effettivamente eseguite, i piani e gli audit salvati.
Origine: snapshot in sola lettura della Campagna 41 e relativo ledger SQLite.
Non contiene risultati attesi costruiti al posto delle prove.

Il replay non visita questi URL e non interroga modelli. La risposta necessaria
al futuro approfondimento di NHW non esiste: attualità, incarico, compenso e
volume rimangono sconosciuti. Per Punto Infissi non esistono un browser audit
e una verifica commerciale originali: il replay può correggere la preselezione,
senza simulare una qualifica.

Le altre regressioni usano le fixture delle campagne 38–40 già conservate in
`agent91` e nei test precedenti. Gli scenari di coda e i cinque flussi di
`test_agent7_multiflow` sono sintetici e non rappresentano clienti reali.
