const app = document.getElementById("app");

let lastError = "";
let diagnosticMessage = "";
let currentDiagnosticTest = "";
let lastState = null;
let currentView = "home";
let maintenanceTab = "inventory";
let editingSku = null;
let feedbackSequence = 0;
let feedbackPolling = false;
let laneInputLockedUntil = 0;

const CONTROL_ICONS = {
  adult: "•",
  alert: "!",
  arrow_right: "→",
  bandage: "+",
  body: "•",
  check: "✓",
  check_circle: "✓",
  child: "•",
  choice: "•",
  close: "×",
  droplet: "●",
  edit: "✎",
  environment: "•",
  exit: "×",
  flame: "▲",
  heart_pulse: "♥",
  help: "?",
  home: "⌂",
  infant: "•",
  lightning: "⚡",
  limb: "•",
  lungs: "↕",
  minus: "−",
  more: "…",
  people: "👥",
  refresh: "↻",
  search_off: "⌕̸",
  shield_check: "✓",
  skip: "⇥",
  snowflake: "✣",
  speaker_repeat: "🔊↻",
  trend_down: "↓",
  x: "×",
};

class CompressionMetronome {
  constructor() {
    this.context = null;
    this.active = false;
    this.bpm = 110;
    this.nextBeatAt = 0;
    this.timer = null;
    this.operatorDucked = false;
    this.speechDucked = false;
    this.duckDb = -12;
  }

  async resumeFromGesture() {
    const AudioClock = window.AudioContext || window.webkitAudioContext;
    if (!AudioClock) return;
    if (!this.context) this.context = new AudioClock();
    if (this.context.state === "suspended") await this.context.resume();
    if (this.active && !this.timer) {
      this.nextBeatAt = this.context.currentTime + 0.04;
      this.schedule();
    }
  }

  update(config = {}) {
    if (!config.active) {
      this.stop();
      return;
    }
    this.bpm = Number(config.target_bpm || 110);
    this.operatorDucked = Boolean(config.operator_ducked);
    this.duckDb = Number(config.duck_db ?? -12);
    if (this.active) return;
    this.active = true;
    if (this.context?.state === "running") {
      this.nextBeatAt = this.context.currentTime + 0.04;
      this.schedule();
    }
  }

  schedule() {
    if (!this.active || !this.context || this.context.state !== "running") {
      this.timer = null;
      return;
    }
    const horizon = this.context.currentTime + 0.12;
    while (this.nextBeatAt < horizon) {
      this.scheduleBeat(this.nextBeatAt);
      this.nextBeatAt += 60 / this.bpm;
    }
    this.timer = window.setTimeout(() => this.schedule(), 25);
  }

  scheduleBeat(beatAt) {
    const oscillator = this.context.createOscillator();
    const gain = this.context.createGain();
    const duckDb = this.operatorDucked ? this.duckDb : this.speechDucked ? -8 : 0;
    const duck = 10 ** (duckDb / 20);
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(880, beatAt);
    gain.gain.setValueAtTime(0.0001, beatAt);
    gain.gain.exponentialRampToValueAtTime(0.1 * duck, beatAt + 0.004);
    gain.gain.exponentialRampToValueAtTime(0.0001, beatAt + 0.045);
    oscillator.connect(gain).connect(this.context.destination);
    oscillator.start(beatAt);
    oscillator.stop(beatAt + 0.05);

    const delay = Math.max(0, (beatAt - this.context.currentTime) * 1000);
    window.setTimeout(() => {
      if (!this.active) return;
      const pulse = document.querySelector(".metronome-pulse");
      pulse?.classList.remove("beat");
      requestAnimationFrame(() => pulse?.classList.add("beat"));
    }, delay);
  }

  stop() {
    this.active = false;
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = null;
    document.querySelector(".metronome-pulse")?.classList.remove("beat");
  }

  setSpeechActive(active) {
    this.speechDucked = Boolean(active);
  }
}

const compressionMetronome = new CompressionMetronome();

class AudioGuideService {
  constructor() {
    this.lastSequence = -1;
    this.utterance = null;
  }

  sync(audioState = {}) {
    const sequence = Number(audioState.playback_sequence ?? -1);
    if (sequence === this.lastSequence) return;
    this.lastSequence = sequence;
    if (audioState.playback_command !== "SPEAK" || audioState.voice_suppressed) {
      this.stop();
      return;
    }
    this.speak(String(audioState.last_prompt || ""));
  }

