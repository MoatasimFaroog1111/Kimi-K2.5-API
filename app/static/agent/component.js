export class AgentWorkspaceComponent {
  constructor(root, actions) {
    this.root = root;
    this.actions = actions;
    this.#build();
  }

  render(state) {
    this.root.classList.toggle("is-running", Boolean(state.isRunning));
    this.statusText.textContent = this.#workspaceLabel(state.workspace);
    this.statusDot.dataset.mode = state.workspace?.mode || "not-configured";
    this.runState.textContent = state.isRunning ? "الوكيل يعمل الآن" : "جاهز لمهمة جديدة";
    this.clearButton.disabled = state.isRunning;

    this.#renderPlan(state.plan);
    this.#renderActivities(state.activities);
    this.#renderResult(state.result, state.error);
    this.#renderProposal(state.proposal);
  }

  #build() {
    this.root.innerHTML = `
      <div class="agent-hero">
        <div>
          <p class="agent-eyebrow">AGENT MODE · APPROVAL FIRST</p>
          <h2>وكيل برمجي يخطط، يراجع، ويقترح التغييرات</h2>
          <p>قراءة آمنة للمستودع، خطة واضحة، معاينة فروقات، ثم Pull Request بعد موافقتك فقط.</p>
        </div>
        <button id="agentClear" class="agent-secondary-button" type="button">مهمة جديدة</button>
      </div>
      <div class="agent-status-bar">
        <span class="agent-status-dot" id="agentStatusDot"></span>
        <strong id="agentStatusText">جاري قراءة حالة مساحة العمل…</strong>
        <span id="agentRunState">جاهز لمهمة جديدة</span>
      </div>
      <div class="agent-grid">
        <section class="agent-card">
          <div class="agent-card-title"><span>01</span><h3>خطة التنفيذ</h3></div>
          <div id="agentPlan" class="agent-empty">لم تبدأ مهمة بعد.</div>
        </section>
        <section class="agent-card">
          <div class="agent-card-title"><span>02</span><h3>سجل النشاط</h3></div>
          <div id="agentActivity" class="agent-activity agent-empty">ستظهر خطوات القراءة والتحليل هنا.</div>
        </section>
      </div>
      <section class="agent-card agent-result-card">
        <div class="agent-card-title"><span>03</span><h3>نتيجة الوكيل</h3></div>
        <pre id="agentResult" class="agent-result">اكتب المهمة في مربع الرسالة ثم أرسلها.</pre>
      </section>
      <section id="agentProposalCard" class="agent-card agent-proposal-card" hidden>
        <div class="agent-card-title"><span>04</span><h3>مقترح التغييرات</h3></div>
        <div id="agentProposalSummary"></div>
        <div id="agentChanges" class="agent-changes"></div>
        <div class="agent-approval-actions">
          <button id="agentApprove" class="agent-primary-button" type="button">الموافقة وإنشاء Pull Request</button>
          <button id="agentReject" class="agent-secondary-button danger" type="button">رفض المقترح</button>
          <button id="agentUndo" class="agent-secondary-button" type="button" hidden>إلغاء Pull Request</button>
        </div>
      </section>
    `;

    this.statusDot = this.root.querySelector("#agentStatusDot");
    this.statusText = this.root.querySelector("#agentStatusText");
    this.runState = this.root.querySelector("#agentRunState");
    this.plan = this.root.querySelector("#agentPlan");
    this.activity = this.root.querySelector("#agentActivity");
    this.result = this.root.querySelector("#agentResult");
    this.proposalCard = this.root.querySelector("#agentProposalCard");
    this.proposalSummary = this.root.querySelector("#agentProposalSummary");
    this.changes = this.root.querySelector("#agentChanges");
    this.approveButton = this.root.querySelector("#agentApprove");
    this.rejectButton = this.root.querySelector("#agentReject");
    this.undoButton = this.root.querySelector("#agentUndo");
    this.clearButton = this.root.querySelector("#agentClear");

    this.clearButton.addEventListener("click", this.actions.clear);
    this.approveButton.addEventListener("click", this.actions.approve);
    this.rejectButton.addEventListener("click", this.actions.reject);
    this.undoButton.addEventListener("click", this.actions.undo);
  }

  #renderPlan(plan) {
    this.plan.replaceChildren();
    if (!plan) {
      this.plan.className = "agent-empty";
      this.plan.textContent = "لم تبدأ مهمة بعد.";
      return;
    }
    this.plan.className = "agent-plan";
    const summary = document.createElement("p");
    summary.className = "agent-plan-summary";
    summary.textContent = plan.summary || "خطة التنفيذ";
    const list = document.createElement("ol");
    for (const step of plan.steps || []) {
      const item = document.createElement("li");
      item.textContent = step;
      list.appendChild(item);
    }
    this.plan.append(summary, list);
  }

  #renderActivities(activities) {
    this.activity.replaceChildren();
    if (!activities?.length) {
      this.activity.className = "agent-activity agent-empty";
      this.activity.textContent = "ستظهر خطوات القراءة والتحليل هنا.";
      return;
    }
    this.activity.className = "agent-activity";
    for (const activity of activities.slice().reverse()) {
      const row = document.createElement("div");
      row.className = "agent-activity-row";
      const dot = document.createElement("span");
      dot.className = "agent-activity-dot";
      const text = document.createElement("span");
      text.textContent = activity.message;
      row.append(dot, text);
      this.activity.appendChild(row);
    }
  }

  #renderResult(result, error) {
    this.result.classList.toggle("has-error", Boolean(error));
    this.result.textContent = error || result || "اكتب المهمة في مربع الرسالة ثم أرسلها.";
  }

  #renderProposal(proposal) {
    this.proposalCard.hidden = !proposal;
    if (!proposal) return;

    this.proposalSummary.replaceChildren();
    const summary = document.createElement("p");
    summary.textContent = proposal.summary || "مقترح تغييرات";
    const meta = document.createElement("p");
    meta.className = "agent-proposal-meta";
    meta.textContent = `${proposal.repository || "المستودع"} · ${proposal.base_branch || "main"} · ${proposal.status}`;
    this.proposalSummary.append(summary, meta);

    this.changes.replaceChildren();
    for (const change of proposal.changes || []) {
      const details = document.createElement("details");
      details.className = "agent-change";
      const title = document.createElement("summary");
      title.textContent = `${change.path} — ${change.reason}`;
      const diff = document.createElement("pre");
      diff.textContent = change.diff || "ملف جديد أو لا توجد معاينة فرق.";
      details.append(title, diff);
      this.changes.appendChild(details);
    }

    const applied = proposal.status === "applied";
    this.approveButton.hidden = !proposal.can_approve;
    this.rejectButton.hidden = !proposal.can_approve;
    this.undoButton.hidden = !applied;
    this.approveButton.disabled = !proposal.can_approve;

    if (proposal.pull_request_url) {
      const link = document.createElement("a");
      link.className = "agent-pr-link";
      link.href = proposal.pull_request_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "فتح Pull Request في GitHub";
      this.proposalSummary.appendChild(link);
    }
  }

  #workspaceLabel(workspace) {
    if (!workspace?.configured) {
      return "وضع التخطيط فقط · اربط مستودع GitHub لتفعيل قراءة الملفات";
    }
    const access = workspace.write_enabled ? "Pull Request بعد الموافقة" : "قراءة فقط";
    return `${workspace.repository} · ${workspace.branch} · ${access}`;
  }
}
