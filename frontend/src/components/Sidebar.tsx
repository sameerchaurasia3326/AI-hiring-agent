import { useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, Users, LogOut, Briefcase, Calendar, Users2, Settings, BarChart3, CheckSquare } from 'lucide-react';
import { useUser } from '../context/UserContext';

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useUser();

  const handleLogout = () => {
    logout();
  };

  const role = user?.role;

  const navItems = [
    { name: 'Dashboard', icon: <LayoutDashboard className="w-5 h-5 mr-3" />, path: '/dashboard', roles: ['admin'] },
    { name: 'My Tasks', icon: <CheckSquare className="w-5 h-5 mr-3" />, path: '/dashboard/my-tasks', roles: ['admin', 'interviewer', 'hiring_manager'] },
    { name: 'Jobs', icon: <Briefcase className="w-5 h-5 mr-3" />, path: '/dashboard/jobs', roles: ['admin'] },
    { name: 'Candidates', icon: <Users className="w-5 h-5 mr-3" />, path: '/dashboard/candidates', roles: ['admin'] },
    { name: 'Interviews', icon: <Calendar className="w-5 h-5 mr-3" />, path: '/dashboard/interviews', roles: ['admin', 'interviewer', 'hiring_manager'] },
    { name: 'Team', icon: <Users2 className="w-5 h-5 mr-3" />, path: '/dashboard/team', roles: ['admin', 'interviewer', 'hiring_manager'] },
    { name: 'Analytics', icon: <BarChart3 className="w-5 h-5 mr-3" />, path: '/dashboard/analytics', roles: ['admin', 'interviewer', 'hiring_manager'] },
    { name: 'Settings', icon: <Settings className="w-5 h-5 mr-3" />, path: '/dashboard/settings', roles: ['admin', 'interviewer', 'hiring_manager'] },
  ];

  const filteredItems = navItems.filter(item => !item.roles || item.roles.includes(role || ''));

  return (
    <aside className="w-64 bg-slate-900 flex flex-col fixed h-full z-10">
      <div className="h-20 flex items-center px-8 cursor-pointer" onClick={() => navigate('/dashboard')}>
        <span className="text-2xl font-black text-white tracking-tighter">HIRING<span className="text-blue-500">.</span>AI</span>
      </div>

      <nav className="flex-1 px-4 py-8 space-y-1 overflow-y-auto">
        {filteredItems.map((item) => {
          // Exact match for dashboard, prefix match for others
          const isActive = item.path === '/dashboard' 
            ? location.pathname === '/dashboard' 
            : location.pathname.startsWith(item.path);

          return (
            <button
              key={item.name}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center px-4 py-3 rounded-xl transition-all font-semibold ${
                isActive
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/40' // Active
                  : 'text-slate-400 hover:text-white hover:bg-slate-800' // Inactive
              }`}
            >
              {item.icon}
              {item.name}
            </button>
          );
        })}
      </nav>

      <div className="p-6 border-t border-slate-800">
        <button 
          onClick={handleLogout} 
          className="flex w-full items-center px-4 py-3 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-xl transition-all font-medium whitespace-nowrap"
        >
          <LogOut className="w-5 h-5 mr-3" /> Sign Out
        </button>
      </div>
    </aside>
  );
}
