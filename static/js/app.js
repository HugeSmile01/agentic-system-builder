/* ===================================================================
   Agentic System Builder – Client-side Application
   Author: John Rish Ladica | SLSU-HC – SITS
   =================================================================== */

(function () {
  "use strict";

  // ---------------------------------------------------------------
  // State
  // ---------------------------------------------------------------
  let token = localStorage.getItem("asb_token") || "";
  let currentUser = null;
  let currentProjectId = null;
  let pipelineData = {};   // { refined, plan }

  // ---------------------------------------------------------------
  // DOM helpers
  // ---------------------------------------------------------------
  const $ = (sel) => document.querySelector(sel);
  const show = (el) => el.classList.remove("hidden");
  const hide = (el) => el.classList.add("hidden");

  // ---------------------------------------------------------------
  // Toast notifications
  // ---------------------------------------------------------------
  function toast(msg, type) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "toast visible" + (type ? " " + type : "");
    setTimeout(() => { el.className = "toast"; }, 3000);
  }

  // ---------------------------------------------------------------
  // API helper
  // ---------------------------------------------------------------
  async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = "Bearer " + token;
    Object.assign(headers, opts.headers || {});

    const res = await fetch(path, { ...opts, headers });
    if (!res.ok) {
      let msg = "Request failed";
      try { msg = (await res.json()).error || msg; } catch (_e) { /* ignore */ }
      throw new Error(msg);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  }

  // ---------------------------------------------------------------
  // Auth
  // ---------------------------------------------------------------
  function switchScreen(name) {
    document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
    const el = $("#" + name);
    if (el) el.classList.add("active");
  }

  window.showLogin = () => { hide($("#register-form")); show($("#login-form")); };
  window.showRegister = () => { hide($("#login-form")); show($("#register-form")); };

  window.handleLogin = async () => {
    const email = $("#login-email").value.trim();
    const password = $("#login-password").value;
    if (!email || !password) return toast("Fill in all fields", "error");
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      token = data.token;
      localStorage.setItem("asb_token", token);
      currentUser = data.user;
      enterDashboard();
    } catch (e) { toast(e.message, "error"); }
  };

  window.handleRegister = async () => {
    const full_name = $("#reg-name").value.trim();
    const email = $("#reg-email").value.trim();
    const password = $("#reg-password").value;
    if (!email || !password) return toast("Email and password required", "error");
    try {
      const data = await api("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, full_name }),
      });
      token = data.token;
      localStorage.setItem("asb_token", token);
      currentUser = data.user;
      toast("Account created!", "success");
      enterDashboard();
    } catch (e) { toast(e.message, "error"); }
  };

  window.handleLogout = () => {
    token = "";
    currentUser = null;
    localStorage.removeItem("asb_token");
    switchScreen("auth-screen");
  };

  async function enterDashboard() {
    if (!currentUser) {
      try {
        currentUser = await api("/api/auth/me");
      } catch (_e) {
        window.handleLogout();
        return;
      }
    }
    $("#user-name").textContent = currentUser.full_name || currentUser.email;
    switchScreen("dashboard");
    loadProjects();
  }

  // ---------------------------------------------------------------
  // Projects
  // ---------------------------------------------------------------
  window.loadProjects = async () => {
    const list = $("#projects-list");
    list.innerHTML = "<p class='hint'>Loading …</p>";
    try {
      const data = await api("/api/projects");
      if (!data.projects.length) {
        list.innerHTML = "<p class='hint'>No projects yet. Create your first one above.</p>";
        return;
      }
      list.innerHTML = data.projects
        .map((p) => {
          const badgeClass = p.status === "generated" ? "badge-generated" : "badge-draft";
          return `<div class="list-item" data-id="${p.id}" data-name="${esc(p.name)}" data-goal="${esc(p.goal || "")}">
            <div class="list-item-info">
              <strong>${esc(p.name)}</strong>
              <small>${esc(p.goal || "")}</small>
            </div>
            <span class="badge ${badgeClass}">${esc(p.status)}</span>
          </div>`;
        })
        .join("");
      list.querySelectorAll(".list-item").forEach((el) => {
        el.addEventListener("click", () => {
          selectProject(Number(el.dataset.id), el.dataset.name, el.dataset.goal);
        });
      });
    } catch (e) {
      list.innerHTML = "<p class='hint'>Failed to load projects.</p>";
    }
  };

  window.createProject = async () => {
    const name = $("#proj-name").value.trim();
    const goal = $("#proj-goal").value.trim();
    const audience = $("#proj-audience").value.trim();
    if (!name || !goal) return toast("Name and goal are required", "error");
    try {
      const data = await api("/api/projects", {
        method: "POST",
        body: JSON.stringify({ name, goal, audience }),
      });
      toast("Project created!", "success");
      $("#proj-name").value = "";
      $("#proj-goal").value = "";
      $("#proj-audience").value = "";
      selectProject(data.id, name, goal);
      loadProjects();
    } catch (e) { toast(e.message, "error"); }
  };

  function selectProject(id, name, goal) {
    currentProjectId = id;
    pipelineData = {};
    const section = $("#pipeline-section");
    show(section);
    $("#pipeline-project-name").textContent = name + (goal ? " — " + goal : "");
    ["refine", "plan", "generate", "export"].forEach((s) => {
      $("#status-" + s).textContent = "";
    });
    hide($("#pipeline-output"));
    section.scrollIntoView({ behavior: "smooth" });
  };

  // ---------------------------------------------------------------
  // Pipeline
  // ---------------------------------------------------------------
  function showOutput(data) {
    const out = $("#pipeline-output");
    show(out);
    $("#pipeline-pre").textContent = JSON.stringify(data, null, 2);
  }

  window.runRefine = async () => {
    if (!currentProjectId) return toast("Select a project first", "error");
    const goal = $("#proj-goal").value.trim() || $("#pipeline-project-name").textContent;
    $("#status-refine").textContent = "⏳";
    try {
      const data = await api("/api/refine-prompt", {
        method: "POST",
        body: JSON.stringify({ prompt: goal, project_id: currentProjectId }),
      });
      pipelineData.refined = data.refined;
      $("#status-refine").textContent = "✅";
      showOutput(data.refined);
      toast("Prompt refined", "success");
    } catch (e) { $("#status-refine").textContent = "❌"; toast(e.message, "error"); }
  };

  window.runPlan = async () => {
    if (!pipelineData.refined) return toast("Run Refine first", "error");
    $("#status-plan").textContent = "⏳";
    try {
      const data = await api("/api/generate-plan", {
        method: "POST",
        body: JSON.stringify({ refined_spec: pipelineData.refined, project_id: currentProjectId }),
      });
      pipelineData.plan = data.plan;
      $("#status-plan").textContent = "✅";
      showOutput(data.plan);
      toast("Plan generated", "success");
    } catch (e) { $("#status-plan").textContent = "❌"; toast(e.message, "error"); }
  };

  window.runGenerate = async () => {
    if (!pipelineData.plan || !pipelineData.refined) return toast("Run Refine & Plan first", "error");
    $("#status-generate").textContent = "⏳";
    try {
      const data = await api("/api/generate-system", {
        method: "POST",
        body: JSON.stringify({ plan: pipelineData.plan, refined_spec: pipelineData.refined, project_id: currentProjectId }),
      });
      $("#status-generate").textContent = "✅";
      showOutput(data);
      toast("System generated!", "success");
      loadProjects();
    } catch (e) { $("#status-generate").textContent = "❌"; toast(e.message, "error"); }
  };

  window.runExport = async () => {
    if (!currentProjectId) return toast("Select a project first", "error");
    $("#status-export").textContent = "⏳";
    try {
      const res = await fetch("/api/projects/" + currentProjectId + "/export", {
        headers: { Authorization: "Bearer " + token },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: "Export failed" }));
        throw new Error(err.error);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "project.zip";
      a.click();
      URL.revokeObjectURL(url);
      $("#status-export").textContent = "✅";
      toast("Downloaded!", "success");
    } catch (e) { $("#status-export").textContent = "❌"; toast(e.message, "error"); }
  };

  // ---------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ---------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------
  if (token) {
    enterDashboard();
  } else {
    switchScreen("auth-screen");
  }
})();
