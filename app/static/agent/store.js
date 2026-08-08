const STORAGE_KEY = "kimi_agent_workspace_v2";
const LEGACY_STORAGE_KEY = "kimi_agent_workspace_v1";
const MODE_KEY = "kimi_workspace_mode_v1";

export class AgentStore {
  constructor() {
    this.state = this.#load();
  }

  get mode() {
    return localStorage.getItem(MODE_KEY) || "chat";
  }

  setMode(mode) {
    localStorage.setItem(MODE_KEY, mode === "agent" ? "agent" : "chat");
  }

  resetTask() {
    this.state = this.#emptyState();
    this.save();
  }

  save() {
    this.state.updatedAt = new Date().toISOString();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(this.state));
  }

  addMessage(role, content) {
    this.state.messages.push({
      role,
      content,
      createdAt: new Date().toISOString(),
    });
    this.state.messages = this.state.messages.slice(-40);
    this.save();
  }

  addActivity(message, stage = "progress") {
    this.state.activities.push({
      id: crypto.randomUUID(),
      message,
      stage,
      createdAt: new Date().toISOString(),
    });
    this.state.activities = this.state.activities.slice(-80);
    this.save();
  }

  history() {
    return this.state.messages
      .slice(-20)
      .map(({ role, content }) => ({ role, content }));
  }

  #load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
        || localStorage.getItem(LEGACY_STORAGE_KEY)
        || "null";
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return {
          workspace: parsed.workspace || null,
          runId: parsed.runId || null,
          messages: Array.isArray(parsed.messages) ? parsed.messages : [],
          plan: parsed.plan || null,
          knowledge: Array.isArray(parsed.knowledge) ? parsed.knowledge : [],
          searchCandidates: Array.isArray(parsed.searchCandidates) ? parsed.searchCandidates : [],
          security: parsed.security || null,
          review: parsed.review || null,
          validation: parsed.validation || null,
          activities: Array.isArray(parsed.activities) ? parsed.activities : [],
          result: typeof parsed.result === "string" ? parsed.result : "",
          proposal: parsed.proposal || null,
          isRunning: false,
          error: "",
          updatedAt: parsed.updatedAt || new Date().toISOString(),
        };
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
    return this.#emptyState();
  }

  #emptyState() {
    return {
      workspace: null,
      runId: null,
      messages: [],
      plan: null,
      knowledge: [],
      searchCandidates: [],
      security: null,
      review: null,
      validation: null,
      activities: [],
      result: "",
      proposal: null,
      isRunning: false,
      error: "",
      updatedAt: new Date().toISOString(),
    };
  }
}
