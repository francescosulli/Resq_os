# ResQ Clinical Flow 1.0 -> 1.1

Release prodotto invariata: ResQ Prototype Architecture 1.1.

## Source attivi

- Clinical Flow: `ResQ_flow_nodes_v1_1.json`
- State Machine: `ResQ_state_machine_spec_v1_1.yaml`
- Automotive BOM: `ResQ_Automotive_BOM_v1_0.yaml`, invariata
- UX/Human Factors: 1.1

## Delta clinico completo

1. Aggiunto l'evento semantico `EV_AED_AVAILABLE`, con significato esclusivo:
   un DAE e' fisicamente disponibile presso il soccorritore.
2. Aggiunto `ADULT_CPR --EV_AED_AVAILABLE--> AED_USE`.
3. Aggiunto `ADULT_CPR_LOOP --EV_AED_AVAILABLE--> AED_USE`.
4. Modificato `ADULT_CPR --CONTINUA--> ADULT_CPR_LOOP`; `CONTINUA` non apre piu'
   la domanda sequenziale sul DAE.
5. `AED_AVAILABLE` resta `compatibility_only` per il recovery di sessioni Flow
   1.0 gia' persistite. Nessun nuovo percorso 1.1 entra in questo stato.
6. Aggiunto al context il flag operativo `aed_present`. Non rappresenta ritmo,
   shock, accensione del dispositivo o placche applicate.

## Invarianti

- Tutti i 62 prompt sono identici al Flow 1.0.
- `AED_USE --FATTO--> ADULT_CPR_LOOP` e' invariato.
- Nessuna transizione pediatrica e' stata aggiunta.
- BOM, MaterialRequest, quantita', inventario, 112 e readiness sono invariati.
- Nessuna logica interpreta il ritmo o decide se erogare uno shock.

## Gap pediatrico

`PED_CPR` e `PED_CPR_COMP_ONLY` citano il DAE, ma il source-of-truth non
definisce un percorso DAE pediatrico ne' il relativo stato di ritorno. Serve una
decisione clinica esplicita prima di rendere interattivo il reminder pediatrico.
