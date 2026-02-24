const ReviewWorkbench = {
  init() {
    $("#btnRunSectionReview").addEventListener("click", guarded(() => this.runSectionReview()));
    $("#btnApplyReviewNote").addEventListener("click", guarded(() => this.applyReviewInteraction()));
    $("#btnBuildFinalDraft").addEventListener("click", guarded(() => this.buildFinalDraft()));
    $("#reviewSectionSelect").addEventListener("change", () => this.onSectionSwitch());
  },

  refreshSectionSelect() {
    const select = $("#reviewSectionSelect");
    const current = select.value;
    select.innerHTML = "";

    if (!state.sections.length) {
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "暂无章节";
      select.appendChild(empty);
      this.renderOverallMetrics();
      return;
    }

    state.sections.forEach((section) => {
      const option = document.createElement("option");
      option.value = section.section_key;
      option.textContent = `${section.section_key} ${section.section_title} | ${sectionStatusLabel(section.status)}`;
      select.appendChild(option);
    });

    if (current && getSectionByKey(current)) {
      select.value = current;
    }

    this.onSectionSwitch();
    this.renderOverallMetrics();
  },

  onSectionSwitch() {
    const section = getSectionByKey($("#reviewSectionSelect").value);
    if (!section) {
      $("#reviewUserNote").value = "";
      $("#reviewReport").innerHTML = `<p class="hint">审核后会显示本章合规与得分情况。</p>`;
      return;
    }

    $("#reviewUserNote").value = section.review?.userNote || "";
    $("#reviewDecision").value = section.reviewDecision || "PASS";
    this.renderReviewReport(section);
  },

  async runSectionReview() {
    const section = getSectionByKey($("#reviewSectionSelect").value);
    if (!section) {
      Toast.error("请先选择章节");
      return;
    }

    const draftText = section.finalDraft.trim();
    if (!draftText) {
      Toast.error("该章节暂无最终稿，无法审核");
      return;
    }

    const evidence = (section.evidenceHits || []).map((item) => ({
      evidence_id: item.chunk_id,
      text: item.text,
    }));

    const evidenceIds = evidence.map((item) => item.evidence_id);

    setTaskStatus(`章节审核中：${section.section_key}`);

    const validateRes = await api("/v1/generation/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        requirement_id: section.section_key,
        generated_text: draftText,
        evidence_ids: evidenceIds,
        evidence,
      }),
    });

    const pricingRes = await api("/v1/policy/pricing-fuse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: draftText }),
    });

    const coverage = Number(validateRes.coverage || 0);
    const baseScore = coverage * 70;
    const gateBonus = validateRes.status === "SUPPORTED" ? 20 : 8;
    const pricingBonus = pricingRes.blocked ? 0 : 10;
    const penalty = (validateRes.missing_sentences || []).length * 4;
    const score = Math.max(0, Math.min(100, Math.round(baseScore + gateBonus + pricingBonus - penalty)));

    section.review = {
      validate: validateRes,
      pricing: pricingRes,
      score,
      reviewedAt: new Date().toISOString(),
      userNote: section.review?.userNote || "",
    };

    this.renderReviewReport(section);
    this.renderOverallMetrics();

    setTaskStatus(`章节审核完成：${section.section_key}`);
    Toast.success(`章节审核完成，得分 ${score}`);
  },

  renderReviewReport(section) {
    const report = $("#reviewReport");
    const review = section.review;
    if (!review) {
      report.innerHTML = `<p class="hint">尚未执行审核。请点击“执行章节审核评分”。</p>`;
      return;
    }

    const missing = review.validate.missing_sentences || [];
    report.innerHTML = `
      <div class="review-line"><span>章节</span><strong>${escapeHtml(section.section_key)} ${escapeHtml(section.section_title)}</strong></div>
      <div class="review-line"><span>合规状态</span><strong>${escapeHtml(review.validate.status)}</strong></div>
      <div class="review-line"><span>覆盖率</span><strong>${(Number(review.validate.coverage || 0) * 100).toFixed(1)}%</strong></div>
      <div class="review-line"><span>价格内容熔断</span><strong>${review.pricing.blocked ? "触发（需处理）" : "未触发"}</strong></div>
      <div class="review-line"><span>本章评分</span><strong>${review.score}</strong></div>
      <div class="review-line"><span>缺失提示</span><strong>${escapeHtml(missing.length ? missing.join("；") : "无")}</strong></div>
    `;
  },

  applyReviewInteraction() {
    const section = getSectionByKey($("#reviewSectionSelect").value);
    if (!section) {
      Toast.error("请先选择章节");
      return;
    }

    const decision = $("#reviewDecision").value;
    const note = $("#reviewUserNote").value.trim();

    section.reviewDecision = decision;
    section.review = section.review || { score: 0, validate: { coverage: 0, status: "NEED_HUMAN_INPUT", missing_sentences: [] }, pricing: { blocked: false, reasons: [] } };
    section.review.userNote = note;

    if (note) {
      const block = `\n\n【审核交互记录】\n结论：${decision}\n说明：${note}`;
      if (!section.finalDraft.includes("【审核交互记录】")) {
        section.finalDraft = `${section.finalDraft.trim()}${block}`.trim();
      }
    }

    if (decision === "REWRITE") {
      section.status = "NEED_REWRITE";
    } else if (decision === "ADJUST_PASS") {
      section.status = section.status === "SECTION_CONFIRMED" ? "SECTION_CONFIRMED" : "SUPPORTED";
    } else if (section.status === "NEW" || section.status === "NEED_REWRITE") {
      section.status = "SUPPORTED";
    }

    BidWorkbench.renderSectionList();
    BidWorkbench.renderSectionEditor();
    this.renderReviewReport(section);
    this.renderOverallMetrics();

    Toast.success("审核交互结果已应用到章节最终稿");
  },

  buildFinalDraft() {
    const completedSections = state.sections
      .filter((section) => section.finalDraft && section.finalDraft.trim())
      .sort((a, b) => a.section_key.localeCompare(b.section_key, "zh-CN"));

    if (!completedSections.length) {
      Toast.error("尚无可汇总章节");
      return false;
    }

    const header = [
      `项目ID：${state.projectId || "未设置"}`,
      `编制时间：${new Date().toLocaleString("zh-CN")}`,
      state.analysisDetail?.run?.filename ? `对应招标文件：${state.analysisDetail.run.filename}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    const body = completedSections
      .map((section) => `# ${section.section_key} ${section.section_title}\n\n${section.finalDraft.trim()}`)
      .join("\n\n");

    state.finalBidDraft = `${header}\n\n${body}`;
    $("#finalDraftPreview").value = state.finalBidDraft;
    $("#publishFinalDraft").value = state.finalBidDraft;

    this.renderOverallMetrics();
    Toast.success("最终投标文件已形成，可进入排版与终审");
    return true;
  },

  renderOverallMetrics() {
    const total = state.sections.length;
    const confirmed = state.sections.filter((section) => section.status === "SECTION_CONFIRMED").length;
    const reviewed = state.sections.filter((section) => section.review).length;
    const scores = state.sections.map((section) => section.review?.score).filter((score) => typeof score === "number");
    const avgScore = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;

    const ready = total > 0 && confirmed === total && reviewed === total && avgScore >= 75;

    $("#reviewOverallMetrics").innerHTML = [
      { k: "章节总数", v: total },
      { k: "已确认章节", v: confirmed },
      { k: "已审核章节", v: reviewed },
      { k: "平均得分", v: avgScore },
      { k: "可终审状态", v: ready ? "是" : "否" },
    ]
      .map(
        (item) => `
          <div class="summary-card">
            <div class="k">${escapeHtml(String(item.k))}</div>
            <div class="v">${escapeHtml(String(item.v))}</div>
          </div>
        `,
      )
      .join("");
  },
};

