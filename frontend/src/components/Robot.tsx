import { useLottie } from 'lottie-react';
import animationData from '../assets/robot.json';

export default function Robot() {
  const options = {
    animationData: animationData,
    loop: true,
    autoplay: true,
  };

  const { View } = useLottie(options);

  return (
    <div className="relative z-10 w-full flex items-center justify-center pointer-events-none">
      <div className="w-full h-full max-w-[400px] aspect-square object-contain drop-shadow-[0_20px_40px_rgba(56,189,248,0.2)]">
        {View}
      </div>
    </div>
  );
}
