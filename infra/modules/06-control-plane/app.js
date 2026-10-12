// Configuration
// In both local development (via serve_control_panel.py) and production (via CloudFront /api routing),
// all administrative actions and telemetry queries are routed to /api.
const API_BASE = "/api";

let allTenants = [];
let storageChart = null;
let healthChart = null;
let ecsStreamChart = null;
let albStreamChart = null;
let auditLogs = [];

// Streaming Telemetry State
let streamIntervalSeconds = 15;
let remainingCountdown = 15;
let streamTickerTimer = null;
let isStreamPaused = false;

// MFA Challenge State
let pendingChallengeToken = null;
let pendingMfaUser = null;
let pendingMfaRole = null;
let pendingMfaSecret = null;

// ==========================================
// 1. AUTHENTICATION, MFA & RBAC SESSION
// ==========================================
function getAuthHeaders() {
  const token = sessionStorage.getItem("saas_admin_token");
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

function handleUnauthorized() {
  sessionStorage.removeItem("saas_admin_token");
  sessionStorage.removeItem("saas_admin_email");
  sessionStorage.removeItem("saas_admin_role");
  if (streamTickerTimer) clearInterval(streamTickerTimer);
  document.getElementById("loginScreen")?.classList.remove("d-none");
  document.getElementById("appContainer")?.classList.add("d-none");
  const alertBox = document.getElementById("loginAlert");
  if (alertBox) {
    alertBox.innerText = "Session expired or unauthorized. Please sign in.";
    alertBox.classList.remove("d-none");
  }
}

function checkSession() {
  const token = sessionStorage.getItem("saas_admin_token");
  const userEmail = sessionStorage.getItem("saas_admin_email");
  const userRole = sessionStorage.getItem("saas_admin_role") || "SuperAdmin";
  if (token) {
    document.getElementById("loginScreen")?.classList.add("d-none");
    document.getElementById("appContainer")?.classList.remove("d-none");
    const userDisp = document.getElementById("adminUserDisplay");
    if (userDisp)
      userDisp.innerText = userEmail ? userEmail.split("@")[0] : "admin";
    const emailDisp = document.getElementById("dropdownUserEmail");
    if (emailDisp) emailDisp.innerText = userEmail || "admin@png261.dev";
    applyRbacPermissions(userRole);
    loadTenants();
    renderAuditTrail();
  } else {
    document.getElementById("loginScreen")?.classList.remove("d-none");
    document.getElementById("appContainer")?.classList.add("d-none");
  }
}

function fillPersona(type) {
  const emailInput = document.getElementById("loginEmail");
  const passInput = document.getElementById("loginPassword");
  if (!emailInput || !passInput) return;
  if (type === "admin") {
    emailInput.value = "admin@png261.dev";
    passInput.value = "AdminPassword123!";
  } else if (type === "ops") {
    emailInput.value = "ops@png261.dev";
    passInput.value = "OperatorPassword123!";
  } else if (type === "auditor") {
    emailInput.value = "auditor@png261.dev";
    passInput.value = "AuditorPassword123!";
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value.trim();
  const alertBox = document.getElementById("loginAlert");
  const submitBtn = document.getElementById("btnLoginSubmit");

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML =
      '<span class="spinner-border spinner-border-sm me-1"></span> Verifying...';
  }

  try {
    const res = await fetch(API_BASE || "/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "LOGIN",
        username: email,
        password: password,
      }),
    });
    const data = await res.json();
    if (res.ok && data.status === "MFA_REQUIRED") {
      // Transition to Step 2 TOTP verification
      pendingChallengeToken = data.challenge_token;
      pendingMfaUser = data.user || email;
      pendingMfaRole = data.role || "SuperAdmin";
      pendingMfaSecret =
        data.demo_totp_secret || "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP";

      document.getElementById("loginStep1")?.classList.add("d-none");
      document.getElementById("loginStep2")?.classList.remove("d-none");
      alertBox.classList.add("d-none");

      const uDisp = document.getElementById("mfaUserDisplay");
      if (uDisp) uDisp.innerText = pendingMfaUser;
      const rBadge = document.getElementById("mfaRoleBadge");
      if (rBadge) {
        rBadge.innerText = pendingMfaRole;
        rBadge.className = `badge ${pendingMfaRole === "SuperAdmin" ? "bg-danger" : pendingMfaRole === "TenantOperator" ? "bg-primary" : "bg-warning text-dark"}`;
      }
      const secDisp = document.getElementById("demoMfaSecret");
      if (secDisp) secDisp.innerText = pendingMfaSecret;

      const mfaInput = document.getElementById("loginMfaCode");
      if (mfaInput) {
        mfaInput.value = "";
        mfaInput.focus();
      }
    } else if (res.ok && data.token) {
      sessionStorage.setItem("saas_admin_token", data.token);
      sessionStorage.setItem("saas_admin_email", email);
      sessionStorage.setItem("saas_admin_role", data.role || "SuperAdmin");
      alertBox.classList.add("d-none");
      checkSession();
    } else {
      alertBox.innerText =
        data.error || "Authentication failed. Invalid master credentials.";
      alertBox.classList.remove("d-none");
    }
  } catch (err) {
    alertBox.innerText = "Network or server error: " + err.message;
    alertBox.classList.remove("d-none");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML =
        '<i class="bi bi-box-arrow-in-right me-1"></i> Sign In to Control Panel';
    }
  }
}

