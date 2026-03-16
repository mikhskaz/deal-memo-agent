/* ═══════════════════════════════════════════
   Deal Memo Agent — Frontend Controller
   Vanilla JS: Upload → SSE Progress → Memo
   ═══════════════════════════════════════════ */

(function () {
    "use strict";

    // ── State ──
    let selectedFile = null;
    let currentJobId = null;
    let eventSource = null;
    let allExpanded = false;

    // ── Elements ──
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const screens = {
        upload: $("#uploadScreen"),
        processing: $("#processingScreen"),
        memo: $("#memoScreen"),
    };

    const els = {
        dropzone: $("#dropzone"),
        fileInput: $("#fileInput"),
        fileInfo: $("#fileInfo"),
        fileName: $("#fileName"),
        fileSize: $("#fileSize"),
        removeFile: $("#removeFile"),
        analyzeBtn: $("#analyzeBtn"),
        uploadError: $("#uploadError"),
        processingFileName: $("#processingFileName"),
        processingSubtitle: $("#processingSubtitle"),
        processingError: $("#processingError"),
        processingErrorText: $("#processingErrorText"),
        memoCompany: $("#memoCompany"),
        memoDate: $("#memoDate"),
        memoModel: $("#memoModel"),
        memoSections: $("#memoSections"),
        sourcesList: $("#sourcesList"),
        sidebarContent: $("#sidebarContent"),
        downloadBtn: $("#downloadBtn"),
        expandAllBtn: $("#expandAllBtn"),
        sidebarToggle: $("#sidebarToggle"),
        backBtn: $("#backBtn"),
        connectionStatus: $("#connectionStatus"),
        currentTime: $("#currentTime"),
    };

    // ── Utilities ──
    function formatBytes(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / 1048576).toFixed(1) + " MB";
    }

    function showScreen(name) {
        Object.values(screens).forEach((s) => s.classList.remove("active"));
        screens[name].classList.add("active");
    }

    function updateClock() {
        const now = new Date();
        els.currentTime.textContent = now.toLocaleTimeString("en-US", {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ── Upload Screen ──

    // Drag & drop
    els.dropzone.addEventListener("click", () => els.fileInput.click());

    els.dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        els.dropzone.classList.add("dragover");
    });

    els.dropzone.addEventListener("dragleave", () => {
        els.dropzone.classList.remove("dragover");
    });

    els.dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        els.dropzone.classList.remove("dragover");
        const file = e.dataTransfer.files[0];
        if (file) selectFile(file);
    });

    els.fileInput.addEventListener("change", (e) => {
        if (e.target.files[0]) selectFile(e.target.files[0]);
    });

    function selectFile(file) {
        // Validate
        if (!file.name.toLowerCase().endsWith(".pdf")) {
            showUploadError("Only PDF files are accepted.");
            return;
        }
        if (file.size > 50 * 1024 * 1024) {
            showUploadError("File too large — maximum size is 50 MB.");
            return;
        }

        selectedFile = file;
        els.fileName.textContent = file.name;
        els.fileSize.textContent = formatBytes(file.size);
        els.fileInfo.classList.remove("hidden");
        els.analyzeBtn.classList.remove("hidden");
        els.dropzone.classList.add("hidden");
        els.uploadError.classList.add("hidden");
    }

    els.removeFile.addEventListener("click", () => {
        selectedFile = null;
        els.fileInput.value = "";
        els.fileInfo.classList.add("hidden");
        els.analyzeBtn.classList.add("hidden");
        els.dropzone.classList.remove("hidden");
    });

    function showUploadError(msg) {
        els.uploadError.textContent = msg;
        els.uploadError.classList.remove("hidden");
    }

    // Upload
    els.analyzeBtn.addEventListener("click", async () => {
        if (!selectedFile) return;

        els.analyzeBtn.disabled = true;
        els.analyzeBtn.querySelector(".btn-text").textContent = "Uploading...";
        els.uploadError.classList.add("hidden");

        const formData = new FormData();
        formData.append("file", selectedFile);

        try {
            const resp = await fetch("/upload", { method: "POST", body: formData });
            const data = await resp.json();

            if (!resp.ok) {
                throw new Error(data.detail || "Upload failed");
            }

            currentJobId = data.job_id;
            startProcessing();
        } catch (err) {
            showUploadError(err.message);
            els.analyzeBtn.disabled = false;
            els.analyzeBtn.querySelector(".btn-text").textContent = "Analyze Document";
        }
    });

    // ── Processing Screen ──

    function startProcessing() {
        els.processingFileName.textContent = selectedFile.name;
        els.processingSubtitle.textContent = "Pipeline initializing...";
        els.processingError.classList.add("hidden");

        // Reset all stages
        $$(".pipeline-stage").forEach((el) => {
            el.classList.remove("active", "complete", "error");
            const msg = el.querySelector(".stage-message");
            if (msg) msg.textContent = "";
        });

        showScreen("processing");
        els.connectionStatus.textContent = "PROCESSING";
        els.connectionStatus.style.color = "var(--running)";

        connectSSE(currentJobId);
    }

    function connectSSE(jobId) {
        if (eventSource) eventSource.close();

        eventSource = new EventSource(`/status/${jobId}`);

        eventSource.addEventListener("pipeline_update", (e) => {
            const data = JSON.parse(e.data);
            handlePipelineUpdate(data);
        });

        eventSource.addEventListener("complete", (e) => {
            const data = JSON.parse(e.data);
            eventSource.close();
            eventSource = null;
            els.connectionStatus.textContent = "COMPLETE";
            els.connectionStatus.style.color = "var(--success)";
            loadMemo(data.job_id);
        });

        eventSource.addEventListener("error", (e) => {
            if (e.data) {
                const data = JSON.parse(e.data);
                showProcessingError(data.stage, data.message);
            }
            eventSource.close();
            eventSource = null;
            els.connectionStatus.textContent = "ERROR";
            els.connectionStatus.style.color = "var(--error)";
        });

        eventSource.onerror = () => {
            // SSE connection error (not pipeline error)
            els.processingSubtitle.textContent = "Connection lost — retrying...";
        };
    }

    const STAGE_ORDER = ["ingest", "extract", "enrich", "draft", "export"];

    function handlePipelineUpdate(data) {
        const { stage, status, message } = data;

        els.processingSubtitle.textContent = message || `Stage: ${stage} — ${status}`;

        const stageIdx = STAGE_ORDER.indexOf(stage);

        // Mark all prior stages complete
        STAGE_ORDER.forEach((s, i) => {
            const el = $(`.pipeline-stage[data-stage="${s}"]`);
            if (i < stageIdx) {
                el.classList.remove("active");
                el.classList.add("complete");
            } else if (i === stageIdx) {
                if (status === "complete") {
                    el.classList.remove("active");
                    el.classList.add("complete");
                } else {
                    el.classList.remove("complete");
                    el.classList.add("active");
                }
            }
        });

        // Update message
        const msgEl = $(`#msg-${stage}`);
        if (msgEl && message) msgEl.textContent = message;
    }

    function showProcessingError(stage, message) {
        if (stage) {
            const el = $(`.pipeline-stage[data-stage="${stage}"]`);
            if (el) {
                el.classList.remove("active");
                el.classList.add("error");
            }
        }
        els.processingError.classList.remove("hidden");
        els.processingErrorText.textContent = message || "An unexpected error occurred.";
    }

    // ── Memo Screen ──

    const SECTION_LABELS = {
        executive_summary: "Executive Summary",
        business_description: "Business Description",
        market_opportunity: "Market Opportunity",
        financial_overview: "Financial Overview",
        key_risks: "Key Risks",
        management_team: "Management Team",
        diligence_questions: "Diligence Questions",
        recommended_next_step: "Recommended Next Steps",
    };

    const SECTION_ORDER = [
        "executive_summary",
        "business_description",
        "market_opportunity",
        "financial_overview",
        "key_risks",
        "management_team",
        "diligence_questions",
        "recommended_next_step",
    ];

    async function loadMemo(jobId) {
        try {
            const resp = await fetch(`/memo/${jobId}`);
            if (!resp.ok) throw new Error("Failed to load memo");
            const data = await resp.json();
            renderMemo(data);
            showScreen("memo");
        } catch (err) {
            showProcessingError(null, "Failed to load memo: " + err.message);
        }
    }

    function renderMemo(data) {
        // Header
        els.memoCompany.textContent = `Investment Memo: ${data.company_name || "Unknown Company"}`;
        els.memoDate.textContent = data.generated_at
            ? new Date(data.generated_at).toLocaleString()
            : "";
        els.memoModel.textContent = "Claude Sonnet 4.5";
        els.downloadBtn.href = data.docx_download_url || "#";

        // Sections
        els.memoSections.innerHTML = "";
        SECTION_ORDER.forEach((id, idx) => {
            const content = data.memo?.[id];
            if (!content) return;

            const section = document.createElement("div");
            section.className = "memo-section" + (idx === 0 ? " expanded" : "");

            section.innerHTML = `
                <div class="memo-section-header">
                    <span class="memo-section-title">
                        <span class="section-number">${String(idx + 1).padStart(2, "0")}</span>
                        ${SECTION_LABELS[id] || id}
                    </span>
                    <span class="section-chevron">&#9654;</span>
                </div>
                <div class="memo-section-body">
                    <div class="memo-section-content">${markdownToHtml(content)}</div>
                </div>
            `;

            section.querySelector(".memo-section-header").addEventListener("click", () => {
                section.classList.toggle("expanded");
            });

            els.memoSections.appendChild(section);
        });

        // Sources
        els.sourcesList.innerHTML = "";
        if (data.sources && data.sources.length > 0) {
            data.sources.forEach((src, i) => {
                const item = document.createElement("div");
                item.className = "source-item";
                item.innerHTML = `
                    <span class="source-num">[${i + 1}]</span>
                    <span class="source-title">${escapeHtml(src.title)}</span>
                    <a class="source-link" href="${escapeHtml(src.url)}" target="_blank" rel="noopener">${truncateUrl(src.url)}</a>
                `;
                els.sourcesList.appendChild(item);
            });
        } else {
            els.sourcesList.innerHTML = '<div style="font-size:12px;color:var(--text-tertiary)">No web sources used.</div>';
        }

        // Sidebar — extraction data
        renderSidebar(data.extraction);
    }

    function renderSidebar(extraction) {
        els.sidebarContent.innerHTML = "";
        if (!extraction) {
            els.sidebarContent.innerHTML = '<div style="color:var(--text-tertiary);font-size:12px;">No extraction data.</div>';
            return;
        }

        const fields = [
            ["Company", extraction.company_name],
            ["Sector", extraction.sector],
            ["Sub-Sector", extraction.sub_sector],
            ["HQ", extraction.headquarters],
            ["Founded", extraction.founded_year],
            ["Employees", extraction.employee_count],
            ["Business Model", extraction.business_model],
            ["Deal Type", extraction.deal_type?.replace("_", " ")],
            ["Revenue", extraction.revenue_current],
            ["Prior Revenue", extraction.revenue_prior_year],
            ["Growth Rate", extraction.revenue_growth_rate],
            ["EBITDA", extraction.ebitda_current],
            ["EBITDA Margin", extraction.ebitda_margin],
            ["ARR", extraction.arr],
            ["Gross Margin", extraction.gross_margin],
            ["NRR", extraction.nrr],
            ["Customers", extraction.customer_count],
            ["Valuation", extraction.asking_price_or_valuation],
            ["TAM", extraction.total_addressable_market],
        ];

        fields.forEach(([label, value]) => {
            const div = document.createElement("div");
            div.className = "sidebar-field";
            div.innerHTML = `
                <div class="sidebar-field-label">${label}</div>
                <div class="sidebar-field-value ${value == null ? "empty" : ""}">${value ?? "—"}</div>
            `;
            els.sidebarContent.appendChild(div);
        });

        // List fields
        const listFields = [
            ["Key Customers", extraction.key_customers],
            ["Competitive Advantages", extraction.competitive_advantages],
            ["Geographic Markets", extraction.geographic_markets],
            ["Key Risks", extraction.key_risks_mentioned],
        ];

        listFields.forEach(([label, items]) => {
            if (!items || items.length === 0) return;
            const div = document.createElement("div");
            div.className = "sidebar-field";
            div.innerHTML = `<div class="sidebar-field-label">${label}</div>
                <div class="sidebar-field-value list-value">${items.map((t) => `<span class="sidebar-tag">${escapeHtml(t)}</span>`).join("")}</div>`;
            els.sidebarContent.appendChild(div);
        });

        // Management team
        if (extraction.management_team && extraction.management_team.length > 0) {
            const div = document.createElement("div");
            div.className = "sidebar-field";
            div.innerHTML = `<div class="sidebar-field-label">Management Team</div>
                <div class="sidebar-field-value list-value">${extraction.management_team
                    .map((m) => `<span class="sidebar-tag">${escapeHtml(m.name)} — ${escapeHtml(m.title)}</span>`)
                    .join("")}</div>`;
            els.sidebarContent.appendChild(div);
        }
    }

    // Expand / collapse all
    els.expandAllBtn.addEventListener("click", () => {
        allExpanded = !allExpanded;
        $$(".memo-section").forEach((s) => {
            if (allExpanded) s.classList.add("expanded");
            else s.classList.remove("expanded");
        });
        els.expandAllBtn.textContent = allExpanded ? "Collapse All" : "Expand All";
    });

    // Sidebar toggle
    els.sidebarToggle.addEventListener("click", () => {
        const sidebar = $("#memoSidebar");
        sidebar.classList.toggle("collapsed");
    });

    // Back button
    els.backBtn.addEventListener("click", () => {
        // Reset state
        selectedFile = null;
        currentJobId = null;
        if (eventSource) { eventSource.close(); eventSource = null; }

        els.fileInput.value = "";
        els.fileInfo.classList.add("hidden");
        els.analyzeBtn.classList.add("hidden");
        els.analyzeBtn.disabled = false;
        els.analyzeBtn.querySelector(".btn-text").textContent = "Analyze Document";
        els.dropzone.classList.remove("hidden");
        els.uploadError.classList.add("hidden");
        els.connectionStatus.textContent = "READY";
        els.connectionStatus.style.color = "var(--success)";

        showScreen("upload");
    });

    // ── Markdown helpers ──

    function markdownToHtml(md) {
        if (!md) return "";
        let html = escapeHtml(md);

        // Headings
        html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');

        // Bold
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

        // Italic
        html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

        // Unordered lists
        html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
        html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

        // Ordered lists (simple)
        html = html.replace(/^\d+\.\s(.+)$/gm, "<li>$1</li>");

        // Paragraphs
        html = html
            .split("\n\n")
            .map((block) => {
                block = block.trim();
                if (!block) return "";
                if (block.startsWith("<h") || block.startsWith("<ul") || block.startsWith("<ol") || block.startsWith("<li")) return block;
                return `<p>${block.replace(/\n/g, "<br>")}</p>`;
            })
            .join("\n");

        return html;
    }

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function truncateUrl(url) {
        try {
            const u = new URL(url);
            const path = u.pathname.length > 30 ? u.pathname.slice(0, 30) + "..." : u.pathname;
            return u.hostname + path;
        } catch {
            return url.length > 50 ? url.slice(0, 50) + "..." : url;
        }
    }
})();
