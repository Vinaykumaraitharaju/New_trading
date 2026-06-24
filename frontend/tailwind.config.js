export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#05080f",
        ink: "#08101a",
        panel: "#0f1624",
        line: "#243244",
        bull: "#36d58b",
        bear: "#ff6c86",
        buildup: "#ffd166",
        text: "#ecf5ff",
        muted: "#91a4bc"
      },
      fontFamily: {
        display: ["Inter", "SF Pro Display", "sans-serif"],
        body: ["Inter", "SF Pro Text", "sans-serif"]
      },
      boxShadow: {
        signal: "0 24px 48px rgba(0,0,0,0.28)",
        neon: "0 0 32px rgba(34,211,238,0.18)"
      },
      backdropBlur: {
        xl2: "28px"
      },
      animation: {
        shimmer: "shimmer 1.6s linear infinite"
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" }
        }
      }
    }
  },
  plugins: []
};
