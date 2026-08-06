"use strict";

const STORAGE = {
  conversations: "kimi_workspace_conversations_v1",
  activeConversation: "kimi_workspace_active_v1",
  theme: "kimi_workspace_theme_v1",
  sessionKey: "kimi_gateway_key_session_v1",
  rememberedKey: "kimi_gateway_key_local_v1",
};

const MODEL_LABELS = {
  "kimi-k2.6": "Kimi K2.6 · متوازن",
  "kimi-k2.7-code": "Kimi K2.7 Code · موصى به للبرمجة",
  "kimi-k2.7-code-highspeed": "Kimi K2.7 Code Highspeed · أسرع",
  "kimi-k3": "Kimi K3 · أقوى استدلال",
};

const dom = {
  appShell: document.getElementById("appShell"),
  authOverlay: document.getElementById("authOverlay"),
  authForm: document.getElementById("authForm"),
  authSubmit: document.getElementById("authSubmit"),
  authError: document.getElementById("authError"),
  gatewayKey: document.getElementById("gatewayKey"),
  rememberKey: document.getElementById("rememberKey"),
  toggleSecret: document.getElementById("toggleSecret"),
  sidebar: document.getElementById("sidebar"),
  sidebarBackdrop: document.getElementById("sidebarBackdrop"),
  openSidebar: document.getElementById("openSidebar"),
  closeSidebar: document.getElementById("closeSidebar"),
  newChatButton: document.getElementById("newChatButton"),
  conversationSearch: document.getElementById("conversationSearch"),
  conversationList: document.getElementById("conversationList"),
  conversationCount: document.getElementById("conversationCount"),
  exportButton: document.getElementById("exportButton"),
  deleteButton: document.getElementById("deleteButton"),
  conversationTitle: document.getElementById("conversationTitle"),
  connectionDot: document.getElementById("connectionDot"),
  connectionStatus: document.getElementById("connectionStatus"),
  modelSelect: document.getElementById("modelSelect"),
  themeButton: document.getElementById("themeButton"),
  lockButton: document.getElementById("lockButton"),
  messages: document.getElementById("messages"),
  composer: document.getElementById("composer"),
  messageInput: document.getElementById("messageInput"),
  sendButton: document.getElementById("sendButton"),
  toast: document.getElementById("toast"),
};

const state = {
  conversations: loadConversations(),
  activeId: localStorage.getItem(STORAGE.activeConversation),
  gatewayKey: "",
  models: [],
  defaultModel: "",
  isSending: false,
  toastTimer: null,
};

initialize();

function initialize() {
  applyInitialTheme();
  ensureActiveConversation();
  bindEvents();
  renderAll();

  const savedKey = getSavedGatewayKey();
  if (savedKey) {
    unlockWorkspace(savedKey, Boolean(localStorage.getItem(STORAGE.rememberedKey)), true);
  } else {
    showAuthentication();
  }
}

function bindEvents() {
  dom.authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const key = dom.gatewayKey.value.trim();
    if (!key) {
      dom.authError.textContent = "أدخل مفتاح الدخول أولًا.";
      return;
    }
    await unlockWorkspace(key, dom.rememberKey.checked, false);
  });

  dom.toggleSecret.addEventListener("click", () => {
    dom.gatewayKey.type = dom.gatewayKey.type === "password" ? "text" : "password";
  });

  dom.lockButton.addEventListener("click", () => {
    clearSavedGatewayKey();
    state.gatewayKey = "";
    showAuthentication("أدخل مفتاحًا جديدًا للمتابعة.");
  });

  dom.newChatButton.addEventListener("click", () => {
    createConversation();
    closeMobileSidebar();
    dom.messageInput.focus();
  });

  dom.conversationSearch.addEventListener("input", renderConversationList);
  dom.exportButton.addEventListener("click", exportActiveConversation);
  dom.deleteButton.addEventListener("click", deleteActiveConversation);

  dom.modelSelect.addEventListener("change", () => {
    const conversation = getActiveConversation();
    if (!conversation) return;
    conversation.model = dom.modelSelect.value;
    conversation.updatedAt = new Date().toISOString();
    persistConversations();
    renderConversationList();
    showToast(`تم اختيار ${getModelLabel(conversation.model)}`);
  });

  dom.themeButton.addEventListener("click", toggleTheme);
  dom.openSidebar.addEventListener("click", openMobileSidebar);
  dom.closeSidebar.addEventListener("click", closeMobileSidebar);
  dom.sidebarBackdrop.addEventListener("click", closeMobileSidebar);

  dom.composer.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendCurrentMessage();
  });

  dom.messageInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      await sendCurrentMessage();
    }
  });

  dom.messageInput.addEventListener("input", resizeComposer);
}