function cancelMfaStep() {
  pendingChallengeToken = null;
  pendingMfaSecret = null;
  document.getElementById("loginStep2")?.classList.add("d-none");
  document.getElementById("loginStep1")?.classList.remove("d-none");
  const alertBox = document.getElementById("loginAlert");
  if (alertBox) alertBox.classList.add("d-none");
}

function copyDemoSecret() {
  if (pendingMfaSecret) {
    navigator.clipboard.writeText(pendingMfaSecret).then(() => {
      showToast("Authenticator secret copied to clipboard");
    });
  }
}

async function generateTotpCodeBrowser(secretBase32) {
  try {
    const cleanSecret = secretBase32.replace(/[\s=]/g, "").toUpperCase();
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    let bits = "";
    for (let i = 0; i < cleanSecret.length; i++) {
      const val = alphabet.indexOf(cleanSecret.charAt(i));
      if (val === -1) continue;
      bits += val.toString(2).padStart(5, "0");
    }
    const bytes = new Uint8Array(Math.floor(bits.length / 8));
    for (let i = 0; i < bytes.length; i++) {
      bytes[i] = parseInt(bits.substr(i * 8, 8), 2);
    }
    const key = await crypto.subtle.importKey(
      "raw",
      bytes,
      { name: "HMAC", hash: "SHA-1" },
      false,
      ["sign"],
    );
    const epoch = Math.floor(Date.now() / 1000);
    const counter = Math.floor(epoch / 30);
    const counterBuffer = new ArrayBuffer(8);
    const counterView = new DataView(counterBuffer);
    counterView.setUint32(4, counter, false);
    const sig = await crypto.subtle.sign("HMAC", key, counterBuffer);
    const sigBytes = new Uint8Array(sig);
    const offset = sigBytes[sigBytes.length - 1] & 0x0f;
    const codeVal =
      (((sigBytes[offset] & 0x7f) << 24) |
        ((sigBytes[offset + 1] & 0xff) << 16) |
        ((sigBytes[offset + 2] & 0xff) << 8) |
        (sigBytes[offset + 3] & 0xff)) %
      1000000;
    return codeVal.toString().padStart(6, "0");
  } catch (err) {
    console.error("Browser TOTP computation error:", err);
    return null;
  }
}

async function autofillTotpCode() {
  if (!pendingMfaSecret) return;
  const code = await generateTotpCodeBrowser(pendingMfaSecret);
  if (code) {
    const input = document.getElementById("loginMfaCode");
    if (input) {
      input.value = code;
      input.focus();
    }
    showToast(`Generated RFC 6238 TOTP Code: ${code}`);
  }
}

async function handleMfaSubmit(e) {
  e.preventDefault();
  const code = document.getElementById("loginMfaCode").value.trim();
  const alertBox = document.getElementById("loginAlert");
  const submitBtn = document.getElementById("btnMfaSubmit");

  if (!code || code.length !== 6) {
    alertBox.innerText = "Please enter a valid 6-digit code.";
    alertBox.classList.remove("d-none");
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML =
      '<span class="spinner-border spinner-border-sm me-1"></span> Verifying Code...';
  }

  try {
    const res = await fetch(API_BASE || "/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "VERIFY_MFA",
        challenge_token: pendingChallengeToken,
        mfa_code: code,
      }),
    });
    const data = await res.json();
    if (res.ok && data.token) {
      sessionStorage.setItem("saas_admin_token", data.token);
      sessionStorage.setItem("saas_admin_email", data.user || pendingMfaUser);
      sessionStorage.setItem("saas_admin_role", data.role || pendingMfaRole);
      alertBox.classList.add("d-none");
      cancelMfaStep();
      checkSession();
    } else {
      alertBox.innerText =
        data.error || "Verification failed. Invalid or expired TOTP code.";
      alertBox.classList.remove("d-none");
    }
  } catch (err) {
    alertBox.innerText = "Network error: " + err.message;
    alertBox.classList.remove("d-none");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML =
        '<i class="bi bi-check2-circle me-1"></i> Verify &amp; Sign In';
    }
  }
}

