# ResQ Clinical Flow 1.1 -> 1.2

- `PED_CPR + EV_AED_AVAILABLE -> AED_USE` come evento parallelo alla RCP.
- `PED_CPR_COMP_ONLY + EV_AED_AVAILABLE -> AED_USE` come evento parallelo alla RCP.
- `aed_return_state` viene valorizzato all'ingresso in `AED_USE` e limita il
  ritorno a `PED_CPR`, `PED_CPR_COMP_ONLY` o `ADULT_CPR_LOOP` secondo lo stato
  RCP di provenienza.
- `AED_USE` resta condiviso e usa `age_class` solo per la presentazione: guida
  pediatrica per `INFANT`, guida demandata al DAE per l'ambiguo profilo `CHILD`
  e modalità standard per `ADULT`.
- Il DAE decide analisi e scarica; ResQ non introduce `shock_required`,
  `shockable_rhythm` o interpretazione ECG.
