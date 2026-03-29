import { motion } from "framer-motion";

export default function Background() {
  const stars = Array.from({ length: 80 });
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none z-0 bg-gradient-to-br from-[#0B0118] via-[#120B2E] to-[#040D21]">
      
      {/* Deep Space Depth Layers */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(147,51,234,0.15),transparent_70%)]" />
      
      {/* Twinkling Stars */}
      {stars.map((_, i) => {
        const left = Math.random() * 100;
        const top = Math.random() * 100;
        const size = Math.random() * 2 + 0.5;
        const duration = Math.random() * 3 + 2;
        const delay = Math.random() * 5;
        
        return (
          <motion.div
            key={i}
            initial={{ opacity: 0.2 }}
            animate={{ 
              opacity: [0.2, 0.8, 0.2],
              scale: [1, 1.2, 1],
            }}
            transition={{ 
              duration, 
              repeat: Infinity, 
              delay,
              ease: "easeInOut" 
            }}
            style={{ 
              width: size, 
              height: size, 
              left: `${left}%`, 
              top: `${top}%`,
              boxShadow: size > 1.5 ? '0 0 4px rgba(255,255,255,0.8)' : 'none'
            }}
            className="absolute rounded-full bg-white"
          />
        );
      })}

      {/* Nebula Clouds */}
      <div className="absolute -top-20 -left-20 w-[500px] h-[500px] bg-purple-600/10 rounded-full blur-[120px] mix-blend-screen animate-pulse" />
      <div className="absolute -bottom-20 -right-20 w-[600px] h-[600px] bg-blue-600/10 rounded-full blur-[120px] mix-blend-screen" />
      
      {/* Subtle Shooting Star Effect */}
      <motion.div
        initial={{ x: "-10%", y: "20%", opacity: 0 }}
        animate={{ 
          x: ["0%", "150%"],
          y: ["20%", "80%"],
          opacity: [0, 1, 0]
        }}
        transition={{ 
          duration: 2, 
          repeat: Infinity, 
          repeatDelay: 8,
          ease: "easeOut"
        }}
        className="absolute w-[100px] h-[1px] bg-gradient-to-r from-transparent via-white to-transparent rotate-[-35deg]"
      />
    </div>
  );
}