  speak(text) {
    if (!text || !("speechSynthesis" in window)) return;
    this.stop();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "it-IT";
    utterance.rate = 0.94;
    utterance.pitch = 1;
    const voices = window.speechSynthesis.getVoices();
    utterance.voice = voices.find((voice) => voice.lang?.toLowerCase().startsWith("it")) || null;
    utterance.onstart = () => compressionMetronome.setSpeechActive(true);
    utterance.onend = () => compressionMetronome.setSpeechActive(false);
    utterance.onerror = () => compressionMetronome.setSpeechActive(false);
    this.utterance = utterance;
    window.speechSynthesis.speak(utterance);
  }

  stop() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    this.utterance = null;
    compressionMetronome.setSpeechActive(false);
  }
}

const audioGuide = new AudioGuideService();

const UI_TEXT = {
  defaultError: "Errore ResQ",
  languageLabel: "Lingua clinica",
  emergencyStart: "AVVIA EMERGENZA",
  maintenance: "Inventario / Manutenzione",
  footerNote: "Prototipo non validato clinicamente. In emergenza reale chiama il 112 e segui l'operatore.",
  home: "Home",
  diagnostics: "Diagnostica",
  diagnosticsSubtitle: "Hardware e servizi locali",
  testCompartments: "Test vani",
  testRefillNfc: "Refill NFC",
  testAudio: "Test audio",
  appStatus: "Stato app",
  ready: "Pronto",
  diagnosticCompartmentsDone: "Test illuminazione vani completato",
  diagnosticRefillNfcDone: "[NFC REFILL] Refill simulato registrato",
  diagnosticAudioDone: "[AUDIO] Test guida audio simulata completato",
  diagnosticStatusDone: "App 1.1 attiva, BOM e servizi offline pronti",
};

const KIT_STATUS_LABELS = {
  READY: "PRONTO",
  MAINTENANCE: "MANUTENZIONE",
  REFILL_REQUIRED: "RIFORNIMENTO",
  NON_OPERATIONAL: "NON OPERATIVO",
};

const INVENTORY_STATUS_LABELS = {
  AVAILABLE: "Disponibile",
  PENDING_USE: "Uso da confermare",
  SUSPECTED_MISSING: "Probabile mancante",
  USED: "Usato",
  MISSING: "Mancante",
  EXPIRED: "Scaduto",
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || UI_TEXT.defaultError);
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function languageBar(state = null, emergencyMode = false) {
  const version = state?.ux_version && !emergencyMode
    ? `<span class="version-label">UX ${escapeHtml(state.ux_version)}</span>`
    : "";
  return `
    <nav class="language-bar" aria-label="${escapeHtml(UI_TEXT.languageLabel)}">
      <img class="bar-logo" src="/static/img/resq-logo.svg" alt="ResQ">
      <div class="flag-group">
        ${version}
        <span class="flag-button active" aria-label="Italiano">
          <span class="flag" aria-hidden="true">🇮🇹</span>
          <span>IT</span>
        </span>
      </div>
    </nav>
  `;
}

function errorMarkup() {
  return lastError ? `<div class="error-banner">${escapeHtml(lastError)}</div>` : "";
}

function diagnosticResult(testName) {
  const messages = {
    led: UI_TEXT.diagnosticCompartmentsDone,
    refill_nfc: UI_TEXT.diagnosticRefillNfcDone,
    audio: UI_TEXT.diagnosticAudioDone,
    status: UI_TEXT.diagnosticStatusDone,
  };
  return messages[testName] || UI_TEXT.ready;
}

async function guarded(action) {
  const viewBeforeAction = currentView;
  try {
    lastError = "";
    await action();
  } catch (error) {
    lastError = error.message;
    const state = await request("/api/state");
    lastState = state;
    if (viewBeforeAction === "maintenance") {
      renderMaintenance();
    } else {
      renderFromState(state);
    }
  }
}

async function sync() {
  const state = await request("/api/state");
  renderFromState(state);
}

function renderFromState(state) {
  lastState = state;
  feedbackSequence = Math.max(
    feedbackSequence,
    Number(state.input_feedback?.sequence || 0),
  );
  currentView = state.mode;
  if (state.mode === "home") {
    compressionMetronome.stop();
    audioGuide.stop();
    renderHome(state);
    return;
  }
  renderEmergency(state);
}

