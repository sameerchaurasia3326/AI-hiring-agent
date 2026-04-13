/**
 * Hiring AI — Dashboard Controllers
 * ────────────────────────────────────
 * Handles data fetching, UI state, and form submissions.
 */

// ── Configuration ──
const API_BASE = window.location.origin;
// For demonstration, we'll store a token. In production, this comes from login.
let AUTH_TOKEN = localStorage.getItem('hiring_ai_token') || "";

// ── DOM Elements ──
const elements = {
  btnOpenModal: document.getElementById('btn-add-candidate'),
  btnCloseModal: document.getElementById('btn-close-modal'),
  btnCancelModal: document.getElementById('btn-cancel-modal'),
  modalOverlay: document.getElementById('modal-add-candidate'),
  formAddCandidate: document.getElementById('form-add-candidate'),
  candidateListBody: document.getElementById('candidate-list-body'),
  jobDropdown: document.getElementById('cand-job-id'),
  userName: document.getElementById('user-name'),
  userAvatar: document.getElementById('user-avatar'),
  toastContainer: document.getElementById('toast-container')
};

// ── Initialisation ──
document.addEventListener('DOMContentLoaded', async () => {
  console.log("🚀 Dashboard Initialising...");
  
  // 1. Sync User Info (Mock for now, or fetch from /current-user)
  elements.userName.textContent = "Interviewer Admin";
  elements.userAvatar.textContent = "IA";

  // 2. Initial Data Fetch
  await fetchJobs();
  await fetchCandidates();
});

// ── Event Listeners ──
elements.btnOpenModal.addEventListener('click', () => {
  elements.modalOverlay.style.display = 'grid';
});

const closeModal = () => {
  elements.modalOverlay.style.display = 'none';
  elements.formAddCandidate.reset();
};

elements.btnCloseModal.addEventListener('click', closeModal);
elements.btnCancelModal.addEventListener('click', closeModal);

elements.formAddCandidate.addEventListener('submit', async (e) => {
  e.preventDefault();
  
  const formData = {
    name: document.getElementById('cand-name').value,
    email: document.getElementById('cand-email').value,
    resume_url: document.getElementById('cand-resume').value,
    job_id: document.getElementById('cand-job-id').value
  };

  try {
    const btnSubmit = document.getElementById('btn-submit-candidate');
    btnSubmit.disabled = true;
    btnSubmit.textContent = "Adding...";

    const res = await fetch(`${API_BASE}/candidates`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${AUTH_TOKEN}`
      },
      body: JSON.stringify(formData)
    });

    if (res.ok) {
      showToast("Candidate added and shortlisted ✅");
      closeModal();
      await fetchCandidates(); // Refresh list
    } else {
      const error = await res.json();
      showToast(`❌ Error: ${error.detail || 'Failed to add candidate'}`, "danger");
    }
  } catch (err) {
    showToast("❌ Network error. Please try again.", "danger");
  } finally {
    const btnSubmit = document.getElementById('btn-submit-candidate');
    btnSubmit.disabled = false;
    btnSubmit.textContent = "Add Candidate";
  }
});

// ── API Handlers ──

async function fetchJobs() {
  try {
    const res = await fetch(`${API_BASE}/jobs`, {
      headers: { 'Authorization': `Bearer ${AUTH_TOKEN}` }
    });
    const jobs = await res.json();
    
    // Clear and Fill Dropdown
    elements.jobDropdown.innerHTML = '<option value="">Select an active job...</option>';
    jobs.forEach(job => {
      const opt = document.createElement('option');
      opt.value = job.id;
      opt.textContent = `${job.title} (${job.location})`;
      elements.jobDropdown.appendChild(opt);
    });
  } catch (err) {
    console.error("Failed to fetch jobs", err);
  }
}

async function fetchCandidates() {
  try {
    const res = await fetch(`${API_BASE}/candidates`, {
      headers: { 'Authorization': `Bearer ${AUTH_TOKEN}` }
    });
    const candidates = await res.json();
    
    renderCandidates(candidates);
  } catch (err) {
    console.error("Failed to fetch candidates", err);
  }
}

// ── UI Helpers ──

function renderCandidates(candidates) {
  if (candidates.length === 0) {
    elements.candidateListBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 3rem;">No candidates found. Start by adding one!</td></tr>`;
    return;
  }

  elements.candidateListBody.innerHTML = candidates.map(c => `
    <tr>
      <td>
        <div style="font-weight: 500;">${c.name}</div>
        <div style="font-size: 0.75rem; color: var(--text-secondary);">${c.email}</div>
      </td>
      <td><span class="badge badge-shortlisted">Shortlisted</span></td>
      <td><span style="font-size: 0.8rem; background: rgba(255,255,255,0.05); padding: 0.2rem 0.5rem; border-radius: 4px;">Manual</span></td>
      <td style="color: var(--text-secondary); font-size: 0.85rem;">Just now</td>
      <td>
        <button class="btn" style="padding: 0.3rem 0.6rem; font-size: 0.75rem; border: 1px solid var(--border);">View Profile</button>
      </td>
    </tr>
  `).join('');
}

function showToast(message, type = "success") {
  const toast = document.createElement('div');
  toast.className = `toast ${type === 'danger' ? 'toast-danger' : ''}`;
  toast.innerHTML = `
    <div style="flex: 1;">${message}</div>
    <button onclick="this.parentElement.remove()" style="background:none; border:none; color:white; cursor:pointer;">&times;</button>
  `;
  
  elements.toastContainer.appendChild(toast);
  
  // Auto-remove after 5 seconds
  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, 5000);
}
