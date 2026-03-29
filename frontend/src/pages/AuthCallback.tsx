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

    if (token) {
      localStorage.setItem('hiring_ai_token', token);
      if (role) localStorage.setItem('hiring_ai_role', role);
      if (email) localStorage.setItem('hiring_ai_email', email);
      
      // Navigate to dashboard
      navigate('/dashboard', { replace: true });
    } else {
      // Missing token, go back to login
      navigate('/login', { replace: true });
    }
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-900">
      <Loader2 className="w-12 h-12 text-blue-600 animate-spin mb-4" />
      <h2 className="text-xl font-medium text-slate-700 dark:text-slate-300">Authenticating...</h2>
      <p className="text-slate-500 dark:text-slate-400 mt-2">Setting up your session.</p>
    </div>
  );
};

export default AuthCallback;
