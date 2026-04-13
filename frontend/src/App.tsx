import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, Calendar } from 'lucide-react';

// Pages
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
import Settings from './pages/Settings';
import AcceptInvite from './pages/AcceptInvite';
import AuthCallback from './pages/AuthCallback';
import Placeholder from './pages/Placeholder';

// Layouts & Context
import DashboardLayout from './layouts/DashboardLayout';
import { UserProvider, useUser } from './context/UserContext';

/**
 * RootRedirect: Intelligent base-URL routing
 * Handles users landing on '/' by checking their session and role.
 */
const RootRedirect = () => {
  const { user, loading } = useUser();
  
  if (loading) {
    return (
      <div className="h-screen w-full flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-950">
        <Loader2 className="w-10 h-10 text-blue-500 animate-spin mb-4" />
        <p className="text-slate-500 font-medium animate-pulse">Syncing Session...</p>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;
  
  return user.role === 'interviewer' 
    ? <Navigate to="/dashboard/my-tasks" replace /> 
    : <Navigate to="/dashboard" replace />;
};

/**
 * ProtectedRoute: Comprehensive Auth & RBAC Guard
 * Ensures user is authenticated and has the required role.
 */
const ProtectedRoute = ({ children, allowedRoles = [] }: { children: React.ReactNode, allowedRoles?: string[] }) => {
  const { user, loading } = useUser();
  
  if (loading) {
    return (
      <div className="h-screen w-full flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-950">
        <Loader2 className="w-10 h-10 text-blue-500 animate-spin mb-4" />
        <p className="text-slate-500 font-medium animate-pulse">Syncing Session...</p>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Role-Based Access Control
  if (allowedRoles.length > 0 && !allowedRoles.includes(user.role || '')) {
    console.warn(`🛡️ [RBAC] Role '${user.role}' not authorized for this route. Required:`, allowedRoles);
    return user.role === 'interviewer' 
      ? <Navigate to="/dashboard/my-tasks" replace /> 
      : <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

const PageWrapper = ({ children }: { children: React.ReactNode }) => (
  <motion.div
    initial={{ opacity: 0, scale: 0.98, filter: 'blur(4px)' }}
    animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
    exit={{ opacity: 0, scale: 1.00, filter: 'blur(4px)' }}
    transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
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
        {/* Absolute Root */}
        <Route path="/" element={<RootRedirect />} />
        
        {/* Public Routes */}
        <Route path="/login" element={<PageWrapper><Login /></PageWrapper>} />
        <Route path="/signup" element={<PageWrapper><Signup /></PageWrapper>} />
        <Route path="/accept-invite/:token" element={<PageWrapper><AcceptInvite /></PageWrapper>} />
        <Route path="/auth/callback" element={<PageWrapper><AuthCallback /></PageWrapper>} />

        {/* Protected Dashboard Shell with Path Prefix */}
        <Route 
          path="/dashboard"
          element={
            <ProtectedRoute allowedRoles={['admin', 'interviewer', 'hiring_manager']}>
              <DashboardLayout />
            </ProtectedRoute>
          } 
        >
          {/* Default Dashboard (Admin) */}
          <Route index element={<ProtectedRoute allowedRoles={['admin']}><PageWrapper><Dashboard /></PageWrapper></ProtectedRoute>} />
          
          {/* Modular Feature Routes */}
          <Route path="jobs" element={<ProtectedRoute allowedRoles={['admin']}><PageWrapper><Dashboard /></PageWrapper></ProtectedRoute>} />
          <Route path="jobs/new" element={<ProtectedRoute allowedRoles={['admin']}><PageWrapper><CreateJob /></PageWrapper></ProtectedRoute>} />
          <Route path="jobs/:job_id" element={<ProtectedRoute allowedRoles={['admin']}><PageWrapper><JobDetail /></PageWrapper></ProtectedRoute>} />
          <Route path="jobs/:job_id/candidates/:candidate_id" element={<ProtectedRoute allowedRoles={['admin']}><PageWrapper><CandidateDetail /></PageWrapper></ProtectedRoute>} />
          <Route path="candidates" element={<ProtectedRoute allowedRoles={['admin', 'hiring_manager']}><PageWrapper><Candidates /></PageWrapper></ProtectedRoute>} />
          <Route path="team" element={<ProtectedRoute allowedRoles={['admin', 'interviewer']}><PageWrapper><Team /></PageWrapper></ProtectedRoute>} />
          <Route path="analytics" element={<ProtectedRoute allowedRoles={['admin', 'interviewer']}><PageWrapper><Analytics /></PageWrapper></ProtectedRoute>} />
          <Route path="settings" element={<ProtectedRoute allowedRoles={['admin', 'interviewer']}><PageWrapper><Settings /></PageWrapper></ProtectedRoute>} />

          {/* Shared / Interviewer Workflow */}
          <Route path="my-tasks" element={<PageWrapper><MyTasks /></PageWrapper>} />
          <Route path="interviews" element={<PageWrapper><Placeholder title="Interviews" icon={Calendar} /></PageWrapper>} />
        </Route>
        
        {/* Helper Alias for Interviewers per legacy request */}
        <Route path="/interviewer" element={<Navigate to="/dashboard/my-tasks" replace />} />
        
        {/* Global Fallback to avoid infinite loops */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  );
};

function App() {
  return (
    <UserProvider>
      <Router>
        <AnimatedRoutes />
      </Router>
    </UserProvider>
  );
}

export default App;
