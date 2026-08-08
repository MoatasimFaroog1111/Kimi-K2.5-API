import { AgentApi } from "./api.js";
import { AgentWorkspaceComponent } from "./component.js";
import { AgentStore } from "./store.js";

class AgentModeController {
  constructor() {
    this.api = new AgentApi();
    this.store = new AgentStore();
    this.messages = document.getElementById("messages");
    this.composer = document.getElementById("composer");
    this.input = document.getElementById("messageInput");
    this.sendButton = document.getElementById("sendButton");
    this.title = document.getElementById("conversationTitle");
    this.root = document.createElement("section");
    this.root.id = "agentWorkspace";
    this.root.className = "agent-workspace";
    this.root.hidden = true;
    document.querySelector(".composer-wrap").before(this.root);

    this.component = new AgentWorkspaceComponent(this.root, {
      clear: () => this.clear(),
      approve: () => this.approve(),
      reject: () => this.reject(),
      undo: () => this.undo(),
      refreshCi: () => this.refreshCi(),
    });

    this.#wireModeSwitch();
    this.#bindInterceptors();
    this.setMode(this.store.mode, false);
    this.component.render(this.store.state);
  }

  async setMode(mode, notify = true) {
    const normalized = mode === "agent" ? "agent" : "chat";
    this.store.setMode(normalized);
    document.documentElement.dataset.workspaceMode = normalized;
    const isAgent = normalized === "agent";
    this.root.hidden = !isAgent;
    this.messages.hidden = isAgent;

    this.switch.querySelectorAll("button[data-mode]").forEach((button) => {
      const active = button.dataset.mode === normalized;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });

    this.input.placeholder = isAgent
      ? "صف المهمة التي تريد من الوكيل تنفيذها على المشروع…"
      : "اسأل Kimi أي شيء…";

    if (isAgent) {
      this.title.textContent = "Agent Intelligence V3";
      await this.refreshStatus();
      this.input.focus();
    } else {
      this.title.textContent = window.kimiChat?.store.activeConversation?.title || "محادثة جديدة";
    }

    window.dispatchEvent(new CustomEvent("kimi:mode-change", {
      detail: { mode: normalized },
    }));

    if (notify) {
      this.#toast(isAgent ? "تم تفعيل Agent Intelligence V3." : "تم تفعيل وضع المحادثة.");
    }
  }

  async refreshStatus() {
    try {
      this.store.state.workspace = await this.api.status();
      this.store.state.error = "";
    } catch (error) {
      this.store.state.error = this.#humanize(error);
    }
    this.store.save();
    this.component.render(this.store.state);
  }

  async run() {
    const task = this.input.value.trim();
    if (!task || this.store.state.isRunning) return;

    const model = document.getElementById("modelSelect")?.value;
    Object.assign(this.store.state, {
      isRunning: true,
      error: "",
      result: "",
      runId: null,
      plan: null,
      knowledge: [],
      searchCandidates: [],
      semanticHits: [],
      security: null,
      review: null,
      validation: null,
      sandboxValidation: null,
      ciFeedback: null,
      proposal: null,
    });
    this.store.addMessage("user", task);
    this.store.addActivity("تم استلام المهمة وبدء Agent Intelligence V3.", "start");
    this.input.value = "";
    this.sendButton.disabled = true;
    this.component.render(this.store.state);

    try {
      await this.api.streamTask(
        {
          message: task,
          model,
          history: this.store.history().slice(0, -1),
        },
        (event) => this.#handleEvent(event),
      );
      if (this.store.state.result.trim()) {
        this.store.addMessage("assistant", this.store.state.result.trim());
      }
    } catch (error) {
      this.store.state.error = this.#humanize(error);
      this.store.addActivity(this.store.state.error, "error");
    } finally {
      this.store.state.isRunning = false;
      this.sendButton.disabled = false;
      this.store.save();
      this.component.render(this.store.state);
      this.input.focus();
    }
  }

  clear() {
    if (this.store.state.isRunning) return;
    this.store.resetTask();
    this.component.render(this.store.state);
    this.refreshStatus();
  }