const ReviewScoreDashboard = {
  init() {
    $("#btnFetchReviewApi")?.addEventListener("click", guarded(() => this.fetchReview()));
    $("#btnFetchScoreApi")?.addEventListener("click", guarded(() => this.fetchScore()));
    this.renderReviewSummary(null);
    this.renderScoreSummary(null);
  },

  currentSectionKey() {
    return $("#reviewSectionSelect")?.value?.trim() || "";
  },

  renderReviewSummary(data) {
    const card = $("#reviewSummaryCard");
    if (!card) return;
    if (!data) {
      card.querySelector(".metric-value").textContent = "--";
      card.querySelector(".metric-sub").textContent = "等待审核";
      return;
    }
    card.querySelector(".metric-value").textContent = data.status || "--";
    card.querySelector(".metric-sub").textContent = data.created_at || "";
  },

  renderScoreSummary(data) {
    const card = $("#scoringSummaryCard");
    if (!card) return;
    if (!data) {
      card.querySelector(".metric-value").textContent = "--";
      card.querySelector(".metric-sub").textContent = "等待评分";
      return;
    }
    card.querySelector(".metric-value").textContent = Number(data.score_total || 0).toFixed(1);
    card.querySelector(".metric-sub").textContent = data.created_at || "";
  },

  setDetail(text) {
    const box = $("#reviewSummaryDetail");
    if (box) box.textContent = text;
  },

  async fetchReview() {
    const sectionKey = this.currentSectionKey();
    if (!sectionKey) {
      Toast.error("请先选择章节");
      return;
    }
    const projectId = ensureProjectId();
    const res = await api("/v1/workflow/section/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId, section_key: sectionKey }),
    });
    this.renderReviewSummary(res);
    this.setDetail(JSON.stringify(res, null, 2));
  },

  async fetchScore() {
    const projectId = ensureProjectId();
    const res = await api("/v1/workflow/scoring/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId }),
    });
    this.renderScoreSummary(res);
    this.setDetail(JSON.stringify(res, null, 2));
  },
};
