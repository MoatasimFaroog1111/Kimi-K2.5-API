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
    this.runId.textContent = state.runId ? `Run ${state.runId}` : "Agent Runtime V4";
    this.runState.textContent = this.#runStateLabel(state);
    this.autoModel.checked = state.autoModel !== false;
    this.clearButton.disabled = state.isRunning;

    const paused = state.runStatus === "paused";
    const terminal = ["completed", "cancelled", "failed"].includes(state.runStatus);
    this.pauseButton.hidden = !state.runId || !state.isRunning;
    this.pauseButton.disabled = state.isControlPending;
    this.resumeButton.hidden = !paused;
    this.resumeButton.disabled = state.isRunning || state.isControlPending;
    this.cancelButton.hidden = !state.runId || terminal;
    this.cancelButton.disabled = state.isControlPending;

    this.#renderRuntime(state);
    this.#renderContextBudget(state);
    this.#renderKnowledge(state.knowledge);
    this.#renderSemantic(state.semanticHits);
    this.#renderPlan(state.plan);
    this.#renderSecurityReview(state.security, state.review);
    this.#renderSandbox(state.validation, state.sandboxValidation);
    this.#renderCi(state.ciFeedback || state.proposal?.ci_feedback, state.proposal);
    this.#renderRuns(state.recentRuns, state.runId);
    this.#renderActivities(state.activities);
    this.#renderResult(state.result, state.error);
    this.#renderProposal(state.proposal);
  }

  #build() {
    this.root.innerHTML = `
      <div class="agent-hero agent-v4-hero">
        <div>
          <p class="agent-eyebrow">RESUMABLE · ROUTED · BUDGETED · APPROVAL FIRST</p>
          <h2>Agent Runtime V4</h2>
          <p>Checkpoint → Model Router → Context Manager → Engineering Pipeline → Sandbox → Per‑file Approval → Pull Request → CI Repair Proposal.</p>
        </div>
        <div class="agent-hero-actions">
          <label class="agent-router-toggle">
            <input id="agentAutoModel" type="checkbox" checked>
            <span>Auto Model Router</span>
          </label>
          <button id="agentClear" class="agent-secondary-button" type="button">مهمة جديدة</button>
        </div>
      </div>

      <div class="agent-status-bar agent-runtime-bar">
        <span class="agent-status-dot" id="agentStatusDot"></span>
        <strong id="agentStatusText">جاري قراءة حالة مساحة العمل…</strong>
        <span id="agentRunId">Agent Runtime V4</span>
        <span id="agentRunState">جاهز لمهمة جديدة</span>
        <div class="agent-runtime-actions">
          <button id="agentPause" class="agent-secondary-button" type="button" hidden>إيقاف مؤقت</button>
          <button id="agentResume" class="agent-primary-button" type="button" hidden>استئناف</button>
          <button id="agentCancel" class="agent-secondary-button danger" type="button" hidden>إلغاء</button>
        </div>
      </div>

      <div class="agent-pipeline" aria-label="مراحل الوكيل">
        <span>Checkpoint</span><span>Router</span><span>Context</span><span>Memory</span>
        <span>Semantic</span><span>Planner</span><span>Coder</span><span>Security</span>
        <span>Reviewer</span><span>Tester</span><span>Sandbox</span><span>Approval</span><span>CI</span>
      </div>

      <div class="agent-grid agent-grid-v4">
        <section class="agent-card agent-runtime-card">
          <div class="agent-card-title"><span>01</span><h3>Runtime + Model Router</h3></div>
          <div id="agentRuntime" class="agent-empty">تظهر حالة التشغيل والنموذج المختار هنا.</div>
        </section>
        <section class="agent-card">
          <div class="agent-card-title"><span>02</span><h3>Context + Budget</h3></div>
          <div id="agentContextBudget" class="agent-empty">تظهر ميزانية السياق والتوكن هنا.</div>
        </section>
        <section class="agent-card">
          <div class="agent-card-title"><span>03</span><h3>ذاكرة المشروع</h3></div>
          <div id="agentKnowledge" class="agent-empty">لم يتم استرجاع معرفة بعد.</div>
        </section>
        <section class="agent-card">
          <div class="agent-card-title"><span>04</span><h3>Semantic Code Intelligence</h3></div>
          <div id="agentSemantic" class="agent-empty">تظهر الملفات الأعلى صلة هنا.</div>
        </section>
        <section class="agent-card">
          <div class="agent-card-title"><span>05</span><h3>خطة Planner</h3></div>
          <div id="agentPlan" class="agent-empty">لم تبدأ مهمة بعد.</div>
        </section>
        <section class="agent-card">
          <div class="agent-card-title"><span>06</span><h3>Security + Reviewer</h3></div>
          <div id="agentReview" class="agent-empty">تظهر نتيجة المراجعة المستقلة هنا.</div>
        </section>
        <section class="agent-card">
          <div class="agent-card-title"><span>07</span><h3>Pre‑Approval Sandbox</h3></div>
          <div id="agentSandbox" class="agent-empty">تظهر الاختبارات الفعلية هنا.</div>
        </section>
        <section class="agent-card">
          <div class="agent-card-title"><span>08</span><h3>GitHub CI</h3></div>
          <div id="agentCi" class="agent-empty">يظهر CI بعد Pull Request.</div>
          <div class="agent-inline-actions">
            <button id="agentRefreshCi" class="agent-secondary-button" type="button" hidden>تحديث CI</button>
            <button id="agentRepairCi" class="agent-primary-button" type="button" hidden>إنشاء Fix Proposal</button>
          </div>
        </section>
      </div>

      <section class="agent-card agent-runs-card">
        <div class="agent-card-title"><span>09</span><h3>المهام المحفوظة</h3></div>
        <div id="agentRecentRuns" class="agent-empty">لا توجد مهام محفوظة بعد.</div>
      </section>

      <section class="agent-card agent-activity-card">
        <div class="agent-card-title"><span>10</span><h3>سجل النشاط</h3></div>
        <div id="agentActivity" class="agent-activity agent-empty">ستظهر مراحل التنفيذ هنا.</div>
      </section>

      <section class="agent-card agent-result-card">
        <div class="agent-card-title"><span>11</span><h3>نتيجة الوكيل</h3></div>
        <pre id="agentResult" class="agent-result">اكتب المهمة في مربع الرسالة ثم أرسلها.</pre>
      </section>

      <section id="agentProposalCard" class="agent-card agent-proposal-card" hidden>
        <div class="agent-card-title"><span>12</span><h3>Per‑file Approval</h3></div>
        <div id="agentProposalSummary"></div>
        <p class="agent-file-approval-note">حدد الملفات التي تسمح للوكيل بإرسالها إلى GitHub. الملفات غير المحددة لن تُكتب.</p>
        <div id="agentChanges" class="agent-changes"></div>
        <div class="agent-approval-actions">
          <button id="agentApprove" class="agent-primary-button" type="button">إنشاء Pull Request بالملفات المحددة</button>
          <button id="agentReject" class="agent-secondary-button danger" type="button">رفض المقترح</button>
          <button id="agentUndo" class="agent-secondary-button" type="button" hidden>إلغاء Pull Request</button>
        </div>
      </section>
    `;

    this.statusDot = this.root.querySelector("#agentStatusDot");
    this.statusText = this.root.querySelector("#agentStatusText");
    this.runId = this.root.querySelector("#agentRunId");
    this.runState = this.root.querySelector("#agentRunState");
    this.autoModel = this.root.querySelector("#agentAutoModel");
    this.pauseButton = this.root.querySelector("#agentPause");
    this.resumeButton = this.root.querySelector("#agentResume");
    this.cancelButton = this.root.querySelector("#agentCancel");
    this.runtime = this.root.querySelector("#agentRuntime");
    this.contextBudget = this.root.querySelector("#agentContextBudget");
    this.knowledge = this.root.querySelector("#agentKnowledge");
    this.semantic = this.root.querySelector("#agentSemantic");
    this.plan = this.root.querySelector("#agentPlan");
    this.review = this.root.querySelector("#agentReview");
    this.sandbox = this.root.querySelector("#agentSandbox");
    this.ci = this.root.querySelector("#agentCi");
    this.refreshCiButton = this.root.querySelector("#agentRefreshCi");
    this.repairCiButton = this.root.querySelector("#agentRepairCi");
    this.recentRuns = this.root.querySelector("#agentRecentRuns");
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
    this.pauseButton.addEventListener("click", this.actions.pause);
    this.resumeButton.addEventListener("click", this.actions.resume);
    this.cancelButton.addEventListener("click", this.actions.cancel);
    this.autoModel.addEventListener("change", () => this.actions.autoModel(this.autoModel.checked));
    this.approveButton.addEventListener("click", this.actions.approve);
    this.rejectButton.addEventListener("click", this.actions.reject);
    this.undoButton.addEventListener("click", this.actions.undo);
    this.refreshCiButton.addEventListener("click", this.actions.refreshCi);
    this.repairCiButton.addEventListener("click", this.actions.repairCi);
  }

  #renderRuntime(state) {
    this.runtime.replaceChildren();
    if (!state.runId && !state.modelRoute) {
      this.runtime.className = "agent-empty";
      this.runtime.textContent = "ابدأ مهمة ليتم إنشاء Run دائم واختيار النموذج تلقائيًا.";
      return;
    }
    this.runtime.className = "agent-runtime-panel";
    const rows = [
      ["Status", state.runStatus || (state.isRunning ? "running" : "ready")],
      ["Model", state.modelRoute?.selected_model || "—"],
      ["Route", state.modelRoute ? `${state.modelRoute.mode} · ${state.modelRoute.tier}` : "—"],
    ];
    for (const [label, value] of rows) {
      const row = document.createElement("div");
      const span = document.createElement("span");
      span.textContent = label;
      const strong = document.createElement("strong");
      strong.textContent = value;
      row.append(span, strong);
      this.runtime.appendChild(row);
    }
    if (state.modelRoute?.reason) {
      const reason = document.createElement("p");
      reason.textContent = state.modelRoute.reason;
      this.runtime.appendChild(reason);
    }
  }

  #renderContextBudget(state) {
    this.contextBudget.replaceChildren();
    if (!state.contextReport && !state.budget) {
      this.contextBudget.className = "agent-empty";
      this.contextBudget.textContent = "تظهر معلومات ضغط السياق واستهلاك الميزانية أثناء التنفيذ.";
      return;
    }
    this.contextBudget.className = "agent-budget-panel";
    if (state.contextReport) {
      const context = document.createElement("div");
      context.className = "agent-budget-block";
      const strong = document.createElement("strong");
      strong.textContent = "Context";
      const span = document.createElement("span");
      span.textContent = `${state.contextReport.prepared_chars || 0} chars · ~${state.contextReport.estimated_tokens || 0} tokens`;
      context.append(strong, span);
      if (state.contextReport.compacted) {
        const small = document.createElement("small");
        small.textContent = `تم الضغط من ${state.contextReport.original_chars || 0} حرف${state.contextReport.dropped_paths?.length ? ` · استُبعد ${state.contextReport.dropped_paths.length} ملف` : ""}.`;
        context.appendChild(small);
      }
      this.contextBudget.appendChild(context);
    }
    if (state.budget) {
      const budget = document.createElement("div");
      budget.className = "agent-budget-block";
      const strong = document.createElement("strong");
      strong.textContent = "Run Budget";
      const used = state.budget.estimated_tokens_used || 0;
      const limit = state.budget.token_limit || 1;
      const span = document.createElement("span");
      span.textContent = `${used.toLocaleString()} / ${limit.toLocaleString()} tokens`;
      const meter = document.createElement("div");
      meter.className = "agent-budget-meter";
      const fill = document.createElement("i");
      fill.style.width = `${Math.min(100, Math.round((used / limit) * 100))}%`;
      meter.appendChild(fill);
      const cost = document.createElement("small");
      cost.textContent = state.budget.cost_tracking
        ? `Estimated cost: $${Number(state.budget.estimated_cost_usd || 0).toFixed(4)} / $${Number(state.budget.cost_limit_usd || 0).toFixed(2)}`
        : "Cost tracking غير مفعّل لأن أسعار النماذج لم تُضبط.";
      budget.append(strong, span, meter, cost);
      this.contextBudget.appendChild(budget);
    }
  }

  #renderKnowledge(items) {
    this.knowledge.replaceChildren();
    if (!items?.length) {
      this.knowledge.className = "agent-empty";
      this.knowledge.textContent = "لا توجد معرفة سابقة مرتبطة بالمهمة.";
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
      this.semantic.textContent = "لم يكتمل التحليل الدلالي بعد.";
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
      row.append(header, reason);
      this.semantic.appendChild(row);
    }
  }

  #renderPlan(plan) {
    this.plan.replaceChildren();
    if (!plan) {
      this.plan.className = "agent-empty";
      this.plan.textContent = "لم تبدأ خطة بعد.";
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
        const p = document.createElement("p");
        p.textContent = reason;
        risk.appendChild(p);
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
        const p = document.createElement("p");
        p.textContent = finding;
        verdict.appendChild(p);
      }
      this.review.appendChild(verdict);
    }
  }

  #renderSandbox(validation, sandbox) {
    this.sandbox.replaceChildren();
    if (!validation && !sandbox) {
      this.sandbox.className = "agent-empty";
      this.sandbox.textContent = "لم تبدأ اختبارات Sandbox بعد.";
      return;
    }
    this.sandbox.className = "agent-validation-panel";
    if (validation?.workflowProfiles?.length) {
      const profiles = document.createElement("div");
      profiles.className = "agent-profile-list";
      for (const profile of validation.workflowProfiles) {
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
    const applied = proposal?.status === "applied";
    this.refreshCiButton.hidden = !applied;
    this.repairCiButton.hidden = !(applied && ci?.status === "completed" && ci?.conclusion === "failure");
    if (!ci) {
      this.ci.className = "agent-empty";
      this.ci.textContent = applied ? "Pull Request موجود. حدّث CI لقراءة النتائج." : "يظهر CI بعد Pull Request.";
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

  #renderRuns(runs, activeRunId) {
    this.recentRuns.replaceChildren();
    if (!runs?.length) {
      this.recentRuns.className = "agent-empty";
      this.recentRuns.textContent = "لا توجد مهام محفوظة بعد.";
      return;
    }
    this.recentRuns.className = "agent-runs-list";
    for (const run of runs.slice(0, 20)) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "agent-run-row";
      if (run.id === activeRunId) button.classList.add("active");
      const task = document.createElement("strong");
      task.textContent = run.task || run.id;
      const meta = document.createElement("span");
      meta.textContent = `${run.status} · ${run.stage} · ${run.selected_model || "model"}`;
      button.append(task, meta);
      button.addEventListener("click", () => this.actions.openRun(run.id));
      this.recentRuns.appendChild(button);
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
    meta.textContent = `${proposal.repository || "المستودع"} · base ${proposal.base_branch || "main"} · ${proposal.status}${proposal.parent_proposal_id ? ` · fix for ${proposal.parent_proposal_id}` : ""}`;
    this.proposalSummary.append(summary, meta);

    const approved = new Set(proposal.approved_paths || []);
    this.changes.replaceChildren();
    for (const change of proposal.changes || []) {
      const card = document.createElement("div");
      card.className = "agent-change-v4";
      const label = document.createElement("label");
      label.className = "agent-file-approval";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = approved.has(change.path);
      checkbox.disabled = !proposal.can_select_files;
      checkbox.addEventListener("change", () => this.actions.toggleFile(change.path, checkbox.checked));
      const text = document.createElement("span");
      const strong = document.createElement("strong");
      strong.textContent = change.path;
      const small = document.createElement("small");
      small.textContent = change.reason || "";
      text.append(strong, small);
      label.append(checkbox, text);
      card.appendChild(label);
      if (change.diff) {
        const details = document.createElement("details");
        const title = document.createElement("summary");
        title.textContent = "عرض الفرق";
        const diff = document.createElement("pre");
        diff.textContent = change.diff;
        details.append(title, diff);
        card.appendChild(details);
      }
      this.changes.appendChild(card);
    }

    const selectedCount = approved.size;
    const applied = proposal.status === "applied";
    this.approveButton.hidden = proposal.status !== "pending";
    this.rejectButton.hidden = proposal.status !== "pending";
    this.undoButton.hidden = !applied;
    this.approveButton.disabled = proposal.status !== "pending" || selectedCount === 0;
    this.approveButton.textContent = selectedCount
      ? `إنشاء Pull Request بـ ${selectedCount} ملف`
      : "حدد ملفًا واحدًا على الأقل";

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

  #runStateLabel(state) {
    if (state.isControlPending) return "جارٍ تطبيق أمر التحكم عند أقرب Checkpoint…";
    if (state.runStatus === "paused") return "متوقف مؤقتًا ومحفوظ";
    if (state.runStatus === "cancelled") return "تم إلغاء المهمة";
    if (state.runStatus === "waiting-approval") return "بانتظار موافقتك";
    if (state.runStatus === "failed") return "فشلت المهمة";
    if (state.isRunning) return "الوكيل يعمل الآن";
    return "جاهز لمهمة جديدة";
  }

  #workspaceLabel(workspace) {
    if (!workspace?.configured) {
      return "وضع التخطيط فقط · اربط مستودع GitHub لتفعيل القراءة والتغييرات";
    }
    const access = workspace.write_enabled ? "Pull Request بعد الموافقة" : "قراءة فقط";
    const version = workspace.agent_core_version ? ` · Core V${workspace.agent_core_version}` : "";
    return `${workspace.repository} · ${workspace.branch} · ${access}${version}`;
  }
}
