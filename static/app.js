const app = document.getElementById("app");

const LANGUAGE_KEY = "resq_language";
const LANGUAGES = [
  { code: "it", flag: "🇮🇹", label: "Italiano" },
  { code: "en", flag: "🇬🇧", label: "English" },
];

let protocols = [];
let lastError = "";
let diagnosticMessage = "";
let currentDiagnosticTest = "";
let lastState = null;
let currentView = "home";
let currentLanguage = localStorage.getItem(LANGUAGE_KEY) || "it";

if (!LANGUAGES.some((language) => language.code === currentLanguage)) {
  currentLanguage = "it";
}
document.documentElement.lang = currentLanguage;

const UI_TEXT = {
  it: {
    defaultError: "Errore ResQ",
    languageLabel: "Lingua",
    emergencyStart: "AVVIA EMERGENZA",
    maintenance: "Manutenzione / Diagnostica",
    footerNote: "Demo dimostrativa. In emergenza reale chiama il 112 e segui personale formato.",
    selectionTitle: "Selezione emergenza",
    selectionSubtitle: "Scegli il protocollo dimostrativo piu' vicino alla situazione.",
    home: "Home",
    back: "Indietro",
    repeatAudio: "Ripeti audio",
    question: "Domanda",
    instruction: "Istruzione",
    yes: "S&Igrave;",
    no: "NO",
    requestedObject: "Oggetto richiesto",
    take: "Prendi",
    compartment: "Vano",
    confirmItem: "Ho preso il presidio",
    continue: "Continua",
    endProtocol: "Fine protocollo",
    requestedItems: "Presidi richiesti",
    noRequestedItems: "Nessun presidio richiesto",
    answers: "Risposte",
    noAnswers: "Nessuna risposta registrata",
    backHome: "Torna alla home",
    diagnostics: "Diagnostica",
    diagnosticsSubtitle: "Hardware in modalita' simulata",
    testCompartments: "Test vani",
    testRefillNfc: "Refill NFC",
    testAudio: "Test audio",
    appStatus: "Stato app",
    ready: "Pronto",
    diagnosticCompartmentsDone: "Test illuminazione vani completato",
    diagnosticRefillNfcDone: "[NFC REFILL] Refill simulato registrato",
    diagnosticAudioDone: "[AUDIO] Test guida audio simulata completato",
    diagnosticStatusDone: "App attiva, backend operativo, hardware in simulazione",
  },
  en: {
    defaultError: "ResQ error",
    languageLabel: "Language",
    emergencyStart: "START EMERGENCY",
    maintenance: "Maintenance / Diagnostics",
    footerNote: "Demonstration only. In a real emergency, call 112 and follow trained responders.",
    selectionTitle: "Emergency selection",
    selectionSubtitle: "Choose the demonstration protocol closest to the situation.",
    home: "Home",
    back: "Back",
    repeatAudio: "Repeat audio",
    question: "Question",
    instruction: "Instruction",
    yes: "YES",
    no: "NO",
    requestedObject: "Requested item",
    take: "Take",
    compartment: "Compartment",
    confirmItem: "I have taken the item",
    continue: "Continue",
    endProtocol: "Protocol complete",
    requestedItems: "Requested items",
    noRequestedItems: "No requested items",
    answers: "Answers",
    noAnswers: "No answers recorded",
    backHome: "Back to home",
    diagnostics: "Diagnostics",
    diagnosticsSubtitle: "Hardware in simulated mode",
    testCompartments: "Compartments test",
    testRefillNfc: "Refill NFC",
    testAudio: "Audio test",
    appStatus: "App status",
    ready: "Ready",
    diagnosticCompartmentsDone: "Compartment lighting test completed",
    diagnosticRefillNfcDone: "[NFC REFILL] Simulated refill registered",
    diagnosticAudioDone: "[AUDIO] Simulated audio guide test completed",
    diagnosticStatusDone: "App active, backend operational, hardware simulated",
  },
};

