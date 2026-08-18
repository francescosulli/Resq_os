# ResQ UX State Audit v1.1

Audit source-driven dei 62 stati con Clinical Flow 1.2. I numeri dei tasti non sono mostrati in Emergency Mode; le corsie restano posizionali. Il DAE è equivalente su touch e pulsante fisico nell'adulto e nel pediatrico.

| Stato | Modalita | SX | CENTRO | DX | # | RIPETI | DAE | 112 | RCP |
|---|---|---|---|---|---:|---|---|---|---|
| `EM_START` | ACTION | ESCI [neutral] | - | INIZIA [success] | 2 | none | - | hidden_unless_service_call_already_active | off |
| `SCENE_SAFE` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `SCENE_UNSAFE` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | call_now_panel | off |
| `SCENE_RECHECK` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `WAIT_SAFE` | ACTION | - | RIPETI [support] | RIVALUTA [support] | 2 | center_softkey | - | hidden_unless_service_call_already_active | off |
| `MULTI_CASUALTY` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `MULTI_ACTION` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | call_now_panel | off |
| `MASSIVE_BLEED` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `BLEED_DIRECT_PRESSURE` | CRITICAL_ACTION | NON TROVO [danger] | - | FATTO [success] | 2 | header_touch | - | call_now_panel | off |
| `MAT_FALLBACK_BLEED` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | hidden_unless_service_call_already_active | off |
| `BLEED_CONTROLLED` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `BLEED_LIMB` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `TOURNIQUET` | CRITICAL_ACTION | NON TROVO [danger] | - | FATTO [success] | 2 | header_touch | - | call_now_panel | off |
| `HEMOSTATIC` | CRITICAL_ACTION | NON TROVO [danger] | - | FATTO [success] | 2 | header_touch | - | call_now_panel | off |
| `RESPONSIVE` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `UNRESP_CALL` | CALL_112 | - | RIPETI [support] | HO CHIAMATO [success] | 2 | center_softkey | - | call_now_focus | off |
| `AGE_BLS` | EVALUATION | LATTANTE [neutral] | BAMBINO [neutral] | ADULTO [neutral] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `ADULT_BREATH_CHECK` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `ADULT_CPR` | CRITICAL_ACTION | DAE DISPONIBILE [warning] | RIPETI [support] | CONTINUA [success] | 3 | center_softkey | LEFT [touch/hardware] | operator_priority_if_active_else_contextual_operator_panel | 110_bpm_audio_visual |
| `AED_AVAILABLE` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `AED_USE` | CRITICAL_ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | operator_priority_if_active_else_contextual_operator_panel | off |
| `ADULT_CPR_LOOP` | CRITICAL_ACTION | DAE DISPONIBILE [warning] | RIPETI [support] | RESPIRA [success] | 3 | center_softkey | LEFT [touch/hardware] | hidden_unless_service_call_already_active | 110_bpm_audio_visual |
| `PED_BREATH_CHECK` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `PED_5_BREATHS` | ACTION | PROBLEMA [danger] | - | FATTO [success] | 2 | header_touch | - | operator_priority_if_active_else_contextual_operator_panel | off |
| `PED_CPR` | CRITICAL_ACTION | PROBLEMA [danger] | DAE DISPONIBILE [warning] | RESPIRA [success] | 3 | header_touch | CENTER [touch/hardware] | operator_priority_if_active_else_contextual_operator_panel | 110_bpm_audio_visual |
| `TRAUMA_UNRESP` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `RECOVERY_POSITION` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | hidden_unless_service_call_already_active | off |
| `TRAUMA_AIRWAY` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | operator_priority_if_active_else_contextual_operator_panel | off |
| `A_AIRWAY` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `CHOKE_SUDDEN` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `CHOKE_AGE` | EVALUATION | LATTANTE [neutral] | BAMBINO [neutral] | ADULTO [neutral] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `CHOKE_ADULT` | ACTION | PEGGIORA [danger] | - | RISOLTO [success] | 2 | header_touch | - | conditional_no_call_now_banner | off |
| `CHOKE_CHILD` | ACTION | PEGGIORA [danger] | - | RISOLTO [success] | 2 | header_touch | - | conditional_no_call_now_banner | off |
| `CHOKE_INFANT` | ACTION | PEGGIORA [danger] | - | RISOLTO [success] | 2 | header_touch | - | conditional_no_call_now_banner | off |
| `B_BREATHING` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `BREATHING_SEVERE` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | call_now_panel | off |
| `C_CIRCULATION` | EVALUATION | SANGUE [neutral] | MALORE [neutral] | NESSUNA [neutral] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `C_MALAISE` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `C_CALL112` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | call_now_panel | off |
| `D_NEURO` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `D_NEURO_ACTION` | ACTION | PEGGIORA [danger] | - | FATTO [success] | 2 | header_touch | - | prominent_call_panel | off |
| `E_EXPOSURE` | EVALUATION | TRAUMA [neutral] | USTIONE/AMBIENTE [neutral] | ALTRO [neutral] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `TRAUMA_SELECT` | EVALUATION | FERITA [neutral] | ARTO [neutral] | TESTA/TORACE [neutral] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `WOUND_CARE` | ACTION | NON TROVO [danger] | - | FATTO [success] | 2 | header_touch | - | hidden_unless_service_call_already_active | off |
| `WOUND_FALLBACK` | ACTION | PEGGIORA [danger] | - | FATTO [success] | 2 | header_touch | - | hidden_unless_service_call_already_active | off |
| `LIMB_TRAUMA` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | hidden_unless_service_call_already_active | off |
| `MAJOR_TRAUMA` | ACTION | PEGGIORA [danger] | - | FATTO [success] | 2 | header_touch | - | prominent_call_panel | off |
| `ENV_SELECT` | EVALUATION | USTIONE [neutral] | FREDDO [neutral] | ALTRO [neutral] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `BURN` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | hidden_unless_service_call_already_active | off |
| `COLD` | ACTION | NON TROVO [danger] | - | FATTO [success] | 2 | header_touch | - | hidden_unless_service_call_already_active | off |
| `ENV_OTHER` | ACTION | - | RIPETI [support] | FATTO [success] | 2 | center_softkey | - | conditional_no_call_now_banner | off |
| `LOCAL_CARE` | ACTION | PEGGIORA [danger] | - | FATTO [success] | 2 | header_touch | - | hidden_unless_service_call_already_active | off |
| `MONITOR` | ACTION | PEGGIORA [danger] | - | STABILE [success] | 2 | header_touch | - | hidden_unless_service_call_already_active | off |
| `HANDOVER` | ACTION | - | RIPETI [support] | CHIUDI [neutral] | 2 | center_softkey | - | hidden_unless_service_call_already_active | off |
| `POST_EVENT_INVENTORY` | ACTION | CORREGGI [warning] | - | CONFERMA [success] | 2 | none | - | hidden_unless_service_call_already_active | off |
| `SESSION_END` | ACTION | - | - | HOME [neutral] | 1 | none | - | hidden_unless_service_call_already_active | off |
| `WOUND_PPE` | ACTION | NON TROVO [danger] | SALTA [neutral] | FATTO [success] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `PED_FACE_SHIELD_OPTION` | ACTION | NON TROVO [danger] | SALTA [neutral] | PRESO [success] | 3 | header_touch | - | operator_priority_if_active_else_contextual_operator_panel | off |
| `PED_CPR_MODE` | EVALUATION | NO [danger] | NON SO [warning] | SÌ [danger] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `PED_CPR_COMP_ONLY` | CRITICAL_ACTION | DAE DISPONIBILE [warning] | RIPETI [support] | RESPIRA [success] | 3 | center_softkey | LEFT [touch/hardware] | operator_priority_if_active_else_contextual_operator_panel | 110_bpm_audio_visual |
| `BURN_COVER` | ACTION | NON TROVO [danger] | SALTA [neutral] | FATTO [success] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
| `LIMB_SUPPORT_OPTION` | ACTION | NON TROVO [danger] | SALTA [neutral] | FATTO [success] | 3 | header_touch | - | hidden_unless_service_call_already_active | off |
