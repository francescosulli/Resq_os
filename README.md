# ResQ Prototype Architecture 1.1

ResQ e' una web app locale per Raspberry Pi 5 e display touch da 9 pollici. La
release esegue il Flow 1.2, risolve i presidi fisici tramite la BOM Automotive
v1.0 e applica lo strato UX & Human Factors 1.1. Il delta clinico rispetto al
Flow 1.1 chiude il solo percorso DAE parallelo durante la RCP pediatrica.

Versioni: ResQ Prototype Architecture 1.1, Flow 1.2, State Machine 1.2,
Automotive BOM 1.0 e UX & Human Factors 1.1. Il tag candidato e'
`resq-prototype-v1.1`. ResQ Connect e' local-first; il trasporto
Bluetooth/Wi-Fi non e' implementato in questa release. Il flow ha stato
`prototype_clinical_flow_v1_2_not_clinically_certified`: il prototipo non e'
clinicamente certificato, non e' un dispositivo medico e non sostituisce
formazione, 112 o personale sanitario.

La fonte unica dei metadata software e degli hash congelati e'
`config/release.json`. Il runtime e `GET /api/spec` espongono da questo file:
Product `ResQ`, Release `Prototype Architecture 1.1`, Clinical Flow `1.2`,
State Machine `1.2`, Automotive BOM `1.0` e UX & Human Factors `1.1`.

## Source of truth

Il runtime carica insieme:

- `config/handoff/ResQ_flow_nodes_v1_2.json`: 62 stati, prompt, soft-key,
  transizioni e gli ingressi DAE paralleli adulto e pediatrico;
- `config/handoff/ResQ_state_machine_spec_v1_2.yaml`: architettura, servizi,
  contratto `EV_AED_AVAILABLE`, `aed_return_state` e invarianti;
- `config/handoff/ResQ_Automotive_BOM_v1_0.yaml`: 21 SKU, 14 MaterialRequest,
  quantita', compartimenti, slot, fallback e 5 LED di zona.
- `config/handoff/ResQ_UX_spec_v1_1.yaml`: mapping dei 62 stati sulle tre
  corsie fisiche/touch, etichette, ruoli colore e posizione di `RIPETI`;
- `config/handoff/ResQ_UI_tokens_v1_1.yaml`: layout portrait, feedback e token
  semantici;
- `config/handoff/ResQ_112_UX_v1_1.yaml`: presentazione 112 e contesto di
  briefing osservazionale;
- `config/handoff/ResQ_CPR_metronome_v1_1.yaml`: cadenza audio/visiva a 110 bpm.

`HandoffSpecLoader` blocca l'avvio se versioni, target, MaterialRequest, SKU,
zone o servizi non sono coerenti. Controlla inoltre che ogni stato abbia al
massimo una MaterialRequest e una zona LED e che il flow non contenga campi
fisici `sku`, `slot` o `led_id`.

`UXSpecLoader` convalida i quattro file 1.1 contro i tre source-of-truth
clinici: stesso insieme di 62 stati, stessi eventi e policy 112, da uno a tre
controlli attivi, colori accessibili e metronomo limitato ai quattro stati CPR
previsti.

I file v0.5, Flow 1.0/1.1 e i vecchi `protocols/*.json` restano nel repository come
storico, ma non sono eseguiti dal runtime. I tre nomi file caricabili e i relativi
SHA-256 sono dichiarati in `config/release.json` e verificati a ogni avvio; non
esiste fallback automatico verso configurazioni precedenti.

## Architettura

```text
UI / API / tre pulsanti fisici
             |
         eventi semantici
             |
      EmergencyFlow
             |
             +-- ClinicalStateMachine   target dal Flow 1.2 e contratto SM 1.2
             +-- UXSpec                 presentazione e controlli 1.1
             +-- MaterialService        MaterialRequest -> BOM resolver
             +-- InventoryService       stato operativo della valigetta
             |      +-- InventoryInstance  lotto/scadenza/quantita'/stato
             +-- Call112Service         stato chiamata/priorita'
             +-- EmergencyBriefContext  sole osservazioni gia' raccolte
             +-- UIAudioService         ciclo voce, repeat e metronomo
             +-- AppSyncService         coda offline ResQ Connect
             +-- StateManager           snapshot + event log JSONL
```

La `ClinicalStateMachine` non importa la BOM e non conosce SKU, slot o ID LED.
`MaterialService` prova in ordine `preferred` e `fallback` della BOM. Se
l'utente preme `NON TROVO` e un altro SKU e' disponibile, il flow resta nello
stesso stato e cambia solo il presidio fisico. Il ramo clinico `NON TROVO` viene
attraversato soltanto dopo l'esaurimento dei candidati BOM.

Il mapping incrementale completo e le questioni aperte sono in
`docs/migration_v1_0.md`.