async function unlockWorkspace(key, remember, automatic) {
  setAuthBusy(true);
  dom.authError.textContent = automatic ? "جاري التحقق من المفتاح المحفوظ…" : "";
  setConnection("جاري التحقق…", "pending");

  try {
    const { models, defaultModel } = await fetchWorkspaceConfiguration(key);
    state.gatewayKey = key;
    state.models = models;
    state.defaultModel = defaultModel;
    saveGatewayKey(key, remember);
    normalizeConversationModels();
    populateModelSelect();
    persistConversations();
    hideAuthentication();
    renderAll();
    setConnection("متصل وآمن", "online");
    dom.messageInput.focus();
  } catch (error) {
    state.gatewayKey = "";
    clearSavedGatewayKey();
    setConnection("غير متصل", "offline");
    dom.authError.textContent = humanizeError(error, "تعذر التحقق من مفتاح الدخول.");
    if (automatic) {
      dom.gatewayKey.value = "";
    }
  } finally {
    setAuthBusy(false);
  }
}

async function fetchWorkspaceConfiguration(key) {
  const headers = { "X-API-Key": key };
  const [healthResponse, modelsResponse] = await Promise.all([
    fetch("/health", { cache: "no-store" }),
    fetch("/models", { headers, cache: "no-store" }),
  ]);

  const modelsPayload = await readJson(modelsResponse);
  if (!modelsResponse.ok) {
    const error = new Error(modelsPayload.detail || "تعذر قراءة النماذج المتاحة.");
    error.status = modelsResponse.status;
    throw error;
  }

  const healthPayload = healthResponse.ok ? await readJson(healthResponse) : {};
  const models = Array.isArray(modelsPayload.models)
    ? modelsPayload.models.filter((model) => typeof model === "string")
    : [];

  if (!models.length) {
    throw new Error("لم تُرجع الخدمة أي نماذج متاحة.");
  }

  const defaultModel = models.includes(healthPayload.model)
    ? healthPayload.model
    : models[0];

  return { models, defaultModel };
}

function showAuthentication(message = "") {
  dom.appShell.classList.add("is-locked");
  dom.authOverlay.classList.remove("hidden");
  dom.authError.textContent = message;
  window.setTimeout(() => dom.gatewayKey.focus(), 60);
}

function hideAuthentication() {
  dom.authOverlay.classList.add("hidden");
  dom.appShell.classList.remove("is-locked");
  dom.gatewayKey.value = "";
  dom.authError.textContent = "";
}

function setAuthBusy(isBusy) {
  dom.authSubmit.disabled = isBusy;
  dom.gatewayKey.disabled = isBusy;
  dom.authSubmit.querySelector("span").textContent = isBusy
    ? "جاري التحقق…"
    : "فتح مساحة العمل";
}

function getSavedGatewayKey() {
  return sessionStorage.getItem(STORAGE.sessionKey)
    || localStorage.getItem(STORAGE.rememberedKey)
    || "";
}

function saveGatewayKey(key, remember) {
  clearSavedGatewayKey();
  if (remember) {
    localStorage.setItem(STORAGE.rememberedKey, key);
  } else {
    sessionStorage.setItem(STORAGE.sessionKey, key);
  }
}

function clearSavedGatewayKey() {
  sessionStorage.removeItem(STORAGE.sessionKey);
  localStorage.removeItem(STORAGE.rememberedKey);
}

function loadConversations() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE.conversations) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item.id === "string")
      .map((item) => ({
        id: item.id,
        title: typeof item.title === "string" ? item.title : "محادثة جديدة",
        model: typeof item.model === "string" ? item.model : "",
        messages: Array.isArray(item.messages)
          ? item.messages.filter(isValidSavedMessage).slice(-200)
          : [],
        createdAt: item.createdAt || new Date().toISOString(),
        updatedAt: item.updatedAt || new Date().toISOString(),
      }));
  } catch {
    return [];
  }
}

function isValidSavedMessage(message) {
  return message
    && ["user", "assistant"].includes(message.role)
    && typeof message.content === "string";
}