function applyRbacPermissions(role) {
  const roleBadge = document.getElementById("adminRoleBadge");
  const roleText = document.getElementById("dropdownUserRole");
  const provisionBtn = document.getElementById("btnProvisionTrigger");
  const auditorNotice = document.getElementById("auditorRestrictedNotice");

  if (roleBadge) {
    roleBadge.innerText = role;
    if (role === "SuperAdmin") {
      roleBadge.className = "badge bg-danger ms-2";
      roleBadge.innerHTML =
        '<i class="bi bi-shield-shaded me-1"></i>SuperAdmin';
    } else if (role === "TenantOperator") {
      roleBadge.className = "badge bg-primary ms-2";
      roleBadge.innerHTML = '<i class="bi bi-tools me-1"></i>TenantOperator';
    } else {
      roleBadge.className = "badge bg-warning text-dark ms-2";
      roleBadge.innerHTML = '<i class="bi bi-eye me-1"></i>SecurityAuditor';
    }
  }

  if (roleText) {
    roleText.innerText = `Role: ${role} (${role === "SuperAdmin" ? "Full Control" : role === "TenantOperator" ? "Operations Only" : "Read-Only Audit"})`;
  }

  if (role === "SecurityAuditor") {
    if (provisionBtn) provisionBtn.classList.add("d-none");
    if (auditorNotice) auditorNotice.classList.remove("d-none");
  } else {
    if (provisionBtn) provisionBtn.classList.remove("d-none");
    if (auditorNotice) auditorNotice.classList.add("d-none");
  }
}

function handleLogout() {
  sessionStorage.removeItem("saas_admin_token");
  sessionStorage.removeItem("saas_admin_email");
  sessionStorage.removeItem("saas_admin_role");
  if (streamTickerTimer) clearInterval(streamTickerTimer);
  checkSession();
}

// ==========================================
// 2. TAB SWITCHING
// ==========================================
function switchTab(tab) {
  const tenantsView = document.getElementById("tenantsTabView");
  const cwView = document.getElementById("cloudwatchTabView");
  const tenantsBtn = document.getElementById("tab-tenants-btn");
  const cwBtn = document.getElementById("tab-cloudwatch-btn");

  if (tab === "cloudwatch") {
    tenantsView.classList.add("d-none");
    cwView.classList.remove("d-none");
    tenantsBtn.classList.remove("active");
    cwBtn.classList.add("active");

    // Start streaming & load widgets
    initCloudWatchStream();
    loadAllCloudWatchWidgets();
  } else {
    cwView.classList.add("d-none");
    tenantsView.classList.remove("d-none");
    cwBtn.classList.remove("active");
    tenantsBtn.classList.add("active");
  }
}

// ==========================================
// 3. IMMUTABLE DYNAMODB AUDIT TRAIL
// ==========================================
async function renderAuditTrail() {
  const tbody = document.getElementById("auditTrailBody");
  if (!tbody) return;

  try {
    const headers = getAuthHeaders();
    const res = await fetch(API_BASE || "/", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({ action: "AUDIT_LOGS" }),
    });
    if (res.status === 401) {
      handleUnauthorized();
      return;
    }
    if (res.ok) {
      const data = await res.json();
      const logs = data.audit_logs || [];
      if (!logs.length) {
        tbody.innerHTML =
          '<tr><td colspan="7" class="text-muted text-center py-3">No audit records found in DynamoDB.</td></tr>';
        return;
      }
      tbody.innerHTML = logs
        .map((log) => {
          const ts = (log.timestamp || "").replace("T", " ").substring(0, 19);
          const roleBadge =
            log.role === "SuperAdmin"
              ? `<span class="badge bg-danger-subtle text-danger border border-danger-subtle">${log.role}</span>`
              : log.role === "TenantOperator"
                ? `<span class="badge bg-primary-subtle text-primary border border-primary-subtle">${log.role}</span>`
                : `<span class="badge bg-warning-subtle text-dark border border-warning-subtle">${log.role || "Auditor"}</span>`;

          const outcomeBadge =
            log.status === "SUCCESS"
              ? `<span class="badge bg-success-subtle text-success border border-success-subtle"><i class="bi bi-check-circle me-1"></i>SUCCESS</span>`
              : log.status === "DENIED"
                ? `<span class="badge bg-warning-subtle text-warning border border-warning-subtle"><i class="bi bi-shield-x me-1"></i>DENIED</span>`
                : `<span class="badge bg-danger-subtle text-danger border border-danger-subtle"><i class="bi bi-x-circle me-1"></i>FAILED</span>`;

          let actionBadge = `<span class="badge bg-secondary font-monospace">${log.action}</span>`;
          if (log.action.includes("LOGIN") || log.action.includes("MFA")) {
            actionBadge = `<span class="badge bg-info-subtle text-info border border-info-subtle font-monospace">${log.action}</span>`;
          } else if (log.action.includes("PROVISION")) {
            actionBadge = `<span class="badge bg-success-subtle text-success border border-success-subtle font-monospace">${log.action}</span>`;
          } else if (log.action.includes("SUSPEND")) {
            actionBadge = `<span class="badge bg-warning-subtle text-warning border border-warning-subtle font-monospace">${log.action}</span>`;
          } else if (log.action.includes("DELETE")) {
            actionBadge = `<span class="badge bg-danger-subtle text-danger border border-danger-subtle font-monospace">${log.action}</span>`;
          }

          return `
                    <tr>
                        <td class="text-muted small font-monospace">${ts}</td>
                        <td>${actionBadge}</td>
                        <td><code class="fw-semibold text-dark">${log.target || "system"}</code></td>
                        <td><small>${log.actor || "anonymous"}</small></td>
                        <td>${roleBadge}</td>
                        <td>${outcomeBadge}</td>
                        <td class="font-monospace small text-muted">${log.ip_address || "127.0.0.1"}</td>
                    </tr>
                `;
        })
        .join("");
    } else {
      tbody.innerHTML =
        '<tr><td colspan="7" class="text-warning text-center py-2"><i class="bi bi-exclamation-triangle me-1"></i>Failed to fetch audit records from server.</td></tr>';
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-danger text-center py-2">Error loading audit trail: ${err.message}</td></tr>`;
  }
}

