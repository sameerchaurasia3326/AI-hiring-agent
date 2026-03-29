import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Users, Mail, CheckCircle2, Clock, Search, Send, CheckSquare, Square } from 'lucide-react';
import { api } from '../services/api';

interface Candidate {
  id: string;
  name: string;
  email: string;
  status: string;
  job_title: string;
  rejected_at_stage: string;
  rejection_email_sent: boolean;
  rejected_at: string | null;
}

export default function Candidates() {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('rejected');
  const [searchTerm, setSearchTerm] = useState('');
  const [sendingEmailId, setSendingEmailId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isBulkSending, setIsBulkSending] = useState(false);

  const fetchCandidates = async () => {
    try {
      setLoading(true);
      const data = await api.getCandidates({ status: filter });
      setCandidates(data);
      setSelectedIds(new Set()); // Reset selection on fetch
    } catch (err: any) {
      console.error('Failed to fetch candidates:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
  }, [filter]);

  const handleSendEmail = async (candidateId: string) => {
    try {
      setSendingEmailId(candidateId);
      await api.sendRejectionEmail(candidateId);
      await fetchCandidates();
    } catch (err: any) {
      console.error('Failed to send rejection email:', err);
      alert(err.response?.data?.detail || 'Failed to send email. Please try again.');
    } finally {
      setSendingEmailId(null);
    }
  };

  const handleBulkSend = async () => {
    if (selectedIds.size === 0) return;
    try {
      setIsBulkSending(true);
      await api.bulkSendRejectionEmail(Array.from(selectedIds));
      await fetchCandidates();
      alert(`Successfully processed ${selectedIds.size} candidates.`);
    } catch (err: any) {
      console.error('Failed to send bulk emails:', err);
      alert('Failed to send bulk emails. Some may have failed.');
    } finally {
      setIsBulkSending(false);
    }
  };

  const toggleSelect = (id: string) => {
    const newSelection = new Set(selectedIds);
    if (newSelection.has(id)) newSelection.delete(id);
    else newSelection.add(id);
    setSelectedIds(newSelection);
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredCandidates.length) {
      setSelectedIds(new Set());
    } else {
      const eligible = filteredCandidates
        .filter(c => c.status === 'rejected' && !c.rejection_email_sent)
        .map(c => c.id);
      setSelectedIds(new Set(eligible));
    }
  };

  const filteredCandidates = candidates.filter(c => 
    c.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
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
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-5xl font-black text-gray-900 tracking-tight">Candidates</h1>
            <p className="text-gray-500 mt-3 text-lg font-medium">Manage and communicate with talent across all your hiring pipelines.</p>
          </div>
          
          <AnimatePresence>
            {selectedIds.size > 0 && (
              <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
                className="flex items-center gap-4 bg-blue-600 p-2 pl-6 rounded-2xl shadow-xl shadow-blue-200"
              >
                <span className="text-white font-black text-sm uppercase tracking-widest">{selectedIds.size} Selected</span>
                <button 
                  onClick={handleBulkSend}
                  disabled={isBulkSending}
                  className="bg-white text-blue-600 px-6 py-3 rounded-xl font-black text-xs hover:bg-gray-50 transition-colors flex items-center gap-2"
                >
                  {isBulkSending ? <Clock className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  Send Bulk Rejection
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </header>

      {/* Primary Tabs & Filters */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-10">
        <div className="flex items-center bg-gray-100 p-1 rounded-2xl w-fit">
          <button 
            onClick={() => setFilter('rejected')}
            className={`px-6 py-2.5 rounded-xl text-sm font-black transition-all ${filter === 'rejected' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-400 hover:text-gray-600'}`}
          >
            Rejected
          </button>
          <button 
            onClick={() => setFilter('')}
            className={`px-6 py-2.5 rounded-xl text-sm font-black transition-all ${filter === '' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-400 hover:text-gray-600'}`}
          >
            All Candidates
          </button>
        </div>

        <div className="relative group">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-blue-600 transition-colors" />
          <input 
            type="text" 
            placeholder="Search by name, email, or job..."
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
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-50 text-[10px] font-black uppercase tracking-[0.2em] text-gray-400">
                  <th className="px-8 py-6 w-10">
                    <button onClick={toggleSelectAll} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
                      {selectedIds.size === filteredCandidates.length && filteredCandidates.length > 0
                        ? <CheckSquare className="w-4 h-4 text-blue-600" />
                        : <Square className="w-4 h-4 text-gray-300" />}
                    </button>
                  </th>
                  <th className="px-8 py-6">Candidate</th>
                  <th className="px-8 py-6">Job Pipeline</th>
                  <th className="px-8 py-6">Rejected At</th>
                  <th className="px-8 py-6">Communication</th>
                  <th className="px-8 py-6 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                <AnimatePresence>
                  {filteredCandidates.map((cand, idx) => {
                    const isEligible = cand.status === 'rejected' && !cand.rejection_email_sent;
                    return (
                      <motion.tr 
                        key={cand.id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.03 }}
                        className={`group hover:bg-gray-50/50 transition-colors ${selectedIds.has(cand.id) ? 'bg-blue-50/30' : ''}`}
                      >
                        <td className="px-8 py-6 w-10">
                          {isEligible ? (
                            <button onClick={() => toggleSelect(cand.id)} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
                              {selectedIds.has(cand.id) 
                                ? <CheckSquare className="w-4 h-4 text-blue-600" />
                                : <Square className="w-4 h-4 text-gray-300" />}
                            </button>
                          ) : (
                            <Square className="w-4 h-4 text-gray-100 cursor-not-allowed" />
                          )}
                        </td>
                        <td className="px-8 py-6">
                          <div className="flex items-center gap-4">
                            <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center text-white text-xs font-black shadow-lg shadow-slate-200">
                              {cand.name.charAt(0)}
                            </div>
                            <div>
                              <p className="font-bold text-gray-900 leading-tight group-hover:text-blue-600 transition-colors cursor-pointer" onClick={() => navigate(`/dashboard/jobs/any/candidates/${cand.id}`)}>
                                {cand.name}
                              </p>
                              <p className="text-xs text-gray-400 font-medium mt-0.5">{cand.email}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-8 py-6">
                          <div className="flex flex-col">
                            <span className="text-sm font-bold text-gray-700">{cand.job_title}</span>
                            <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest mt-1">Stage: {cand.rejected_at_stage}</span>
                          </div>
                        </td>
                        <td className="px-8 py-6">
                          <div className="flex items-center gap-2 text-gray-500 font-medium text-xs">
                            <Clock className="w-3.5 h-3.5" />
                            {cand.rejected_at ? new Date(cand.rejected_at).toLocaleDateString() : 'N/A'}
                          </div>
                        </td>
                        <td className="px-8 py-6">
                          {cand.rejection_email_sent ? (
                            <div className="flex items-center gap-2 text-emerald-600 font-black text-[10px] uppercase tracking-widest bg-emerald-50 px-3 py-1.5 rounded-full border border-emerald-100 w-fit">
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              Email Sent
                            </div>
                          ) : (
                            <div className="flex items-center gap-2 text-amber-600 font-black text-[10px] uppercase tracking-widest bg-amber-50 px-3 py-1.5 rounded-full border border-amber-100 w-fit">
                              <Mail className="w-3.5 h-3.5" />
                              Pending
                            </div>
                          )}
                        </td>
                        <td className="px-8 py-6 text-right">
                          {cand.status === 'rejected' && (
                            <button
                              disabled={cand.rejection_email_sent || sendingEmailId === cand.id}
                              onClick={() => handleSendEmail(cand.id)}
                              className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-xs transition-all shadow-sm ${
                                cand.rejection_email_sent 
                                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed border border-gray-200'
                                  : 'bg-slate-900 border border-slate-950 text-white hover:bg-blue-600 hover:border-blue-700 active:scale-95'
                              }`}
                            >
                              {sendingEmailId === cand.id ? (
                                <>
                                  <Clock className="w-3.5 h-3.5 animate-spin" />
                                  Sending...
                                </>
                              ) : cand.rejection_email_sent ? (
                                <>
                                  <CheckCircle2 className="w-3.5 h-3.5" />
                                  Sent
                                </>
                              ) : (
                                <>
                                  <Send className="w-3.5 h-3.5" />
                                  Send Email
                                </>
                              )}
                            </button>
                          )}
                        </td>
                      </motion.tr>
                    );
                  })}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