function ensureActiveConversation() {
  if (!state.conversations.length) {
    const conversation = buildConversation();
    state.conversations.push(conversation);
    state.activeId = conversation.id;
  }

  if (!state.conversations.some((item) => item.id === state.activeId)) {
    state.activeId = [...state.conversations]
      .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))[0].id;
  }

  localStorage.setItem(STORAGE.activeConversation, state.activeId);
}

function buildConversation() {
  const now = new Date().toISOString();
  return {
    id: makeId(),
    title: "محادثة جديدة",
    model: state.defaultModel || state.models[0] || "",
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

function createConversation() {
  const conversation = buildConversation();
  state.conversations.push(conversation);
  state.activeId = conversation.id;
  persistConversations();
  renderAll();
}

function getActiveConversation() {
  return state.conversations.find((item) => item.id === state.activeId) || null;
}

function setActiveConversation(id) {
  if (!state.conversations.some((item) => item.id === id)) return;
  state.activeId = id;
  localStorage.setItem(STORAGE.activeConversation, id);
  renderAll();
  closeMobileSidebar();
}

function normalizeConversationModels() {
  for (const conversation of state.conversations) {
    if (!state.models.includes(conversation.model)) {
      conversation.model = state.defaultModel || state.models[0];
    }
  }
}

function persistConversations() {
  try {
    localStorage.setItem(STORAGE.conversations, JSON.stringify(state.conversations));
    localStorage.setItem(STORAGE.activeConversation, state.activeId);
  } catch {
    showToast("تعذر حفظ المحادثات محليًا؛ قد تكون مساحة المتصفح ممتلئة.");
  }
}

function renderAll() {
  renderConversationList();
  renderHeader();
  renderMessages();
  populateModelSelect();
}

function renderConversationList() {
  const query = dom.conversationSearch.value.trim().toLocaleLowerCase("ar");
  const sorted = [...state.conversations].sort(
    (a, b) => new Date(b.updatedAt) - new Date(a.updatedAt),
  );
  const filtered = query
    ? sorted.filter((item) => item.title.toLocaleLowerCase("ar").includes(query))
    : sorted;

  dom.conversationCount.textContent = String(state.conversations.length);
  dom.conversationList.replaceChildren();

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty-history";
    empty.textContent = "لا توجد محادثات مطابقة لبحثك.";
    dom.conversationList.appendChild(empty);
    return;
  }

  for (const conversation of filtered) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `conversation-item${conversation.id === state.activeId ? " active" : ""}`;
    button.dataset.id = conversation.id;
    button.innerHTML = `
      <span class="conversation-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M5 6h14v10H9l-4 4V6Z"/></svg>
      </span>
      <span class="conversation-copy">
        <span class="conversation-name"></span>
        <span class="conversation-meta"></span>
      </span>
    `;
    button.querySelector(".conversation-name").textContent = conversation.title;
    button.querySelector(".conversation-meta").textContent = `${getModelShortLabel(conversation.model)} · ${formatRelativeDate(conversation.updatedAt)}`;
    button.addEventListener("click", () => setActiveConversation(conversation.id));
    dom.conversationList.appendChild(button);
  }
}

function renderHeader() {
  const conversation = getActiveConversation();
  dom.conversationTitle.textContent = conversation?.title || "محادثة جديدة";
  document.title = conversation && conversation.title !== "محادثة جديدة"
    ? `${conversation.title} · Kimi`
    : "Kimi Coding Workspace";
}

function populateModelSelect() {
  const conversation = getActiveConversation();
  const currentValue = conversation?.model || state.defaultModel;
  dom.modelSelect.replaceChildren();

  if (!state.models.length) {
    const option = document.createElement("option");
    option.value = currentValue || "";
    option.textContent = currentValue ? getModelLabel(currentValue) : "جاري تحميل النماذج…";
    dom.modelSelect.appendChild(option);
    dom.modelSelect.disabled = true;
    return;
  }

  dom.modelSelect.disabled = false;
  for (const model of state.models) {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = getModelLabel(model);
    option.selected = model === currentValue;
    dom.modelSelect.appendChild(option);
  }
}

function renderMessages() {
  const conversation = getActiveConversation();
  dom.messages.replaceChildren();

  if (!conversation || !conversation.messages.length) {
    renderWelcome();
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const message of conversation.messages) {
    fragment.appendChild(buildMessageElement(message));
  }

  if (state.isSending) {
    fragment.appendChild(buildTypingElement());
  }

  dom.messages.appendChild(fragment);
  attachCopyHandlers();
  scrollMessagesToBottom(false);
}