function renderHome(state = lastState) {
  currentView = "home";
  app.innerHTML = `
    <section class="screen home-screen">
      ${languageBar(state)}
      <div class="home-core">
        <div class="brand-block">
          <h1 class="brand">
            <img
              class="brand-logo"
              src="/static/img/resq-logo-payoff.svg"
              alt="ResQ - Smart Care, Safe Action"
            >
          </h1>
          <p class="subtitle">Smart First Aid Case</p>
        </div>
        ${errorMarkup()}
        <div class="home-action">
          <button class="emergency-button" type="button" onclick="ResQ.startEmergency()">
            ${escapeHtml(UI_TEXT.emergencyStart)}
          </button>
          <button class="maintenance-button" type="button" onclick="ResQ.openDiagnostics()">
            <span>${escapeHtml(UI_TEXT.maintenance)}</span>
            <small class="status-${escapeHtml(state.services?.inventory?.kit_status || "MAINTENANCE")}">
              ${escapeHtml(kitStatusLabel(state.services?.inventory?.kit_status))}
            </small>
          </button>
        </div>
      </div>
      <p class="footer-note">${escapeHtml(UI_TEXT.footerNote)}</p>
    </section>
  `;
}

function renderEmergency(state) {
  const materials = state.services?.materials || {};
  const inventory = state.services?.inventory || {};
  const ux = state.ux || {};
  const callout = state.top_level_state === "EMERGENCY" ? call112Markup(ux.call112) : "";
  const material = materialMarkup(materials, inventory, state.state_id);
  const phase = phaseLabel(state.clinical_phase, state.top_level_state);
  const repeat = headerRepeatMarkup(ux.repeat);
  const screenMode = String(ux.screen_mode || "ACTION");
  const screenModeClass = screenMode.toLowerCase().replaceAll("_", "-");
  const statusStrip = statusStripMarkup(state);
  const instruction = instructionMarkup(state, callout, material);

  app.innerHTML = `
    <section
      class="screen protocol-screen emergency-screen screen-mode-${escapeHtml(screenModeClass)}"
      data-state-id="${escapeHtml(state.state_id)}"
      data-screen-mode="${escapeHtml(screenMode)}"
    >
      ${languageBar(state, true)}
      <div class="state-header">
        <div>
          <div class="state-code">${escapeHtml(phase || "RESQ")}</div>
          <h1>${escapeHtml(state.label)}</h1>
        </div>
        ${repeat}
      </div>
      ${errorMarkup()}
      ${statusStrip}
      <div class="protocol-layout single-pane">
        <section class="primary-pane clinical-pane ${ux.call112?.operator_active ? "operator-priority" : ""}">
          <div class="instruction-block">
            ${screenMode === "CALL_112" ? "" : `<div class="step-label">${escapeHtml(screenModeLabel(screenMode))}</div>`}
            <div class="instruction-copy">
              ${instruction}
            </div>
          </div>
          ${softKeysMarkup(state.soft_keys || [], materials)}
        </section>
      </div>
    </section>
  `;
  compressionMetronome.update(ux.metronome);
  audioGuide.sync(state.services?.ui_audio || {});
}

function screenModeLabel(mode) {
  const labels = {
    EVALUATION: "VALUTA",
    ACTION: "FAI ORA",
    CRITICAL_ACTION: "AZIONE CRITICA",
  };
  return labels[mode] || "FAI ORA";
}

function instructionMarkup(state, callout, material) {
  const ux = state.ux || {};
  if (ux.screen_mode === "CALL_112") {
    return `
      ${callout}
      ${material}
    `;
  }
  if (ux.aed_use?.active) {
    const guidance = ux.aed_use.guidance || {};
    return `
      <div class="aed-use-guide" data-age-class="${escapeHtml(ux.aed_use.age_class || "UNKNOWN")}">
        <h2><span aria-hidden="true">⚡</span>${escapeHtml(ux.aed_use.title || "USA IL DAE")}</h2>
        <p>${escapeHtml(guidance.lead || state.prompt)}</p>
        <strong>${escapeHtml(guidance.mode || "")}</strong>
        <small>${escapeHtml(guidance.fallback || "")}</small>
      </div>
      ${material}
    `;
  }
  if (ux.metronome?.active) {
    const sentences = promptSentences(state.prompt);
    return `
      <div class="critical-cpr-core">
        <h2>COMPRESSIONI</h2>
        ${metronomeMarkup(ux.metronome, true)}
        ${aedReminderMarkup(ux.aed_reminder)}
        <p class="critical-lead">${escapeHtml(sentences[0] || state.prompt)}</p>
        ${sentences.slice(1).length ? `
          <div class="critical-guidance">
            ${sentences.slice(1).map((sentence) => `<span>${escapeHtml(sentence)}</span>`).join("")}
          </div>
        ` : ""}
      </div>
      ${material}
    `;
  }
  return `
    ${callout}
    <p class="instruction">${escapeHtml(state.prompt)}</p>
    ${material}
  `;
}

function promptSentences(prompt) {
  return String(prompt || "").match(/[^.!?]+[.!?]+|[^.!?]+$/g)?.map((part) => part.trim()) || [];
}