## Avvio locale

```bash
python3 -m pip install -r requirements.txt
python3 main.py --port 8080 --open-browser
```

Il bind predefinito e' `127.0.0.1`: `python3 main.py` non espone il prototipo
sulla rete. Solo per sviluppo su una LAN fidata, l'ascolto su tutte le
interfacce deve essere richiesto esplicitamente:

```bash
python3 main.py --host 0.0.0.0 --port 8080
```

## Test

```bash
PYTHONPYCACHEPREFIX=/tmp/resq_pycache \
  python3 -m unittest discover -s tests -v
```

La suite copre i sette source of truth, tutti i collegamenti dei 62 stati, BLS
adulto e pediatrico, mapping corsie 1.1, pannelli 112, metronomo, fallback BOM,
inventario e scadenze, stati kit, session ID finale, sync locale, persistenza
Flow 1.2, migrazione prudente da v0.5 e recovery degli snapshot Flow 1.0/1.1.

## Materiali e inventario

Durante l'emergenza un presidio risolto contiene:

- MaterialRequest semantica;
- SKU e nome italiano dalla BOM;
- quantita';
- compartimento, slot e LED di zona;
- indicazione se e' stato usato un fallback BOM.

Il prelievo aggiunge lo SKU a `PENDING_USE` senza decrementare lo stock. Nel
post-evento `CORREGGI` abilita i controlli quantita' per SKU. Solo `CONFERMA`
decrementa lo stock, aggiorna gli usi e crea la coda non bloccante per ResQ
Connect.

La BOM resta il catalogo immutabile delle quantita' previste. Al primo avvio,
se lo snapshot non esiste, ogni SKU nasce con quantita' disponibile uguale alla
quantita' prevista dalla BOM. Lotto e scadenza restano intenzionalmente ignoti:
sono segnalati in Manutenzione e non vengono inventati dal software. Ogni
valigetta ha
un `InventoryInstance` separato per SKU con quantita' disponibile, lotto,
scadenza, data di inserimento, timestamp e stato. La Manutenzione calcola lo
stato generale e per zona: `READY`, `MAINTENANCE`, `REFILL_REQUIRED` o
`NON_OPERATIONAL`. Questa traduzione e' centralizzata in `ReadinessPolicy`; la
policy 1.0 mantiene un presidio critico mancante come `NON_OPERATIONAL`, ma il
mapping e' configurabile per una release futura.

`PPE_GLOVES` usa due unita' BOM, cioe' un paio. `NON TROVO` marca lo SKU
risolto `SUSPECTED_MISSING`, lo rende non disponibile e poi richiede al
`MaterialService` il fallback BOM. Nel post-evento il sospetto puo' essere
confermato come mancante o corretto.

La barriera CPR pediatrica e' opzionale: sia `SALTA` sia `PRESO` portano a
`PED_5_BREATHS`. La sua indisponibilita' non salta ventilazioni o altre azioni
cliniche.

## Persistenza

```text
data/session_state.json
data/session_events.jsonl
```

Lo schema runtime corrente e' `3` e salva anche versione BOM, Inventory
Instance, SKU pendenti o sospetti, risoluzione materiale e coda sync. Il
payload ResQ Connect contiene le istanze complete, un timestamp di coda e una
chiave di idempotenza. Snapshot e conferme vengono sostituiti atomicamente; una
coda `SYNC_PENDING` sopravvive al riavvio e non blocca Emergency Mode.

La chiusura completa prima in memoria il reset dei servizi session-scoped e poi
produce un solo snapshot `IDLE`. L'evento conclusivo, con il `session_id`
originale, e' incluso nel commit e riversato nel journal mediante `event_id`:
se il processo si interrompe tra le due operazioni, il riavvio lo riconcilia
senza duplicarlo.

I dati runtime non fanno parte del pacchetto installato. Per riportare una
installazione di sviluppo allo stato iniziale, a servizio fermo e fuori da
Emergency Mode:

```bash
python3 reset_runtime_state.py --confirm-reset
```

Il comando elimina sessione, log eventi, cache e coda sync, quindi ricrea le
Inventory Instance dalla BOM v1.0. Rifiuta il reset se trova un intervento
attivo o recuperabile.

Uno snapshot v0.5 in `IDLE` viene migrato al runtime corrente: gli usi semantici gia'
finalizzati vengono associati allo SKU preferito BOM e lo stock viene
ricalcolato. Un intervento clinico v0.5 ancora attivo non viene convertito ne'
ripreso automaticamente: la UI richiede l'annullamento esplicito prima di
iniziare una sessione Flow 1.2. Uno snapshot Flow 1.0 o 1.1 viene invece recuperato
direttamente, preservando Inventory Instance e servizi, e risalvato come 1.2.

## Display target

