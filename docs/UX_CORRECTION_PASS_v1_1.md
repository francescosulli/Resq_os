# ResQ UX 1.1 - Final Correction Pass

Il correction pass originale modificava esclusivamente presentazione, input
adapter e servizi UX. La successiva patch Flow 1.1 aggiunge soltanto il percorso
DAE parallelo adulto descritto nel changelog dedicato.

## Correzioni applicate

- Rimossi numeri e metadata di sviluppo dalla Emergency UI.
- Introdotte le modalita' visuali EVALUATION, ACTION, CRITICAL_ACTION e CALL_112.
- Applicata la grammatica colore source-driven: valutazioni danger/warning/danger,
  categorie neutral e azioni con ruolo semantico.
- Ridotta CALL NOW a numero 112, cinque voci e una frase; azioni critiche e
  operator priority usano una status strip compatta.
- Collegato AudioGuideService a SpeechSynthesis, con stop al cambio stato,
  repeat reale e sospensione con operatore.
- Resa la CPR una schermata critica dedicata con pulse, 110 bpm, riferimento
  100-120/min e promemoria DAE persistente.
- Reso ButtonController esclusivamente posizionale e condiviso il feedback e
  debounce tra touch e hardware.

## Stato DAE/RCP

Flow 1.1 risolve il conflitto adulto con `EV_AED_AVAILABLE` da `ADULT_CPR` e
`ADULT_CPR_LOOP` verso `AED_USE`. Il gap rimane pediatrico: `PED_CPR` e
`PED_CPR_COMP_ONLY` non hanno target di ingresso/ritorno DAE definiti e quindi
mantengono un reminder non interattivo.

## Evidenze

Gli screenshot 720 x 1280 sono in `docs/screenshots/v1_1_correction/` e
coprono SCENE_SAFE, B_BREATHING, BLEED_DIRECT_PRESSURE, UNRESP_CALL,
ADULT_CPR, ADULT_CPR con operator priority, AED_USE e BURN_COVER.
