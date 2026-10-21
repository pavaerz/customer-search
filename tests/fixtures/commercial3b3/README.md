# Campagna 20 — prove storiche per 3B.3

`campaign20.json.gz`: snapshot read-only della campagna 20, acquisito il 17 ottobre 2026. Contiene 88 apparizioni, 23 revisioni, 7 registrazioni AI, coda/contatori e 61 pagine originali già nella cache locale. Le pagine corrispondono esattamente a URL e `checked_at` dei documenti salvati. Non sono stati acquisiti nuovi siti.

Il file non contiene chiavi API o impostazioni di autenticazione. Contiene i contatti aziendali pubblici presenti nelle pagine già raccolte; non pubblicarlo automaticamente. Gli output AI invalidi originali non furono conservati: non è possibile ricostruire la frase che causò ciascun errore.

Il replay è **parziale**: discovery, identità, filtro AI sui bundle storici e selezione browser. Non riproduce rete, tempi, nuovi budget, browser o risposte del modello. Non costituisce una nuova campagna né una misura di conversione.

Le fixture definite nel test Python sono dichiarate sintetiche. Il browser simulato del test di allocazione verifica solo pianificazione e quote; la suite browser distinta usa pagine locali controllate per misurare il renderer reale.
