import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, Eye, EyeOff, Sun, Moon } from 'lucide-react';
import { api } from '../services/api';
import HeroSection from '../components/HeroSection';

const Particles = () => {
  const particles = Array.from({ length: 30 });
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
      {particles.map((_, i) => {
        const left = Math.random() * 100;
        const top = Math.random() * 100;
        const duration = Math.random() * 15 + 10;
        return (
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0, x: `${left}vw`, y: `${top}vh` }}
            animate={{ opacity: [0, 0.4, 0], scale: [0, 1.5, 0], y: [`${top}vh`, `${top - 20}vh`] }}
            transition={{ duration, repeat: Infinity, delay: Math.random() * 5 }}
            className="absolute rounded-full w-1.5 h-1.5 bg-white/40 dark:bg-indigo-400/50"
          />
        );
      })}
    </div>
  );
};

export default function Signup() {
  const [formData, setFormData] = useState({ company_name: '', email: '', password: '' });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem('theme');
    if (saved) return saved === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  useEffect(() => {
    if (isDark) { document.documentElement.classList.add('dark'); localStorage.setItem('theme', 'dark'); } 
    else { document.documentElement.classList.remove('dark'); localStorage.setItem('theme', 'light'); }
  }, [isDark]);

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await api.signup({
        email: formData.email,
        password: formData.password,
        company_name: formData.company_name
      });
      navigate('/login');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center p-4 sm:p-8 lg:p-12 bg-[#94A3B8] dark:bg-slate-950 transition-colors duration-300 relative overflow-hidden">
      <Particles />

      {/* Master Floating Card */}
      <div className="w-full max-w-6xl flex flex-col lg:flex-row bg-white dark:bg-slate-900 rounded-[2.5rem] overflow-hidden shadow-2xl min-h-[720px] relative">
        
        {/* Top-Right Theme Toggle */}
        <button onClick={() => setIsDark(!isDark)} className="absolute top-6 right-6 z-50 p-3 bg-white/80 dark:bg-slate-800/80 backdrop-blur-md rounded-full shadow-sm text-slate-500 dark:text-slate-400 hover:scale-105 transition-transform flex items-center justify-center">
           <AnimatePresence mode="wait">
             <motion.div key={isDark ? "dark" : "light"} initial={{ scale: 0, rotate: -90 }} animate={{ scale: 1, rotate: 0 }} exit={{ scale: 0, rotate: 90 }} transition={{ duration: 0.2 }}>
               {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
             </motion.div>
           </AnimatePresence>
        </button>

        {/* Left Form Pane */}
        <div className="w-full lg:w-[50%] flex flex-col relative bg-gradient-to-br from-[#FDFBF2] to-[#F1EBD0] dark:from-slate-800 dark:to-slate-900 p-8 sm:p-12 lg:p-16">
          
          {/* Logo Pill */}
          <div className="inline-flex items-center px-[1.125rem] py-1.5 rounded-[2rem] border border-slate-300 dark:border-white/10 text-sm font-medium text-slate-700 dark:text-slate-300 bg-transparent w-max mb-12 lg:mb-0 lg:absolute lg:top-10 lg:left-12">
            Hiring.AI
          </div>

          <div className="flex-1 flex flex-col items-center justify-center w-full relative z-10 pt-4 lg:pt-0">
            <div className="w-full max-w-[340px]">
              <h1 className="text-[1.75rem] leading-tight text-slate-800 dark:text-white font-medium text-center mb-1">Create an account</h1>
              <p className="text-slate-500 dark:text-slate-400 text-[13px] text-center mb-8">Sign up and get 30 day free trial</p>

              {error && (
                <div className="mb-6 p-4 bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 text-sm rounded-xl">
                  {error}
                </div>
              )}

              <form className="space-y-[1.15rem]" onSubmit={handleSignup}>
                <div>
                  <label className="block text-[11px] text-slate-500 dark:text-slate-400 mb-1.5 ml-4 font-medium">Company name</label>
                  <input required placeholder="Acme Corp" value={formData.company_name} onChange={e => setFormData({...formData, company_name: e.target.value})} className="w-full px-6 py-[0.85rem] rounded-[2rem] bg-white dark:bg-slate-800/80 border-none shadow-sm text-[13px] placeholder:text-slate-300 dark:placeholder:text-slate-500 outline-none focus:ring-2 focus:ring-[#FACC15] transition-all text-slate-700 dark:text-white" />
                </div>
                
                <div>
                  <label className="block text-[11px] text-slate-500 dark:text-slate-400 mb-1.5 ml-4 font-medium">Email</label>
                  <input required type="email" placeholder="amelia@company.com" value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} className="w-full px-6 py-[0.85rem] rounded-[2rem] bg-white dark:bg-slate-800/80 border-none shadow-sm text-[13px] placeholder:text-slate-300 dark:placeholder:text-slate-500 outline-none focus:ring-2 focus:ring-[#FACC15] transition-all text-slate-700 dark:text-white" />
                </div>

                <div className="relative">
                  <label className="block text-[11px] text-slate-500 dark:text-slate-400 mb-1.5 ml-4 font-medium">Password</label>
                  <div className="relative">
                    <input required type={showPassword ? "text" : "password"} placeholder="••••••••••••••••" value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})} className="w-full pl-6 pr-12 py-[0.85rem] rounded-[2rem] bg-white dark:bg-slate-800/80 border-none shadow-sm text-[13px] placeholder:text-slate-300 dark:placeholder:text-slate-500 outline-none focus:ring-2 focus:ring-[#FACC15] transition-all text-slate-700 dark:text-white" />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-4 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-white transition-colors">
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                
                <button type="submit" disabled={loading} className="w-full mt-8 py-[0.85rem] rounded-[2rem] bg-[#FACC15] hover:bg-[#EAB308] disabled:bg-[#fde047] disabled:cursor-not-allowed shadow-[0_4px_14px_0_rgba(250,204,21,0.39)] text-slate-900 text-[13px] font-medium transition-all flex items-center justify-center mt-6">
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Submit'}
                </button>

                <div className="flex gap-4 mt-4">
                  <button type="button" className="flex-1 flex items-center justify-center gap-2 py-[0.65rem] rounded-[2rem] border border-slate-300/80 dark:border-white/10 bg-transparent text-[11px] font-semibold text-slate-700 dark:text-slate-300 hover:bg-white/50 dark:hover:bg-slate-800/50 transition-colors shadow-sm">
                    {/* Apple Icon SVG */}
                    <svg viewBox="0 0 384 512" className="w-[14px] h-[14px] fill-current text-slate-800 dark:text-white"><path d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z"/></svg> 
                    Apple
                  </button>
                  <button type="button" className="flex-1 flex items-center justify-center gap-2 py-[0.65rem] rounded-[2rem] border border-slate-300/80 dark:border-white/10 bg-transparent text-[11px] font-semibold text-slate-700 dark:text-slate-300 hover:bg-white/50 dark:hover:bg-slate-800/50 transition-colors shadow-sm">
                     {/* Google Icon SVG */}
                    <svg viewBox="0 0 24 24" className="w-[14px] h-[14px]"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
                    Google
                  </button>
                </div>
              </form>
            </div>
          </div>

          <div className="flex justify-between items-center w-full text-[10px] sm:text-[11px] text-slate-500 dark:text-slate-400 mt-12 lg:mt-0 lg:absolute lg:bottom-10 lg:left-0 lg:px-12 xl:px-16 w-full">
            <span>Have any account? <Link to="/login" className="font-semibold text-slate-800 dark:text-white hover:underline underline-offset-2">Sign in</Link></span>
            <span className="underline underline-offset-2 hover:text-slate-700 dark:hover:text-slate-200 cursor-pointer transition-colors">Terms & Conditions</span>
          </div>

        </div>

        {/* Right Image Pane */}
        <div className="w-full lg:w-[50%] relative bg-slate-900 hidden sm:block min-h-[300px] lg:min-h-0">
          <div className="w-full h-full relative overflow-hidden lg:rounded-bl-none shadow-[20px_20px_60px_rgba(0,0,0,0.5)] flex items-center justify-center">
            
            <div className="absolute inset-0 xl:scale-100 flex items-center justify-center">
               <HeroSection />
            </div>

            {/* Soft inner glow overlay for dynamic lighting */}
            <div className="absolute inset-0 ring-1 ring-inset ring-white/10 rounded-[2rem] pointer-events-none" />
          </div>
        </div>
        
      </div>
    </div>
  );
}
