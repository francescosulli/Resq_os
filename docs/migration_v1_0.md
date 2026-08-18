# Migrazione incrementale Flow v0.5 -> Flow/BOM v1.0

## Diff sintetico

- Stati clinici: 56 -> 62.
- Stati rimossi: nessuno.
- Nuovi stati: `WOUND_PPE`, `PED_FACE_SHIELD_OPTION`, `PED_CPR_MODE`,
  `PED_CPR_COMP_ONLY`, `BURN_COVER`, `LIMB_SUPPORT_OPTION`.
- Nodi esistenti modificati dal JSON: 11.
- MaterialRequest attive per stato: massimo 1.
- Zone LED attive: massimo 1 alla volta.
- Inventario: da ID semantici a SKU fisici e quantita' BOM.
- Persistenza: schema 1 -> schema 3 (schema 2 migrato automaticamente).

## Mapping componenti

| Componente v0.5 | Migrazione v1.0 |
| --- | --- |
| `ClinicalStateMachine` | riusata; carica il JSON v1.0 |
| `EmergencyFlow` | riusato come coordinatore; gestisce gli esiti del resolver |
| `HandoffSpecLoader` | esteso da 2 a 3 source of truth |
| `KitProfile` semplificato | sostituito da `BOMCatalog` |
| `MaterialService` | risolve SKU, fallback, zona, slot e LED dalla BOM |
| `InventoryService` | Inventory Instance, pending, sospetti, scadenze e stato kit |
| `StateManager` | riusato con snapshot schema 3 |
| `LEDController` | riceve zona e `led_id` gia' risolti |
| UI | mostra dati BOM e correzione quantita' post-evento |

## Modifiche del grafo

### Ferite

`TRAUMA_SELECT -> WOUND_PPE -> WOUND_CARE`. I guanti e la medicazione sono due
richieste separate, quindi non attivano due zone nello stesso stato.

### Pediatrico

`PED_BREATH_CHECK` porta a `PED_FACE_SHIELD_OPTION` quando la respirazione non e'
normale o e' incerta. `SALTA` e `PRESO` convergono entrambi su
`PED_5_BREATHS`. Dopo le cinque ventilazioni, `PED_CPR_MODE` seleziona
`PED_CPR` oppure `PED_CPR_COMP_ONLY` tramite i target JSON.

### Ustioni

`BURN` contiene solo il raffreddamento. La richiesta sterile opzionale e' in
`BURN_COVER`.

### Trauma arto

`LIMB_TRAUMA` contiene l'azione clinica; `LIMB_SUPPORT_OPTION` gestisce il
supporto fisico opzionale.

### Emorragie e ferite

`BLEED_DIRECT_PRESSURE` e `WOUND_CARE` richiedono una sola MaterialRequest.
`MAT_FALLBACK_BLEED` e `WOUND_FALLBACK` non richiedono piu' materiali ResQ:
sono raggiunti solo quando il MaterialService ha esaurito gli SKU compatibili.

## Risoluzione BOM

`BOMCatalog` legge `preferred`, `fallback` e `selection_policy`. Il risultato
fisico contiene SKU, nome, quantita', zona, slot e LED. `NON TROVO` esclude lo
SKU corrente e tenta il successivo senza inviare un evento alla Clinical State
Machine. Solo l'assenza di ulteriori candidati produce
`EV_MATERIAL_UNAVAILABLE`, associato al pulsante e al target gia' presenti nel
JSON.

Gli stati opzionali espongono tre sole azioni UI: `SALTA`, `NON TROVO` e
`FATTO`. `SALTA` segue il target JSON senza modificare l'inventario; `NON
TROVO` resta nel medesimo stato mentre il servizio prova i fallback. Se non ne
rimangono, l'utente puo' ancora scegliere `SALTA` sul target clinico originale.

La richiesta `PPE_GLOVES` consuma due unita' dello SKU guanti, cioe' un paio,
senza modificare la quantita' prevista di 8 unita' nella BOM.

La richiesta `DRESSING_FIXATION`, oggi non usata da alcuno stato, ha candidati
in C2 e C3. Il resolver supporta questa BOM accendendo sempre una sola zona alla
volta e cambiandola solo insieme allo SKU selezionato.

## Persistenza

Gli snapshot v1.0 includono `schema_version: 3`, `spec_version`, `bom_version`,
Inventory Instance, SKU pending o sospetti, MaterialRequest pending,
risoluzione corrente e coda sync. Ogni istanza salva quantita', stato, lotto,
scadenza, data di inserimento e timestamp di aggiornamento.

Migrazione v0.5:

- `IDLE/SESSION_END`: usi semantici finalizzati -> SKU BOM preferito, poi
  salvataggio immediato in schema 3;
- intervento attivo: nessuna conversione clinica; `RIPRENDI` e' disabilitato e
  resta disponibile soltanto l'annullamento esplicito.

Uno snapshot Flow v1.0 in schema 2 viene arricchito con le Inventory Instance
senza modificare lo stato clinico. La chiusura resetta in memoria motore e
servizi, poi persiste una sola immagine `IDLE`. L'evento finale conserva il
`session_id` ed e' riconciliato nel journal tramite un `event_id` idempotente.

## Questioni non reinterpretate

1. Lo YAML v1.0 non definisce gli eventi delle selezioni a tre vie
   (`ADULTO/BAMBINO/LATTANTE`, categorie trauma e ambiente). Restano adapter
   deterministici `EV_SELECT_*`; i target provengono sempre dal JSON.
2. `material_semantics` nel JSON contiene note descrittive sui fallback, ma il
   runtime non le analizza: l'ordine fisico viene letto esclusivamente dalla
   BOM YAML.
3. Il protocollo di trasporto/autenticazione ResQ Connect non e' specificato;
   resta una coda offline non bloccante.
4. Il ramo BOOT elenca stati ma non eventi/transizioni; il runtime continua a
   effettuare controlli sincroni prima di IDLE senza inventare un grafo BOOT.

## Congelamento Prototype Architecture 1.0

La chiusura della release non modifica flow, prompt, transizioni, MaterialRequest
o quantita' BOM. Il runtime carica esclusivamente i tre source of truth v1.0 con
nome esplicito e inizializza un inventario assente dalle quantita' BOM.

La readiness e' calcolata da una sola `ReadinessPolicy`, mantenendo il mapping
1.0. Persistenza e conferme post-evento usano sostituzione atomica; il ripristino
di `PENDING_USE` non consuma il presidio e la conferma gia' salvata non puo'
decrementarlo nuovamente. La coda ResQ Connect e' persistente, non bloccante e
deduplicata mediante chiave di idempotenza, senza trasporto Bluetooth/Wi-Fi.

Il pacchetto esclude sessioni, event log, cache, code sync e inventari generati.
`reset_runtime_state.py --confirm-reset` e' un comando di sviluppo intenzionale:
rifiuta l'esecuzione durante una sessione attiva e ricrea le Inventory Instance
dalla BOM.

`config/release.json` e' la fonte unica per versioni, nome artefatto, nomi e hash
dei source-of-truth. `scripts/build_release.py` genera uno ZIP deterministico da
una lista di inclusione e omette configurazioni v0.5, runtime e metadata locali.

L'Inventory Instance 1.0 rappresenta un solo lotto/scadenza per SKU. Il
multi-lotto e' esplicitamente rinviato a una futura evoluzione e non viene
simulato in questa release.