// ==========================================
// 4. TENANT MANAGEMENT & DYNAMODB API
// ==========================================
async function loadTenants() {
  try {
    const headers = getAuthHeaders();
    headers["Accept"] = "application/json";
    const res = await fetch(API_BASE || "/", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({ action: "LIST" }),
    });
    if (res.status === 401) {
      handleUnauthorized();
      return;
    }
    const data = await res.json();
    allTenants = data.tenants || [];
    updateMetrics();
    filterTenants();
    updateTenantCharts();
    showToast("Tenant registry synchronized with DynamoDB");
  } catch (err) {
    console.error("Failed to load tenants:", err);
    showToast("Error loading tenants: " + err.message, true);
  }
}

function updateMetrics() {
  const total = allTenants.length;
  const active = allTenants.filter((t) => t.status === "ACTIVE").length;
  const suspended = allTenants.filter((t) => t.status === "SUSPENDED").length;
  const totalQuota = allTenants.reduce(
    (sum, t) => sum + (parseInt(t.quota_gb) || 0),
    0,
  );

  document.getElementById("kpiTotal").innerText = total;
  document.getElementById("kpiActive").innerText = active;
  document.getElementById("kpiSuspended").innerText = suspended;
  document.getElementById("kpiQuota").innerText = totalQuota;
}

function filterTenants() {
  const search = document.getElementById("searchInput").value.toLowerCase();
  const status = document.getElementById("statusFilter").value;

  const filtered = allTenants.filter((t) => {
    const matchesSearch =
      (t.tenant_id && t.tenant_id.toLowerCase().includes(search)) ||
      (t.domain && t.domain.toLowerCase().includes(search)) ||
      (t.admin_email && t.admin_email.toLowerCase().includes(search));

    const matchesStatus = status === "ALL" || t.status === status;
    return matchesSearch && matchesStatus;
  });

  renderTenantTable(filtered);
}