const ITEM_I18N = {
  en: {
    gloves: {
      name: "Disposable gloves",
      compartment: "Protection compartment",
    },
    thermal_blanket: {
      name: "Thermal blanket",
      compartment: "Blanket compartment",
    },
    sterile_gauze: {
      name: "Sterile gauze",
      compartment: "Gauze compartment",
    },
    bandage: {
      name: "Bandage",
      compartment: "Bandage compartment",
    },
    plaster_gauze: {
      name: "Plaster or gauze",
      compartment: "Dressings compartment",
    },
    sterile_cover: {
      name: "Non-adherent sterile gauze or sterile drape",
      compartment: "Sterile supplies compartment",
    },
    triangular_bandage: {
      name: "Triangular bandage or drape",
      compartment: "Support compartment",
    },
  },
};

const TEXT_I18N = {
  en: {
    "Protocollo dimostrativo: non sostituisce formazione, 112 o personale sanitario.":
      "Demonstration protocol: it does not replace training, 112 or medical personnel.",
    "Gestione persona incosciente completata in modalita' demo.":
      "Unconscious person protocol completed in demo mode.",
    "Gestione sanguinamento completata in modalita' demo.":
      "Bleeding protocol completed in demo mode.",
    "Gestione ustione completata in modalita' demo.":
      "Burn protocol completed in demo mode.",
    "Gestione trauma/frattura completata in modalita' demo.":
      "Trauma/fracture protocol completed in demo mode.",
    "Protocollo completato.": "Protocol completed.",
    "Continua": "Continue",
    "Prepara guanti": "Prepare gloves",
    "Ho chiamato": "I called",
    "Prendi presidio": "Take item",
    "Fine": "Finish",
    "Rispondi si' o no per continuare": "Answer yes or no to continue",
    "Questo step non richiede una risposta si/no":
      "This step does not require a yes/no answer",
    "Nessun protocollo attivo": "No active protocol",
  },
};

const PROTOCOL_I18N = {
  en: {
    protocols: {
      unconscious: {
        title: "Unconscious person",
        steps: {
          demo_notice: {
            instruction: "Demonstration protocol. If the situation is serious or uncertain, call 112.",
          },
          scene_safety: {
            instruction: "Approach only if the scene is safe. Prepare personal protection.",
            action_label: "Prepare gloves",
          },
          gloves: {
            instruction: "Put on disposable gloves before giving assistance.",
          },
          check_response: {
            instruction: "Speak clearly and observe the reaction.",
            question: "Does the person respond when called?",
          },
          responsive: {
            instruction: "Keep the person calm and assess other symptoms. If they worsen, call 112.",
          },
          call_112: {
            instruction: "Call 112 immediately and follow the operator's instructions.",
            action_label: "I called",
          },
          check_breathing: {
            instruction: "Watch for chest movement and listen for breathing without wasting time.",
            question: "Is the person breathing normally?",
          },
          recovery_position: {
            instruction: "If you do not suspect trauma, place them in the recovery position and keep monitoring.",
          },
          cpr: {
            instruction: "Start CPR only if you are trained and follow the instructions from 112.",
          },
          thermal_blanket: {
            instruction: "Protect the person from cold while waiting for help.",
          },
          end: {
            instruction: "Demonstration protocol completed. Keep monitoring and follow 112.",
            summary: "Unconscious person protocol completed in demo mode.",
          },
        },
      },
      bleeding: {
        title: "Bleeding",
        steps: {
          demo_notice: {
            instruction: "Demonstration protocol. If bleeding is severe, call 112.",
          },
          heavy_question: {
            instruction: "Observe the wound without delaying the request for help if the situation is serious.",
            question: "Is the bleeding heavy?",
          },
          gloves: {
            instruction: "Put on gloves before applying pressure.",
          },
          gauze: {
            instruction: "Prepare sterile gauze to protect the wound.",
          },
          bandage: {
            instruction: "Prepare a bandage to keep the dressing in place.",
          },
          direct_pressure: {
            instruction: "Apply direct pressure to the wound and stay in contact with 112 if needed.",
            action_label: "Finish",
          },
          minor_instruction: {
            instruction: "Protect the wound according to what is available and monitor changes.",
            action_label: "Take item",
          },
          plaster: {
            instruction: "Use gauze or a plaster to cover a minor wound.",
          },
          end: {
            instruction: "Demonstration protocol completed. Monitor the person and ask for help if they worsen.",
            summary: "Bleeding protocol completed in demo mode.",
          },
        },
      },
      burn: {
        title: "Burn",
        steps: {
          demo_notice: {
            instruction: "Demonstration protocol. If the burn is serious or you are unsure, call 112.",
          },
          severity_question: {
            instruction: "Quickly assess location and extent without touching the area unnecessarily.",
            question: "Is the burn extensive or does it involve face, hands, genitals or airways?",
          },
          call_112: {
            instruction: "Call 112 and follow the operator's instructions.",
          },
          cooling: {
            instruction: "Cool with running water if available, without delaying the 112 call when needed.",
            action_label: "Take item",
          },
          sterile_cover: {
            instruction: "Cover with non-adherent sterile material or a sterile drape according to availability.",
          },
          end: {
            instruction: "Demonstration protocol completed. Keep monitoring and ask for help if the situation changes.",
            summary: "Burn protocol completed in demo mode.",
          },
        },
      },
      trauma: {
        title: "Trauma / fracture",
        steps: {
          demo_notice: {
            instruction: "Demonstration protocol. Avoid unnecessary movement and call for help if the situation is serious.",
          },
          movement_question: {
            instruction: "Observe the limb without forcing movement.",
            question: "Can the person move the limb without intense pain?",
          },
          monitor: {
            instruction: "Keep the person calm, limit effort and monitor pain.",
          },
          immobilize: {
            instruction: "Immobilize as much as possible without forcing and call for help.",
            action_label: "Take item",
          },
          triangular_bandage: {
            instruction: "Prepare soft support to limit movement.",
          },
          bleeding_question: {
            instruction: "Check whether there is associated bleeding.",
            question: "Is there associated bleeding?",
          },
          bleeding_redirect: {
            instruction: "Switch to the Bleeding protocol or ask 112 for support if bleeding is significant.",
            action_label: "Finish",
          },
          end: {
            instruction: "Demonstration protocol completed. Keep monitoring and limit movement.",
            summary: "Trauma/fracture protocol completed in demo mode.",
          },
        },
      },
    },
  },
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
    throw new Error(data.error || t("defaultError"));
  }
  return data;
}

