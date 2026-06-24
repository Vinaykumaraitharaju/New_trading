import { motion } from "framer-motion";

export function LoadingBar() {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/8">
      <motion.div
        className="h-full w-1/3 rounded-full bg-gradient-to-r from-cyan-300 via-violet-400 to-teal-300"
        animate={{ x: ["-10%", "240%"] }}
        transition={{ duration: 1.8, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
      />
    </div>
  );
}