function renderTenantTable(tenants) {
  const tbody = document.getElementById("tenantTableBody");
  if (!tenants.length) {
    tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center py-5 text-muted">
                    <i class="bi bi-inbox fs-1 d-block mb-2 text-secondary"></i>
                    No tenants match your search criteria.
                </td>
            </tr>
        `;
    return;
  }

  tbody.innerHTML = tenants
    .map((t) => {
      const tid = t.tenant_id;
      const domain = t.domain || `${tid}.png261.dev`;
      const email = t.admin_email || `admin@${tid}.com`;
      const quota = t.quota_gb || 100;
      const status = t.status || "ACTIVE";
      const updated = (t.last_updated || "").replace("T", " ").substring(0, 19);

      const svcName = t.service_name || `service-${tid}`;
      const dbName = t.database_name || `nc_${tid.replace(/-/g, "_")}`;
      const apId = t.efs_access_point_id
        ? `<span class="badge bg-secondary-subtle text-secondary font-monospace" style="font-size: 0.7rem;"><i class="bi bi-hdd-fill me-1"></i>${t.efs_access_point_id}</span>`
        : `<span class="badge bg-light text-muted font-monospace" style="font-size: 0.7rem;">/tenants/${tid}/config</span>`;

      const containerBadge =
        status === "ACTIVE"
          ? `<div class="d-flex flex-column gap-1">
                <span class="badge bg-success-subtle text-success border border-success-subtle font-monospace text-start">
                    <i class="bi bi-cpu-fill me-1"></i> ${svcName} (1 task)
                </span>
                <span class="badge bg-info-subtle text-info border border-info-subtle font-monospace text-start">
                    <i class="bi bi-database me-1"></i> ${dbName}
                </span>
                ${apId}
               </div>`
          : `<div class="d-flex flex-column gap-1">
                <span class="badge bg-secondary-subtle text-muted border font-monospace text-start">
                    <i class="bi bi-pause-fill me-1"></i> ${svcName} (0 tasks / $0)
                </span>
                <span class="badge bg-info-subtle text-info border border-info-subtle font-monospace text-start">
                    <i class="bi bi-database me-1"></i> ${dbName}
                </span>
                ${apId}
               </div>`;

      const statusBadge =
        status === "ACTIVE"
          ? `<span class="badge bg-success-subtle text-success border border-success-subtle"><i class="bi bi-check-circle-fill me-1"></i>ACTIVE</span>`
          : `<span class="badge bg-warning-subtle text-warning border border-warning-subtle"><i class="bi bi-pause-circle-fill me-1"></i>SUSPENDED</span>`;

      const role = sessionStorage.getItem("saas_admin_role") || "SuperAdmin";
      let actionButtons = "";

      if (role === "SecurityAuditor") {
        actionButtons = `<span class="badge bg-light text-muted border py-1 px-2" title="Mutations disabled for SecurityAuditor"><i class="bi bi-eye me-1"></i>Read Only</span>`;
      } else if (role === "TenantOperator") {
        const toggleBtn =
          status === "ACTIVE"
            ? `<button class="btn btn-sm btn-outline-warning me-1" onclick="toggleTenantStatus('${tid}', 'SUSPEND')" title="Suspend (0 tasks / FinOps $0)"><i class="bi bi-pause-fill"></i> Suspend</button>`
            : `<button class="btn btn-sm btn-outline-success me-1" onclick="toggleTenantStatus('${tid}', 'RESUME')" title="Resume (1 task)"><i class="bi bi-play-fill"></i> Resume</button>`;
        const deleteBtn = `<button class="btn btn-sm btn-outline-secondary disabled ms-1" title="Delete restricted to SuperAdmin role" disabled><i class="bi bi-lock-fill"></i></button>`;
        actionButtons = toggleBtn + deleteBtn;
      } else {
        // SuperAdmin
        const toggleBtn =
          status === "ACTIVE"
            ? `<button class="btn btn-sm btn-outline-warning me-1" onclick="toggleTenantStatus('${tid}', 'SUSPEND')" title="Suspend (0 tasks / FinOps $0)"><i class="bi bi-pause-fill"></i> Suspend</button>`
            : `<button class="btn btn-sm btn-outline-success me-1" onclick="toggleTenantStatus('${tid}', 'RESUME')" title="Resume (1 task)"><i class="bi bi-play-fill"></i> Resume</button>`;
        const deleteBtn = `<button class="btn btn-sm btn-outline-danger ms-1" onclick="deleteTenant('${tid}')" title="Permanently delete tenant"><i class="bi bi-trash"></i></button>`;
        actionButtons = toggleBtn + deleteBtn;
      }

      return `
            <tr>
                <td class="ps-3">
                    <div class="fw-bold">${tid}</div>
                    <small class="text-muted">Partition: HASH</small>
                </td>
                <td>
                    <div>
                        <a href="https://${domain}" target="_blank" class="domain-link fw-bold text-decoration-none">
                            ${domain} <i class="bi bi-box-arrow-up-right small"></i>
                        </a>
                    </div>
                    <div class="mt-1">
                        <span class="badge bg-light text-secondary border font-monospace" style="font-size: 0.7rem;" title="Admin credentials stored securely in AWS Secrets Manager">
                            <i class="bi bi-shield-lock-fill text-warning me-1"></i>AWS Secrets Manager
                        </span>
                    </div>
                </td>
                <td>${email}</td>
                <td><span class="badge bg-light text-dark border">${quota} GB</span></td>
                <td>${statusBadge}</td>
                <td>${containerBadge}</td>
                <td class="text-muted small">${updated} UTC</td>
                <td class="text-end pe-3">
                    ${actionButtons}
                </td>
            </tr>
        `;
    })
    .join("");
}

// ==========================================
// 5. ACTION HANDLERS
// ==========================================
async function toggleTenantStatus(tid, action) {
  const verb = action === "SUSPEND" ? "Suspend" : "Resume";
  if (!confirm(`Are you sure you want to ${verb} tenant "${tid}"?`)) return;

  try {
    const res = await fetch(API_BASE || "/", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ action, tenant_id: tid }),
    });
    if (res.status === 401) {
      handleUnauthorized();
      return;
    }
    const data = await res.json();
    if (res.status === 403) {
      showToast(`⚠️ Forbidden: ${data.error || "Lacks RBAC permission"}`, true);
      renderAuditTrail();
      return;
    }
    if (res.ok) {
      showToast(
        `Tenant ${tid} successfully ${action === "SUSPEND" ? "suspended" : "resumed"}!`,
      );
      loadTenants();
      renderAuditTrail();
    } else {
      showToast(data.error || "Action failed", true);
      renderAuditTrail();
    }
  } catch (err) {
    showToast("Network error: " + err.message, true);
  }
}

async function deleteTenant(tid) {
  if (!confirm(`⚠️ DANGER: Permanently delete tenant "${tid}" from registry?`))
    return;

  try {
    const res = await fetch(API_BASE || "/", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ action: "DELETE", tenant_id: tid }),
    });
    if (res.status === 401) {
      handleUnauthorized();
      return;
    }
    const data = await res.json();
    if (res.status === 403) {
      showToast(
        `⚠️ Forbidden: ${data.error || "Lacks RBAC permission to delete"}`,
        true,
      );
      renderAuditTrail();
      return;
    }
    if (res.ok) {
      showToast(`Tenant ${tid} deleted from registry.`);
      loadTenants();
      renderAuditTrail();
    } else {
      showToast(data.error || "Delete failed", true);
      renderAuditTrail();
    }
  } catch (err) {
    showToast("Network error: " + err.message, true);
  }
}

async function handleProvisionSubmit(e) {
  e.preventDefault();
  const tid = document
    .getElementById("formTenantId")
    .value.trim()
    .toLowerCase();
  const domain =
    document.getElementById("formDomain").value.trim() || `${tid}.png261.dev`;
  const email = document.getElementById("formEmail").value.trim();
  const quota = parseInt(document.getElementById("formQuota").value) || 100;

  const btn = document.getElementById("btnSubmitProvision");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Provisioning...`;

  try {
    const res = await fetch(API_BASE || "/", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({
        action: "PROVISION",
        tenant_id: tid,
        domain: domain,
        admin_email: email,
        quota_gb: quota,
      }),
    });
    if (res.status === 401) {
      handleUnauthorized();
      return;
    }
    const data = await res.json();
    if (res.status === 403) {
      showToast(
        `⚠️ Forbidden: ${data.error || "Lacks RBAC permission to provision"}`,
        true,
      );
      renderAuditTrail();
      return;
    }
    if (res.ok) {
      showToast(`🎉 Dedicated tenant "${tid}" successfully provisioned!`);
      const modalEl = document.getElementById("provisionModal");
      const modal = bootstrap.Modal.getInstance(modalEl);
      if (modal) modal.hide();
      document.getElementById("provisionForm").reset();
      loadTenants();
      renderAuditTrail();
    } else {
      showToast(data.error || "Provisioning failed", true);
      renderAuditTrail();
    }
  } catch (err) {
    showToast("Network error: " + err.message, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="bi bi-cpu me-1"></i> Launch Tenant Instance`;
  }
}

// ==========================================
// 6. TENANT OVERVIEW CHARTS
// ==========================================
function updateTenantCharts() {
  const ctxStorage = document.getElementById("storageChart")?.getContext("2d");
  if (ctxStorage) {
    const labels = allTenants.map((t) => t.tenant_id);
    const dataQuota = allTenants.map((t) => parseInt(t.quota_gb) || 100);

    if (storageChart) storageChart.destroy();
    storageChart = new Chart(ctxStorage, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Storage Quota (GB)",
            data: dataQuota,
            backgroundColor: "#0073bb",
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            title: { display: true, text: "Gigabytes (GB)" },
          },
        },
      },
    });
  }

  const ctxHealth = document.getElementById("healthChart")?.getContext("2d");
  if (ctxHealth) {
    const activeCount = allTenants.filter((t) => t.status === "ACTIVE").length;
    const suspendedCount = allTenants.filter(
      (t) => t.status === "SUSPENDED",
    ).length;

    if (healthChart) healthChart.destroy();
    healthChart = new Chart(ctxHealth, {
      type: "doughnut",
      data: {
        labels: ["Active", "Suspended"],
        datasets: [
          {
            data: [activeCount, suspendedCount],
            backgroundColor: ["#1d8102", "#d13212"],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" },
        },
      },
    });
  }
}

// ==========================================
// 7. REAL-TIME CLOUDWATCH TELEMETRY STREAMING
// ==========================================
function initCloudWatchStream() {
  if (streamTickerTimer) return; // already active
  streamCloudWatchMetrics();
  remainingCountdown = streamIntervalSeconds;

  streamTickerTimer = setInterval(() => {
    if (isStreamPaused) return;

    remainingCountdown--;
    const countdownEl = document.getElementById("streamCountdown");
    if (countdownEl) countdownEl.innerText = `${remainingCountdown}s`;

    if (remainingCountdown <= 0) {
      remainingCountdown = streamIntervalSeconds;
      streamCloudWatchMetrics();
    }
  }, 1000);
}

function handleIntervalChange(val) {
  const seconds = parseInt(val);
  const statusText = document.getElementById("streamStatusText");
  const liveDot = document.getElementById("liveDot");
  const countdownEl = document.getElementById("streamCountdown");

  if (seconds === 0) {
    isStreamPaused = true;
    if (statusText) statusText.innerText = "STREAMING PAUSED";
    if (liveDot) liveDot.classList.add("paused");
    if (countdownEl) countdownEl.innerText = "PAUSED";
  } else {
    isStreamPaused = false;
    streamIntervalSeconds = seconds;
    remainingCountdown = seconds;
    if (statusText) statusText.innerText = `STREAMING ACTIVE (${seconds}s)`;
    if (liveDot) liveDot.classList.remove("paused");
    if (countdownEl) countdownEl.innerText = `${seconds}s`;
    streamCloudWatchMetrics();
  }
}

function triggerManualMetricsRefresh() {
  streamCloudWatchMetrics();
  loadAllCloudWatchWidgets();
  if (!isStreamPaused) remainingCountdown = streamIntervalSeconds;
}

async function streamCloudWatchMetrics() {
  try {
    const res = await fetch(API_BASE || "/", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ action: "METRICS" }),
    });
    if (res.status === 401) {
      handleUnauthorized();
      return;
    }
    const data = await res.json();
    const metrics = data.metrics || {};

    renderEcsStreamChart(metrics.cpu_main, metrics.mem_main);
    renderAlbStreamChart(metrics.alb_req, metrics.alb_latency);

    const now = new Date();
    const lastEl = document.getElementById("lastStreamUpdate");
    if (lastEl) lastEl.innerText = now.toLocaleTimeString();
  } catch (err) {
    console.error("Telemetry streaming error:", err);
  }
}

function renderEcsStreamChart(cpuMetric, memMetric) {
  const ctx = document.getElementById("ecsStreamChart")?.getContext("2d");
  if (!ctx) return;

  const timestamps =
    cpuMetric && cpuMetric.timestamps && cpuMetric.timestamps.length
      ? cpuMetric.timestamps
      : [];
  const cpuVals =
    cpuMetric && cpuMetric.values && cpuMetric.values.length
      ? cpuMetric.values
      : [];
  const memVals =
    memMetric && memMetric.values && memMetric.values.length
      ? memMetric.values
      : [];

  // Update KPI indicators
  const lastCpu = cpuVals.length ? cpuVals[cpuVals.length - 1] : null;
  const lastMem = memVals.length ? memVals[memVals.length - 1] : null;
  const cpuDisp = document.getElementById("currentCpuVal");
  const memDisp = document.getElementById("currentMemVal");
  if (cpuDisp)
    cpuDisp.innerText =
      typeof lastCpu === "number"
        ? lastCpu.toFixed(1)
        : lastCpu !== null
          ? lastCpu
          : "--";
  if (memDisp)
    memDisp.innerText =
      typeof lastMem === "number"
        ? lastMem.toFixed(1)
        : lastMem !== null
          ? lastMem
          : "--";

  if (ecsStreamChart) {
    ecsStreamChart.data.labels = timestamps;
    ecsStreamChart.data.datasets[0].data = cpuVals;
    ecsStreamChart.data.datasets[1].data = memVals;
    ecsStreamChart.update("none"); // silent fast update
  } else {
    ecsStreamChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: timestamps,
        datasets: [
          {
            label: "CPU Utilization (%)",
            data: cpuVals,
            borderColor: "#ff7f0e",
            backgroundColor: "rgba(255, 127, 14, 0.1)",
            borderWidth: 2,
            tension: 0.3,
            fill: true,
          },
          {
            label: "Memory Utilization (%)",
            data: memVals,
            borderColor: "#1f77b4",
            backgroundColor: "rgba(31, 119, 180, 0.1)",
            borderWidth: 2,
            tension: 0.3,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "top", labels: { boxWidth: 12 } },
          tooltip: { enabled: true },
        },
        scales: {
          y: {
            beginAtZero: true,
            max: 100,
            title: { display: true, text: "Utilization %" },
          },
          x: {
            grid: { display: false },
          },
        },
      },
    });
  }
}

function renderAlbStreamChart(reqMetric, latencyMetric) {
  const ctx = document.getElementById("albStreamChart")?.getContext("2d");
  if (!ctx) return;

  const timestamps =
    reqMetric && reqMetric.timestamps && reqMetric.timestamps.length
      ? reqMetric.timestamps
      : [];
  const reqVals =
    reqMetric && reqMetric.values && reqMetric.values.length
      ? reqMetric.values
      : [];
  const latencyVals =
    latencyMetric && latencyMetric.values && latencyMetric.values.length
      ? latencyMetric.values
      : [];

  // Update KPI indicators
  const lastReq = reqVals.length ? reqVals[reqVals.length - 1] : null;
  const lastLatency = latencyVals.length
    ? latencyVals[latencyVals.length - 1]
    : null;
  const reqDisp = document.getElementById("currentReqVal");
  const latencyDisp = document.getElementById("currentLatencyVal");
  if (reqDisp)
    reqDisp.innerText =
      typeof lastReq === "number"
        ? Math.round(lastReq)
        : lastReq !== null
          ? lastReq
          : "--";
  if (latencyDisp)
    latencyDisp.innerText =
      typeof lastLatency === "number"
        ? lastLatency.toFixed(3)
        : lastLatency !== null
          ? lastLatency
          : "--";

  if (albStreamChart) {
    albStreamChart.data.labels = timestamps;
    albStreamChart.data.datasets[0].data = reqVals;
    albStreamChart.data.datasets[1].data = latencyVals;
    albStreamChart.update("none");
  } else {
    albStreamChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: timestamps,
        datasets: [
          {
            label: "Request Count (Sum)",
            data: reqVals,
            borderColor: "#9467bd",
            backgroundColor: "rgba(148, 103, 189, 0.1)",
            borderWidth: 2,
            yAxisID: "y",
            tension: 0.2,
            fill: true,
          },
          {
            label: "Response Latency (s)",
            data: latencyVals,
            borderColor: "#8c564b",
            backgroundColor: "rgba(140, 86, 75, 0.1)",
            borderWidth: 2,
            yAxisID: "y1",
            tension: 0.2,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "top", labels: { boxWidth: 12 } },
        },
        scales: {
          y: {
            type: "linear",
            display: true,
            position: "left",
            beginAtZero: true,
            title: { display: true, text: "Requests (Sum)" },
          },
          y1: {
            type: "linear",
            display: true,
            position: "right",
            beginAtZero: true,
            grid: { drawOnChartArea: false },
            title: { display: true, text: "Latency (s)" },
          },
          x: {
            grid: { display: false },
          },
        },
      },
    });
  }
}

// ==========================================
// 8. AWS NATIVE CLOUDWATCH WIDGETS
// ==========================================
async function loadCloudWatchWidget(widgetType) {
  const loader = document.getElementById(`loader-${widgetType}`);
  const img = document.getElementById(`widgetImg-${widgetType}`);
  if (loader) loader.classList.remove("d-none");
  if (img) img.classList.add("d-none");

  try {
    const res = await fetch(API_BASE || "/", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ action: "WIDGET", widget: widgetType }),
    });
    if (res.status === 401) {
      handleUnauthorized();
      return;
    }
    const data = await res.json();
    if (data.image_base64 && img) {
      img.src = `data:image/png;base64,${data.image_base64}`;
      img.onload = () => {
        if (loader) loader.classList.add("d-none");
        img.classList.remove("d-none");
      };
    } else {
      console.warn(`No image data for widget ${widgetType}`);
      if (loader) loader.classList.add("d-none");
    }
  } catch (err) {
    console.error(`Error loading widget ${widgetType}:`, err);
    if (loader) loader.classList.add("d-none");
  }
}

function loadAllCloudWatchWidgets() {
  loadCloudWatchWidget("saas_fleet");
  loadCloudWatchWidget("ecs_compute");
  loadCloudWatchWidget("alb_traffic");
}

function showToast(msg, isError = false) {
  const toastEl = document.getElementById("liveToast");
  const toastMsg = document.getElementById("toastMessage");
  if (toastMsg) toastMsg.innerText = msg;
  if (toastEl) {
    toastEl.className = `toast align-items-center text-bg-${isError ? "danger" : "primary"} border-0`;
    const toast = new bootstrap.Toast(toastEl, { delay: 3500 });
    toast.show();
  }
}

// Initialize on load
document.addEventListener("DOMContentLoaded", checkSession);
