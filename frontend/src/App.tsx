import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import JobDetail from './pages/JobDetail';
import CreateJob from './pages/CreateJob';
import MyTasks from './pages/MyTasks';
import CandidateDetail from './pages/CandidateDetail';
import Analytics from './pages/Analytics';
import Candidates from './pages/Candidates';
import Team from './pages/Team';
import DashboardLayout from './layouts/DashboardLayout';
import Placeholder from './pages/Placeholder';
import Settings from './pages/Settings';
import { Calendar } from 'lucide-react';

import AcceptInvite from './pages/AcceptInvite';
import AuthCallback from './pages/AuthCallback';

// JWT Decoder Utility
const parseJwt = (token: string) => {
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch (e) {
    return null;
  }
};

// Simple Auth Guard
const ProtectedRoute = ({ children, allowedRoles = [] }: { children: React.ReactNode, allowedRoles?: string[] }) => {
  const token = localStorage.getItem('hiring_ai_token');
  
  if (!token) return <Navigate to="/login" replace />;

  const decoded = parseJwt(token);
  
  // If token is formally tampered with or malformed
  if (!decoded) {
    localStorage.removeItem('hiring_ai_token');
    localStorage.removeItem('hiring_ai_role');
    return <Navigate to="/login" replace />;
  }

  // Cryptographic Expiration Check (JWT `exp` is in seconds, JS Date.now() is ms)
  const isExpired = decoded.exp * 1000 < Date.now();
  if (isExpired) {
    localStorage.removeItem('hiring_ai_token');
    localStorage.removeItem('hiring_ai_role');
    return <Navigate to="/login" replace />;
  }

  // Trusted Extracted State
  const role = decoded.role || localStorage.getItem('hiring_ai_role'); 
  
  if (allowedRoles.length > 0 && !allowedRoles.includes(role || '')) {
    // Redirect interviewer to tasks automatically
    if (role === 'interviewer') return <Navigate to="/dashboard/my-tasks" replace />;
    return <Navigate to="/dashboard" replace />;
  }

  return children;
};

const PageWrapper = ({ children }: { children: React.ReactNode }) => (
  <motion.div
    initial={{ opacity: 0, scale: 0.98, filter: 'blur(4px)' }}
    animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
    exit={{ opacity: 0, scale: 1.02, filter: 'blur(4px)' }}
    transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
    className="h-full w-full"
  >
    {children}
  </motion.div>
);

const AnimatedRoutes = () => {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        {/* Public Routes */}
        <Route path="/" element={<Navigate to="/login" />} />
        <Route path="/login" element={<PageWrapper><Login /></PageWrapper>} />
        <Route path="/signup" element={<PageWrapper><Signup /></PageWrapper>} />
        <Route path="/accept-invite/:token" element={<PageWrapper><AcceptInvite /></PageWrapper>} />
        <Route path="/auth/callback" element={<PageWrapper><AuthCallback /></PageWrapper>} />

        {/* Protected Admin Routes */}
        <Route 
          path="/dashboard" 
          element={
            <ProtectedRoute allowedRoles={['admin', 'interviewer', 'hiring_manager']}>
              <PageWrapper>
                <DashboardLayout />
              </PageWrapper>
            </ProtectedRoute>
          } 
        >
          <Route path="" element={<Dashboard />} />
          <Route path="jobs" element={<Dashboard />} />
          <Route path="jobs/new" element={<CreateJob />} />
          <Route path="jobs/:job_id" element={<JobDetail />} />
          <Route path="jobs/:job_id/candidates/:candidate_id" element={<CandidateDetail />} />
          <Route path="my-tasks" element={<MyTasks />} />
          <Route path="candidates" element={<Candidates />} />
          <Route path="interviews" element={<Placeholder title="Interviews" icon={Calendar} />} />
          <Route path="team" element={<Team />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        
        {/* Protected Interviewer Routes */}
        <Route 
          path="/my-tasks" 
          element={
            <ProtectedRoute allowedRoles={['admin', 'interviewer', 'hiring_manager']}>
              <Navigate to="/dashboard/my-tasks" replace />
            </ProtectedRoute>
          } 
        />
        
        {/* Fallback */}
        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    </AnimatePresence>
  );
};

function App() {
  return (
    <Router>
      <AnimatedRoutes />
    </Router>
  );
}

export default App;