function renderWelcome() {
  const welcome = document.createElement("div");
  welcome.className = "welcome";
  welcome.innerHTML = `
    <div class="welcome-badge"><span></span>جاهز باستخدام ${escapeHtml(getModelShortLabel(getActiveConversation()?.model || state.defaultModel))}</div>
    <h1>حوّل فكرتك إلى <span class="gradient-text">كود جاهز للعمل</span></h1>
    <p>اطلب بناء ميزة، تحليل خطأ، مراجعة معمارية، أو تحسين مشروع كامل. تُحفظ محادثاتك تلقائيًا على هذا المتصفح.</p>
    <div class="prompt-grid">
      <button class="prompt-card" type="button" data-prompt="صمّم لي هيكل مشروع FastAPI احترافي يلتزم بمبادئ SOLID، واشرح وظيفة كل ملف.">
        <strong>تصميم مشروع احترافي</strong>
        <small>هيكل واضح، فصل مسؤوليات، وإعداد جاهز للإنتاج.</small>
        <svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>
      </button>
      <button class="prompt-card" type="button" data-prompt="سأرسل لك رسالة خطأ برمجية. حلّل السبب الجذري ثم أعطني خطوات إصلاح آمنة خطوة بخطوة.">
        <strong>تحليل خطأ معقّد</strong>
        <small>تحديد السبب الجذري وخطة إصلاح قابلة للتنفيذ.</small>
        <svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>
      </button>
      <button class="prompt-card" type="button" data-prompt="راجع الكود الذي سأرسله من ناحية الأمان والأداء وقابلية الصيانة، ثم اقترح نسخة محسنة كاملة.">
        <strong>مراجعة وتحسين الكود</strong>
        <small>أمان، أداء، نظافة الكود، وقابلية الصيانة.</small>
        <svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>
      </button>
      <button class="prompt-card" type="button" data-prompt="ساعدني في إضافة ميزة جديدة إلى مشروعي. ابدأ بأسئلة المتطلبات الضرورية فقط ثم اقترح خطة تنفيذ واختبارات.">
        <strong>بناء ميزة جديدة</strong>
        <small>من المتطلبات إلى التنفيذ والاختبارات.</small>
        <svg viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>
      </button>
    </div>
  `;

  welcome.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", async () => {
      dom.messageInput.value = button.dataset.prompt;
      resizeComposer();
      await sendCurrentMessage();
    });
  });

  dom.messages.appendChild(welcome);
}

function buildMessageElement(message) {
  const row = document.createElement("article");
  row.className = `message-row ${message.role}`;
  row.dataset.rawContent = message.content;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = message.role === "user" ? "أنت" : "K";
  avatar.setAttribute("aria-hidden", "true");

  const card = document.createElement("div");
  card.className = "message-card";
  card.innerHTML = `
    <div class="message-meta">
      <span class="message-role">${message.role === "user" ? "أنت" : "Kimi"}</span>
      <button class="copy-message" type="button" aria-label="نسخ الرسالة">
        <svg viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>
        نسخ
      </button>
    </div>
    <div class="message-content">${formatMessageContent(message.content)}</div>
  `;

  row.append(avatar, card);
  return row;
}

function buildTypingElement() {
  const row = document.createElement("article");
  row.className = "message-row assistant";
  row.innerHTML = `
    <div class="message-avatar" aria-hidden="true">K</div>
    <div class="message-card">
      <div class="message-meta"><span class="message-role">Kimi يفكّر</span></div>
      <div class="typing-dots" aria-label="جاري إعداد الرد"><span></span><span></span><span></span></div>
    </div>
  `;
  return row;
}

function formatMessageContent(text) {
  const codePattern = /```([a-zA-Z0-9_+.-]*)\r?\n([\s\S]*?)```/g;
  let html = "";
  let cursor = 0;
  let match;

  while ((match = codePattern.exec(text)) !== null) {
    html += formatPlainText(text.slice(cursor, match.index));
    const language = escapeHtml(match[1] || "code");
    const code = escapeHtml(match[2].replace(/\n$/, ""));
    html += `
      <div class="code-block">
        <div class="code-header"><span>${language}</span><button class="copy-code" type="button">نسخ الكود</button></div>
        <pre><code>${code}</code></pre>
      </div>
    `;
    cursor = codePattern.lastIndex;
  }

  html += formatPlainText(text.slice(cursor));
  return html;
}

function formatPlainText(text) {
  return escapeHtml(text)
    .replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>')
    .replace(/\n/g, "<br>");
}