  async approve() {
    const proposal = this.store.state.proposal;
    if (!proposal?.id || !proposal.can_approve) return;
    const payload = await this.#proposalAction(
      "جارٍ إنشاء فرع وPull Request…",
      () => this.api.approve(proposal.id),
    );
    if (payload?.proposal?.status === "applied") {
      this.#pollCi(payload.proposal.id);
    }
  }

  async reject() {
    const proposal = this.store.state.proposal;
    if (!proposal?.id || !proposal.can_approve) return;
    await this.#proposalAction(
      "جارٍ رفض المقترح…",
      () => this.api.reject(proposal.id),
    );
  }

  async undo() {
    const proposal = this.store.state.proposal;
    if (!proposal?.id || proposal.status !== "applied") return;
    await this.#proposalAction(
      "جارٍ إغلاق Pull Request وحذف الفرع…",
      () => this.api.undo(proposal.id),
    );
  }

  async refreshCi() {
    const proposal = this.store.state.proposal;
    if (!proposal?.id || proposal.status !== "applied") return;
    try {
      const payload = await this.api.ci(proposal.id);
      this.store.state.ciFeedback = payload.ci || null;
      this.store.state.proposal.ci_feedback = payload.ci || null;
      this.store.addActivity(
        `CI: ${payload.ci?.status || "unknown"}${payload.ci?.conclusion ? ` / ${payload.ci.conclusion}` : ""}`,
        "ci",
      );
      this.store.save();
      this.component.render(this.store.state);
    } catch (error) {
      this.store.addActivity(this.#humanize(error), "error");
      this.store.save();
      this.component.render(this.store.state);
    }
  }

  #handleEvent(event) {
    if (event.type === "status") {
      if (event.workspace) this.store.state.workspace = event.workspace;
      this.store.addActivity(event.message || event.stage, event.stage);
    } else if (event.type === "run") {
      this.store.state.runId = event.run_id || null;
      this.store.addActivity(event.message || "بدأت دورة V3.", event.stage || "run");
    } else if (event.type === "knowledge") {
      this.store.state.knowledge = event.items || [];
      this.store.addActivity(event.message || "تم فحص ذاكرة المشروع.", "memory");
    } else if (event.type === "search") {
      this.store.state.searchCandidates = event.candidates || [];
      this.store.addActivity(event.message || "تم البحث داخل بنية المشروع.", "search");
    } else if (event.type === "semantic") {
      this.store.state.semanticHits = event.hits || [];
      this.store.addActivity(event.message || "اكتمل التحليل الدلالي للكود.", "semantic");
    } else if (event.type === "plan") {
      this.store.state.plan = {
        summary: event.summary,
        steps: event.steps || [],
        files: event.files || [],
      };
      this.store.addActivity("اكتملت خطة Planner.", "plan");
    } else if (event.type === "security") {
      this.store.state.security = {
        level: event.level,
        blocked: Boolean(event.blocked),
        reasons: event.reasons || [],
      };
      this.store.addActivity(`اكتمل فحص الأمان: ${event.level}.`, "security");
    } else if (event.type === "review") {
      this.store.state.review = {
        approved: Boolean(event.approved),
        score: Number(event.score || 0),
        findings: event.findings || [],
        requiredChanges: event.required_changes || [],
      };
      this.store.addActivity(
        `اكتملت مراجعة Reviewer بنتيجة ${event.score || 0}/100.`,
        "review",
      );
    } else if (event.type === "validation") {
      this.store.state.validation = {
        checks: event.checks || [],
        workflowProfiles: event.workflow_profiles || [],
        browserRequired: Boolean(event.browser_required),
        availableWorkflows: event.available_workflows || [],
        runner: event.runner || "",
      };
      this.store.addActivity("أكمل Tester خطة التحقق والاختبارات.", "testing");
    } else if (event.type === "sandbox_validation") {
      this.store.state.sandboxValidation = event;
      this.store.addActivity(
        event.passed
          ? `نجح Sandbox في المحاولة ${event.attempt}.`
          : `فشل Sandbox في المحاولة ${event.attempt} وسيحاول الوكيل الإصلاح إن أمكن.`,
        event.passed ? "sandbox" : "auto-repair",
      );
    } else if (event.type === "delta") {
      this.store.state.result += event.content || "";
    } else if (event.type === "approval_required") {
      this.store.state.proposal = event.proposal;
      this.store.state.sandboxValidation = event.proposal?.sandbox_validation || this.store.state.sandboxValidation;
      this.store.addActivity("التغييرات اجتازت المراجعة والـSandbox وتنتظر موافقتك.", "approval");
    } else if (event.type === "done") {
      this.store.addActivity("اكتملت دورة الوكيل.", "done");
    }
    this.store.save();
    this.component.render(this.store.state);
  }

  async #proposalAction(activity, action) {
    this.store.state.isRunning = true;
    this.store.addActivity(activity, "approval");
    this.component.render(this.store.state);
    try {
      const payload = await action();
      this.store.state.proposal = payload.proposal;
      this.store.state.ciFeedback = payload.proposal?.ci_feedback || null;
      this.store.state.error = "";
      this.store.addActivity("تم تحديث حالة المقترح بنجاح.", "done");
      return payload;
    } catch (error) {
      this.store.state.error = this.#humanize(error);
      this.store.addActivity(this.store.state.error, "error");
      return null;
    } finally {
      this.store.state.isRunning = false;
      this.store.save();
      this.component.render(this.store.state);
    }
  }

  async #pollCi(proposalId) {
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, attempt === 0 ? 1500 : 5000));
      if (this.store.state.proposal?.id !== proposalId) return;
      await this.refreshCi();
      if (this.store.state.ciFeedback?.status === "completed") return;
    }
  }

  #wireModeSwitch() {
    this.switch = document.getElementById("workspaceModeSwitch");
    if (!this.switch) {
      this.switch = document.createElement("div");
      this.switch.id = "workspaceModeSwitch";
      this.switch.className = "workspace-mode-switch";
      this.switch.innerHTML = `
        <button type="button" data-mode="chat">محادثة</button>
        <button type="button" data-mode="agent">وكيل</button>
      `;
      document.querySelector(".composer-control-row")?.prepend(this.switch);
    }

    this.switch.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-mode]");
      if (button) this.setMode(button.dataset.mode);
    });
  }

  #bindInterceptors() {
    document.addEventListener("submit", (event) => {
      if (this.store.mode !== "agent" || event.target !== this.composer) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      this.run();
    }, true);

    document.addEventListener("keydown", (event) => {
      if (
        this.store.mode === "agent"
        && event.target === this.input
        && event.key === "Enter"
        && !event.shiftKey
        && !event.isComposing
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
        this.run();
      }
    }, true);
  }

  #humanize(error) {
    if (error?.status === 401) return "مفتاح البوابة غير صحيح أو انتهت صلاحيته.";
    if (error?.status === 503) return error.message || "ميزة الوكيل غير مهيأة بعد.";
    return error?.message || "حدث خطأ غير متوقع داخل الوكيل.";
  }

  #toast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2800);
  }
}

function bootAgent() {
  window.kimiAgent = new AgentModeController();
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", bootAgent, { once: true });
} else {
  bootAgent();
}
