# Rigenerazione evidenze UX 1.1

Le evidenze finali devono provenire dallo ZIP appena generato, non da un server
rimasto aperto durante lo sviluppo.

## Procedura

1. Generare `dist/ResQ_Prototype_Architecture_v1.1.zip`.
2. Estrarre lo ZIP in una directory temporanea vuota.
3. Avviare `main.py` dalla directory estratta con dati runtime assenti.
4. Aprire la UI nel browser di test e impostare il viewport a `720 x 1280`.
5. Raggiungere ogni stato tramite eventi pubblici dell'applicazione, acquisire
   lo screenshot e verificare che `document.scrollWidth/scrollHeight` non superi
   il viewport.
6. Ripetere `ADULT_CPR` a `1280 x 720` per la regressione del monitor fisico.
7. Salvare le immagini in `docs/screenshots/release_candidate_v1_1/`.

## Evidenze obbligatorie

- `01_SCENE_SAFE.png`
- `02_B_BREATHING.png`
- `03_BLEED_DIRECT_PRESSURE.png`
- `04_UNRESP_CALL.png`
- `05_ADULT_CPR.png`
- `06_ADULT_CPR_LOOP.png`
- `07_AED_USE.png`
- `08_AED_RETURN_ADULT_CPR_LOOP.png`
- `09_PED_CPR.png`
- `10_BURN_COVER.png`
- `11_ADULT_CPR_1280x720.png`

Ogni immagine deve essere controllata per assenza di numeri lane, versione UX,
debug, CTA obsolete, sovrapposizioni e overflow. In `ADULT_CPR` e
`ADULT_CPR_LOOP`, `DAE DISPONIBILE` deve occupare LEFT; dopo il ritorno dal DAE
deve comparire il solo stato passivo `DAE PRESENTE`.
