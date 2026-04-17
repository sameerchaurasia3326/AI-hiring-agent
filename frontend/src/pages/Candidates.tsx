import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Users, Clock, Search } from 'lucide-react';
import { api } from '../services/api';
import { Plus, X, User, Mail, Phone, Briefcase } from 'lucide-react';

interface Candidate {
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  job_id: string;
  job_title: string;
  status: string;
  stage: string;
  updated_at: string;
}

export default function Candidates() {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [jobs, setJobs] = useState<any[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    job_id: ''
  });

  const fetchCandidates = async () => {
    try {
      setLoading(true);
      const data = await api.getCandidates();
      setCandidates(data);
    } catch (err: any) {
      console.error('Failed to fetch candidates:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchJobs = async () => {
    try {
      const data = await api.getJobs('active');
      setJobs(data);
    } catch (err: any) {
      console.error('Failed to fetch jobs:', err);
    }
  };

  useEffect(() => {
    fetchCandidates();
    fetchJobs();
  }, []);

  const handleAddCandidate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.job_id) return alert('Please select a job role');
    
    try {
      setIsSubmitting(true);
      
      // 1. Create candidate
      const candRes = await api.createCandidate({
        name: formData.name,
        email: formData.email,
        phone: formData.phone
      });

      // 2. Link to job
      await api.createApplication({
        candidate_id: candRes.candidate_id,
        job_id: formData.job_id,
        status: 'shortlisted',
        stage: 'SHORTLISTING'
      });

      // 3. Success
      alert('Candidate added and shortlisted ✅');
      setShowAddModal(false);
      setFormData({ name: '', email: '', phone: '', job_id: '' });
      fetchCandidates(); // REFRESH immediately
    } catch (err: any) {
      console.error('Failed to manual source:', err);
      alert('Failed to add candidate. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredCandidates = candidates.filter(c => 
    c.candidate_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.candidate_email.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.job_title.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="max-w-7xl mx-auto px-4 pb-20">
      <header className="mb-12">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-slate-900 rounded-lg">
            <Users className="w-5 h-5 text-white" />
          </div>
          <span className="text-slate-500 font-black uppercase tracking-widest text-xs">Talent Management</span>
        </div>
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <h1 className="text-5xl font-black text-gray-900 tracking-tight">Candidates</h1>
            <p className="text-gray-500 mt-3 text-lg font-medium">Manage and communicate with talent across all your hiring pipelines.</p>
          </div>
          <button 
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-2xl font-black shadow-lg shadow-blue-200 transition-all hover:scale-[1.02] active:scale-95 text-sm"
          >
            <Plus className="w-5 h-5" />
            Add Candidate
          </button>
        </div>
      </header>

      {/* Primary Tabs & Filters */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-10">
        <div className="flex items-center bg-gray-100 p-1 rounded-2xl w-fit">
          <div className="px-6 py-2.5 rounded-xl text-sm font-black bg-white text-gray-900 shadow-sm">
            All Applications
          </div>
        </div>

        <div className="relative group">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-blue-600 transition-colors" />
          <input 
            type="text" 
            placeholder="Search candidate or job..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-11 pr-6 py-3 bg-white border border-gray-100 rounded-2xl w-full md:w-80 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/10 focus:border-blue-500 transition-all font-medium text-sm"
          />
        </div>
      </div>

      {loading && (
        <div className="h-64 flex flex-col items-center justify-center gap-4">
          <Clock className="w-10 h-10 text-blue-600 animate-spin" />
          <p className="text-gray-400 font-black uppercase tracking-widest text-xs">Syncing Talent Pool...</p>
        </div>
      )}

      {!loading && (
        <div className="bg-white rounded-[2.5rem] border border-gray-100 shadow-xl shadow-gray-100/50 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-gray-50 text-[10px] font-black uppercase tracking-[0.2em] text-gray-400">
                  <th className="px-8 py-7">Candidate</th>
                  <th className="px-8 py-7">Job Role</th>
                  <th className="px-8 py-7">Stage</th>
                  <th className="px-8 py-7">Status</th>
                  <th className="px-8 py-7">Last Updated</th>
                  <th className="px-8 py-7 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                <AnimatePresence>
                  {filteredCandidates.map((cand, idx) => (
                    <motion.tr 
                      key={`${cand.candidate_id}-${cand.job_id}`}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: idx * 0.03 }}
                      className="group hover:bg-gray-50/50 transition-colors"
                    >
                      <td className="px-8 py-6">
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center text-white text-xs font-black shadow-lg shadow-slate-200">
                            {cand.candidate_name.charAt(0)}
                          </div>
                          <div>
                            <p className="font-bold text-gray-900 leading-tight group-hover:text-blue-600 transition-colors cursor-pointer" 
                               onClick={() => navigate(`/dashboard/jobs/${cand.job_id}/candidates/${cand.candidate_id}`)}>
                              {cand.candidate_name}
                            </p>
                            <p className="text-xs text-gray-400 font-medium mt-0.5">{cand.candidate_email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-8 py-6">
                        <span className="text-sm font-bold text-gray-700">{cand.job_title}</span>
                      </td>
                      <td className="px-8 py-6">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${
                            cand.stage === 'interviewing' ? 'bg-amber-400' :
                            cand.stage === 'shortlisted' ? 'bg-blue-400' :
                            cand.stage === 'rejected' ? 'bg-red-400' : 'bg-emerald-400'
                          }`} />
                          <span className="text-xs font-black uppercase tracking-widest text-gray-500">{cand.stage}</span>
                        </div>
                      </td>
                      <td className="px-8 py-6">
                        <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest ${
                          cand.status === 'shortlisted' ? 'bg-blue-100 text-blue-700' : 
                          cand.status === 'rejected' ? 'bg-red-100 text-red-700' : 
                          'bg-emerald-100 text-emerald-700'
                        }`}>
                          {cand.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="px-8 py-6">
                        <div className="flex items-center gap-2 text-gray-500 font-medium text-xs">
                          <Clock className="w-3.5 h-3.5" />
                          {new Date(cand.updated_at).toLocaleDateString(undefined, {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric'
                          })}
                        </div>
                      </td>
                      <td className="px-8 py-6 text-right">
                        <button
                          onClick={() => navigate(`/dashboard/jobs/${cand.job_id}/candidates/${cand.candidate_id}`)}
                          className="inline-flex items-center px-5 py-2.5 bg-gray-900 border border-transparent text-white rounded-xl text-xs font-black hover:bg-blue-600 transition-all active:scale-95 shadow-sm"
                        >
                          View Profile
                        </button>
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        </div>
      )}
      {/* Add Candidate Modal */}
      <AnimatePresence>
        {showAddModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => !isSubmitting && setShowAddModal(false)}
              className="absolute inset-0 bg-slate-900/60 backdrop-blur-md"
            />
            
            <motion.div 
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: 20 }}
              className="relative w-full max-w-lg bg-white rounded-[2.5rem] shadow-2xl overflow-hidden"
            >
              <div className="p-8 border-b border-gray-50 flex items-center justify-between bg-gray-50/50">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-blue-600 rounded-xl">
                    <Plus className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h2 className="text-xl font-black text-gray-900">Add New Candidate</h2>
                    <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mt-0.5">Manual Sourcing</p>
                  </div>
                </div>
                <button 
                  onClick={() => !isSubmitting && setShowAddModal(false)}
                  className="p-2 hover:bg-gray-200 rounded-full transition-colors"
                >
                  <X className="w-5 h-5 text-gray-400" />
                </button>
              </div>

              <form onSubmit={handleAddCandidate} className="p-8 space-y-6">
                <div className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-black uppercase tracking-widest text-gray-400 mb-2 ml-1">Job Role Selection</label>
                    <div className="relative group">
                      <Briefcase className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-blue-600 transition-colors" />
                      <select 
                        required
                        value={formData.job_id}
                        onChange={(e) => setFormData({...formData, job_id: e.target.value})}
                        className="w-full pl-11 pr-6 py-4 bg-gray-50 border-2 border-transparent rounded-2xl focus:bg-white focus:border-blue-600 outline-none transition-all font-bold text-sm appearance-none"
                      >
                        <option value="">Select a role...</option>
                        {jobs.map(job => (
                          <option key={job.id} value={job.id}>{job.title}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4">
                    <div>
                      <label className="block text-[10px] font-black uppercase tracking-widest text-gray-400 mb-2 ml-1">Full Name</label>
                      <div className="relative group">
                        <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-blue-600 transition-colors" />
                        <input 
                          type="text" 
                          required
                          placeholder="John Doe"
                          value={formData.name}
                          onChange={(e) => setFormData({...formData, name: e.target.value})}
                          className="w-full pl-11 pr-6 py-4 bg-gray-50 border-2 border-transparent rounded-2xl focus:bg-white focus:border-blue-600 outline-none transition-all font-bold text-sm"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-[10px] font-black uppercase tracking-widest text-gray-400 mb-2 ml-1">Email Address</label>
                      <div className="relative group">
                        <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-blue-600 transition-colors" />
                        <input 
                          type="email" 
                          required
                          placeholder="john@example.com"
                          value={formData.email}
                          onChange={(e) => setFormData({...formData, email: e.target.value})}
                          className="w-full pl-11 pr-6 py-4 bg-gray-50 border-2 border-transparent rounded-2xl focus:bg-white focus:border-blue-600 outline-none transition-all font-bold text-sm"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-[10px] font-black uppercase tracking-widest text-gray-400 mb-2 ml-1">Phone (Optional)</label>
                      <div className="relative group">
                        <Phone className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-blue-600 transition-colors" />
                        <input 
                          type="tel" 
                          placeholder="+1 (555) 000-0000"
                          value={formData.phone}
                          onChange={(e) => setFormData({...formData, phone: e.target.value})}
                          className="w-full pl-11 pr-6 py-4 bg-gray-50 border-2 border-transparent rounded-2xl focus:bg-white focus:border-blue-600 outline-none transition-all font-bold text-sm"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="pt-4 flex gap-3">
                  <button 
                    type="button"
                    onClick={() => setShowAddModal(false)}
                    disabled={isSubmitting}
                    className="flex-1 py-4 bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-2xl font-black transition-all active:scale-95 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button 
                    type="submit"
                    disabled={isSubmitting}
                    className="flex-[2] py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-2xl font-black shadow-lg shadow-blue-200 transition-all active:scale-95 disabled:opacity-50 flex items-center justify-center"
                  >
                    {isSubmitting ? (
                      <Clock className="w-5 h-5 animate-spin" />
                    ) : (
                      'Add & Shortlist Candidate'
                    )}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
