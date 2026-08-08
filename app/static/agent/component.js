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
    this.runId.textContent = state.runId ? `Run ${state.runId}` : "Agent Core V2";
    this.clearButton.disabled = state.isRunning;

    this.#renderKnowledge(state.knowledge);
    this.#renderPlan(state.plan);
    this.#renderSecurityReview(state.security, state.review);
    this.#renderValidation(state.validation);
    this.#renderActivities(state.activities);
    this.#renderResult(state.result, state.error);
    this.#renderProposal(state.proposal);
  }

  #build() {
    this.root.innerHTML = `
      <div class="agent-hero">
        <div>
          <p class="agent-eyebrow">MULTI-AGENT · MEMORY · APPROVAL FIRST</p>
          <h2>Agent Core V2</h2>
          <p>Memory → Search → Planner → Coder → Security → Reviewer → Tester → موافقتك → Pull Request.</p>
        </div>
        <button id="agentClear" class="agent-secondary-button" type="button">مهمة جديدة</button>
      </div>

      <div class="agent-status-bar">
        <span class="agent-status-dot" id="agentStatusDot"></span>
        <strong id="agentStatusText">جاري قراءة حالة مساحة العمل…</strong>
        <span id="agentRunId">Agent Core V2</span>
        <span id="agentRunState">جاهز لمهمة جديدة</span>
      </div>

      <div class="agent-pipeline" aria-label="مراحل الوكيل">
        <span>Memory</span><span>Search</span><span>Planner</span><span>Coder</span>
        <span>Security</span><span>Reviewer</span><span>Tester</span><span>Approval</span>
      </div>

      <div class="agent-grid agent-grid-v2">
        <section class="agent-card">
          <div class="agent-card-title"><span>01</span><h3>ذاكرة المشروع</h3></div>
          <div id="agentKnowledge" class="agent-empty">لم يتم استرجاع معرفة بعد.</div>
        </section>

        <section class="agent-card">
          <div class="agent-card-title"><span>02</span><h3>خطة Planner</h3></div>
          <div id="agentPlan" class="agent-empty">لم تبدأ مهمة بعد.</div>
        </section>

        <section class="agent-card">
          <div class="agent-card-title"><span>03</span><h3>Security + Reviewer</h3></div>
          <div id="agentReview" class="agent-empty">تظهر نتيجة المخاطر والمراجعة المستقلة هنا.</div>
        </section>

        <section class="agent-card">
          <div class="agent-card-title"><span>04</span><h3>خطة Tester</h3></div>
          <div id="agentValidation" class="agent-empty">تظهر الاختبارات وBrowser verification هنا.</div>
        </section>
      </div>

      <section class="agent-card agent-activity-card">
        <div class="agent-card-title"><span>05</span><h3>سجل النشاط</h3></div>
        <div id="agentActivity" class="agent-activity agent-empty">ستظهر مراحل التنفيذ هنا.</div>
      </section>

      <section class="agent-card agent-result-card">
        <div class="agent-card-title"><span>06</span><h3>نتيجة الوكيل</h3></div>
        <pre id="agentResult" class="agent-result">اكتب المهمة في مربع الرسالة ثم أرسلها.</pre>
      </section>

      <section id="agentProposalCard" class="agent-card agent-proposal-card" hidden>
        <div class="agent-card-title"><span>07</span><h3>مقترح التغييرات</h3></div>
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
    this.runId = this.root.querySelector("#agentRunId");
    this.runState = this.root.querySelector("#agentRunState");
    this.knowledge = this.root.querySelector("#agentKnowledge");
    this.plan = this.root.querySelector("#agentPlan");
    this.review = this.root.querySelector("#agentReview");
    this.validation = this.root.querySelector("#agentValidation");
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

  #renderKnowledge(items) {
    this.knowledge.replaceChildren();
    if (!items?.length) {
      this.knowledge.className = "agent-empty";
      this.knowledge.textContent = "لا توجد معرفة سابقة مرتبطة بالمهمة حتى الآن.";
      return;
    }
    this.knowledge.className = "agent-knowledge-list";
    for (const item of items.slice(0, 5)) {
      const article = document.createElement("article");
      article.className = "agent-memory-item";
      const title = document.createElement("strong");
      title.textContent = item.title || item.id;
      const summary = document.createElement("p");
      summary.textContent = item.summary || "";
      article.append(title, summary);
      this.knowledge.appendChild(article);
    }
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

  #renderSecurityReview(security, review) {
    this.review.replaceChildren();
    if (!security && !review) {
      this.review.className = "agent-empty";
      this.review.textContent = "تظهر نتيجة المخاطر والمراجعة المستقلة هنا.";
      return;
    }
    this.review.className = "agent-review-panel";

    if (security) {
      const risk = document.createElement("div");
      risk.className = `agent-risk agent-risk-${security.level || "low"}`;
      const heading = document.createElement("strong");
      heading.textContent = `Risk: ${security.level || "unknown"}`;
      risk.appendChild(heading);
      for (const reason of security.reasons || []) {
        const row = document.createElement("p");
        row.textContent = reason;
        risk.appendChild(row);
      }
      this.review.appendChild(risk);
    }

    if (review) {
      const verdict = document.createElement("div");
      verdict.className = `agent-review-verdict ${review.approved ? "approved" : "blocked"}`;
      const heading = document.createElement("strong");
      heading.textContent = `${review.approved ? "Reviewer approved" : "Reviewer blocked"} · ${review.score || 0}/100`;
      verdict.appendChild(heading);
      for (const finding of review.findings || []) {
        const row = document.createElement("p");
        row.textContent = finding;
        verdict.appendChild(row);
      }
      this.review.appendChild(verdict);
    }
  }

  #renderValidation(validation) {
    this.validation.replaceChildren();
    if (!validation) {
      this.validation.className = "agent-empty";
      this.validation.textContent = "تظهر الاختبارات وBrowser verification هنا.";
      return;
    }
    this.validation.className = "agent-validation-panel";
    const profiles = document.createElement("div");
    profiles.className = "agent-profile-list";
    for (const profile of validation.workflowProfiles || []) {
      const chip = document.createElement("span");
      chip.textContent = profile;
      profiles.appendChild(chip);
    }
    this.validation.appendChild(profiles);

    const list = document.createElement("ul");
    for (const check of validation.checks || []) {
      const item = document.createElement("li");
      item.textContent = check;
      list.appendChild(item);
    }
    this.validation.appendChild(list);

    const runner = document.createElement("p");
    runner.className = "agent-runner-note";
    runner.textContent = validation.browserRequired
      ? `Runner: ${validation.runner || "github-actions"} · Chromium browser check required`
      : `Runner: ${validation.runner || "github-actions"}`;
    this.validation.appendChild(runner);
  }

  #renderActivities(activities) {
    this.activity.replaceChildren();
    if (!activities?.length) {
      this.activity.className = "agent-activity agent-empty";
      this.activity.textContent = "ستظهر مراحل التنفيذ هنا.";
      return;
    }
    this.activity.className = "agent-activity";
    for (const activity of activities.slice().reverse()) {
      const row = document.createElement("div");
      row.className = "agent-activity-row";
      const dot = document.createElement("span");
      dot.className = "agent-activity-dot";
      dot.dataset.stage = activity.stage || "progress";
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
    const reviewScore = proposal.review?.score != null ? ` · Review ${proposal.review.score}/100` : "";
    const riskLevel = proposal.risk?.level ? ` · Risk ${proposal.risk.level}` : "";
    meta.textContent = `${proposal.repository || "المستودع"} · ${proposal.base_branch || "main"} · ${proposal.status}${reviewScore}${riskLevel}`;
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
    const version = workspace.agent_core_version ? ` · Core V${workspace.agent_core_version}` : "";
    return `${workspace.repository} · ${workspace.branch} · ${access}${version}`;
  }
}
