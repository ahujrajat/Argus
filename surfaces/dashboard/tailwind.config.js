export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: "#A100FF",
          50: "#F5E5FF",
          100: "#EAC9FF",
          200: "#D18EFF",
          400: "#A100FF",
          600: "#6200CC",
          700: "#430066",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.04)",
        "card-hover": "0 4px 12px rgba(0,0,0,0.10), 0 2px 4px rgba(0,0,0,0.06)",
        sidebar: "2px 0 8px rgba(0,0,0,0.05)",
      },
    },
  },
  plugins: [],
};
