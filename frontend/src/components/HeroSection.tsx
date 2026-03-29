import Background from "./Background";
import Robot from "./Robot";
import SignBoard from "./SignBoard";

export default function HeroSection() {
  return (
    <div className="relative flex flex-col items-center justify-center w-full h-full gap-4 py-8 overflow-hidden">
      <Background />
      <div className="relative z-20 w-full flex flex-col items-center gap-6">
        <SignBoard />
        <Robot />
      </div>
    </div>
  );
}
