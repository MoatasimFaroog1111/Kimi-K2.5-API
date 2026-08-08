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
      pause: () => this.pause(),
      resume: () => this.resume(),
      cancel: () => this.cancel(),
      autoModel: (value) => this.setAutoModel(value),
      approve: () => this.approve(),
      reject: () => this.reject(),
      undo: () => this.undo(),
      refreshCi: () => this.refreshCi(),
      repairCi: () => this.repairCi(),
      openRun: (runId) => this.openRun(runId),
      toggleFile: (path, checked) => this.toggleFile(path, checked),
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
      this.title.textContent = "Agent Runtime V4";
      await Promise.all([this.refreshStatus(), this.refreshRuns()]);
      this.input.focus();
    } else {
      this.title.textContent = window.kimiChat?.store.activeConversation?.title || "محادثة جديدة";
    }

    window.dispatchEvent(new CustomEvent("kimi:mode-change", {
      detail: { mode: normalized },
    }));

    if (notify) {
      this.#toast(isAgent ? "تم تفعيل Agent Runtime V4." : "تم تفعيل وضع المحادثة.");
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

  async refreshRuns() {
    try {
      const payload = await this.api.runs(30);
      this.store.state.recentRuns = payload.runs || [];
    } catch (error) {
      this.store.addActivity(this.#humanize(error), "error");
    }
    this.store.save();
    this.component.render(this.store.state);
  }

  async run() {
    const task = this.input.value.trim();
    if (!task || this.store.state.isRunning) return;

    const model = document.getElementById("modelSelect")?.value || null;
    this.#resetExecutionView();
    Object.assign(this.store.state, {
      isRunning: true,
      runStatus: "running",
    });
    this.store.addMessage("user", task);
    this.store.addActivity("تم استلام المهمة وإنشاء Agent Runtime V4 جديد.", "start");
    this.input.value = "";
    this.sendButton.disabled = true;
    this.component.render(this.store.state);

    try {
      await this.api.streamTask(
        {
          message: task,
          model,
          auto_model: this.store.state.autoModel !== false,
          history: this.store.history().slice(0, -1),
        },
        (event) => this.#handleEvent(event),
      );
      if (this.store.state.result.trim()) {
        this.store.addMessage("assistant", this.store.state.result.trim());
      }
    } catch (error) {
      this.store.state.error = this.#humanize(error);
      this.store.state.runStatus = "failed";
      this.store.addActivity(this.store.state.error, "error");
    } finally {
      this.store.state.isRunning = false;
      this.store.state.isControlPending = false;
      this.sendButton.disabled = false;
      this.store.save();
      await this.refreshRuns();
      this.component.render(this.store.state);
      this.input.focus();
    }
  }

  clear() {
    if (this.store.state.isRunning) return;
    this.store.resetTask();
    this.component.render(this.store.state);
    Promise.all([this.refreshStatus(), this.refreshRuns()]);
  }

  setAutoModel(value) {
    this.store.state.autoModel = Boolean(value);
    this.store.save();
    this.component.render(this.store.state);
  }

  async pause() {
    const runId = this.store.state.runId;
    if (!runId || !this.store.state.isRunning || this.store.state.isControlPending) return;
    this.store.state.isControlPending = true;
    this.store.addActivity("طُلب الإيقاف المؤقت؛ سيتم عند أقرب Checkpoint آمن.", "pause");
    this.store.save();
    this.component.render(this.store.state);
    try {
      const payload = await this.api.pause(runId);
      this.store.state.runStatus = payload.run?.status || "pause-requested";
    } catch (error) {
      this.store.state.isControlPending = false;
      this.store.addActivity(this.#humanize(error), "error");
    }
    this.store.save();
    this.component.render(this.store.state);
  }

  async resume() {
    const runId = this.store.state.runId;
    if (!runId || this.store.state.runStatus !== "paused" || this.store.state.isRunning) return;
    this.store.state.isRunning = true;
    this.store.state.isControlPending = false;
    this.store.state.runStatus = "running";
    this.store.state.error = "";
    this.sendButton.disabled = true;
    this.store.addActivity("جارٍ استئناف المهمة من آخر Checkpoint محفوظ.", "resume");
    this.store.save();
    this.component.render(this.store.state);
    try {
      await this.api.resume(runId, (event) => this.#handleEvent(event));
      if (this.store.state.result.trim()) {
        this.store.addMessage("assistant", this.store.state.result.trim());
      }
    } catch (error) {
      this.store.state.error = this.#humanize(error);
      this.store.state.runStatus = "failed";
      this.store.addActivity(this.store.state.error, "error");
    } finally {
      this.store.state.isRunning = false;
      this.sendButton.disabled = false;
      this.store.save();
      await this.refreshRuns();
      this.component.render(this.store.state);
    }
  }

  async cancel() {
    const runId = this.store.state.runId;
    if (!runId || this.store.state.isControlPending) return;
    this.store.state.isControlPending = true;
    this.store.addActivity("طُلب إلغاء المهمة.", "cancel");
    this.store.save();
    this.component.render(this.store.state);
    try {
      const payload = await this.api.cancel(runId);
      this.store.state.runStatus = payload.run?.status || "cancel-requested";
      if (this.store.state.runStatus === "cancelled") {
        this.store.state.isRunning = false;
        this.store.state.isControlPending = false;
      }
    } catch (error) {
      this.store.state.isControlPending = false;
      this.store.addActivity(this.#humanize(error), "error");
    }
    this.store.save();
    await this.refreshRuns();
    this.component.render(this.store.state);
  }

  async openRun(runId) {
    if (!runId || this.store.state.isRunning) return;
    try {
      const payload = await this.api.run(runId);
      const run = payload.run || {};
      this.store.resetTask();
      Object.assign(this.store.state, {
        runId: run.id || runId,
        runStatus: run.status || null,
        modelRoute: run.route || null,
        contextReport: run.context_report || null,
        budget: run.budget || null,
        proposal: run.proposal || null,
        ciFeedback: run.proposal?.ci_feedback || null,
        error: run.error || "",
      });
      this.store.addActivity(`تم فتح المهمة المحفوظة من المرحلة ${run.stage || "unknown"}.`, "checkpoint");
      this.store.save();
      this.component.render(this.store.state);
      await this.refreshRuns();
    } catch (error) {
      this.store.addActivity(this.#humanize(error), "error");
      this.store.save();
      this.component.render(this.store.state);
    }
  }

  toggleFile(path, checked) {
    const proposal = this.store.state.proposal;
    if (!proposal?.id || proposal.status !== "pending") return;
    const approved = new Set(proposal.approved_paths || []);
    if (checked) approved.add(path);
    else approved.delete(path);
    proposal.approved_paths = [...approved];
    for (const change of proposal.changes || []) {
      change.approved = approved.has(change.path);
    }
    proposal.can_approve = approved.size > 0;
    this.store.save();
    this.component.render(this.store.state);
  }

  async approve() {
    const proposal = this.store.state.proposal;
    if (!proposal?.id || proposal.status !== "pending") return;
    const paths = proposal.approved_paths || [];
    if (!paths.length) {
      this.#toast("حدد ملفًا واحدًا على الأقل.");
      return;
    }
    const payload = await this.#proposalAction(
      "جارٍ تثبيت موافقات الملفات ثم إنشاء Pull Request…",
      async () => {
        const approval = await this.api.setFileApprovals(proposal.id, paths);
        this.store.state.proposal = approval.proposal;
        return this.api.approve(proposal.id);
      },
    );
    if (payload?.proposal?.status === "applied") {
      this.store.state.runStatus = "completed";
      this.#pollCi(payload.proposal.id);
    }
    await this.refreshRuns();
  }

  async reject() {
    const proposal = this.store.state.proposal;
    if (!proposal?.id || proposal.status !== "pending") return;
    await this.#proposalAction(
      "جارٍ رفض المقترح…",
      () => this.api.reject(proposal.id),
    );
    this.store.state.runStatus = "completed";
    await this.refreshRuns();
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

  async repairCi() {
    const parent = this.store.state.proposal;
    if (!parent?.id || parent.status !== "applied") return;
    const model = document.getElementById("modelSelect")?.value || null;
    this.#resetExecutionView({ preserveProposal: false });
    this.store.state.isRunning = true;
    this.store.state.runStatus = "running";
    this.sendButton.disabled = true;
    this.store.addActivity("بدأ Agent Runtime V4 مهمة إصلاح CI منفصلة؛ لن يعدّل PR الأصلي مباشرة.", "ci-repair");
    this.store.save();
    this.component.render(this.store.state);
    try {
      await this.api.repairCi(
        parent.id,
        { model, auto_model: this.store.state.autoModel !== false },
        (event) => this.#handleEvent(event),
      );
    } catch (error) {
      this.store.state.error = this.#humanize(error);
      this.store.state.runStatus = "failed";
      this.store.addActivity(this.store.state.error, "error");
    } finally {
      this.store.state.isRunning = false;
      this.sendButton.disabled = false;
      this.store.save();
      await this.refreshRuns();
      this.component.render(this.store.state);
    }
  }

  #handleEvent(event) {
    if (event.type === "status") {
      if (event.workspace) this.store.state.workspace = event.workspace;
      this.store.addActivity(event.message || event.stage, event.stage);
    } else if (event.type === "run") {
      this.store.state.runId = event.run_id || this.store.state.runId;
      this.store.state.runStatus = "running";
      this.store.addActivity(event.message || "بدأ Agent Runtime V4.", event.stage || "run");
    } else if (event.type === "model_route") {
      this.store.state.modelRoute = event.route || null;
      if (event.route?.selected_model) {
        this.store.addActivity(`Model Router → ${event.route.selected_model} (${event.route.tier}).`, "routing");
      }
    } else if (event.type === "budget") {
      this.store.state.budget = event.budget || null;
    } else if (event.type === "context") {
      this.store.state.contextReport = event.report || null;
      this.store.addActivity(event.message || "اكتمل Context Manager.", "context");
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
      this.store.addActivity("اكتملت خطة Planner وتم حفظ Checkpoint.", "plan");
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
      this.store.addActivity(`Reviewer: ${event.score || 0}/100.`, "review");
    } else if (event.type === "validation") {
      this.store.state.validation = {
        checks: event.checks || [],
        workflowProfiles: event.workflow_profiles || [],
        browserRequired: Boolean(event.browser_required),
        availableWorkflows: event.available_workflows || [],
        runner: event.runner || "",
      };
      this.store.addActivity("أكمل Tester خطة التحقق.", "testing");
    } else if (event.type === "sandbox_validation") {
      this.store.state.sandboxValidation = event;
      this.store.addActivity(
        event.passed
          ? `نجح Sandbox في المحاولة ${event.attempt}.`
          : `فشل Sandbox في المحاولة ${event.attempt} وسيحاول الوكيل الإصلاح إن أمكن.`,
        event.passed ? "sandbox" : "auto-repair",
      );
    } else if (event.type === "run_control") {
      this.store.state.runStatus = event.state;
      this.store.state.isControlPending = false;
      this.store.state.isRunning = false;
      this.store.addActivity(event.message || `Run ${event.state}.`, event.state);
    } else if (event.type === "delta") {
      this.store.state.result += event.content || "";
    } else if (event.type === "approval_required") {
      this.store.state.proposal = event.proposal;
      this.store.state.sandboxValidation = event.proposal?.sandbox_validation || this.store.state.sandboxValidation;
      this.store.state.runStatus = "waiting-approval";
      this.store.addActivity("التغييرات اجتازت البوابات. اختر الملفات التي تريد اعتمادها.", "approval");
    } else if (event.type === "done") {
      if (!event.waiting_approval && this.store.state.runStatus !== "paused" && this.store.state.runStatus !== "cancelled") {
        this.store.state.runStatus = "completed";
      }
      this.store.addActivity("اكتملت دورة التنفيذ الحالية.", "done");
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

  #resetExecutionView({ preserveProposal = false } = {}) {
    Object.assign(this.store.state, {
      error: "",
      result: "",
      runId: null,
      runStatus: null,
      modelRoute: null,
      contextReport: null,
      budget: null,
      plan: null,
      knowledge: [],
      searchCandidates: [],
      semanticHits: [],
      security: null,
      review: null,
      validation: null,
      sandboxValidation: null,
      ciFeedback: null,
      proposal: preserveProposal ? this.store.state.proposal : null,
      isControlPending: false,
    });
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
