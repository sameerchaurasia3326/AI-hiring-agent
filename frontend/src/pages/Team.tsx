import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Users2, Mail, Shield, Calendar, CheckCircle2, XCircle, UserPlus, Loader2, Search, Filter, X, Trash2 } from 'lucide-react';
import { api } from '../services/api';

interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: string;
  is_calendar_connected: boolean;
}

export default function Team() {
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: '', role: 'interviewer' });
  const [inviting, setInviting] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const currentEmail = localStorage.getItem('hiring_ai_email');
  const userRole = localStorage.getItem('hiring_ai_role');
  const isAdmin = userRole === 'admin';

  useEffect(() => {
    fetchTeam();
  }, []);

  const fetchTeam = async () => {
    try {
      const data = await api.getTeam();
      setTeam(data);
    } catch (error) {
      console.error('Failed to fetch team:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviting(true);
    try {
      await api.inviteMember(inviteForm);
      setToast({ message: `Invite sent to ${inviteForm.email}`, type: 'success' });
      setShowInviteModal(false);
      setInviteForm({ email: '', role: 'interviewer' });
    } catch (error: any) {
      setToast({ message: error.response?.data?.detail || 'Failed to send invite', type: 'error' });
    } finally {
      setInviting(false);
    }
  };

  const handleRemove = async (member: TeamMember) => {
    if (!window.confirm(`Are you sure you want to remove ${member.name} (${member.email}) from the team?`)) {
      return;
    }

    try {
      await api.removeTeamMember(member.id);
      setToast({ message: `${member.name} removed successfully`, type: 'success' });
      fetchTeam(); // Refresh list
    } catch (error: any) {
      setToast({ message: error.response?.data?.detail || 'Failed to remove member', type: 'error' });
    }
  };

  const filteredTeam = team.filter(member => 
    member.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
    member.email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="max-w-[1240px] mx-auto animate-fade-in pb-12">
      <AnimatePresence>
        {toast && (
          <motion.div 
            initial={{ opacity: 0, y: -50 }} 
            animate={{ opacity: 1, y: 0 }} 
            exit={{ opacity: 0, scale: 0.9 }} 
            className={`fixed top-8 right-8 z-[100] px-6 py-4 rounded-xl shadow-2xl flex items-center gap-3 border ${
              toast.type === 'success' ? 'bg-white border-green-100' : 'bg-red-50 border-red-100'
            }`}
          >
            <span className="font-semibold text-gray-900">{toast.message}</span>
            <button onClick={() => setToast(null)}><X className="w-4 h-4 text-gray-400" /></button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 tracking-tight flex items-center gap-3">
            <Users2 className="w-8 h-8 text-blue-600" /> Team Management
          </h1>
          <p className="text-gray-500 mt-1">Manage your interviewers and check their calendar availability.</p>
        </div>
        {isAdmin && (
          <button 
            onClick={() => setShowInviteModal(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-xl font-bold shadow-lg shadow-blue-600/20 active:scale-95 transition-all flex items-center gap-2"
          >
            <UserPlus className="w-5 h-5" /> Invite Team Member
          </button>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="p-4 border-b border-gray-100 bg-gray-50/50 flex flex-col sm:flex-row gap-4 items-center justify-between">
          <div className="relative w-full sm:w-96">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input 
              type="text" 
              placeholder="Search by name or email..." 
              className="w-full pl-10 pr-4 py-2 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none transition-all text-sm"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500 font-medium">
            <Filter className="w-4 h-4" />
            <span>{filteredTeam.length} Members</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-gray-50 text-[10px] font-bold uppercase tracking-widest text-gray-400 border-b border-gray-100">
                <th className="px-6 py-4">Member</th>
                <th className="px-6 py-4">Role</th>
                <th className="px-6 py-4">Calendar Connection</th>
                <th className="px-6 py-4">Status</th>
                {isAdmin && <th className="px-6 py-4">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-600 mx-auto mb-2" />
                    <p className="text-gray-400 font-medium">Loading team database...</p>
                  </td>
                </tr>
              ) : filteredTeam.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center">
                    <p className="text-gray-400 font-medium">No team members found.</p>
                  </td>
                </tr>
              ) : (
                filteredTeam.map((member) => (
                  <tr key={member.id} className="hover:bg-gray-50/50 transition-colors group">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold">
                          {member.name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-bold text-gray-900">{member.name}</p>
                          <p className="text-xs text-gray-500 flex items-center gap-1">
                            <Mail className="w-3 h-3" /> {member.email}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ${
                        member.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'
                      }`}>
                        <Shield className="w-3 h-3" />
                        {member.role.replace('_', ' ').toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      {member.is_calendar_connected ? (
                        <div className="flex items-center gap-2 text-green-600 font-bold text-sm">
                          <div className="w-8 h-8 rounded-lg bg-green-100 flex items-center justify-center">
                            <Calendar className="w-4 h-4 text-green-600" />
                          </div>
                          Connected
                          <CheckCircle2 className="w-4 h-4" />
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 text-gray-400 font-medium text-sm">
                          <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
                            <Calendar className="w-4 h-4 text-gray-400" />
                          </div>
                          Not Connected
                          <XCircle className="w-4 h-4" />
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <span className="w-2 h-2 rounded-full bg-green-500 inline-block mr-2 ring-4 ring-green-100 animate-pulse" />
                      <span className="text-sm font-semibold text-gray-700">Active</span>
                    </td>
                    {isAdmin && (
                      <td className="px-6 py-4">
                        {member.email !== currentEmail && (
                          <button 
                            onClick={() => handleRemove(member)}
                            className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                            title="Remove from team"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Invite Modal */}
      <AnimatePresence>
        {showInviteModal && (
          <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 overflow-hidden">
            <motion.div 
              initial={{ opacity: 0 }} 
              animate={{ opacity: 1 }} 
              exit={{ opacity: 0 }}
              onClick={() => setShowInviteModal(false)}
              className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm"
            />
            <motion.div 
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: 20 }}
              className="relative w-full max-w-md bg-white rounded-3xl shadow-2xl overflow-hidden p-8"
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-black text-gray-900 tracking-tight">Invite Team Member</h2>
                <button onClick={() => setShowInviteModal(false)} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
                  <X className="w-5 h-5 text-gray-400" />
                </button>
              </div>

              <form onSubmit={handleInvite} className="space-y-6">
                <div>
                  <label className="block text-sm font-bold text-gray-700 mb-2">Email Address</label>
                  <input 
                    type="email" 
                    required
                    placeholder="interviewer@company.com"
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                    value={inviteForm.email}
                    onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-gray-700 mb-2">Platform Role</label>
                  <select 
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-blue-500 outline-none transition-all bg-white"
                    value={inviteForm.role}
                    onChange={(e) => setInviteForm({ ...inviteForm, role: e.target.value })}
                  >
                    <option value="interviewer">Interviewer (Can only see assigned candidates)</option>
                    <option value="hiring_manager">Hiring Manager (Can see all jobs)</option>
                  </select>
                </div>
                
                <div className="pt-2">
                  <p className="text-xs text-gray-500 leading-relaxed mb-6">
                    We will send an invitation email to this address. They will be prompted to create an account and join your organization.
                  </p>
                  <button 
                    disabled={inviting}
                    type="submit" 
                    className="w-full bg-blue-600 hover:bg-blue-700 text-white py-4 rounded-2xl font-black shadow-xl shadow-blue-600/20 active:scale-95 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {inviting ? <><Loader2 className="w-5 h-5 animate-spin" /> Sending...</> : 'Send Invitation Email'}
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
