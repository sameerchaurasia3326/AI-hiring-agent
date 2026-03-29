import { motion } from 'framer-motion';
import { Hammer } from 'lucide-react';

export default function Placeholder({ title, icon: Icon }: { title: string, icon: any }) {
  return (
    <div className="h-[80vh] w-full flex flex-col items-center justify-center">
      <motion.div 
        initial={{ opacity: 0, scale: 0.9, y: 20 }} 
        animate={{ opacity: 1, scale: 1, y: 0 }} 
        className="bg-white p-12 rounded-3xl shadow-sm border border-gray-100 flex flex-col items-center max-w-md text-center"
      >
        <div className="w-20 h-20 bg-blue-50 rounded-3xl flex items-center justify-center mb-6 relative">
          <Icon className="w-10 h-10 text-blue-600 opacity-50" />
          <div className="absolute -bottom-2 -right-2 bg-slate-900 border-4 border-white p-2 rounded-full">
            <Hammer className="w-4 h-4 text-amber-400" />
          </div>
        </div>
        <h2 className="text-3xl font-bold text-gray-900 mb-3 tracking-tight">{title}</h2>
        <p className="text-gray-500 mb-8 leading-relaxed">
          This feature is currently under active development. Our AI agents are building out the new functionality for the {title} module.
        </p>
        <div className="inline-flex items-center gap-2 bg-amber-50 text-amber-700 px-4 py-2 rounded-full text-xs font-black uppercase tracking-widest border border-amber-200">
          <span className="relative flex h-2 w-2 mr-1">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
          </span>
          Coming Soon
        </div>
      </motion.div>
    </div>
  );
}