function attachCopyHandlers() {
  dom.messages.querySelectorAll(".copy-message").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = button.closest(".message-row");
      await copyText(row?.dataset.rawContent || "");
      showToast("تم نسخ الرسالة.");
    });
  });

  dom.messages.querySelectorAll(".copy-code").forEach((button) => {
    button.addEventListener("click", async () => {
      const code = button.closest(".code-block")?.querySelector("code")?.textContent || "";
      await copyText(code);
      button.textContent = "تم النسخ";
      window.setTimeout(() => { button.textContent = "نسخ الكود"; }, 1200);
    });
  });
}

async function sendCurrentMessage() {
  const text = dom.messageInput.value.trim();
  if (!text || state.isSending) return;

  if (!state.gatewayKey) {
    showAuthentication("أدخل مفتاح الدخول قبل إرسال الرسائل.");
    return;
  }

  const conversation = getActiveConversation();
  if (!conversation) return;

  if (!conversation.model) {
    showToast("اختر نموذجًا أولًا.");
    return;
  }

  const history = conversation.messages
    .slice(-40)
    .map(({ role, content }) => ({ role, content }));

  const now = new Date().toISOString();

  conversation.messages.push({
    role: "user",
    content: text,
    createdAt: now,
  });

  conversation.updatedAt = now;

  if (conversation.title === "محادثة جديدة") {
    conversation.title = makeConversationTitle(text);
  }

  dom.messageInput.value = "";
  resizeComposer();

  state.isSending = true;
  dom.sendButton.disabled = true;

  persistConversations();
  renderAll();
  scrollMessagesToBottom(true);

  let assistantMessage = null;
  let renderScheduled = false;

  const scheduleStreamRender = () => {
    if (renderScheduled) return;

    renderScheduled = true;

    window.requestAnimationFrame(() => {
      renderScheduled = false;
      renderAll();
      scrollMessagesToBottom(false);
    });
  };

  try {
    const response = await fetch("/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": state.gatewayKey,
      },
      body: JSON.stringify({
        message: text,
        model: conversation.model,
        history,
      }),
    });

    if (!response.ok) {
      const payload = await readJson(response);
      const error = new Error(
        payload.detail || `فشل الطلب برمز ${response.status}.`,
      );
      error.status = response.status;
      throw error;
    }

    if (!response.body) {
      throw new Error("المتصفح لا يدعم قراءة الرد المتدفق.");
    }

    assistantMessage = {
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
    };

    conversation.messages.push(assistantMessage);
    renderAll();
    scrollMessagesToBottom(true);

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let completed = false;

    const processLine = (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;

      let event;

      try {
        event = JSON.parse(trimmed);
      } catch {
        throw new Error("وصلت بيانات غير صالحة من الخادم.");
      }

      if (event.type === "delta") {
        assistantMessage.content += event.content || "";
        conversation.updatedAt = new Date().toISOString();
        scheduleStreamRender();
        return;
      }

      if (event.type === "done") {
        completed = true;
        conversation.model = event.model || conversation.model;
        return;
      }

      if (event.type === "error") {
        throw new Error(event.detail || "حدث خطأ أثناء بث الرد.");
      }
    };

    while (true) {
      const { value, done } = await reader.read();

      buffer += decoder.decode(value || new Uint8Array(), {
        stream: !done,
      });

      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        processLine(line);
      }

      if (done) {
        if (buffer.trim()) {
          processLine(buffer);
        }
        break;
      }
    }

    if (!completed && !assistantMessage.content.trim()) {
      throw new Error("انتهى الاتصال من دون استلام رد.");
    }

    if (!assistantMessage.content.trim()) {
      assistantMessage.content = "لم يُرجع النموذج نصًا.";
    }

    conversation.updatedAt = new Date().toISOString();
    persistConversations();
    setConnection("متصل وآمن", "online");
  } catch (error) {
    if (assistantMessage && !assistantMessage.content.trim()) {
      conversation.messages = conversation.messages.filter(
        (message) => message !== assistantMessage,
      );
    }

    persistConversations();

    if (error.status === 401) {
      state.gatewayKey = "";
      clearSavedGatewayKey();
      showAuthentication(
        "انتهت صلاحية مفتاح الدخول أو تم تغييره.",
      );
    } else {
      showToast(humanizeError(error, "تعذر إرسال الرسالة."));
      setConnection("حدث خطأ في الطلب", "offline");
    }
  } finally {
    state.isSending = false;
    dom.sendButton.disabled = false;

    persistConversations();
    renderAll();
    scrollMessagesToBottom(true);
    dom.messageInput.focus();
  }
}

