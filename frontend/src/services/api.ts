import axios from 'axios';

// Definitive timeout to prevent hanging UI on slow networks
axios.defaults.timeout = 15000; // 15 seconds

// Automatically inject JWT Token into required requests via Interceptor
axios.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('hiring_ai_token');

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// Globally trap 401 Unauthorized endpoints to log the user out cleanly
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      console.warn("🔒 [SESSION] Unauthorized access detected. Clearing session and redirecting...");
      // Definitive cleanup of all session keys
      localStorage.clear();
      sessionStorage.clear();

      // Hard redirect protects against frozen react-router states or stale cache
      window.location.href = '/login?reason=expired';
    }
    return Promise.reject(error);
  }
);

export const api = {
  login: async (credentials: any) => {
    // Backend expects JSON SignupRequest { email, password }
    const res = await axios.post('/api/login', {
      email: credentials.email,
      password: credentials.password
    });
    return res.data;
  },

  signup: async (userData: any) => {
    // Backend expects SignupRequest { company_name, email, password }
    const res = await axios.post('/api/signup', userData);
    return res.data;
  },

  verifyEmail: async (payload: { email: string; otp: string }) => {
    const res = await axios.post('/api/verify-email', payload);
    return res.data;
  },

  resendOtp: async (payload: { email: string }) => {
    const res = await axios.post('/api/resend-otp', payload);
    return res.data;
  },

  getJobs: async (status: string = 'active') => {
    const res = await axios.get(`/api/jobs?status=${status}`);
    return res.data;
  },

  getJdTemplates: async () => {
    const res = await axios.get('/api/jd-templates');
    return res.data;
  },

  getJob: async (job_id: string) => {
    const res = await axios.get(`/api/jobs/${job_id}`);
    return res.data;
  },

  createJob: async (payload: any) => {
    const res = await axios.post('/api/jobs', payload);
    return res.data;
  },

  approveJd: async (job_id: string, payload: { approved: boolean; feedback: string }) => {
    const res = await axios.post(`/api/jobs/${job_id}/approve-jd`, payload);
    return res.data;
  },

  disconnectLinkedin: async () => {
    const res = await axios.delete('/api/integrations/linkedin');
    return res.data;
  },

  disconnectGoogleCalendar: async () => {
    const res = await axios.delete('/api/integrations/google');
    return res.data;
  },


  cancelJob: async (job_id: string) => {
    const res = await axios.post(`/api/jobs/${job_id}/cancel`);
    return res.data;
  },

  resumeJob: async (job_id: string) => {
    const res = await axios.post(`/api/jobs/${job_id}/resume`);
    return res.data;
  },

  deleteJob: async (job_id: string) => {
    const res = await axios.delete(`/api/jobs/${job_id}`);
    return res.data;
  },

  suggestJobFields: async (payload: { job_title: string, skills: string[] }) => {
    // Extended timeout: Ollama (local LLM) can take 20-30s on memory-constrained systems
    const res = await axios.post('/api/suggest', payload, { timeout: 60000 });
    return res.data;
  },

  chatWithHRAssistant: async (payload: { job_title: string, skills: string[], message: string }) => {
    // Extended timeout: same reason as suggestJobFields
    const res = await axios.post('/api/jobs/ai-chat', payload, { timeout: 60000 });
    return res.data;
  },

  acceptInvite: async (payload: { token: string; name: string; password: string }) => {
    const res = await axios.post('/api/accept-invite', payload);
    return res.data;
  },

  getTeam: async () => {
    const res = await axios.get('/api/team');
    return res.data.team;
  },

  inviteMember: async (payload: { email: string, role: string }) => {
    const res = await axios.post('/api/invite-user', payload);
    return res.data;
  },

  removeTeamMember: async (userId: string) => {
    const res = await axios.delete(`/api/team/${userId}`);
    return res.data;
  },

  getMyTasks: async () => {
    const res = await axios.get('/api/my-tasks');
    return res.data;
  },

  getInterviewerCandidates: async () => {
    const res = await axios.get('/api/interviewer/candidates');
    return res.data;
  },

  getInterviewerInterviews: async () => {
    const res = await axios.get('/api/interviewer/interviews');
    return res.data;
  },

  submitEvaluation: async (applicationId: string, payload: { rating: number, notes: string, decision: 'select' | 'reject' }) => {
    const res = await axios.post(`/api/applications/${applicationId}/evaluate`, payload);
    return res.data;
  },

  submitInterviewFeedback: async (interviewId: string, payload: { rating: number, notes: string, decision: string }) => {
    const res = await axios.post(`/api/interviews/${interviewId}/feedback`, payload);
    return res.data;
  },

  submitDecision: async (candidateId: string, decision: 'approve' | 'reject') => {
    const res = await axios.post('/api/submit-decision', {
      candidate_id: candidateId,
      decision: decision
    });
    return res.data;
  },

  getCandidate: async (candidate_id: string) => {
    const res = await axios.get(`/api/candidates/${candidate_id}`);
    return res.data;
  },

  getCandidateFeedback: async (candidate_id: string) => {
    const res = await axios.get(`/api/candidates/${candidate_id}/feedback`);
    return res.data;
  },

  getFeedbackAnalytics: async () => {
    const res = await axios.get('/api/analytics/feedback');
    return res.data;
  },

  submitFeedback: async (payload: { candidate_id: string, stage_id: string, decision: string, rating: number, feedback_text: string }) => {
    const res = await axios.post('/api/submit-feedback', payload);
    return res.data;
  },

  getCandidates: async (params?: { status?: string }) => {
    const res = await axios.get('/api/candidates', { params });
    return res.data;
  },

  sendRejectionEmail: async (candidateId: string) => {
    const res = await axios.post('/api/send-rejection-email', {
      candidate_id: candidateId
    });
    return res.data;
  },

  bulkSendRejectionEmail: async (candidateIds: string[]) => {
    const res = await axios.post('/api/bulk-send-rejection-email', {
      candidate_ids: candidateIds
    });
    return res.data;
  },

  selectCandidates: async (job_id: string, candidateIds: string[]) => {
    const res = await axios.post(`/api/jobs/${job_id}/select-candidates`, {
      candidate_ids: candidateIds
    });
    return res.data;
  },

  submitFinalDecision: async (job_id: string, candidateIds: string[]) => {
    const res = await axios.post(`/api/jobs/${job_id}/final-decision`, {
      selected_ids: candidateIds
    });
    return res.data;
  },

  getUserProfile: async () => {
    const res = await axios.get('/api/me');
    return res.data;
  },

  getApplications: async () => {
    const res = await axios.get('/api/applications');
    return res.data;
  },



  createCandidate: async (payload: { name: string, email: string, phone?: string }) => {
    const res = await axios.post('/api/candidates', payload);
    return res.data;
  },

  createApplication: async (payload: { candidate_id: string, job_id: string, status: string, stage: string }) => {
    const res = await axios.post('/api/applications', payload);
    return res.data;
  }
};
