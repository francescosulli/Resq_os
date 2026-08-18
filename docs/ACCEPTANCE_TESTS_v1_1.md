# ResQ UX 1.1 — Acceptance Test Plan

## Input equivalence
- Per ogni lane attiva: touch e tasto fisico devono inviare lo stesso semantic event.
- Un press fisico deve evidenziare la card corrispondente.
- Un touch deve produrre lo stesso feedback della pressione fisica.
- Lane inattive: nessuna card, nessuna hit area, tasto fisico disabilitato.
- Nessuno stato può avere meno di 1 o più di 3 primary controls.
- Il ButtonController accetta solo LEFT, CENTER e RIGHT; nessun alias semantico.
- Touch e hardware condividono il debounce e non producono doppi eventi.
- Nessuna card Emergency mostra i numeri 1, 2 o 3.

## RIPETI
- Se center è libero, EV_REPEAT può occupare la corsia centrale.
- Se center è occupato, RIPETI compare nell'utility header.
- RIPETI non modifica lo stato clinico.
- Ingresso stato e RIPETI producono un comando SPEAK reale verso SpeechSynthesis.
- Il cambio stato ferma l'istruzione precedente prima di pronunciare la nuova.
- RIPETI è disabilitato durante OPERATOR_PRIORITY.

## 112
- CONDITIONAL non deve apparire come “chiama ora”.
- CALL NOW deve essere dominato dal numero 112, cinque sole voci di briefing e una frase finale.
- Dopo HO CHIAMATO e nelle azioni critiche il pannello deve essere compatto.
- La call briefing mostra solo dati osservati; i campi ignoti restano prompt, mai valori inventati.
- OPERATOR_PRIORITY sospende la voce ResQ concorrente.
- Il flow visivo continua durante l'operatore.
- Il metronomo CPR continua in operator priority con ducking.

## RCP
- ADULT_CPR, ADULT_CPR_LOOP, PED_CPR, PED_CPR_COMP_ONLY: metronomo audio/visivo attivo.
- Target nominale 110 bpm (periodo nominale ~545.45 ms).
- Uscendo dallo stato CPR il metronomo si arresta immediatamente.
- PED_5_BREATHS e AED_USE non devono avere il metronomo compressioni.
- ADULT_CPR e ADULT_CPR_LOOP usano LEFT per DAE DISPONIBILE, con evento identico
  su touch e pulsante fisico.
- EV_AED_AVAILABLE porta direttamente ad AED_USE senza richiedere CONTINUA.
- CONTINUA da ADULT_CPR mantiene la RCP entrando in ADULT_CPR_LOOP.
- Dopo AED_USE la RCP riparte con metronomo, LEFT DAE viene disattivato e compare
  lo stato passivo DAE PRESENTE.
- PED_CPR e PED_CPR_COMP_ONLY mantengono un reminder passivo finché non sono
  approvati ingresso e ritorno DAE pediatrici.
- Nessuna nuova transizione clinica / nessuna gestione automatica 30:2.

## Colori/accessibilità
- Ogni primary control ha testo visibile.
- Nessun significato dipende solo dal colore.
- Contrasto testo/sfondo target >= 4.5:1.
- Nelle valutazioni NO e SÌ sono danger, NON SO è warning.
- Le scelte categoriali sono neutral.
- Nelle azioni FATTO è success, NON TROVO è danger e RIPETI è support.
- Verificare in scala di grigi e con simulazione di principali deficit di visione cromatica.

## Regression
- Tutti i test della 1.0 devono continuare a passare.
- Tutti i 62 stati devono avere mapping UX valido.
- Flow 1.1 e State Machine 1.1 devono differire dalla 1.0 solo per il delta
  RCP/DAE documentato; Automotive BOM 1.0 deve rimanere byte-identica.
- Verificare i dieci screenshot obbligatori a 720 × 1280 e una regressione
  1280 × 720 senza overflow.
- Eseguire l'intera suite sia dal repository sia dallo ZIP estratto.
