import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

const AuthCallback = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const token = searchParams.get('token');
    const role = searchParams.get('role');
    const email = searchParams.get('email');

    console.log("🔍 [CALLBACK] Params detected:", { hasToken: !!token, role, email });

    if (token) {
      // [NUCLEAR] Clear all old session state before saving new credentials to prevent crossover
      localStorage.clear();
      sessionStorage.clear();

      localStorage.setItem('hiring_ai_token', token);
      if (role) localStorage.setItem('hiring_ai_role', role);
      if (email) localStorage.setItem('hiring_ai_email', email);
      
      console.info("✅ [CALLBACK] Session stored. Navigating to functional area...");

      // Use navigate() instead of window.location.href to maintain SPA state and prevent race conditions
      if (role === 'interviewer') {
        navigate('/dashboard/my-tasks', { replace: true });
      } else {
        navigate('/dashboard', { replace: true });
      }
    } else {
      console.error("❌ [CALLBACK] Missing token in URL redirect. Returning to login.");
      // Missing token, go back to login
      navigate('/login?error=missing_token', { replace: true });
    }
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900">
      <Loader2 className="w-12 h-12 text-blue-600 animate-spin mb-4" />
      <h2 className="text-xl font-medium text-slate-700 dark:text-slate-300 tracking-tight">Authenticating...</h2>
      <p className="text-slate-500 dark:text-slate-400 mt-2 text-sm">Finishing your secure sign-in.</p>
    </div>
  );
};

export default AuthCallback;
