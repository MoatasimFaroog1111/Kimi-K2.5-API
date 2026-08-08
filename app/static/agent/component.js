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
    this.runId.textContent = state.runId ? `Run ${state.runId}` : "Agent Intelligence V3";
    this.clearButton.disabled = state.isRunning;

    this.#renderKnowledge(state.knowledge);
    this.#renderSemantic(state.semanticHits);
    this.#renderPlan(state.plan);
    this.#renderSecurityReview(state.security, state.review);
    this.#renderSandbox(state.validation, state.sandboxValidation);
    this.#renderCi(state.ciFeedback || state.proposal?.ci_feedback, state.proposal);
    this.#renderActivities(state.activities);
    this.#renderResult(state.result, state.error);
    this.#renderProposal(state.proposal);
  }

  #build() {
    this.root.innerHTML = `
      <div class="agent-hero">
        <div>
          <p class="agent-eyebrow">SEMANTIC · SANDBOX · AUTO-REPAIR · CI FEEDBACK</p>
          <h2>Agent Intelligence V3</h2>
          <p>Memory → Search → Semantic → Planner → Coder → Security → Reviewer → Tester → Sandbox → Auto‑Repair → موافقتك → Pull Request → CI.</p>
        </div>
        <button id="agentClear" class="agent-secondary-button" type="button">مهمة جديدة</button>
      </div>

      <div class="agent-status-bar">
        <span class="agent-status-dot" id="agentStatusDot"></span>
        <strong id="agentStatusText">جاري قراءة حالة مساحة العمل…</strong>
        <span id="agentRunId">Agent Intelligence V3</span>
        <span id="agentRunState">جاهز لمهمة جديدة</span>
      </div>

      <div class="agent-pipeline" aria-label="مراحل الوكيل">
        <span>Memory</span><span>Search</span><span>Semantic</span><span>Planner</span>
        <span>Coder</span><span>Security</span><span>Reviewer</span><span>Tester</span>
        <span>Sandbox</span><span>Approval</span><span>CI</span>
      </div>

      <div class="agent-grid agent-grid-v2">
        <section class="agent-card">
          <div class="agent-card-title"><span>01</span><h3>ذاكرة المشروع</h3></div>
          <div id="agentKnowledge" class="agent-empty">لم يتم استرجاع معرفة بعد.</div>
        </section>

        <section class="agent-card">
          <div class="agent-card-title"><span>02</span><h3>Semantic Code Intelligence</h3></div>
          <div id="agentSemantic" class="agent-empty">تظهر الملفات الأعلى صلة بعد تحليل البنية والمحتوى.</div>
        </section>

        <section class="agent-card">
          <div class="agent-card-title"><span>03</span><h3>خطة Planner</h3></div>
          <div id="agentPlan" class="agent-empty">لم تبدأ مهمة بعد.</div>
        </section>

        <section class="agent-card">
          <div class="agent-card-title"><span>04</span><h3>Security + Reviewer</h3></div>
          <div id="agentReview" class="agent-empty">تظهر نتيجة المخاطر والمراجعة المستقلة هنا.</div>
        </section>

        <section class="agent-card">
          <div class="agent-card-title"><span>05</span><h3>Pre‑Approval Sandbox</h3></div>
          <div id="agentSandbox" class="agent-empty">تظهر الاختبارات الفعلية ومحاولات الإصلاح التلقائي هنا.</div>
        </section>

        <section class="agent-card">
          <div class="agent-card-title"><span>06</span><h3>GitHub CI Feedback</h3></div>
          <div id="agentCi" class="agent-empty">يظهر CI بعد إنشاء Pull Request.</div>
          <button id="agentRefreshCi" class="agent-secondary-button agent-ci-refresh" type="button" hidden>تحديث CI</button>
        </section>
      </div>

      <section class="agent-card agent-activity-card">
        <div class="agent-card-title"><span>07</span><h3>سجل النشاط</h3></div>
        <div id="agentActivity" class="agent-activity agent-empty">ستظهر مراحل التنفيذ هنا.</div>
      </section>

      <section class="agent-card agent-result-card">
        <div class="agent-card-title"><span>08</span><h3>نتيجة الوكيل</h3></div>
        <pre id="agentResult" class="agent-result">اكتب المهمة في مربع الرسالة ثم أرسلها.</pre>
      </section>

      <section id="agentProposalCard" class="agent-card agent-proposal-card" hidden>
        <div class="agent-card-title"><span>09</span><h3>مقترح التغييرات</h3></div>
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
    this.semantic = this.root.querySelector("#agentSemantic");
    this.plan = this.root.querySelector("#agentPlan");
    this.review = this.root.querySelector("#agentReview");
    this.sandbox = this.root.querySelector("#agentSandbox");
    this.ci = this.root.querySelector("#agentCi");
    this.refreshCiButton = this.root.querySelector("#agentRefreshCi");
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
    this.refreshCiButton.addEventListener("click", this.actions.refreshCi);
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

  #renderSemantic(hits) {
    this.semantic.replaceChildren();
    if (!hits?.length) {
      this.semantic.className = "agent-empty";
      this.semantic.textContent = "تظهر الملفات الأعلى صلة بعد تحليل البنية والمحتوى.";
      return;
    }
    this.semantic.className = "agent-semantic-list";
    for (const hit of hits.slice(0, 8)) {
      const row = document.createElement("article");
      row.className = "agent-semantic-hit";
      const header = document.createElement("div");
      const path = document.createElement("strong");
      path.textContent = hit.path;
      const score = document.createElement("span");
      score.textContent = `${hit.score || 0}/100`;
      header.append(path, score);
      const reason = document.createElement("p");
      reason.textContent = hit.rationale || "";
      const symbols = document.createElement("small");
      symbols.textContent = (hit.symbols || []).slice(0, 8).join(" · ");
      row.append(header, reason, symbols);
      this.semantic.appendChild(row);
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

  #renderSandbox(validation, sandbox) {
    this.sandbox.replaceChildren();
    if (!validation && !sandbox) {
      this.sandbox.className = "agent-empty";
      this.sandbox.textContent = "تظهر الاختبارات الفعلية ومحاولات الإصلاح التلقائي هنا.";
      return;
    }
    this.sandbox.className = "agent-validation-panel";
    if (validation) {
      const profiles = document.createElement("div");
      profiles.className = "agent-profile-list";
      for (const profile of validation.workflowProfiles || []) {
        const chip = document.createElement("span");
        chip.textContent = profile;
        profiles.appendChild(chip);
      }
      this.sandbox.appendChild(profiles);
    }
    if (sandbox) {
      const verdict = document.createElement("p");
      verdict.className = `agent-sandbox-verdict ${sandbox.passed ? "passed" : "failed"}`;
      verdict.textContent = `${sandbox.passed ? "Sandbox passed" : "Sandbox failed"} · attempt ${sandbox.attempt || 1}`;
      this.sandbox.appendChild(verdict);
      const list = document.createElement("ul");
      for (const check of sandbox.checks || []) {
        const item = document.createElement("li");
        item.className = `agent-check-${check.status || "skipped"}`;
        item.textContent = `${check.name}: ${check.status}`;
        if (check.output) item.title = check.output;
        list.appendChild(item);
      }
      this.sandbox.appendChild(list);
    }
  }

  #renderCi(ci, proposal) {
    this.ci.replaceChildren();
    const canRefresh = proposal?.status === "applied";
    this.refreshCiButton.hidden = !canRefresh;
    if (!ci) {
      this.ci.className = "agent-empty";
      this.ci.textContent = canRefresh
        ? "Pull Request موجود. اضغط تحديث CI أو انتظر التحديث التلقائي."
        : "يظهر CI بعد إنشاء Pull Request.";
      return;
    }
    this.ci.className = "agent-ci-panel";
    const headline = document.createElement("strong");
    headline.textContent = `CI: ${ci.status || "unknown"}${ci.conclusion ? ` · ${ci.conclusion}` : ""}`;
    this.ci.appendChild(headline);
    for (const job of ci.jobs || []) {
      const row = document.createElement("article");
      row.className = `agent-ci-job agent-ci-${job.conclusion || job.status || "pending"}`;
      const title = document.createElement("span");
      title.textContent = `${job.name} · ${job.conclusion || job.status}`;
      row.appendChild(title);
      if (job.failed_steps?.length) {
        const failed = document.createElement("small");
        failed.textContent = `Failed: ${job.failed_steps.join(", ")}`;
        row.appendChild(failed);
      }
      if (job.url) {
        const link = document.createElement("a");
        link.href = job.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "GitHub";
        row.appendChild(link);
      }
      this.ci.appendChild(row);
    }
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
    const sandbox = proposal.sandbox_validation?.passed ? " · Sandbox passed" : "";
    meta.textContent = `${proposal.repository || "المستودع"} · ${proposal.base_branch || "main"} · ${proposal.status}${reviewScore}${riskLevel}${sandbox}`;
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
    const version = workspace.agent_core_version ? ` · Intelligence V${workspace.agent_core_version}` : "";
    return `${workspace.repository} · ${workspace.branch} · ${access}${version}`;
  }
}