function aedReminderMarkup(reminder = {}) {
  if (!reminder.visible) return "";
  if (reminder.interactive && reminder.event) {
    return `
      <button
        class="aed-reminder aed-availability-cta"
        type="button"
        data-event="${escapeHtml(reminder.event)}"
        aria-label="Segnala DAE disponibile"
        onclick="ResQ.sendUtilityEvent(this.dataset.event, this)"
      >
        <span aria-hidden="true">⚡</span>
        <strong>${escapeHtml(reminder.label || "DAE DISPONIBILE")}</strong>
      </button>
    `;
  }
  return `
    <div class="aed-reminder ${reminder.present ? "aed-present" : ""}" aria-label="Stato DAE">
      <span aria-hidden="true">⚡</span>
      <strong>${escapeHtml(reminder.label || "DAE APPENA DISPONIBILE")}</strong>
    </div>
  `;
}

function statusStripMarkup(state) {
  const items = [];
  const call112 = state.ux?.call112 || {};
  const materials = state.services?.materials || {};
  if (call112.visible && call112.display_variant?.startsWith("compact")) {
    items.push(`
      <span class="status-strip-item status-call112 ${call112.display_variant === "compact_operator" ? "operator" : ""}">
        <span aria-hidden="true">☎</span>
        ${escapeHtml(call112.compact_label || "112 IN CORSO")}
      </span>
    `);
  }
  if (materials.active_led_zone) {
    const compartment = String(materials.active_led_zone).split("_")[0];
    items.push(`
      <span class="status-strip-item status-material">
        <span aria-hidden="true">▣</span>
        ${escapeHtml(compartment)} ILLUMINATO
      </span>
    `);
  }
  if (!items.length) return "";
  return `<div class="emergency-status-strip" aria-label="Stati operativi">${items.join("")}</div>`;
}

function headerRepeatMarkup(repeat = {}) {
  if (repeat.mode !== "header_touch") return "";
  return `
    <button
      class="header-repeat"
      type="button"
      aria-label="Ripeti istruzione"
      onclick="ResQ.repeatInstruction()"
      ${repeat.enabled ? "" : "disabled"}
    >
      <span aria-hidden="true">🔊↻</span>
      <strong>RIPETI</strong>
    </button>
  `;
}

function phaseLabel(phase, topLevel) {
  const labels = {
    SCENE_SAFETY: "SICUREZZA DELLA SCENA",
    MULTI_CASUALTY: "PIÙ PERSONE COINVOLTE",
    LIFE_THREATS: "PERICOLI IMMEDIATI",
    UNRESPONSIVE_BLS: "PERSONA NON RESPONSIVA",
    RESPONSIVE_ABCDE: "VALUTAZIONE",
    MONITORING: "MONITORAGGIO",
    HANDOVER: "CONSEGNA AI SOCCORSI",
    POST_EVENT: "CHIUSURA INTERVENTO",
  };
  return labels[phase] || labels[topLevel] || "INTERVENTO RESQ";
}

function typeLabel(type) {
  const labels = {
    decision: "VALUTA E SCEGLI",
    decision_3: "SCEGLI",
    action: "AZIONE",
    material_action: "MATERIALE E AZIONE",
    material_action_optional: "MATERIALE OPZIONALE",
    material_fallback: "ALTERNATIVA MATERIALE",
    loop: "CONTINUA",
    monitor: "MONITORAGGIO",
    terminal_monitor: "ATTESA E MONITORAGGIO",
    terminal: "CONCLUSIONE",
    maintenance: "REVISIONE",
    resume: "RIPRISTINO",
  };
  return labels[type] || "ISTRUZIONE";
}

function call112Markup(presentation = {}) {
  if (!presentation.visible || presentation.display_variant !== "call_now") return "";
  const briefing = presentation.briefing;
  const icons = {
    where: "⌖",
    what: "!",
    people: CONTROL_ICONS.people,
    condition: "♥",
    hazards: "△",
  };
  const briefingMarkup = briefing ? `
    <div class="call-briefing">
      <h3>Dì all'operatore:</h3>
      <ul>
        ${(briefing.items || []).map((item) => {
          const detail = item.observed && item.text
            ? item.text
            : item.display_fallback || item.fallback_prompt;
          return `
            <li class="briefing-item ${item.observed ? "observed" : "prompt"}">
              <span aria-hidden="true">${icons[item.id] || "•"}</span>
              <strong>${escapeHtml(item.label)}</strong>
              <small>${escapeHtml(detail || "")}</small>
            </li>
          `;
        }).join("")}
      </ul>
      <p>Rispondi alle domande e segui le istruzioni dell'operatore.</p>
    </div>
  ` : "";
  return `
    <section class="call112-panel call-now-focus" data-presentation-mode="call_now" aria-label="Attivazione chiamata 112">
      <div class="call112-headline">
        <strong>CHIAMA IL 112 ORA</strong>
        <span aria-label="Numero unico di emergenza 112">112</span>
      </div>
      ${briefingMarkup}
    </section>
  `;
}

