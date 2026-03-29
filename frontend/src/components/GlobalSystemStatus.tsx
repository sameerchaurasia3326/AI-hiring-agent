import { useEffect, useState } from 'react';
import { api } from '../services/api';

export default function GlobalSystemStatus() {
  const [status, setStatus] = useState<'idle' | 'processing' | 'error'>('idle');

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const jobs = await api.getJobs();
        // Check if any job is in a processing state
        const activeStates = ['JD_DRAFT', 'WAITING_FOR_APPLICATIONS', 'SCREENING', 'JD_APPROVAL_PENDING', 'HR_REVIEW_PENDING', 'processing'];
        const isProcessing = jobs.some((j: any) => activeStates.includes(j.status));
        setStatus(isProcessing ? 'processing' : 'idle');
      } catch (e) {
        setStatus('error');
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  if (status === 'error') {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-red-50 border border-red-100 rounded-full text-xs font-bold text-red-600 shadow-sm">
        <span className="relative flex h-2 w-2">
          <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
        </span>
        System Error
      </div>
    );
  }

  if (status === 'processing') {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-full text-xs font-bold text-amber-700 shadow-sm transition-all">
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
        </span>
        AI Processing...
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-100 rounded-full text-xs font-bold text-emerald-700 shadow-sm transition-all">
      <span className="relative flex h-2.5 w-2.5">
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
      </span>
      All systems active
    </div>
  );
}
