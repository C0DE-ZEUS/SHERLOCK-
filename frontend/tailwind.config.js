/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B1020",
        surface: { DEFAULT: "#111827", raised: "#172033", sunken: "#0E1424" },
        line: { DEFAULT: "rgba(255,255,255,0.08)", strong: "rgba(255,255,255,0.14)" },
        fg: { DEFAULT: "#F8FAFC", muted: "#94A3B8", subtle: "#7C8BA1" },
        accent: { DEFAULT: "#14B8A6", bright: "#2DD4BF", ink: "#04201D", wash: "rgba(20,184,166,0.12)" },
        ai: { DEFAULT: "#818CF8", bright: "#A5B4FC", wash: "rgba(129,140,248,0.13)" },
        warn: { DEFAULT: "#F59E0B", fg: "#FCD34D", wash: "rgba(245,158,11,0.12)" },
        danger: { DEFAULT: "#EF4444", fg: "#FCA5A5", wash: "rgba(239,68,68,0.12)" },
      },
      fontFamily: {
        sans: ["Inter Variable", "Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Cascadia Mono", "Consolas", "monospace"],
      },
      boxShadow: {
        glass: "0 1px 0 0 rgba(255,255,255,0.05) inset, 0 20px 50px -20px rgba(0,0,0,0.6)",
        lift: "0 10px 30px -12px rgba(0,0,0,0.55)",
      },
      keyframes: {
        "fade-up": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        shimmer: { from: { transform: "translateX(-100%)" }, to: { transform: "translateX(100%)" } },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out both",
        shimmer: "shimmer 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