function t(key) {
  return UI_TEXT[currentLanguage]?.[key] || UI_TEXT.it[key] || key;
}

function format(text, values = {}) {
  return Object.entries(values).reduce(
    (result, [key, value]) => result.replaceAll(`{${key}}`, value),
    text,
  );
}

function translateText(value) {
  if (!value) {
    return value;
  }
  return TEXT_I18N[currentLanguage]?.[value] || value;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function languageBar() {
  const buttons = LANGUAGES.map((language) => {
    const active = language.code === currentLanguage;
    return `
      <button
        class="flag-button ${active ? "active" : ""}"
        type="button"
        aria-pressed="${active}"
        title="${escapeHtml(language.label)}"
        onclick="ResQ.setLanguage('${language.code}')"
      >
        <span class="flag" aria-hidden="true">${language.flag}</span>
        <span>${language.code.toUpperCase()}</span>
      </button>
    `;
  }).join("");

  return `
    <nav class="language-bar" aria-label="${escapeHtml(t("languageLabel"))}">
      <span class="language-label">${escapeHtml(t("languageLabel"))}</span>
      <div class="flag-group">${buttons}</div>
    </nav>
  `;
}

function errorMarkup() {
  if (!lastError) {
    return "";
  }
  return `<div class="error-banner">${escapeHtml(lastError)}</div>`;
}

function getProtocolTranslation(protocolId) {
  return PROTOCOL_I18N[currentLanguage]?.protocols?.[protocolId] || {};
}

function localizeProtocol(protocol) {
  if (!protocol) {
    return null;
  }
  const translation = getProtocolTranslation(protocol.id);
  return {
    ...protocol,
    title: translation.title || protocol.title,
    disclaimer: translation.disclaimer || translateText(protocol.disclaimer),
  };
}

function localizeItem(item) {
  if (!item) {
    return null;
  }
  const translation = ITEM_I18N[currentLanguage]?.[item.refill_tag] || {};
  return {
    ...item,
    name: translation.name || translateText(item.name),
    compartment: translation.compartment || translateText(item.compartment),
  };
}

function localizeStep(protocolId, step) {
  if (!step) {
    return null;
  }
  const protocolTranslation = getProtocolTranslation(protocolId);
  const stepTranslation = protocolTranslation.steps?.[step.id] || {};
  const localized = {
    ...step,
    instruction: stepTranslation.instruction || translateText(step.instruction),
    action_label: stepTranslation.action_label || translateText(step.action_label) || t("continue"),
  };

  if (step.question) {
    localized.question = stepTranslation.question || translateText(step.question);
  }
  if (step.summary) {
    localized.summary = stepTranslation.summary || translateText(step.summary);
  }
  if (step.item) {
    localized.item = localizeItem(step.item);
  }
  return localized;
}

function diagnosticResult(testName) {
  const messages = {
    led: t("diagnosticCompartmentsDone"),
    refill_nfc: t("diagnosticRefillNfcDone"),
    audio: t("diagnosticAudioDone"),
    status: t("diagnosticStatusDone"),
  };
  return messages[testName] || t("ready");
}

async function guarded(action) {
  try {
    lastError = "";
    await action();
  } catch (error) {
    lastError = translateText(error.message);
    await sync();
  }
}

async function loadProtocols() {
  protocols = await request("/api/protocols");
}

async function sync() {
  if (!protocols.length) {
    await loadProtocols();
  }
  const state = await request("/api/state");
  renderFromState(state);
}

function renderFromState(state) {
  lastState = state;
  currentView = state.mode;

  if (state.mode === "selecting") {
    renderSelection();
    return;
  }
  if (state.mode === "protocol") {
    renderProtocol(state);
    return;
  }
  if (state.mode === "completed") {
    renderDone(state);
    return;
  }
  renderHome();
}

function renderHome() {
  currentView = "home";
  app.innerHTML = `
    <section class="screen home-screen">
      ${languageBar()}
      <div class="brand-block">
        <h1 class="brand">ResQ</h1>
        <p class="subtitle">Smart First Aid Case</p>
      </div>
      <div class="home-action">
        ${errorMarkup()}
        <button class="emergency-button" type="button" onclick="ResQ.startEmergency()">
          ${escapeHtml(t("emergencyStart"))}
        </button>
        <button class="maintenance-button" type="button" onclick="ResQ.openDiagnostics()">
          ${escapeHtml(t("maintenance"))}
        </button>
      </div>
      <p class="footer-note">
        ${escapeHtml(t("footerNote"))}
      </p>
    </section>
  `;
}

function renderSelection() {
  currentView = "selecting";
  const cards = protocols
    .map((protocol) => localizeProtocol(protocol))
    .map(
      (protocol) => `
        <button class="choice-card" type="button" onclick="ResQ.startProtocol('${escapeHtml(protocol.id)}')">
          <strong>${escapeHtml(protocol.title)}</strong>
          <span>${escapeHtml(protocol.disclaimer)}</span>
        </button>
      `,
    )
    .join("");

  app.innerHTML = `
    <section class="screen">
      ${languageBar()}
      <div class="topbar">
        <div class="topbar-title">
          <h1>${escapeHtml(t("selectionTitle"))}</h1>
          <p class="disclaimer">${escapeHtml(t("selectionSubtitle"))}</p>
        </div>
        <button class="ghost-button" type="button" onclick="ResQ.goHome()">${escapeHtml(t("home"))}</button>
      </div>
      ${errorMarkup()}
      <div class="selection-grid">${cards}</div>
    </section>
  `;
}

function protocolTopbar(state) {
  const protocol = localizeProtocol(state.protocol);
  return `
    <div class="topbar">
      <div class="topbar-title">
        <h1>${escapeHtml(protocol.title)}</h1>
        <p class="disclaimer">${escapeHtml(protocol.disclaimer)}</p>
      </div>
      <div class="action-row">
        <button class="ghost-button" type="button" onclick="ResQ.back()">${escapeHtml(t("back"))}</button>
        <button class="ghost-button" type="button" onclick="ResQ.repeatAudio()">${escapeHtml(t("repeatAudio"))}</button>
      </div>
    </div>
  `;
}

function renderProtocol(state) {
  currentView = "protocol";
  const protocol = localizeProtocol(state.protocol);
  const step = localizeStep(protocol.id, state.step);
  if (step.type === "item") {
    renderItem(state);
    return;
  }

  const controls =
    step.type === "question"
      ? `
        <div class="yes-no-row">
          <button class="choice-button yes-button" type="button" onclick="ResQ.answer('yes')">${t("yes")}</button>
          <button class="choice-button no-button" type="button" onclick="ResQ.answer('no')">${escapeHtml(t("no"))}</button>
        </div>
      `
      : `
        <div class="action-row">
          <button class="primary-button" type="button" onclick="ResQ.next()">${escapeHtml(step.action_label)}</button>
        </div>
      `;

  const question = step.question
    ? `<p class="question">${escapeHtml(step.question)}</p>`
    : "";

  app.innerHTML = `
    <section class="screen">
      ${languageBar()}
      ${protocolTopbar(state)}
      ${errorMarkup()}
      <div class="protocol-layout single-pane">
        <section class="primary-pane">
          <div>
            <div class="step-label">${escapeHtml(step.type === "question" ? t("question") : t("instruction"))}</div>
            <p class="instruction">${escapeHtml(step.instruction)}</p>
            ${question}
          </div>
          ${controls}
        </section>
      </div>
    </section>
  `;
}

function renderItem(state) {
  currentView = "protocol";
  const protocol = localizeProtocol(state.protocol);
  const step = localizeStep(protocol.id, state.step);
  const item = step.item;

  app.innerHTML = `
    <section class="screen">
      ${languageBar()}
      ${protocolTopbar(state)}
      ${errorMarkup()}
      <div class="protocol-layout single-pane">
        <section class="item-pane">
          <div class="step-label">${escapeHtml(t("requestedObject"))}</div>
          <h2 class="item-title">${escapeHtml(t("take"))}: ${escapeHtml(item.name)}</h2>
          <p class="compartment">${escapeHtml(t("compartment"))}: ${escapeHtml(item.compartment)}</p>
          <div class="action-row">
            <button class="primary-button" type="button" onclick="ResQ.next()">
              ${escapeHtml(t("confirmItem"))}
            </button>
          </div>
        </section>
      </div>
    </section>
  `;
}

function renderDone(state) {
  currentView = "completed";
  const protocol = localizeProtocol(state.protocol);
  const step = localizeStep(protocol.id, state.step);
  const items = state.requested_items
    .map((item) => localizeItem(item))
    .map(
      (item) => `
        <li>${escapeHtml(item.name)} - ${escapeHtml(item.compartment)}</li>
      `,
    )
    .join("");
  const answers = state.answers
    .map(
      (answer) => `
        <li>${escapeHtml(translateText(answer.question))}: ${answer.answer === "yes" ? escapeHtml(t("yes").replaceAll("&Igrave;", "I")) : escapeHtml(t("no"))}</li>
      `,
    )
    .join("");
  const summary = translateText(state.summary) || step?.summary || t("continue");

  app.innerHTML = `
    <section class="screen">
      ${languageBar()}
      <div class="topbar">
        <div class="topbar-title">
          <h1>${escapeHtml(t("endProtocol"))}</h1>
          <p class="disclaimer">${escapeHtml(protocol?.disclaimer || "")}</p>
        </div>
      </div>
      ${errorMarkup()}
      <section class="primary-pane">
        <div>
          <div class="step-label">${escapeHtml(protocol?.title || "ResQ")}</div>
          <p class="instruction">${escapeHtml(summary)}</p>
          <h2>${escapeHtml(t("requestedItems"))}</h2>
          <ul class="summary-list">${items || `<li>${escapeHtml(t("noRequestedItems"))}</li>`}</ul>
          <h2>${escapeHtml(t("answers"))}</h2>
          <ul class="summary-list">${answers || `<li>${escapeHtml(t("noAnswers"))}</li>`}</ul>
        </div>
        <div class="action-row">
          <button class="danger-button" type="button" onclick="ResQ.goHome()">${escapeHtml(t("backHome"))}</button>
        </div>
      </section>
    </section>
  `;
}

function renderDiagnostics() {
  currentView = "diagnostics";
  app.innerHTML = `
    <section class="screen">
      ${languageBar()}
      <div class="topbar">
        <div class="topbar-title">
          <h1>${escapeHtml(t("diagnostics"))}</h1>
          <p class="disclaimer">${escapeHtml(t("diagnosticsSubtitle"))}</p>
        </div>
        <button class="ghost-button" type="button" onclick="ResQ.goHome()">${escapeHtml(t("home"))}</button>
      </div>
      ${errorMarkup()}
      <div class="diagnostic-grid">
        <button class="diagnostic-button" type="button" onclick="ResQ.runDiagnostic('led')">${escapeHtml(t("testCompartments"))}</button>
        <button class="diagnostic-button" type="button" onclick="ResQ.runDiagnostic('refill_nfc')">${escapeHtml(t("testRefillNfc"))}</button>
        <button class="diagnostic-button" type="button" onclick="ResQ.runDiagnostic('audio')">${escapeHtml(t("testAudio"))}</button>
        <button class="diagnostic-button" type="button" onclick="ResQ.runDiagnostic('status')">${escapeHtml(t("appStatus"))}</button>
      </div>
      <div class="diagnostic-result">${escapeHtml(diagnosticMessage || t("ready"))}</div>
    </section>
  `;
}

function setLanguage(language) {
  if (!LANGUAGES.some((item) => item.code === language)) {
    return;
  }
  currentLanguage = language;
  localStorage.setItem(LANGUAGE_KEY, currentLanguage);
  document.documentElement.lang = currentLanguage;
  if (currentDiagnosticTest) {
    diagnosticMessage = diagnosticResult(currentDiagnosticTest);
  }
  if (currentView === "diagnostics") {
    renderDiagnostics();
    return;
  }
  if (lastState) {
    renderFromState(lastState);
    return;
  }
  sync();
}

async function startEmergency() {
  await guarded(async () => {
    diagnosticMessage = "";
    currentDiagnosticTest = "";
    const state = await request("/api/emergency/start", { method: "POST" });
    renderFromState(state);
  });
}

async function startProtocol(protocolId) {
  await guarded(async () => {
    const state = await request(`/api/protocols/${encodeURIComponent(protocolId)}/start`, {
      method: "POST",
    });
    renderFromState(state);
  });
}

async function answer(value) {
  await guarded(async () => {
    const state = await request("/api/answer", {
      method: "POST",
      body: JSON.stringify({ answer: value }),
    });
    renderFromState(state);
  });
}

async function next() {
  await guarded(async () => {
    const state = await request("/api/next", { method: "POST" });
    renderFromState(state);
  });
}

async function back() {
  await guarded(async () => {
    const state = await request("/api/back", { method: "POST" });
    renderFromState(state);
  });
}

async function repeatAudio() {
  await guarded(async () => {
    const state = await request("/api/audio/repeat", { method: "POST" });
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
  renderDiagnostics();
}

async function runDiagnostic(testName) {
  await guarded(async () => {
    await request(`/api/diagnostics/${encodeURIComponent(testName)}`, {
      method: "POST",
    });
    currentDiagnosticTest = testName;
    diagnosticMessage = diagnosticResult(testName);
    renderDiagnostics();
  });
}

async function pressHardware(buttonName) {
  await guarded(async () => {
    const state = await request(`/api/buttons/${encodeURIComponent(buttonName)}`, {
      method: "POST",
    });
    renderFromState(state);
  });
}

document.addEventListener("keydown", (event) => {
  const tagName = event.target?.tagName || "";
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tagName)) {
    return;
  }

  const key = event.key.toLowerCase();
  const map = {
    y: "yes",
    s: "yes",
    n: "no",
    escape: "back",
    backspace: "back",
    r: "repeat_audio",
    h: "home_emergency",
    " ": "home_emergency",
  };

  if (map[key]) {
    event.preventDefault();
    pressHardware(map[key]);
  }
});

window.ResQ = {
  setLanguage,
  startEmergency,
  startProtocol,
  answer,
  next,
  back,
  repeatAudio,
  goHome,
  openDiagnostics,
  runDiagnostic,
};

sync();
