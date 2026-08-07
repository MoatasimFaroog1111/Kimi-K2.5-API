import { STORAGE } from "./constants.js";
import { getModelLabel, humanizeError, sanitizeFileName } from "./utils.js";

export class ChatController {
  constructor({ store, api, auth, sidebar, header, messages, composer, toast }) {
    this.store = store;
    this.api = api;
    this.auth = auth;
    this.sidebar = sidebar;
    this.header = header;
    this.messages = messages;
    this.composer = composer;
    this.toast = toast;
  }

  initialize() {
    this.#applyInitialTheme();
    this.#bindComponents();
    this.renderAll();

    const savedKey = this.store.savedGatewayKey;
    if (savedKey) {
      this.unlock(savedKey, this.store.rememberedGatewayKey, true);
    } else {
      this.auth.show();
    }

    window.addEventListener("kimi:mode-change", (event) => {
      if (event.detail?.mode === "chat") this.renderAll();
    });
  }

  async unlock(key, remember, automatic = false) {
    this.auth.setBusy(true);
    this.auth.setError(automatic ? "جاري التحقق من المفتاح المحفوظ…" : "");
    this.header.setConnection("جاري الاتصال…", "pending");

    try {
      const { models, defaultModel } = await this.api.configuration(key);
      this.store.setGatewayKey(key, remember);
      this.store.setModels(models, defaultModel);
      this.auth.hide();
      this.renderAll();
      this.header.setConnection("متصل", "online");
      this.composer.focus();
    } catch (error) {
      this.store.clearGatewayKey();
      this.header.setConnection("غير متصل", "offline");
      this.auth.setError(humanizeError(error, "تعذر التحقق من مفتاح الدخول."));
      if (automatic) this.auth.input.value = "";
    } finally {
      this.auth.setBusy(false);
    }
  }

  renderAll() {
    const { conversations, activeId, models, defaultModel, isSending } = this.store.state;
    const conversation = this.store.activeConversation;
    this.sidebar.render(conversations, activeId);
    this.header.renderTitle(conversation?.title || "محادثة جديدة");
    this.composer.renderModels(models, conversation?.model || defaultModel);
    this.messages.render(
      conversation,
      isSending,
      getModelLabel(conversation?.model || defaultModel),
    );
  }

  async sendCurrentMessage(providedText = "") {
    if (document.documentElement.dataset.workspaceMode === "agent") return;
    const text = (providedText || this.composer.value).trim();
    if (!text || this.store.state.isSending) return;

    if (!this.store.state.gatewayKey) {
      this.auth.show("أدخل مفتاح الدخول قبل إرسال الرسائل.");
      return;
    }

    const conversation = this.store.activeConversation;
    if (!conversation?.model) {
      this.toast.show("اختر نموذجًا أولًا.");
      return;
    }

    const history = this.store.history(40);
    this.store.addUserMessage(text);
    this.composer.clear();
    this.store.state.isSending = true;
    this.composer.setBusy(true);
    const assistantMessage = this.store.addAssistantMessage("");
    this.renderAll();
    this.messages.scrollToBottom(true);

    let completed = false;
    let renderScheduled = false;
    const scheduleRender = () => {
      if (renderScheduled) return;
      renderScheduled = true;
      window.requestAnimationFrame(() => {
        renderScheduled = false;
        this.renderAll();
        this.messages.scrollToBottom(false);
      });
    };

    try {
      await this.api.streamMessage({
        key: this.store.state.gatewayKey,
        message: text,
        model: conversation.model,
        history,
        onEvent: (event) => {
          if (event.type === "delta") {
            assistantMessage.content += event.content || "";
            this.store.touch();
            scheduleRender();
            return;
          }
          if (event.type === "done") {
            completed = true;
            if (event.model) conversation.model = event.model;
            return;
          }
          if (event.type === "error") {
            const error = new Error(event.detail || "حدث خطأ أثناء بث الرد.");
            throw error;
          }
        },
      });

      if (!completed && !assistantMessage.content.trim()) {
        throw new Error("انتهى الاتصال من دون استلام رد.");
      }
      if (!assistantMessage.content.trim()) {
        assistantMessage.content = "لم يُرجع النموذج نصًا.";
      }
      this.store.touch();
      this.store.persist();
      this.header.setConnection("متصل", "online");
    } catch (error) {
      if (!assistantMessage.content.trim()) {
        this.store.removeMessage(assistantMessage);
      }

      if (error.status === 401) {
        this.store.clearGatewayKey();
        this.auth.show("انتهت صلاحية مفتاح الدخول أو تم تغييره.");
      } else {
        this.toast.show(humanizeError(error, "تعذر إرسال الرسالة."));
        this.header.setConnection("تعذر إكمال الطلب", "offline");
      }
    } finally {
      this.store.state.isSending = false;
      this.composer.setBusy(false);
      if (!this.store.persist()) {
        this.toast.show("تعذر حفظ المحادثة محليًا.");
      }
      this.renderAll();
      this.messages.scrollToBottom(true);
      this.composer.focus();
    }
  }

  #bindComponents() {
    this.auth.bind({
      onSubmit: (key, remember) => this.unlock(key, remember, false),
    });

    this.sidebar.bind({
      onNew: () => {
        this.store.createConversation();
        this.sidebar.close();
        this.renderAll();
        this.composer.focus();
      },
      onSearch: () => this.sidebar.render(this.store.state.conversations, this.store.state.activeId),
      onSelect: (id) => {
        this.store.selectConversation(id);
        this.sidebar.close();
        this.renderAll();
      },
      onExport: () => this.#exportConversation(),
      onDelete: () => this.#deleteConversation(),
    });

    this.header.bind({
      onTheme: () => this.#toggleTheme(),
      onLock: () => {
        this.store.clearGatewayKey();
        this.auth.show("أدخل مفتاحًا جديدًا للمتابعة.");
      },
    });

    this.messages.bind({
      onPrompt: async (prompt) => {
        this.composer.setValue(prompt);
        await this.sendCurrentMessage(prompt);
      },
    });

    this.composer.bind({
      onSubmit: (text) => this.sendCurrentMessage(text),
      onModelChange: (model) => {
        this.store.setActiveModel(model);
        this.renderAll();
        this.toast.show(`تم اختيار ${getModelLabel(model)}`);
      },
    });
  }

  #deleteConversation() {
    const conversation = this.store.activeConversation;
    if (!conversation) return;
    const confirmed = window.confirm(`حذف «${conversation.title}» من هذا المتصفح؟`);
    if (!confirmed) return;
    this.store.deleteActiveConversation();
    this.renderAll();
    this.toast.show("تم حذف المحادثة.");
  }

  #exportConversation() {
    const data = this.store.exportActiveConversation();
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${sanitizeFileName(data.title)}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    this.toast.show("تم تصدير المحادثة.");
  }

  #applyInitialTheme() {
    const saved = window.localStorage.getItem(STORAGE.theme);
    document.documentElement.dataset.theme = saved || "light";
  }

  #toggleTheme() {
    const current = document.documentElement.dataset.theme || "light";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem(STORAGE.theme, next);
    this.toast.show(next === "dark" ? "الوضع الداكن" : "الوضع الفاتح");
  }
}
