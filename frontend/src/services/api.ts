import axios from 'axios';

// Automatically inject JWT Token into required requests via Interceptor
axios.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('hiring_ai_token');
    if (token && config.headers) {
      config.headers['Authorization'] = `Bearer ${token}`;
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
      localStorage.removeItem('hiring_ai_token');
      localStorage.removeItem('hiring_ai_role');
      // Hard redirect protects against frozen react-router states
      window.location.href = '/login';
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

  getJobs: async () => {
    const res = await axios.get('/api/jobs');
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

  cancelJob: async (job_id: string) => {
    const res = await axios.post(`/api/jobs/${job_id}/cancel`);
    return res.data;
  },

  deleteJob: async (job_id: string) => {
    const res = await axios.delete(`/api/jobs/${job_id}`);
    return res.data;
  },

  suggestJobFields: async (payload: { job_title: string, skills: string[] }) => {
    const res = await axios.post('/api/suggest', payload);
    return res.data;
  },

  chatWithHRAssistant: async (payload: { job_title: string, skills: string[], message: string }) => {
    const res = await axios.post('/api/jobs/ai-chat', payload);
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

  getUserProfile: async () => {
    const res = await axios.get('/api/me');
    return res.data;
  }
};
