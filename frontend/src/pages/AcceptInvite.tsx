import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { api } from '../services/api';

export default function AcceptInvite() {
  const { token } = useParams();
  
  const [formData, setFormData] = useState({ name: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleAccept = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await api.acceptInvite({
        token: token || '',
        name: formData.name,
        password: formData.password
      });

      if (res.access_token) {
        localStorage.setItem('hiring_ai_token', res.access_token);
        localStorage.setItem('hiring_ai_email', res.email);
        localStorage.setItem('hiring_ai_role', res.role);
        localStorage.setItem('hiring_ai_name', res.name);
      }

      setSuccess(true);
      
      // Auto redirect based on role after short delay
      setTimeout(() => {
        window.location.href = res.role === 'admin' ? '/dashboard' : '/dashboard/my-tasks';
      }, 1500);
      
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to accept invitation. It may have expired.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-50 p-4">
        <motion.div initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} className="bg-white rounded-2xl shadow-xl p-8 max-w-sm w-full text-center border border-gray-100">
          <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-green-100 mb-6">
            <CheckCircle2 className="h-8 w-8 text-green-600" />
          </div>
          <h3 className="text-2xl font-bold text-gray-900 mb-2">Welcome to the Team!</h3>
          <p className="text-sm text-gray-500 mb-6">Your account is ready. Redirecting to your dashboard...</p>
          <Loader2 className="w-6 h-6 animate-spin text-blue-600 mx-auto" />
        </motion.div>
      </div>
    );
  }

  return (
    <div className="h-screen w-full flex items-center justify-center bg-gray-50 p-4">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md bg-white rounded-2xl shadow-xl p-8 border border-gray-100">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 tracking-tight">Accept Invitation</h1>
          <p className="text-sm text-gray-500 mt-2">Set up your profile to join the workspace</p>
        </div>

        <AnimatePresence mode="wait">
          {error && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="mb-6 p-4 bg-red-50 border-l-4 border-red-500 text-red-700 text-sm rounded-r flex items-start">
              <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
              <span>{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        <form onSubmit={handleAccept} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
            <input 
              type="text" 
              required 
              value={formData.name}
              onChange={(e) => setFormData({...formData, name: e.target.value})}
              placeholder="Jane Doe" 
              className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 shadow-sm outline-none bg-gray-50 focus:bg-white text-gray-900"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Create Password</label>
            <input 
              type="password" 
              required 
              minLength={8}
              value={formData.password}
              onChange={(e) => setFormData({...formData, password: e.target.value})}
              placeholder="••••••••" 
              className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 shadow-sm outline-none bg-gray-50 focus:bg-white text-gray-900"
            />
          </div>

          <button 
            type="submit" 
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 rounded-lg shadow-md transition-all flex justify-center items-center mt-2 disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Join Workspace'}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
