import { motion } from 'framer-motion';

export default function SignBoard() {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.5, y: 20 }}
      animate={{
        opacity: 1,
        scale: [1, 1.05, 1],
        y: [0, -10, 0],
        rotate: [-1, 1, -1]
      }}
      transition={{
        duration: 4,
        repeat: Infinity,
        ease: "easeInOut",
        delay: 0.5
      }}
      className="relative z-20 flex flex-col items-center justify-center pointer-events-none"
      style={{ 
        filter: 'drop-shadow(0 10px 30px rgba(247, 99, 195, 0.6))'
      }}
    >
      <div className="relative group">
        {/* Animated Glow underlay - More vibrant */}
        <motion.div 
          animate={{ 
            opacity: [0.6, 0.9, 0.6],
            scale: [0.95, 1.05, 0.95]
          }}
          transition={{ duration: 3, repeat: Infinity }}
          className="absolute -inset-2 bg-gradient-to-r from-[#F763C3] via-[#9333EA] to-[#F763C3] rounded-[2rem] blur-xl opacity-80"
        />
        
        {/* The Speech Bubble Card - More solid for readability */}
        <div className="relative px-10 py-5 bg-gradient-to-br from-white/20 to-purple-900/40 backdrop-blur-2xl border border-white/30 rounded-2xl flex items-center justify-center shadow-2xl">
          <h2 className="text-xl sm:text-2xl font-bold text-white tracking-widest drop-shadow-md">
            Hi, welcome to Hiring.AI
          </h2>
          
          {/* Subtle bubble tail/indicator */}
          <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-4 h-4 bg-[#9333EA]/60 rotate-45 border-r border-b border-white/20" />
        </div>
      </div>
    </motion.div>
  );
}
