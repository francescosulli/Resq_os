# Pediatric AED Gap v1.1

> Stato: chiuso dal Clinical Flow 1.2. Questo documento resta come audit storico
> del comportamento 1.1; il delta approvato e' in
> `CHANGELOG_Flow_v1_1_to_v1_2.md`.

## Ambito

Questo documento registra un gap clinico-architetturale della release 1.1. Non
introduce nuove istruzioni, eventi o transizioni e non costituisce una decisione
clinica. Il Clinical Flow 1.1 resta invariato.

## Comportamento attuale

- `PED_CPR` mostra il reminder passivo `DAE APPENA DISPONIBILE`.
- `PED_CPR_COMP_ONLY` mostra lo stesso reminder passivo.
- Il reminder non e' una soft-key, non occupa una lane fisica e non emette eventi.
- `EV_AED_AVAILABLE` e' valido esclusivamente in `ADULT_CPR` e
  `ADULT_CPR_LOOP`.
- `AED_USE -> FATTO` ritorna oggi a `ADULT_CPR_LOOP`.

## Problema aperto

Il DAE e' menzionato nei prompt pediatrici, ma Flow 1.1 non definisce:

- un ingresso DAE parallelo specifico per `PED_CPR` o `PED_CPR_COMP_ONLY`;
- il mantenimento del contesto pediatrico durante l'uso del DAE;
- il corretto stato di ritorno per ciascuna modalita' RCP pediatrica;
- eventuali differenze operative dipendenti da eta' o contesto.

Collegare direttamente uno stato pediatrico all'attuale `AED_USE` farebbe
ritornare il sistema a `ADULT_CPR_LOOP`; questa scorciatoia non e' accettabile.

## Opzioni architetturali da sottoporre ad approvazione clinica

1. `AED_USE` context-aware con un `return_state` esplicito e validato. Riduce gli
   stati duplicati, ma richiede un contratto forte su ingresso, persistenza e
   recovery del target di ritorno.
2. Stato DAE pediatrico dedicato. Rende espliciti prompt e ritorni pediatrici,
   ma duplica parte della struttura e richiede source-of-truth clinici completi.
3. Transizione DAE parametrica con continuazione registrata dal motore. Mantiene
   una singola UI DAE, ma amplia la semantica della Clinical State Machine e deve
   essere definita nella relativa specifica.

Nessuna opzione viene scelta in questa patch. Prima dell'implementazione servono
approvazione clinica e aggiornamento coordinato di Clinical Flow, State Machine,
prompt, ritorni e test di regressione.

## Requisiti minimi per la futura decisione

- definire l'evento ammesso da entrambi gli stati pediatrici;
- definire il ritorno corretto a `PED_CPR` o `PED_CPR_COMP_ONLY`;
- preservare eta', stato 112, metronomo e recovery dopo riavvio;
- impedire ritorni accidentali al percorso adulto;
- mantenere il DAE come dispositivo che guida l'utente, senza introdurre
  decisioni autonome sullo shock.

## Fonti cliniche

Questa analisi e' deliberatamente solo architetturale. Non sono state usate
fonti cliniche per scegliere un comportamento: la scelta resta sospesa e dovra'
essere validata separatamente sui source-of-truth clinici approvati.
