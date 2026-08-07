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
    });

    this.#installModeSwitch();
    this.#bindInterceptors();
    this.setMode(this.store.mode, false);
    this.component.render(this.store.state);
  }

  async setMode(mode, notify = true) {
    const normalized = mode === "agent" ? "agent" : "chat";
    this.store.setMode(normalized);
    const isAgent = normalized === "agent";
    this.root.hidden = !isAgent;
    this.messages.hidden = isAgent;
    this.switch.querySelectorAll("button").forEach((button) => {
      button.classList.toggle("active", button.dataset.mode === normalized);
      button.setAttribute("aria-pressed", String(button.dataset.mode === normalized));
    });
    this.input.placeholder = isAgent
      ? "صف المهمة التي تريد من الوكيل تنفيذها على المشروع…"
      : "اكتب طلبك البرمجي هنا…";
    if (isAgent) {
      this.title.textContent = "Agent Mode · تنفيذ بموافقتك";
      await this.refreshStatus();
      this.input.focus();
    } else {
      this.title.textContent = document.querySelector(
        ".conversation-item.active .conversation-name",
      )?.textContent || "محادثة جديدة";
    }
    if (notify) this.#toast(isAgent ? "تم تفعيل وضع الوكيل." : "تم تفعيل وضع المحادثة.");
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
    this.store.state.isRunning = true;
    this.store.state.error = "";
    this.store.state.result = "";
    this.store.state.plan = null;
    this.store.state.proposal = null;
    this.store.addMessage("user", task);
    this.store.addActivity("تم استلام المهمة وبدء دورة الوكيل.", "start");
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
    await this.#proposalAction("جارٍ إنشاء فرع وPull Request…", () => this.api.approve(proposal.id));
  }

  async reject() {
    const proposal = this.store.state.proposal;
    if (!proposal?.id || !proposal.can_approve) return;
    await this.#proposalAction("جارٍ رفض المقترح…", () => this.api.reject(proposal.id));
  }

  async undo() {
    const proposal = this.store.state.proposal;
    if (!proposal?.id || proposal.status !== "applied") return;
    await this.#proposalAction("جارٍ إغلاق Pull Request وحذف الفرع…", () => this.api.undo(proposal.id));
  }

  #handleEvent(event) {
    if (event.type === "status") {
      if (event.workspace) this.store.state.workspace = event.workspace;
      this.store.addActivity(event.message || event.stage, event.stage);
    } else if (event.type === "plan") {
      this.store.state.plan = {
        summary: event.summary,
        steps: event.steps || [],
        files: event.files || [],
      };
      this.store.addActivity("اكتملت خطة التنفيذ.", "plan");
    } else if (event.type === "delta") {
      this.store.state.result += event.content || "";
    } else if (event.type === "approval_required") {
      this.store.state.proposal = event.proposal;
      this.store.addActivity("التغييرات جاهزة وتنتظر موافقتك.", "approval");
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
      this.store.state.error = "";
      this.store.addActivity("تم تحديث حالة المقترح بنجاح.", "done");
    } catch (error) {
      this.store.state.error = this.#humanize(error);
      this.store.addActivity(this.store.state.error, "error");
    } finally {
      this.store.state.isRunning = false;
      this.store.save();
      this.component.render(this.store.state);
    }
  }

  #installModeSwitch() {
    this.switch = document.getElementById("workspaceModeSwitch");

    if (!this.switch) {
      this.switch = document.createElement("div");
      this.switch.id = "workspaceModeSwitch";
      this.switch.className = "workspace-mode-switch";
      this.switch.setAttribute("aria-label", "اختيار وضع مساحة العمل");
      this.switch.innerHTML = `
        <button type="button" data-mode="chat">محادثة</button>
        <button type="button" data-mode="agent">وكيل</button>
      `;
      document.querySelector(".topbar-actions")?.prepend(this.switch);
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

function bootAgentMode() {
  new AgentModeController();
}

if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", bootAgentMode, { once: true });
} else {
  bootAgentMode();
}
