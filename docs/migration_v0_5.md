# Migrazione ResQ beta -> handoff v0.5

## Principio

La migrazione riusa il server Python, gli adapter hardware, il kiosk e la UI
web esistenti. La logica del vecchio `EmergencyFlow` non viene trasposta: stati,
testi, pulsanti e target clinici provengono direttamente dal JSON v0.5.

Nessuna incoerenza dell'handoff viene risolta modificando prompt o target.

## Mapping

| Beta esistente | Ruolo v0.5 | Esito |
| --- | --- | --- |
| `main.py` | bootstrap e kiosk | riusato |
| server in `resq_core/app.py` | API eventi + statici | riusato e adattato |
| `EmergencyFlow` | coordinatore applicativo | mantenuto, senza decisioni cliniche |
| `StateManager` in memoria | snapshot persistente + event log | esteso |
| `ProtocolLoader` | loader legacy | escluso dal runtime v0.5 |
| `protocols/*.json` | protocolli legacy | conservati, non eseguiti |
| `hardware/buttons.py` | adapter 3 soft-key | adattato |
| `hardware/leds.py` | output `LEDCommand` | riusato tramite `MaterialService` |
| `hardware/audio.py` | output audio/metronomo | riusato tramite `UIAudioService` |
| `hardware/nfc.py` | refill/manutenzione | riusato fuori dal flusso clinico |
| `static/app.js` | renderer passivo dello snapshot | adattato |

## Confini implementati

### Clinical State Machine

- Stato e transizioni provengono da `ResQ_flow_nodes_v0_5.json`.
- Un evento e' accettato solo se corrisponde a uno dei tre pulsanti dello stato.
- Il motore non accede a UI, LED, audio, inventario, rete o 112.
- `NON SO` segue il target prudenziale gia' dichiarato nel JSON.

### Coordinatore

`EmergencyFlow` valida prima l'evento nel motore e solo dopo inoltra gli effetti
ai servizi. Eventi come ripetizione audio e stato dell'operatore non cambiano lo
stato clinico.

### 112

`Call112Service` implementa gli stati YAML e non effettua chiamate autonome.
`OPERATOR_PRIORITY` e' esposto separatamente alla UI; il banner non viene
mostrato nel post-evento.

### Materiali e LED

`MaterialService` risolve gli ID semantici con il catalogo JSON e invia la zona
all'adapter LED esistente. La UI non conosce pin GPIO o slot fisici.

### Inventario

Il prelievo produce `PENDING_USE`. Le quantita' sono conteggiate solo dopo
`CONFERMA` in `POST_EVENT_INVENTORY`. Home non cancella i dati finalizzati.

### ResQ Connect

`AppSyncService` mantiene una coda locale `SYNC_PENDING`, indipendente dalla
Clinical State Machine. Connessione e sincronizzazione non bloccano emergenza.

### UI e pulsanti

Il frontend renderizza lo snapshot del backend. Le posizioni sinistra, centro e
destra sono stabili e i pulsanti fisici inviano solo la posizione, non una
decisione clinica.

## Persistenza e recupero

Ogni evento salva uno snapshot atomico e una riga JSONL con sessione, evento,
stato precedente, stato successivo, richiesta materiale e stato 112. Al riavvio
un intervento attivo non riparte silenziosamente: serve `RIPRENDI` o `ANNULLA`.

## Questioni aperte nell'handoff

1. La sequenza abbreviata descritta nella documentazione di consegna non include
   tutti i passaggi presenti nel JSON. Il runtime segue il JSON completo, quindi
   include sicurezza, multi-casualty, emorragia, responsivita', eta', respiro e
   trauma prima del monitoraggio.
2. `PROBLEMA`, `RIPETI`, `MOSTRA`, `CORREGGI`, `RIVEDI` ed `ESCI` spesso non hanno
   una voce in `next`. Sono trattati come azioni di servizio senza transizione;
   `ESCI` chiude solo da `EM_START`. In particolare l'handoff non definisce come
   `CORREGGI` debba modificare l'inventario.
3. Il YAML elenca gli eventi generali ma non un evento per scelte a tre vie come
   `ADULTO/BAMBINO/LATTANTE` o `TRAUMA/USTIONE/MALORE`. L'adapter genera ID
   deterministici `EV_SELECT_*` dal testo del pulsante JSON. Il target continua a
   essere letto esclusivamente da `next` nel JSON.
4. Il catalogo materiali non contiene nomi localizzati. La UI usa una mappa di
   sola presentazione; ID, zona, inventario e scelta del materiale restano quelli
   del JSON.
5. Non sono specificati pin GPIO, indirizzi dei LED o corrispondenza tra zona
   semantica e vano fisico. L'implementazione inoltra la zona all'adapter simulato.
6. Non e' definito il protocollo ResQ Connect. La beta conserva il payload
   offline, ma non inventa endpoint, autenticazione o regole di merge.
7. Il YAML elenca il ramo BOOT ma non relativi eventi e transizioni. La beta
   esegue validazione specifiche e inizializzazione adapter prima di IDLE, senza
   inventare una state machine BOOT interattiva.

Questi punti richiedono una decisione di prodotto/clinica nell'handoff prima di
estendere il comportamento.