La UI e' ottimizzata per il monitor `1280 x 720` montato verticalmente. Se
Chromium espone una viewport landscape, `display-rotate-90` disegna un canvas
logico `720 x 1280`; se Raspberry espone gia' una viewport portrait, il layout
si adatta direttamente.

Le tre soft-key mantengono sempre le posizioni sinistra, centro e destra. La UI
renderizza soltanto le corsie attive; touch e tasto fisico producono lo stesso
evento semantico e lo stesso feedback. La UI mostra nome BOM, compartimento e
slot del solo presidio attivo.

In Emergency Mode i tasti non mostrano numeri o informazioni di release. Le
quattro modalita' di presentazione (`EVALUATION`, `ACTION`, `CRITICAL_ACTION`,
`CALL_112`) derivano dalla UX spec e non aggiungono stati clinici. Le risposte
`NO` e `SI` delle valutazioni hanno lo stesso ruolo cromatico danger; il colore
esprime invece la funzione nelle azioni operative.

`AudioGuideService` gestisce ingresso stato, stop, nuova istruzione, `RIPETI` e
sospensione durante operator priority. Il browser pronuncia il prompt italiano
con Web Speech `SpeechSynthesis`; il servizio resta separato dalla Clinical
State Machine e puo' essere sostituito da un backend audio hardware. Il
metronomo CPR usa un clock Web Audio nominale a 110 bpm, mostra `100-120/min`,
si arresta uscendo dalla CPR e resta attivo a volume ridotto durante l'operatore
112.

Le schermate CPR espongono `DAE DISPONIBILE` come evento parallelo equivalente
su touch e pulsante fisico: `LEFT` nell'adulto e in `PED_CPR_COMP_ONLY`, `CENTER`
in `PED_CPR`. Tutti i percorsi condividono `AED_USE`; `aed_return_state` riporta
esattamente al loop RCP di provenienza e riattiva il metronomo. Il flag operativo
`aed_present` disattiva la CTA e mostra `DAE PRESENTE`, senza interpretare ritmo
o necessita' di shock. Il delta e' documentato in
`docs/CHANGELOG_Flow_v1_1_to_v1_2.md`.

## API locale

- `GET /api/state`: stato clinico e snapshot servizi;
- `GET /api/spec`: versioni Flow/BOM, numero stati e SKU;
- `GET /api/input-feedback`: ultimo feedback dei tasti fisici;
- `POST /api/emergency/start`: nuova sessione;
- `POST /api/events`: evento semantico;
- `POST /api/audio/repeat`: ripete l'istruzione senza cambiare stato;
- `POST /api/buttons/{left|center|right}`: adapter tasti fisici;
- `POST /api/inventory/correct`: correzione locale `{sku, quantity}` nel
  post-evento;
- `POST /api/inventory/instance`: aggiorna quantita', stato, lotto, scadenza e
  data di inserimento dalla Manutenzione;
- `POST /api/session/resume` e `/api/session/discard`: recupero sessione;
- `POST /api/diagnostics/{led|audio|refill_nfc|status}`: manutenzione locale.

## Raspberry Pi

Prima installazione:

```bash
chmod +x install.sh update.sh
sudo ./install.sh
sudo systemctl start resq.service
```

Aggiornamento dentro `/opt/resq`:

```bash
sudo ./update.sh
```

## Artefatto release

```bash
python3 scripts/build_release.py
```

Il comando genera `dist/ResQ_Prototype_Architecture_v1.1.zip` in modo
riproducibile. Lo ZIP usa una lista di inclusione controllata, contiene codice,
installer, test, documentazione, metadata, Flow/State Machine 1.2, la BOM 1.0
e i quattro source di presentazione 1.1. Non
include repository Git, runtime, log, cache, file temporanei, `.env`, metadata
IDE o configurazioni handoff v0.5. `RELEASE_MANIFEST.json` riporta versioni e
checksum dei file inclusi.

## Limiti correnti

- Gli adapter GPIO e NFC sono ancora simulati; la voce prototipo usa il motore
  SpeechSynthesis disponibile nel browser/sistema operativo.
- La chiamata 112 resta manuale come richiesto dalla specifica.
- `age_class=CHILD` non identifica in modo affidabile il confine ERC di 25 kg o
  circa 8 anni: ResQ demanda al DAE la scelta della modalità e non inventa una
  soglia software o una stima del peso durante l'emergenza.
- ResQ Connect ha una coda persistente local-first, ma il trasporto
  Bluetooth/Wi-Fi non e' implementato.
- Ogni SKU mantiene un solo lotto e una sola scadenza. Il supporto multi-lotto
  e' rimandato a una release futura.
- Le transizioni BOOT non sono definite dall'handoff e non vengono inventate.
- Le scelte a tre vie richiedono ancora eventi adapter `EV_SELECT_*`, perche' il
  relativo evento generico non e' definito nello YAML.
