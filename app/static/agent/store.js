const STORAGE_KEY = "kimi_agent_workspace_v4";
const LEGACY_STORAGE_KEYS = [
  "kimi_agent_workspace_v3",
  "kimi_agent_workspace_v2",
  "kimi_agent_workspace_v1",
];
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

  resetTask({ preserveRuns = true } = {}) {
    const recentRuns = preserveRuns ? this.state.recentRuns : [];
    const workspace = this.state.workspace;
    const autoModel = this.state.autoModel;
    this.state = this.#emptyState();
    this.state.recentRuns = recentRuns;
    this.state.workspace = workspace;
    this.state.autoModel = autoModel;
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
    this.state.activities = this.state.activities.slice(-120);
    this.save();
  }

  history() {
    return this.state.messages
      .slice(-20)
      .map(({ role, content }) => ({ role, content }));
  }

  #load() {
    try {
      let raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        for (const key of LEGACY_STORAGE_KEYS) {
          raw = localStorage.getItem(key);
          if (raw) break;
        }
      }
      const parsed = JSON.parse(raw || "null");
      if (parsed && typeof parsed === "object") {
        return {
          workspace: parsed.workspace || null,
          runId: parsed.runId || null,
          runStatus: parsed.runStatus || null,
          autoModel: parsed.autoModel !== false,
          modelRoute: parsed.modelRoute || null,
          contextReport: parsed.contextReport || null,
          budget: parsed.budget || null,
          recentRuns: Array.isArray(parsed.recentRuns) ? parsed.recentRuns : [],
          messages: Array.isArray(parsed.messages) ? parsed.messages : [],
          plan: parsed.plan || null,
          knowledge: Array.isArray(parsed.knowledge) ? parsed.knowledge : [],
          searchCandidates: Array.isArray(parsed.searchCandidates) ? parsed.searchCandidates : [],
          semanticHits: Array.isArray(parsed.semanticHits) ? parsed.semanticHits : [],
          security: parsed.security || null,
          review: parsed.review || null,
          validation: parsed.validation || null,
          sandboxValidation: parsed.sandboxValidation || null,
          ciFeedback: parsed.ciFeedback || null,
          activities: Array.isArray(parsed.activities) ? parsed.activities : [],
          result: typeof parsed.result === "string" ? parsed.result : "",
          proposal: parsed.proposal || null,
          isRunning: false,
          isControlPending: false,
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
      runStatus: null,
      autoModel: true,
      modelRoute: null,
      contextReport: null,
      budget: null,
      recentRuns: [],
      messages: [],
      plan: null,
      knowledge: [],
      searchCandidates: [],
      semanticHits: [],
      security: null,
      review: null,
      validation: null,
      sandboxValidation: null,
      ciFeedback: null,
      activities: [],
      result: "",
      proposal: null,
      isRunning: false,
      isControlPending: false,
      error: "",
      updatedAt: new Date().toISOString(),
    };
  }
}
