(() => {
  "use strict";

  const TOKEN_KEY = "attendance_admin_token";
  const USER_KEY = "attendance_admin_user";
  const state = {
    token: localStorage.getItem(TOKEN_KEY) || "",
    user: readStoredUser(),
    employeesById: new Map(),
    currentView: "overview",
    clockWidgets: new Map(),
  };

  const titles = {
    overview: ["Overview", "Operational summary for attendance, leave, and payroll."],
    employees: ["Employees", "Manage active and inactive employee records."],
    register: ["Register Employee", "Create an employee record with face enrollment."],
    timeclock: ["Time Clock", "Daily face check-in and check-out for employees."],
    attendance: ["Attendance", "Review today's attendance rows."],
    leaves: ["Leaves", "Approve or reject employee leave requests."],
    payroll: ["Payroll", "Create and inspect monthly payroll runs."],
  };

  const els = {
    authPanel: document.getElementById("auth-panel"),
    workspace: document.getElementById("workspace"),
    loginForm: document.getElementById("login-form"),
    loginUsername: document.getElementById("login-username"),
    loginPassword: document.getElementById("login-password"),
    loginError: document.getElementById("login-error"),
    logoutButton: document.getElementById("logout-button"),
    sessionUser: document.getElementById("session-user"),
    pageTitle: document.getElementById("page-title"),
    pageSubtitle: document.getElementById("page-subtitle"),
    toast: document.getElementById("toast"),
    activeEmployees: document.getElementById("metric-active-employees"),
    presentToday: document.getElementById("metric-present-today"),
    pendingLeaves: document.getElementById("metric-pending-leaves"),
    overviewAttendance: document.getElementById("overview-attendance"),
    overviewLeaves: document.getElementById("overview-leaves"),
    employeesTable: document.getElementById("employees-table"),
    employeeForm: document.getElementById("employee-form"),
    employeeName: document.getElementById("employee-name"),
    employeeEmail: document.getElementById("employee-email"),
    employeePhone: document.getElementById("employee-phone"),
    employeeJoinDate: document.getElementById("employee-join-date"),
    employeeDepartment: document.getElementById("employee-department"),
    employeePosition: document.getElementById("employee-position"),
    employeeSalaryType: document.getElementById("employee-salary-type"),
    employeeBaseSalary: document.getElementById("employee-base-salary"),
    employeeBankAccount: document.getElementById("employee-bank-account"),
    employeeStatus: document.getElementById("employee-status"),
    employeeUsername: document.getElementById("employee-username"),
    employeeTempPassword: document.getElementById("employee-temp-password"),
    employeeFaceImage: document.getElementById("employee-face-image"),
    employeeFormError: document.getElementById("employee-form-error"),
    faceVideo: document.getElementById("face-video"),
    faceCanvas: document.getElementById("face-canvas"),
    facePreview: document.getElementById("face-preview"),
    facePlaceholder: document.getElementById("face-placeholder"),
    faceSharpToggle: document.getElementById("face-sharp-toggle"),
    startCameraButton: document.getElementById("start-camera-button"),
    captureFaceButton: document.getElementById("capture-face-button"),
    detectFaceButton: document.getElementById("detect-face-button"),
    faceQualityStatus: document.getElementById("face-quality-status"),
    attendanceTable: document.getElementById("attendance-table"),
    timeclockTable: document.getElementById("timeclock-table"),
    leavesTable: document.getElementById("leaves-table"),
    leaveStatusFilter: document.getElementById("leave-status-filter"),
    payrollForm: document.getElementById("payroll-form"),
    payrollMonth: document.getElementById("payroll-month"),
    payrollYear: document.getElementById("payroll-year"),
    payrollError: document.getElementById("payroll-error"),
    payrollResult: document.getElementById("payroll-result"),
    payrollReportForm: document.getElementById("payroll-report-form"),
    reportMonth: document.getElementById("report-month"),
    reportYear: document.getElementById("report-year"),
    payrollReportError: document.getElementById("payroll-report-error"),
    payrollReportSummary: document.getElementById("payroll-report-summary"),
    payrollAttendanceTable: document.getElementById("payroll-attendance-table"),
    payrollItemsTable: document.getElementById("payroll-items-table"),
    editModal: document.getElementById("edit-employee-modal"),
    editForm: document.getElementById("edit-employee-form"),
    editError: document.getElementById("edit-employee-error"),
    editId: document.getElementById("edit-employee-id"),
    editName: document.getElementById("edit-name"),
    editEmail: document.getElementById("edit-email"),
    editPhone: document.getElementById("edit-phone"),
    editDepartment: document.getElementById("edit-department"),
    editPosition: document.getElementById("edit-position"),
    editSalaryType: document.getElementById("edit-salary-type"),
    editBaseSalary: document.getElementById("edit-base-salary"),
    editBankAccount: document.getElementById("edit-bank-account"),
    editStatus: document.getElementById("edit-status"),
    leaveForm: document.getElementById("leave-form"),
    leaveEmployeeId: document.getElementById("leave-employee-id"),
    leaveType: document.getElementById("leave-type"),
    leaveStartDate: document.getElementById("leave-start-date"),
    leaveEndDate: document.getElementById("leave-end-date"),
    leaveReason: document.getElementById("leave-reason"),
    leaveFormError: document.getElementById("leave-form-error"),
    historyForm: document.getElementById("attendance-history-form"),
    historyEmployee: document.getElementById("history-employee-id"),
    historyMonth: document.getElementById("history-month"),
    historyYear: document.getElementById("history-year"),
    historyTable: document.getElementById("attendance-history-table"),
  };

  document.addEventListener("DOMContentLoaded", () => {
    initDates();
    bindEvents();
    renderShell();
    if (state.token) {
      loadInitialData();
    }
  });

  function bindEvents() {
    els.loginForm.addEventListener("submit", handleLogin);
    els.logoutButton.addEventListener("click", logout);
    els.employeeForm.addEventListener("submit", handleEmployeeCreate);
    els.employeeEmail.addEventListener("input", suggestEmployeeUsername);
    els.employeesTable.addEventListener("change", handleEmployeeFaceUpdate);
    els.employeeFaceImage.addEventListener("change", handleFaceFileChange);
    els.startCameraButton.addEventListener("click", toggleCamera);
    els.captureFaceButton.addEventListener("click", captureFaceImage);
    els.detectFaceButton.addEventListener("click", inspectSelectedFace);
    els.leaveStatusFilter.addEventListener("change", () => loadLeaves());
    els.payrollForm.addEventListener("submit", handlePayrollRun);
    els.payrollReportForm.addEventListener("submit", handlePayrollReport);
    els.leaveForm.addEventListener("submit", handleLeaveSubmit);
    els.editForm.addEventListener("submit", handleEditEmployeeSubmit);
    document.getElementById("close-edit-modal").addEventListener("click", closeEditModal);
    document.getElementById("cancel-edit-modal").addEventListener("click", closeEditModal);
    els.editModal.addEventListener("click", (e) => { if (e.target === els.editModal) closeEditModal(); });
    els.historyForm.addEventListener("submit", handleAttendanceHistory);
    setupClockWidget("public");
    setupClockWidget("admin");

    document.querySelectorAll("[data-view]").forEach((button) => {
      button.addEventListener("click", () => setView(button.dataset.view));
    });

    document.querySelectorAll("[data-view-jump]").forEach((button) => {
      button.addEventListener("click", () => setView(button.dataset.viewJump));
    });

    document.querySelectorAll("[data-refresh]").forEach((button) => {
      button.addEventListener("click", () => refresh(button.dataset.refresh));
    });

    els.leavesTable.addEventListener("click", (event) => {
      const button = event.target.closest("[data-leave-action]");
      if (!button) return;
      updateLeave(button.dataset.leaveAction, button.dataset.leaveId);
    });

    els.employeesTable.addEventListener("click", handleEmployeeTableClick);
  }

  function initDates() {
    const now = new Date();
    els.employeeJoinDate.value = now.toISOString().slice(0, 10);
    els.payrollMonth.value = String(now.getMonth() + 1);
    els.payrollYear.value = String(now.getFullYear());
    els.reportMonth.value = String(now.getMonth() + 1);
    els.reportYear.value = String(now.getFullYear());
    els.leaveStartDate.value = now.toISOString().slice(0, 10);
    els.leaveEndDate.value = now.toISOString().slice(0, 10);
    els.historyMonth.value = String(now.getMonth() + 1);
    els.historyYear.value = String(now.getFullYear());
  }

  async function handleLogin(event) {
    event.preventDefault();
    clearError(els.loginError);

    try {
      const response = await request("/api/auth/login", {
        method: "POST",
        auth: false,
        body: {
          username: els.loginUsername.value.trim(),
          password: els.loginPassword.value,
        },
      });

      state.token = response.data.access_token;
      state.user = {
        username: response.data.username,
        role: response.data.role,
      };
      localStorage.setItem(TOKEN_KEY, state.token);
      localStorage.setItem(USER_KEY, JSON.stringify(state.user));
      els.loginPassword.value = "";
      renderShell();
      await loadInitialData();
      showToast("Signed in");
    } catch (error) {
      showError(els.loginError, error.message);
    }
  }

  function logout() {
    stopCamera();
    stopClockCameras();
    state.token = "";
    state.user = null;
    state.employeesById.clear();
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    renderShell();
    showToast("Signed out");
  }

  function renderShell() {
    const signedIn = Boolean(state.token);
    els.authPanel.classList.toggle("hidden", signedIn);
    els.workspace.classList.toggle("hidden", !signedIn);
    els.logoutButton.classList.toggle("hidden", !signedIn);
    els.sessionUser.textContent = state.user
      ? `${state.user.username} (${state.user.role})`
      : "Not signed in";
  }

  async function loadInitialData() {
    try {
      await Promise.all([loadSummary(), loadEmployees(), loadAttendance(), loadLeaves()]);
      populateEmployeeDropdowns();
    } catch (error) {
      if (error.status === 401) {
        logout();
        showToast("Session expired");
        return;
      }
      showToast(error.message);
    }
  }

  async function refresh(resource) {
    try {
      if (resource === "employees") await loadEmployees();
      if (resource === "attendance") await loadAttendance();
      if (resource === "leaves") await loadLeaves();
      await loadSummary();
      showToast("Data refreshed");
    } catch (error) {
      showToast(error.message);
    }
  }

  function setView(view) {
    if (view !== "register") {
      stopCamera();
    }
    if (view !== "timeclock") {
      stopClockCamera("admin");
    }
    state.currentView = view;
    const [title, subtitle] = titles[view] || titles.overview;
    els.pageTitle.textContent = title;
    els.pageSubtitle.textContent = subtitle;

    document.querySelectorAll("[data-view]").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === view);
    });
    document.querySelectorAll(".view").forEach((section) => {
      section.classList.toggle("active", section.id === `view-${view}`);
    });
  }

  async function loadSummary() {
    const response = await request("/api/dashboard/summary");
    const data = response.data || {};
    els.activeEmployees.textContent = data.active_employees ?? 0;
    els.presentToday.textContent = data.present_today ?? 0;
    els.pendingLeaves.textContent = data.pending_leaves ?? 0;
  }

  async function loadEmployees() {
    const response = await request("/api/employees");
    const employees = response.data || [];
    state.employeesById = new Map(employees.map((employee) => [String(employee.id), employee]));
    renderEmployees(employees);
    return employees;
  }

  async function loadAttendance() {
    const response = await request("/api/attendance/today");
    const rows = response.data || [];
    renderAttendance(rows);
    return rows;
  }

  async function loadLeaves() {
    const status = els.leaveStatusFilter.value;
    const path = status ? `/api/leaves?status=${encodeURIComponent(status)}` : "/api/leaves";
    const response = await request(path);
    const rows = response.data || [];
    renderLeaves(rows);
    return rows;
  }

  function renderEmployees(employees) {
    if (!employees.length) {
      els.employeesTable.innerHTML = emptyRow(7, "No employees found.");
      return;
    }

    els.employeesTable.innerHTML = employees.map((employee) => `
      <tr>
        <td>
          <strong>${escapeHtml(employee.name)}</strong><br>
          <span>${escapeHtml(employee.email)}</span>
        </td>
        <td>${escapeHtml(employee.department)}</td>
        <td>${escapeHtml(employee.position)}</td>
        <td>${money(employee.base_salary)}</td>
        <td>${statusPill(employee.status)}</td>
        <td>
          <label class="button secondary file-button compact" for="face-update-${escapeHtml(employee.id)}">Update</label>
          <input id="face-update-${escapeHtml(employee.id)}" class="sr-only" data-face-update="${escapeHtml(employee.id)}" type="file" accept="image/*">
        </td>
        <td>
          <div class="action-group">
            <button class="button secondary compact" data-edit-employee="${escapeHtml(employee.id)}" type="button">Edit</button>
            ${employee.status === "active" ? `<button class="button danger compact" data-deactivate-employee="${escapeHtml(employee.id)}" type="button">Deactivate</button>` : ""}
          </div>
        </td>
      </tr>
    `).join("");
    populateEmployeeDropdowns();
  }

  async function handleEmployeeCreate(event) {
    event.preventDefault();
    clearError(els.employeeFormError);

    const faceImage = getSelectedFaceImage();
    if (!faceImage) {
      showError(els.employeeFormError, "Face image is required.");
      return;
    }
    if (!state.faceQuality?.valid) {
      const quality = await inspectSelectedFace();
      if (!quality?.valid) {
        showError(els.employeeFormError, quality?.message || "Face detection must pass before creating employee.");
        return;
      }
    }

    const formData = new FormData();
    appendFormValue(formData, "name", els.employeeName.value);
    appendFormValue(formData, "email", els.employeeEmail.value);
    appendFormValue(formData, "phone", els.employeePhone.value);
    appendFormValue(formData, "department", els.employeeDepartment.value);
    appendFormValue(formData, "position", els.employeePosition.value);
    appendFormValue(formData, "salary_type", els.employeeSalaryType.value);
    appendFormValue(formData, "base_salary", els.employeeBaseSalary.value);
    appendFormValue(formData, "bank_account", els.employeeBankAccount.value);
    appendFormValue(formData, "join_date", els.employeeJoinDate.value);
    appendFormValue(formData, "status", els.employeeStatus.value);
    appendFormValue(formData, "username", els.employeeUsername.value);
    appendFormValue(formData, "temp_password", els.employeeTempPassword.value);
    formData.append("face_image", faceImage, faceImage.name || "face-capture.jpg");

    try {
      await request("/api/employees", {
        method: "POST",
        body: formData,
      });
      resetEmployeeForm();
      await Promise.all([loadEmployees(), loadSummary()]);
      setView("employees");
      showToast("Employee created");
    } catch (error) {
      showError(els.employeeFormError, error.message);
    }
  }

  function appendFormValue(formData, key, value) {
    const cleanValue = String(value || "").trim();
    if (cleanValue || key !== "username") {
      formData.append(key, cleanValue);
    }
  }

  function getSelectedFaceImage() {
    if (state.faceImageBlob) {
      return state.faceImageBlob;
    }
    return els.employeeFaceImage.files[0] || null;
  }

  function resetEmployeeForm() {
    els.employeeForm.reset();
    els.employeeJoinDate.value = new Date().toISOString().slice(0, 10);
    els.employeeTempPassword.value = "Temp12345";
    state.faceImageBlob = null;
    state.faceQuality = null;
    clearFacePreview();
    renderFaceQuality(null);
    stopCamera();
  }

  function suggestEmployeeUsername() {
    if (els.employeeUsername.value.trim()) {
      return;
    }
    const email = els.employeeEmail.value.trim();
    const username = email.includes("@") ? email.split("@", 1)[0] : "";
    els.employeeUsername.value = username;
  }

  function handleFaceFileChange() {
    state.faceImageBlob = null;
    state.faceQuality = null;
    const file = els.employeeFaceImage.files[0];
    if (!file) {
      clearFacePreview();
      renderFaceQuality(null);
      return;
    }
    stopCamera();
    setFacePreview(URL.createObjectURL(file));
    inspectSelectedFace();
  }

  async function handleEmployeeFaceUpdate(event) {
    const input = event.target.closest("[data-face-update]");
    if (!input) {
      return;
    }

    const file = input.files[0];
    const employeeId = input.dataset.faceUpdate;
    if (!file || !employeeId) {
      return;
    }

    const formData = new FormData();
    formData.append("face_image", file, file.name || "face-update.jpg");

    try {
      await request(`/api/employees/${encodeURIComponent(employeeId)}/re-register-face`, {
        method: "POST",
        body: formData,
      });
      input.value = "";
      await loadEmployees();
      showToast(`Face updated for ${employeeName(employeeId)}`);
    } catch (error) {
      input.value = "";
      showToast(error.message);
    }
  }

  async function toggleCamera() {
    if (state.cameraStream) {
      stopCamera();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      showError(els.employeeFormError, "Camera is not available in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      state.cameraStream = stream;
      els.faceVideo.srcObject = stream;
      els.faceVideo.classList.remove("hidden");
      els.facePreview.classList.add("hidden");
      els.facePlaceholder.classList.add("hidden");
      els.captureFaceButton.disabled = false;
      els.startCameraButton.textContent = "Stop camera";
    } catch (error) {
      showError(els.employeeFormError, "Camera permission was denied.");
    }
  }

  function captureFaceImage() {
    if (!state.cameraStream) {
      return;
    }

    const width = els.faceVideo.videoWidth;
    const height = els.faceVideo.videoHeight;
    if (!width || !height) {
      showError(els.employeeFormError, "Camera is still starting.");
      return;
    }

    els.faceCanvas.width = width;
    els.faceCanvas.height = height;
    const context = els.faceCanvas.getContext("2d", { willReadFrequently: true });
    context.filter = "contrast(1.08) brightness(1.04) saturate(1.02)";
    context.drawImage(els.faceVideo, 0, 0, width, height);
    context.filter = "none";
    if (els.faceSharpToggle.checked) {
      sharpenCanvas(els.faceCanvas, 0.35);
    }
    els.faceCanvas.toBlob((blob) => {
      if (!blob) {
        showError(els.employeeFormError, "Could not capture face image.");
        return;
      }
      state.faceImageBlob = new File([blob], "face-capture.jpg", { type: "image/jpeg" });
      els.employeeFaceImage.value = "";
      setFacePreview(URL.createObjectURL(state.faceImageBlob));
      stopCamera();
      inspectSelectedFace();
    }, "image/jpeg", 0.96);
  }

  function sharpenCanvas(canvas, amount) {
    const context = canvas.getContext("2d", { willReadFrequently: true });
    const width = canvas.width;
    const height = canvas.height;
    const image = context.getImageData(0, 0, width, height);
    const source = image.data;
    const output = new Uint8ClampedArray(source);

    for (let y = 1; y < height - 1; y += 1) {
      for (let x = 1; x < width - 1; x += 1) {
        const index = (y * width + x) * 4;
        for (let channel = 0; channel < 3; channel += 1) {
          const center = source[index + channel] * 5;
          const left = source[index - 4 + channel];
          const right = source[index + 4 + channel];
          const top = source[index - width * 4 + channel];
          const bottom = source[index + width * 4 + channel];
          const sharpened = center - left - right - top - bottom;
          output[index + channel] = source[index + channel] * (1 - amount) + sharpened * amount;
        }
      }
    }

    image.data.set(output);
    context.putImageData(image, 0, 0);
  }

  function setFacePreview(src) {
    if (state.facePreviewUrl) {
      URL.revokeObjectURL(state.facePreviewUrl);
    }
    state.facePreviewUrl = src;
    els.facePreview.src = src;
    els.facePreview.classList.remove("hidden");
    els.facePlaceholder.classList.add("hidden");
    els.detectFaceButton.disabled = false;
  }

  function clearFacePreview() {
    if (state.facePreviewUrl) {
      URL.revokeObjectURL(state.facePreviewUrl);
      state.facePreviewUrl = "";
    }
    els.facePreview.removeAttribute("src");
    els.facePreview.classList.add("hidden");
    els.facePlaceholder.classList.remove("hidden");
    els.detectFaceButton.disabled = true;
  }

  async function inspectSelectedFace() {
    clearError(els.employeeFormError);
    const faceImage = getSelectedFaceImage();
    if (!faceImage) {
      state.faceQuality = null;
      renderFaceQuality(null);
      return null;
    }

    renderFaceQuality({ pending: true, message: "Detecting face..." });
    const formData = new FormData();
    formData.append("face_image", faceImage, faceImage.name || "face-capture.jpg");

    try {
      const response = await request("/api/employees/face-quality", {
        method: "POST",
        body: formData,
      });
      state.faceQuality = response.data || null;
      renderFaceQuality(state.faceQuality);
      return state.faceQuality;
    } catch (error) {
      state.faceQuality = { valid: false, message: error.message, confidence: 0 };
      renderFaceQuality(state.faceQuality);
      return state.faceQuality;
    }
  }

  function renderFaceQuality(quality) {
    if (!quality) {
      els.faceQualityStatus.className = "face-quality";
      els.faceQualityStatus.innerHTML = `
        <strong>Waiting for face image</strong>
        <span>Select or capture a face image before creating the employee.</span>
      `;
      return;
    }

    if (quality.pending) {
      els.faceQualityStatus.className = "face-quality pending";
      els.faceQualityStatus.innerHTML = `
        <strong>Detecting face</strong>
        <span>${escapeHtml(quality.message)}</span>
      `;
      return;
    }

    const confidence = Number(quality.confidence || 0);
    els.faceQualityStatus.className = `face-quality ${quality.valid ? "valid" : "invalid"}`;
    els.faceQualityStatus.innerHTML = `
      <strong>${quality.valid ? "Face detected" : "Face not ready"}</strong>
      <span>${escapeHtml(quality.message || "")}${confidence ? ` • ${Math.round(confidence * 100)}% confidence` : ""}</span>
    `;
  }

  function stopCamera() {
    if (state.cameraStream) {
      state.cameraStream.getTracks().forEach((track) => track.stop());
    }
    state.cameraStream = null;
    els.faceVideo.srcObject = null;
    els.faceVideo.classList.add("hidden");
    els.captureFaceButton.disabled = true;
    els.startCameraButton.textContent = "Start camera";
    if (!els.facePreview.getAttribute("src")) {
      els.facePlaceholder.classList.remove("hidden");
    }
  }

  function renderAttendance(rows) {
    const tableHtml = rows.length
      ? rows.map((row) => `
        <tr>
          <td>${escapeHtml(employeeName(row.employee_id))}</td>
          <td>${escapeHtml(row.date)}</td>
          <td>${statusPill(row.status)}</td>
          <td>${formatTime(row.clock_in)}</td>
          <td>${formatTime(row.clock_out)}</td>
          <td>${escapeHtml(row.work_hours || "0.00")}</td>
        </tr>
      `).join("")
      : emptyRow(6, "No attendance recorded today.");

    els.attendanceTable.innerHTML = tableHtml;
    if (els.timeclockTable) {
      els.timeclockTable.innerHTML = rows.length
        ? rows.map((row) => `
          <tr>
            <td>${escapeHtml(employeeName(row.employee_id))}</td>
            <td>${statusPill(row.status)}</td>
            <td>${formatTime(row.clock_in)}</td>
            <td>${formatTime(row.clock_out)}</td>
            <td>${escapeHtml(row.work_hours || "0.00")}</td>
          </tr>
        `).join("")
        : emptyRow(5, "No attendance recorded today.");
    }
    els.overviewAttendance.innerHTML = rows.length
      ? rows.slice(0, 8).map((row) => `
        <tr>
          <td>${escapeHtml(employeeName(row.employee_id))}</td>
          <td>${statusPill(row.status)}</td>
          <td>${formatTime(row.clock_in)}</td>
          <td>${formatTime(row.clock_out)}</td>
        </tr>
      `).join("")
      : emptyRow(4, "No attendance recorded today.");
  }

  function renderLeaves(leaves) {
    els.pendingLeaves.textContent = leaves.filter((leave) => leave.status === "pending").length;

    if (!leaves.length) {
      els.leavesTable.innerHTML = emptyRow(6, "No leave requests found.");
      els.overviewLeaves.innerHTML = '<p class="empty">No leave requests found.</p>';
      return;
    }

    els.leavesTable.innerHTML = leaves.map((leave) => `
      <tr>
        <td>${escapeHtml(employeeName(leave.employee_id))}</td>
        <td>${escapeHtml(leave.leave_type)}</td>
        <td>${escapeHtml(leave.start_date)} to ${escapeHtml(leave.end_date)}</td>
        <td>${escapeHtml(leave.total_days)}</td>
        <td>${statusPill(leave.status)}</td>
        <td>${leaveActions(leave)}</td>
      </tr>
    `).join("");

    const pending = leaves.filter((leave) => leave.status === "pending").slice(0, 5);
    els.overviewLeaves.innerHTML = pending.length
      ? pending.map((leave) => `
        <article class="list-item">
          <strong>${escapeHtml(employeeName(leave.employee_id))}</strong>
          <span>${escapeHtml(leave.leave_type)}: ${escapeHtml(leave.start_date)} to ${escapeHtml(leave.end_date)}</span>
        </article>
      `).join("")
      : '<p class="empty">No pending leave requests.</p>';
  }

  function leaveActions(leave) {
    if (leave.status !== "pending") {
      return '<span class="empty">Reviewed</span>';
    }

    return `
      <div class="inline-actions">
        <button class="button secondary" data-leave-action="approve" data-leave-id="${leave.id}" type="button">Approve</button>
        <button class="button secondary" data-leave-action="reject" data-leave-id="${leave.id}" type="button">Reject</button>
      </div>
    `;
  }

  async function updateLeave(action, leaveId) {
    try {
      await request(`/api/leaves/${encodeURIComponent(leaveId)}/${action}`, { method: "PUT" });
      await Promise.all([loadLeaves(), loadAttendance(), loadSummary()]);
      showToast(`Leave ${action}d`);
    } catch (error) {
      showToast(error.message);
    }
  }

  function handleEmployeeTableClick(event) {
    const editButton = event.target.closest("[data-edit-employee]");
    if (editButton) {
      openEditModal(editButton.dataset.editEmployee);
      return;
    }
    const deactivateButton = event.target.closest("[data-deactivate-employee]");
    if (deactivateButton) {
      deactivateEmployee(deactivateButton.dataset.deactivateEmployee);
    }
  }

  function openEditModal(employeeId) {
    const employee = state.employeesById.get(String(employeeId));
    if (!employee) return;
    els.editId.value = employee.id;
    els.editName.value = employee.name || "";
    els.editEmail.value = employee.email || "";
    els.editPhone.value = employee.phone || "";
    els.editDepartment.value = employee.department || "";
    els.editPosition.value = employee.position || "";
    els.editSalaryType.value = employee.salary_type || "monthly";
    els.editBaseSalary.value = employee.base_salary || "";
    els.editBankAccount.value = employee.bank_account || "";
    els.editStatus.value = employee.status || "active";
    clearError(els.editError);
    els.editModal.classList.remove("hidden");
  }

  function closeEditModal() {
    els.editModal.classList.add("hidden");
    els.editForm.reset();
  }

  async function handleEditEmployeeSubmit(event) {
    event.preventDefault();
    clearError(els.editError);
    const employeeId = els.editId.value;
    const payload = {
      name: els.editName.value.trim(),
      email: els.editEmail.value.trim(),
      phone: els.editPhone.value.trim() || null,
      department: els.editDepartment.value.trim(),
      position: els.editPosition.value.trim(),
      salary_type: els.editSalaryType.value,
      base_salary: els.editBaseSalary.value,
      bank_account: els.editBankAccount.value.trim() || null,
      status: els.editStatus.value,
    };
    try {
      await request(`/api/employees/${encodeURIComponent(employeeId)}`, {
        method: "PUT",
        body: payload,
      });
      closeEditModal();
      await Promise.all([loadEmployees(), loadSummary()]);
      showToast("Employee updated");
    } catch (error) {
      showError(els.editError, error.message);
    }
  }

  async function deactivateEmployee(employeeId) {
    const name = employeeName(employeeId);
    if (!confirm(`Deactivate ${name}? This will disable their account.`)) return;
    try {
      await request(`/api/employees/${encodeURIComponent(employeeId)}`, { method: "DELETE" });
      await Promise.all([loadEmployees(), loadSummary()]);
      showToast(`${name} deactivated`);
    } catch (error) {
      showToast(error.message);
    }
  }

  async function handleLeaveSubmit(event) {
    event.preventDefault();
    clearError(els.leaveFormError);
    const payload = {
      employee_id: Number(els.leaveEmployeeId.value),
      leave_type: els.leaveType.value,
      start_date: els.leaveStartDate.value,
      end_date: els.leaveEndDate.value,
      reason: els.leaveReason.value.trim() || null,
    };
    try {
      await request("/api/leaves", { method: "POST", body: payload });
      els.leaveForm.reset();
      initDates();
      await Promise.all([loadLeaves(), loadSummary()]);
      showToast("Leave request submitted");
    } catch (error) {
      showError(els.leaveFormError, error.message);
    }
  }

  async function handleAttendanceHistory(event) {
    event.preventDefault();
    const employeeId = els.historyEmployee.value;
    const month = Number(els.historyMonth.value);
    const year = Number(els.historyYear.value);
    try {
      const response = await request(`/api/attendance/${encodeURIComponent(employeeId)}?month=${month}&year=${year}`);
      const rows = response.data || [];
      els.historyTable.innerHTML = rows.length
        ? rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.date)}</td>
            <td>${statusPill(row.status)}</td>
            <td>${formatTime(row.clock_in)}</td>
            <td>${formatTime(row.clock_out)}</td>
            <td>${escapeHtml(row.work_hours || "0.00")}</td>
            <td>${escapeHtml(row.note || "-")}</td>
          </tr>
        `).join("")
        : emptyRow(6, "No attendance records for this period.");
      showToast("Attendance history loaded");
    } catch (error) {
      showToast(error.message);
    }
  }

  async function handlePayrollApprove(payrollRunId) {
    if (!confirm("Approve this payroll run? This action cannot be undone.")) return;
    try {
      const response = await request(`/api/payroll/${encodeURIComponent(payrollRunId)}/approve`, { method: "PUT" });
      renderPayrollResult(response.data);
      showToast("Payroll approved");
    } catch (error) {
      showToast(error.message);
    }
  }

  function populateEmployeeDropdowns() {
    const options = Array.from(state.employeesById.values())
      .filter((e) => e.status === "active")
      .map((e) => `<option value="${escapeHtml(e.id)}">${escapeHtml(e.name)}</option>`)
      .join("");
    const defaultOption = '<option value="">Select employee</option>';
    [els.leaveEmployeeId, els.historyEmployee].forEach((select) => {
      if (select) select.innerHTML = defaultOption + options;
    });
  }

  async function handlePayrollRun(event) {
    event.preventDefault();
    clearError(els.payrollError);

    const month = Number(els.payrollMonth.value);
    const year = Number(els.payrollYear.value);
    try {
      const response = await request(`/api/payroll/run?month=${month}&year=${year}`, {
        method: "POST",
      });
      renderPayrollResult(response.data);
      els.reportMonth.value = String(month);
      els.reportYear.value = String(year);
      await loadPayrollData(month, year);
      showToast("Payroll run created");
    } catch (error) {
      showError(els.payrollError, error.message);
    }
  }

  function renderPayrollResult(run) {
    if (!run) {
      els.payrollResult.innerHTML = '<p class="empty">No payroll run returned.</p>';
      return;
    }

    const approveButton = run.status === "draft" || run.status === "submitted"
      ? `<button class="button primary" onclick="(${handlePayrollApprove.toString()})(${escapeHtml(run.id)})" type="button">Approve payroll</button>`
      : "";

    els.payrollResult.innerHTML = `
      <div class="result-grid">
        <div><span>Run ID</span><strong>${escapeHtml(run.id)}</strong></div>
        <div><span>Period</span><strong>${escapeHtml(run.month)}/${escapeHtml(run.year)}</strong></div>
        <div><span>Status</span><strong>${statusPill(run.status)}</strong></div>
        <div><span>Total cost</span><strong>${money(run.total_cost)}</strong></div>
        <div><span>Employees</span><strong>${escapeHtml(run.employee_count ?? "-")}</strong></div>
        <div><span>Created</span><strong>${formatDateTime(run.created_at)}</strong></div>
      </div>
      ${approveButton}
    `;

    const approveEl = els.payrollResult.querySelector(".button.primary");
    if (approveEl) {
      approveEl.onclick = () => handlePayrollApprove(run.id);
    }
  }

  function setupClockWidget(kind) {
    const widget = {
      kind,
      form: document.querySelector(`[data-clock-form="${kind}"]`),
      video: document.querySelector(`[data-clock-video="${kind}"]`),
      canvas: document.querySelector(`[data-clock-canvas="${kind}"]`),
      preview: document.querySelector(`[data-clock-preview="${kind}"]`),
      placeholder: document.querySelector(`[data-clock-placeholder="${kind}"]`),
      cameraButton: document.querySelector(`[data-clock-camera="${kind}"]`),
      captureButton: document.querySelector(`[data-clock-capture="${kind}"]`),
      fileInput: document.querySelector(`[data-clock-file="${kind}"]`),
      error: document.querySelector(`[data-clock-error="${kind}"]`),
      result: document.querySelector(`[data-clock-result="${kind}"]`),
      stream: null,
      imageBlob: null,
      previewUrl: "",
    };

    if (!widget.form) {
      return;
    }

    state.clockWidgets.set(kind, widget);
    widget.form.addEventListener("submit", (event) => handleClockSubmit(event, widget));
    widget.cameraButton.addEventListener("click", () => toggleClockCamera(widget));
    widget.captureButton.addEventListener("click", () => captureClockImage(widget));
    widget.fileInput.addEventListener("change", () => handleClockFileChange(widget));
  }

  async function handleClockSubmit(event, widget) {
    event.preventDefault();
    clearError(widget.error);
    widget.result.classList.add("hidden");
    const action = event.submitter?.dataset.clockAction || "clock-in";
    const faceImage = getClockImage(widget);
    if (!faceImage) {
      showError(widget.error, "Face image is required.");
      return;
    }

    const formData = new FormData();
    formData.append("face_image", faceImage, faceImage.name || `${action}.jpg`);

    try {
      const response = await request(`/api/attendance/${action}`, {
        method: "POST",
        auth: false,
        body: formData,
      });
      renderClockResult(widget, response.data, action);
      clearClockImage(widget);
      stopClockCamera(widget.kind);
      if (state.token) {
        await Promise.all([loadAttendance(), loadSummary()]);
      }
      showToast(action === "clock-in" ? "Check-in recorded" : "Check-out recorded");
    } catch (error) {
      showError(widget.error, error.message);
    }
  }

  function getClockImage(widget) {
    if (widget.imageBlob) {
      return widget.imageBlob;
    }
    return widget.fileInput.files[0] || null;
  }

  function handleClockFileChange(widget) {
    widget.imageBlob = null;
    const file = widget.fileInput.files[0];
    if (!file) {
      clearClockImage(widget);
      return;
    }
    stopClockCamera(widget.kind);
    setClockPreview(widget, URL.createObjectURL(file));
  }

  async function toggleClockCamera(widget) {
    if (widget.stream) {
      stopClockCamera(widget.kind);
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      showError(widget.error, "Camera is not available in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      widget.stream = stream;
      widget.video.srcObject = stream;
      widget.video.classList.remove("hidden");
      widget.preview.classList.add("hidden");
      widget.placeholder.classList.add("hidden");
      widget.captureButton.disabled = false;
      widget.cameraButton.textContent = "Stop camera";
    } catch {
      showError(widget.error, "Camera permission was denied.");
    }
  }

  function captureClockImage(widget) {
    if (!widget.stream) {
      return;
    }

    const width = widget.video.videoWidth;
    const height = widget.video.videoHeight;
    if (!width || !height) {
      showError(widget.error, "Camera is still starting.");
      return;
    }

    widget.canvas.width = width;
    widget.canvas.height = height;
    const context = widget.canvas.getContext("2d", { willReadFrequently: true });
    context.filter = "contrast(1.08) brightness(1.04) saturate(1.02)";
    context.drawImage(widget.video, 0, 0, width, height);
    context.filter = "none";
    sharpenCanvas(widget.canvas, 0.3);
    widget.canvas.toBlob((blob) => {
      if (!blob) {
        showError(widget.error, "Could not capture attendance image.");
        return;
      }
      widget.imageBlob = new File([blob], "attendance-capture.jpg", { type: "image/jpeg" });
      widget.fileInput.value = "";
      setClockPreview(widget, URL.createObjectURL(widget.imageBlob));
      stopClockCamera(widget.kind);
    }, "image/jpeg", 0.96);
  }

  function setClockPreview(widget, src) {
    if (widget.previewUrl) {
      URL.revokeObjectURL(widget.previewUrl);
    }
    widget.previewUrl = src;
    widget.preview.src = src;
    widget.preview.classList.remove("hidden");
    widget.placeholder.classList.add("hidden");
  }

  function clearClockImage(widget) {
    widget.imageBlob = null;
    widget.fileInput.value = "";
    if (widget.previewUrl) {
      URL.revokeObjectURL(widget.previewUrl);
      widget.previewUrl = "";
    }
    widget.preview.removeAttribute("src");
    widget.preview.classList.add("hidden");
    widget.placeholder.classList.remove("hidden");
  }

  function stopClockCamera(kind) {
    const widget = state.clockWidgets.get(kind);
    if (!widget) {
      return;
    }
    if (widget.stream) {
      widget.stream.getTracks().forEach((track) => track.stop());
    }
    widget.stream = null;
    widget.video.srcObject = null;
    widget.video.classList.add("hidden");
    widget.captureButton.disabled = true;
    widget.cameraButton.textContent = "Start camera";
    if (!widget.preview.getAttribute("src")) {
      widget.placeholder.classList.remove("hidden");
    }
  }

  function stopClockCameras() {
    state.clockWidgets.forEach((_, kind) => stopClockCamera(kind));
  }

  function renderClockResult(widget, result, action) {
    const label = action === "clock-in" ? "Checked in" : "Checked out";
    widget.result.innerHTML = `
      <strong>${label}: ${escapeHtml(result?.name || "Employee")}</strong>
      <span>${escapeHtml(result?.status || "")}</span>
      <span>${formatDateTime(result?.clock_in || result?.clock_out)}</span>
      ${result?.work_hours ? `<span>${escapeHtml(result.work_hours)} hours</span>` : ""}
    `;
    widget.result.classList.remove("hidden");
  }

  async function handlePayrollReport(event) {
    event.preventDefault();
    clearError(els.payrollReportError);
    await loadPayrollData(Number(els.reportMonth.value), Number(els.reportYear.value));
  }

  async function loadPayrollData(month, year) {
    try {
      const [attendanceResponse, payrollResponse] = await Promise.all([
        request(`/api/reports/attendance?month=${month}&year=${year}`),
        request(`/api/reports/payroll?month=${month}&year=${year}`).catch((error) => {
          if (error.status === 404 || error.message === "Payroll run not found") {
            return { success: false, data: null, message: "Payroll run not found" };
          }
          throw error;
        }),
      ]);
      const payrollData = payrollResponse.data || null;
      if (payrollData?.payroll_run?.id) {
        const itemsResponse = await request(`/api/payroll/${payrollData.payroll_run.id}/items`);
        payrollData.items = itemsResponse.data || [];
      }
      renderPayrollData(attendanceResponse.data || [], payrollData, month, year);
      showToast("Payroll data loaded");
    } catch (error) {
      showError(els.payrollReportError, error.message);
    }
  }

  function renderPayrollData(attendanceRows, payrollData, month, year) {
    const run = payrollData?.payroll_run || null;
    els.payrollReportSummary.innerHTML = payrollData
      ? `
        <div class="result-grid">
          <div><span>Period</span><strong>${escapeHtml(month)}/${escapeHtml(year)}</strong></div>
          <div><span>Run status</span><strong>${statusPill(run?.status)}</strong></div>
          <div><span>Employees</span><strong>${escapeHtml(payrollData.employee_count ?? 0)}</strong></div>
          <div><span>Gross salary</span><strong>${money(payrollData.gross_salary)}</strong></div>
          <div><span>Deductions</span><strong>${money(Number(payrollData.late_deduction || 0) + Number(payrollData.unpaid_leave_deduction || 0))}</strong></div>
          <div><span>Net pay</span><strong>${money(payrollData.net_pay)}</strong></div>
        </div>
      `
      : '<p class="empty">No payroll run exists for this period. Run payroll to generate payroll items.</p>';

    els.payrollAttendanceTable.innerHTML = attendanceRows.length
      ? attendanceRows.map((row) => `
        <tr>
          <td>${escapeHtml(row.employee_name || employeeName(row.employee_id))}</td>
          <td>${escapeHtml(row.date)}</td>
          <td>${statusPill(row.status)}</td>
          <td>${formatTime(row.clock_in)}</td>
          <td>${formatTime(row.clock_out)}</td>
          <td>${escapeHtml(row.work_hours || "0.00")}</td>
        </tr>
      `).join("")
      : emptyRow(6, "No attendance rows for this period.");

    const items = payrollData?.items || [];
    const runId = payrollData?.payroll_run?.id;
    els.payrollItemsTable.innerHTML = items.length
      ? items.map((item) => `
        <tr>
          <td>${escapeHtml(item.employee_name || employeeName(item.employee_id))}</td>
          <td>${money(item.base_salary)}</td>
          <td>${escapeHtml(item.present_days)}/${escapeHtml(item.working_days)}</td>
          <td>${escapeHtml(item.overtime_hours)}h<br><span>${money(item.overtime_pay)}</span></td>
          <td>${money(Number(item.late_deduction || 0) + Number(item.unpaid_leave_deduction || 0))}</td>
          <td>${money(item.gross_salary || 0)}</td>
          <td>${money(item.tax_amount || 0)}</td>
          <td>${money(item.social_security_employee || 0)}</td>
          <td><strong>${money(item.net_pay)}</strong></td>
          <td>${runId ? `<a class="button secondary compact" href="/api/payroll/${runId}/payslip/${item.employee_id}" target="_blank">PDF</a>` : "-"}</td>
        </tr>
      `).join("")
      : emptyRow(10, "No payroll items for this period.");
  }

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (!(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    if (options.auth !== false && state.token) {
      headers.set("Authorization", `Bearer ${state.token}`);
    }

    const response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body: options.body instanceof FormData ? options.body : JSON.stringify(options.body),
    });

    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (!response.ok || (payload && payload.success === false)) {
      const message = payload?.detail || payload?.message || `Request failed (${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return payload || { success: true, data: null };
  }

  function readStoredUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY));
    } catch {
      return null;
    }
  }

  function employeeName(id) {
    const employee = state.employeesById.get(String(id));
    return employee ? employee.name : `#${id}`;
  }

  function statusPill(status) {
    const value = String(status || "unknown");
    return `<span class="status-pill ${escapeHtml(value.toLowerCase())}">${escapeHtml(value)}</span>`;
  }

  function emptyRow(colspan, message) {
    return `<tr><td colspan="${colspan}" class="empty">${escapeHtml(message)}</td></tr>`;
  }

  function money(value) {
    const number = Number(value || 0);
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    }).format(Number.isFinite(number) ? number : 0);
  }

  function formatTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return escapeHtml(value);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function formatDateTime(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return escapeHtml(value);
    return date.toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function showError(element, message) {
    element.textContent = message;
  }

  function clearError(element) {
    element.textContent = "";
  }

  let toastTimer = null;
  function showToast(message) {
    els.toast.textContent = message;
    els.toast.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      els.toast.classList.add("hidden");
    }, 3000);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();