function metronomeMarkup(config = {}, critical = false) {
  if (!config.active) return "";
  return `
    <div class="metronome-band ${critical ? "critical" : ""} ${config.operator_ducked ? "ducked" : ""}" aria-label="Metronomo compressioni">
      <span class="metronome-pulse" aria-hidden="true"></span>
      <span>
        <strong>${escapeHtml(config.range_label || "100–120/min")}</strong>
        <small>RITMO GUIDA · ${Number(config.target_bpm || 110)} BPM</small>
      </span>
    </div>
  `;
}

function materialMarkup(materials, inventory, stateId) {
  const request = materials.active_request || null;
  const resolved = request?.resolved || null;
  const pending = inventory.pending_items || [];
  const reviewingInventory = stateId === "POST_EVENT_INVENTORY";
  const reviewItems = (inventory.review_items || []).length
    ? inventory.review_items
    : pending;
  if (!request && (!reviewingInventory || !reviewItems.length)) {
    return "";
  }

  if (request && !resolved) {
    return `
      <div class="material-panel unavailable">
        <strong>Nessun presidio ResQ compatibile disponibile</strong>
      </div>
    `;
  }

  const items = resolved ? [resolved] : reviewItems;
  const labels = items.map((item) => {
    const quantity = Number(item.quantity || 1);
    const prefix = quantity > 1 ? `${quantity} × ` : "";
    return `${prefix}${item.name_it}`;
  });
  const location = resolved
    ? `<strong>Vano illuminato: ${escapeHtml(resolved.zone_name_it)} · Slot ${escapeHtml(resolved.slot)}</strong>`
    : "";
  const fallback = resolved?.fallback_used
    ? `<small class="material-fallback">Alternativa BOM disponibile</small>`
    : "";
  const inventoryEditor = reviewingInventory && inventory.correction_enabled
    ? inventoryEditorMarkup(items)
    : `<span>${escapeHtml(labels.join(" · "))}</span>`;
  return `
    <div class="material-panel">
      ${location}
      ${inventoryEditor}
      ${fallback}
    </div>
  `;
}