function deleteActiveConversation() {
  const conversation = getActiveConversation();
  if (!conversation) return;
  const confirmed = window.confirm(`هل تريد حذف "${conversation.title}" نهائيًا من هذا المتصفح؟`);
  if (!confirmed) return;

  state.conversations = state.conversations.filter((item) => item.id !== conversation.id);
  if (!state.conversations.length) {
    state.conversations.push(buildConversation());
  }
  state.activeId = [...state.conversations]
    .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))[0].id;
  persistConversations();
  renderAll();
  showToast("تم حذف المحادثة.");
}

function exportActiveConversation() {
  const conversation = getActiveConversation();
  if (!conversation) return;

  const exportData = {
    title: conversation.title,
    model: conversation.model,
    createdAt: conversation.createdAt,
    exportedAt: new Date().toISOString(),
    messages: conversation.messages.map(({ role, content, createdAt }) => ({
      role,
      content,
      createdAt,
    })),
  };

  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${sanitizeFileName(conversation.title)}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  showToast("تم تصدير المحادثة بصيغة JSON.");
}

function resizeComposer() {
  dom.messageInput.style.height = "auto";
  dom.messageInput.style.height = `${Math.min(dom.messageInput.scrollHeight, 190)}px`;
}

function openMobileSidebar() {
  dom.sidebar.classList.add("open");
  dom.sidebarBackdrop.classList.add("show");
}

function closeMobileSidebar() {
  dom.sidebar.classList.remove("open");
  dom.sidebarBackdrop.classList.remove("show");
}

function applyInitialTheme() {
  const saved = localStorage.getItem(STORAGE.theme);
  const theme = saved || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  document.documentElement.dataset.theme = theme;
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme || "dark";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem(STORAGE.theme, next);
  showToast(next === "dark" ? "تم تفعيل الوضع الداكن." : "تم تفعيل الوضع الفاتح.");
}

function setConnection(text, type) {
  dom.connectionStatus.textContent = text;
  dom.connectionDot.classList.remove("online", "offline");
  if (type === "online") dom.connectionDot.classList.add("online");
  if (type === "offline") dom.connectionDot.classList.add("offline");
}

function showToast(message) {
  window.clearTimeout(state.toastTimer);
  dom.toast.textContent = message;
  dom.toast.classList.add("show");
  state.toastTimer = window.setTimeout(() => dom.toast.classList.remove("show"), 3200);
}

function scrollMessagesToBottom(smooth) {
  window.requestAnimationFrame(() => {
    dom.messages.scrollTo({
      top: dom.messages.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  });
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function humanizeError(error, fallback) {
  if (error?.status === 401) return "مفتاح الدخول غير صحيح.";
  if (error?.status === 400) return error.message || "الطلب غير صالح.";
  if (error?.status === 429) return "تم بلوغ حد الاستخدام أو الرصيد المتاح.";
  if (error?.status === 502) return "تعذر الحصول على رد من مزود النموذج.";
  if (error?.status === 504) return "استغرق النموذج وقتًا أطول من المسموح.";
  return error?.message || fallback;
}

function getModelLabel(model) {
  return MODEL_LABELS[model] || model || "نموذج غير محدد";
}

function getModelShortLabel(model) {
  if (!model) return "Kimi";
  if (model === "kimi-k2.7-code-highspeed") return "K2.7 Highspeed";
  if (model === "kimi-k2.7-code") return "K2.7 Code";
  if (model === "kimi-k2.6") return "K2.6";
  if (model === "kimi-k3") return "K3";
  return model;
}

function makeConversationTitle(text) {
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > 46 ? `${compact.slice(0, 46)}…` : compact;
}

function formatRelativeDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "الآن";
  const diff = Date.now() - date.getTime();
  if (diff < 60_000) return "الآن";
  if (diff < 3_600_000) return `منذ ${Math.floor(diff / 60_000)} د`;
  if (diff < 86_400_000) return `منذ ${Math.floor(diff / 3_600_000)} س`;
  return new Intl.DateTimeFormat("ar-SA", { month: "short", day: "numeric" }).format(date);
}

function sanitizeFileName(value) {
  return (value || "kimi-conversation")
    .replace(/[\\/:*?"<>|]/g, "-")
    .replace(/\s+/g, "-")
    .slice(0, 80);
}

function makeId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
