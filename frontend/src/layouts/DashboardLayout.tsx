import { Outlet } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import GlobalSystemStatus from '../components/GlobalSystemStatus';

export default function DashboardLayout() {
  return (
    <div className="min-h-screen bg-gray-50 flex">
      <Sidebar />
      <div className="flex-1 ml-64 flex flex-col min-h-screen">
        <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-end px-8 sticky top-0 z-30 shadow-sm">
          <GlobalSystemStatus />
        </header>
        <main className="flex-1 p-8 relative">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