function inventoryEditorMarkup(items) {
  return `
    <div class="inventory-editor">
      ${items.map((item) => {
        const quantity = Number(item.quantity || 0);
        const maximum = Number(item.maximum ?? quantity);
        return `
          <div class="inventory-line">
            <span>
              ${escapeHtml(item.name_it)}
              ${item.review_kind === "MISSING" ? "<small>Probabile mancante: indica quanti ne hai trovati</small>" : ""}
            </span>
            <div class="inventory-stepper" aria-label="Quantità ${escapeHtml(item.name_it)}">
              <button
                type="button"
                aria-label="Riduci ${escapeHtml(item.name_it)}"
                onclick="ResQ.correctInventory('${escapeHtml(item.sku)}', ${Math.max(0, quantity - 1)})"
                ${quantity <= 0 ? "disabled" : ""}
              >&minus;</button>
              <strong>${quantity}</strong>
              <button
                type="button"
                aria-label="Aumenta ${escapeHtml(item.name_it)}"
                onclick="ResQ.correctInventory('${escapeHtml(item.sku)}', ${Math.min(maximum, quantity + 1)})"
                ${quantity >= maximum ? "disabled" : ""}
              >+</button>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function softKeysMarkup(softKeys, materials = {}) {
  const byPosition = new Map(softKeys.map((key) => [key.position, key]));
  const lanes = ["left", "center", "right"].map((position) => {
    const key = byPosition.get(position);
    if (!key) {
      return `<div class="soft-key-lane lane-empty" data-lane="${position}" aria-hidden="true"></div>`;
    }
    const unavailableTake = materials.state === "UNAVAILABLE"
      && ["EV_MATERIAL_TAKEN", "EV_ITEM_TAKEN"].includes(key.event);
    if (!key.enabled || !key.event || unavailableTake) {
      return `<div class="soft-key-lane lane-empty" data-lane="${position}" aria-hidden="true"></div>`;
    }
    const icon = CONTROL_ICONS[key.icon] || "•";
    const colorRole = String(key.color_role || "neutral").replace(/[^a-z_]/gi, "");
    return `
      <div class="soft-key-lane" data-lane="${position}">
        <button
          class="soft-key-button role-${escapeHtml(colorRole)}"
          type="button"
          data-event="${escapeHtml(key.event)}"
          data-lane="${position}"
          onclick="ResQ.sendLaneEvent('${position}', '${escapeHtml(key.event)}')"
        >
          <span class="control-icon" aria-hidden="true">${icon}</span>
          <span class="control-label">${escapeHtml(key.label)}</span>
        </button>
      </div>
    `;
  });
  return `<div class="soft-key-row" aria-label="Comandi disponibili">${lanes.join("")}</div>`;
}

function kitStatusLabel(status) {
  return KIT_STATUS_LABELS[status] || KIT_STATUS_LABELS.MAINTENANCE;
}

function inventoryStatusLabel(status) {
  return INVENTORY_STATUS_LABELS[status] || status || "Da verificare";
}

function renderMaintenance() {
  currentView = "maintenance";
  const inventory = lastState?.services?.inventory || {};
  const maintenance = inventory.maintenance || { zones: [], instances: [] };
  const syncState = lastState?.services?.app_sync || {};
  const syncLabel = syncState.queue_state === "SYNC_PENDING"
    ? "DA SINCRONIZZARE"
    : syncState.state === "CONNECTED" ? "SINCRONIZZATO" : "SOLO LOCALE";
  const content = maintenanceTab === "inventory"
    ? maintenanceInventoryMarkup(maintenance)
    : diagnosticsMarkup();

  app.innerHTML = `
    <section class="screen maintenance-screen">
      ${languageBar(lastState)}
      <div class="topbar">
        <div class="topbar-title">
          <h1>Manutenzione</h1>
          <p class="disclaimer">BOM ${escapeHtml(lastState?.bom_version || "1.0")}</p>
        </div>
        <button class="ghost-button" type="button" onclick="ResQ.closeMaintenance()">${escapeHtml(UI_TEXT.home)}</button>
      </div>
      ${errorMarkup()}
      <div class="maintenance-statusbar">
        <div>
          <small>STATO KIT</small>
          <strong class="status-${escapeHtml(maintenance.kit_status || "MAINTENANCE")}">
            ${escapeHtml(kitStatusLabel(maintenance.kit_status))}
          </strong>
        </div>
        <div>
          <small>RESQ CONNECT</small>
          <strong>${escapeHtml(syncLabel)}</strong>
        </div>
      </div>
      <div class="maintenance-tabs" role="tablist">
        <button
          class="${maintenanceTab === "inventory" ? "active" : ""}"
          type="button"
          onclick="ResQ.setMaintenanceTab('inventory')"
        >Inventario</button>
        <button
          class="${maintenanceTab === "diagnostics" ? "active" : ""}"
          type="button"
          onclick="ResQ.setMaintenanceTab('diagnostics')"
        >Diagnostica</button>
      </div>
      <div class="maintenance-content">${content}</div>
    </section>
  `;
}

function maintenanceInventoryMarkup(maintenance) {
  const zones = maintenance.zones || [];
  return `
    <div class="inventory-summary">
      <span>${Number(maintenance.instances?.length || 0)} SKU controllati</span>
      <span>${Number(maintenance.expiry_counts?.EXPIRING_SOON || 0)} in scadenza</span>
      <span>${Number(maintenance.expiry_counts?.EXPIRED || 0)} scaduti</span>
    </div>
    <div class="zone-list">
      ${zones.map((zone) => maintenanceZoneMarkup(zone)).join("")}
    </div>
  `;
}

function maintenanceZoneMarkup(zone) {
  return `
    <section class="inventory-zone">
      <div class="zone-heading">
        <div>
          <h2>${escapeHtml(zone.name_it)}</h2>
          <span>${Number(zone.quantity_available)} / ${Number(zone.quantity_expected)} unità utilizzabili</span>
        </div>
        <strong class="status-${escapeHtml(zone.status)}">${escapeHtml(kitStatusLabel(zone.status))}</strong>
      </div>
      <div class="zone-items">
        ${(zone.items || []).map((item) => maintenanceItemMarkup(item)).join("")}
      </div>
    </section>
  `;
}

function maintenanceItemMarkup(item) {
  const isEditing = editingSku === item.sku;
  const expiry = expiryLabel(item);
  const lot = item.lot ? `Lotto ${item.lot}` : "Lotto da inserire";
  return `
    <div class="maintenance-item status-border-${escapeHtml(item.health)}">
      <div class="maintenance-item-main">
        <div class="maintenance-item-copy">
          <strong>${escapeHtml(item.name_it)}</strong>
          <span>${escapeHtml(item.slot)} · ${escapeHtml(lot)} · ${escapeHtml(expiry)}</span>
          <small class="instance-status status-${escapeHtml(item.status)}">${escapeHtml(inventoryStatusLabel(item.status))}</small>
        </div>
        <div class="maintenance-item-quantity">
          <strong>${Number(item.quantity_usable)} / ${Number(item.quantity_expected)}</strong>
          <span>${escapeHtml(item.unit)}</span>
        </div>
        <button
          class="edit-instance-button"
          type="button"
          aria-label="Modifica ${escapeHtml(item.name_it)}"
          onclick="ResQ.editInventoryInstance('${escapeHtml(item.sku)}')"
        >${isEditing ? "CHIUDI" : "MODIFICA"}</button>
      </div>
      ${isEditing ? inventoryInstanceEditor(item) : ""}
    </div>
  `;
}

function inventoryInstanceEditor(item) {
  const inserted = toLocalDateTime(item.inserted_at);
  const statuses = ["AVAILABLE", "SUSPECTED_MISSING", "MISSING", "USED", "EXPIRED"];
  return `
    <div class="instance-editor" id="instance-editor-${escapeHtml(item.sku)}">
      <label>
        Quantità disponibile
        <input name="quantity" type="number" min="0" value="${Number(item.quantity_available)}">
      </label>
      <label>
        Stato
        <select name="status">
          ${statuses.map((status) => `
            <option value="${status}" ${item.status === status ? "selected" : ""}>
              ${escapeHtml(inventoryStatusLabel(status))}
            </option>
          `).join("")}
        </select>
      </label>
      <label>
        Lotto
        <input name="lot" type="text" value="${escapeHtml(item.lot || "")}" autocomplete="off">
      </label>
      <label>
        Scadenza
        <input name="expiry" type="date" value="${escapeHtml(item.expiry_date || "")}" ${item.expiry_tracking ? "" : "disabled"}>
      </label>
      <label>
        Inserito il
        <input name="inserted" type="datetime-local" value="${escapeHtml(inserted)}">
      </label>
      <button class="save-instance-button" type="button" onclick="ResQ.saveInventoryInstance('${escapeHtml(item.sku)}')">
        SALVA
      </button>
    </div>
  `;
}

function diagnosticsMarkup() {
  return `
    <div class="diagnostic-content">
      <div class="diagnostic-grid">
        <button class="diagnostic-button" type="button" onclick="ResQ.runDiagnostic('led')">${escapeHtml(UI_TEXT.testCompartments)}</button>
        <button class="diagnostic-button" type="button" onclick="ResQ.runDiagnostic('refill_nfc')">${escapeHtml(UI_TEXT.testRefillNfc)}</button>
        <button class="diagnostic-button" type="button" onclick="ResQ.runDiagnostic('audio')">${escapeHtml(UI_TEXT.testAudio)}</button>
        <button class="diagnostic-button" type="button" onclick="ResQ.runDiagnostic('status')">${escapeHtml(UI_TEXT.appStatus)}</button>
      </div>
      <div class="diagnostic-result">${escapeHtml(diagnosticMessage || UI_TEXT.ready)}</div>
    </div>
  `;
}

function expiryLabel(item) {
  if (item.expiry_status === "NOT_TRACKED") return "Nessuna scadenza";
  if (item.expiry_status === "UNKNOWN") return "Scadenza da inserire";
  if (item.expiry_status === "EXPIRED") return item.expiry_date
    ? `Scaduto ${formatDate(item.expiry_date)}`
    : "Scaduto";
  if (item.expiry_status === "EXPIRING_SOON") return `In scadenza ${formatDate(item.expiry_date)}`;
  return `Scade ${formatDate(item.expiry_date)}`;
}

function formatDate(value) {
  if (!value) return "";
  const [year, month, day] = String(value).split("-");
  return `${day}/${month}/${year}`;
}

function toLocalDateTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

async function startEmergency() {
  await guarded(async () => {
    await compressionMetronome.resumeFromGesture();
    diagnosticMessage = "";
    currentDiagnosticTest = "";
    const state = await request("/api/emergency/start", { method: "POST" });
    renderFromState(state);
  });
}

async function sendEvent(event) {
  await guarded(async () => {
    await compressionMetronome.resumeFromGesture();
    const state = await request("/api/events", {
      method: "POST",
      body: JSON.stringify({ event }),
    });
    renderFromState(state);
  });
}

async function sendUtilityEvent(event, control) {
  const now = performance.now();
  if (!event || now < laneInputLockedUntil) return;
  laneInputLockedUntil = now + 140;
  control?.classList.remove("pressed");
  requestAnimationFrame(() => control?.classList.add("pressed"));
  window.setTimeout(() => control?.classList.remove("pressed"), 140);
  await sendEvent(event);
}

function animateLane(lane) {
  const control = document.querySelector(`.soft-key-button[data-lane="${lane}"]`);
  if (!control) return false;
  control.classList.remove("pressed");
  requestAnimationFrame(() => control.classList.add("pressed"));
  window.setTimeout(() => control.classList.remove("pressed"), 140);
  return true;
}

async function sendLaneEvent(lane, event) {
  const now = performance.now();
  if (now < laneInputLockedUntil) return;
  laneInputLockedUntil = now + 140;
  animateLane(lane);
  await sendEvent(event);
}

async function repeatInstruction() {
  await guarded(async () => {
    await compressionMetronome.resumeFromGesture();
    const state = await request("/api/audio/repeat", { method: "POST" });
    renderFromState(state);
  });
}

async function correctInventory(sku, quantity) {
  await guarded(async () => {
    const state = await request("/api/inventory/correct", {
      method: "POST",
      body: JSON.stringify({ sku, quantity }),
    });
    renderFromState(state);
  });
}

async function goHome() {
  await guarded(async () => {
    diagnosticMessage = "";
    currentDiagnosticTest = "";
    const state = await request("/api/home", { method: "POST" });
    renderFromState(state);
  });
}

function openDiagnostics() {
  lastError = "";
  diagnosticMessage = "";
  currentDiagnosticTest = "";
  maintenanceTab = "inventory";
  editingSku = null;
  renderMaintenance();
}

function closeMaintenance() {
  lastError = "";
  editingSku = null;
  renderHome(lastState);
}

function setMaintenanceTab(tab) {
  maintenanceTab = tab === "diagnostics" ? "diagnostics" : "inventory";
  editingSku = null;
  renderMaintenance();
}

function editInventoryInstance(sku) {
  editingSku = editingSku === sku ? null : sku;
  renderMaintenance();
}

async function saveInventoryInstance(sku) {
  await guarded(async () => {
    const editor = document.getElementById(`instance-editor-${sku}`);
    if (!editor) return;
    const insertedValue = editor.querySelector('[name="inserted"]').value;
    const payload = {
      sku,
      quantity_available: Number(editor.querySelector('[name="quantity"]').value),
      status: editor.querySelector('[name="status"]').value,
      lot: editor.querySelector('[name="lot"]').value,
      expiry_date: editor.querySelector('[name="expiry"]').value || null,
      inserted_at: insertedValue ? new Date(insertedValue).toISOString() : "",
    };
    const state = await request("/api/inventory/instance", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    lastState = state;
    editingSku = null;
    renderMaintenance();
  });
}

async function runDiagnostic(testName) {
  await guarded(async () => {
    const result = await request(`/api/diagnostics/${encodeURIComponent(testName)}`, {
      method: "POST",
    });
    currentDiagnosticTest = testName;
    diagnosticMessage = result.message || diagnosticResult(testName);
    lastState = result.state || lastState;
    maintenanceTab = "diagnostics";
    renderMaintenance();
  });
}

async function pressHardware(buttonName) {
  const now = performance.now();
  if (now < laneInputLockedUntil || !animateLane(buttonName)) return;
  laneInputLockedUntil = now + 140;
  await guarded(async () => {
    await compressionMetronome.resumeFromGesture();
    const state = await request(`/api/buttons/${encodeURIComponent(buttonName)}`, {
      method: "POST",
    });
    renderFromState(state);
  });
}

async function pollInputFeedback() {
  if (feedbackPolling || currentView === "home" || currentView === "maintenance") return;
  feedbackPolling = true;
  try {
    const feedback = await request("/api/input-feedback");
    const sequence = Number(feedback.sequence || 0);
    if (sequence > feedbackSequence) {
      feedbackSequence = sequence;
      animateLane(feedback.lane);
      window.setTimeout(() => sync().catch(() => {}), 150);
    }
  } catch (_error) {
    // Feedback polling is auxiliary and must never interrupt Emergency Mode.
  } finally {
    feedbackPolling = false;
  }
}

document.addEventListener("keydown", (event) => {
  const tagName = event.target?.tagName || "";
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tagName)) {
    return;
  }
  const map = {
    "1": "left",
    "2": "center",
    "3": "right",
  };
  const button = map[event.key.toLowerCase()];
  if (button) {
    event.preventDefault();
    pressHardware(button);
  }
});

window.ResQ = {
  startEmergency,
  sendEvent,
  sendUtilityEvent,
  sendLaneEvent,
  repeatInstruction,
  correctInventory,
  goHome,
  openDiagnostics,
  closeMaintenance,
  setMaintenanceTab,
  editInventoryInstance,
  saveInventoryInstance,
  runDiagnostic,
};

sync();
window.setInterval(pollInputFeedback, 80);
