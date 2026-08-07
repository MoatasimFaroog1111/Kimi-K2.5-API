import { DEFAULT_CONVERSATION_TITLE, STORAGE } from "./constants.js";
import { makeConversationTitle, makeId } from "./utils.js";

export class ChatStore {
  constructor(local = window.localStorage, session = window.sessionStorage) {
    this.local = local;
    this.session = session;
    this.state = {
      conversations: this.#loadConversations(),
      activeId: this.local.getItem(STORAGE.activeConversation),
      gatewayKey: "",
      models: [],
      defaultModel: "",
      isSending: false,
    };
    this.ensureActiveConversation();
  }

  get activeConversation() {
    return this.state.conversations.find((item) => item.id === this.state.activeId) || null;
  }

  get savedGatewayKey() {
    return this.session.getItem(STORAGE.sessionKey)
      || this.local.getItem(STORAGE.rememberedKey)
      || "";
  }

  get rememberedGatewayKey() {
    return Boolean(this.local.getItem(STORAGE.rememberedKey));
  }

  setGatewayKey(key, remember) {
    this.clearGatewayKey();
    this.state.gatewayKey = key;
    if (remember) {
      this.local.setItem(STORAGE.rememberedKey, key);
    } else {
      this.session.setItem(STORAGE.sessionKey, key);
    }
  }

  clearGatewayKey() {
    this.state.gatewayKey = "";
    this.session.removeItem(STORAGE.sessionKey);
    this.local.removeItem(STORAGE.rememberedKey);
  }

  setModels(models, defaultModel) {
    this.state.models = [...models];
    this.state.defaultModel = defaultModel;
    for (const conversation of this.state.conversations) {
      if (!models.includes(conversation.model)) {
        conversation.model = defaultModel || models[0] || "";
      }
    }
    this.persist();
  }

  ensureActiveConversation() {
    if (!this.state.conversations.length) {
      const conversation = this.#buildConversation();
      this.state.conversations.push(conversation);
      this.state.activeId = conversation.id;
    }

    if (!this.state.conversations.some((item) => item.id === this.state.activeId)) {
      this.state.activeId = [...this.state.conversations]
        .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))[0].id;
    }

    this.local.setItem(STORAGE.activeConversation, this.state.activeId);
  }

  createConversation() {
    const conversation = this.#buildConversation();
    this.state.conversations.push(conversation);
    this.state.activeId = conversation.id;
    this.persist();
    return conversation;
  }

  selectConversation(id) {
    if (!this.state.conversations.some((item) => item.id === id)) return false;
    this.state.activeId = id;
    this.local.setItem(STORAGE.activeConversation, id);
    return true;
  }

  deleteActiveConversation() {
    const active = this.activeConversation;
    if (!active) return null;

    this.state.conversations = this.state.conversations.filter((item) => item.id !== active.id);
    if (!this.state.conversations.length) {
      this.state.conversations.push(this.#buildConversation());
    }
    this.state.activeId = [...this.state.conversations]
      .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))[0].id;
    this.persist();
    return active;
  }

  setActiveModel(model) {
    const conversation = this.activeConversation;
    if (!conversation) return;
    conversation.model = model;
    conversation.updatedAt = new Date().toISOString();
    this.persist();
  }

  addUserMessage(content) {
    const conversation = this.activeConversation;
    if (!conversation) return null;
    const now = new Date().toISOString();
    const message = { role: "user", content, createdAt: now };
    conversation.messages.push(message);
    conversation.updatedAt = now;
    if (conversation.title === DEFAULT_CONVERSATION_TITLE) {
      conversation.title = makeConversationTitle(content);
    }
    this.persist();
    return message;
  }

  addAssistantMessage(content = "") {
    const conversation = this.activeConversation;
    if (!conversation) return null;
    const message = {
      role: "assistant",
      content,
      createdAt: new Date().toISOString(),
    };
    conversation.messages.push(message);
    conversation.updatedAt = message.createdAt;
    this.persist();
    return message;
  }

  removeMessage(message) {
    const conversation = this.activeConversation;
    if (!conversation) return;
    conversation.messages = conversation.messages.filter((item) => item !== message);
    conversation.updatedAt = new Date().toISOString();
    this.persist();
  }

  touch() {
    const conversation = this.activeConversation;
    if (conversation) conversation.updatedAt = new Date().toISOString();
  }

  history(limit = 40) {
    return (this.activeConversation?.messages || [])
      .slice(-limit)
      .map(({ role, content }) => ({ role, content }));
  }

  exportActiveConversation() {
    const conversation = this.activeConversation;
    if (!conversation) return null;
    return {
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
  }

  persist() {
    try {
      this.local.setItem(STORAGE.conversations, JSON.stringify(this.state.conversations));
      this.local.setItem(STORAGE.activeConversation, this.state.activeId);
      return true;
    } catch {
      return false;
    }
  }

  #buildConversation() {
    const now = new Date().toISOString();
    return {
      id: makeId(),
      title: DEFAULT_CONVERSATION_TITLE,
      model: this.state.defaultModel || this.state.models[0] || "",
      messages: [],
      createdAt: now,
      updatedAt: now,
    };
  }

  #loadConversations() {
    try {
      const parsed = JSON.parse(this.local.getItem(STORAGE.conversations) || "[]");
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter((item) => item && typeof item.id === "string")
        .map((item) => ({
          id: item.id,
          title: typeof item.title === "string" ? item.title : DEFAULT_CONVERSATION_TITLE,
          model: typeof item.model === "string" ? item.model : "",
          messages: Array.isArray(item.messages)
            ? item.messages.filter((message) => (
              message
              && ["user", "assistant"].includes(message.role)
              && typeof message.content === "string"
            )).slice(-200)
            : [],
          createdAt: item.createdAt || new Date().toISOString(),
          updatedAt: item.updatedAt || new Date().toISOString(),
        }));
    } catch {
      return [];
    }
  }
}
