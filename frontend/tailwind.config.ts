import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      boxShadow: {
        panel: "0 24px 80px rgba(15, 23, 42, 0.12)",
      },
      colors: {
        canvas: "#f6f2e8",
        ink: "#12263a",
        mellow: "#f2b450",
        calm: "#6db6a9",
        danger: "#b63a3a",
      },
      borderRadius: {
        "4xl": "2rem",
      },
    },
  },
  plugins: [],
};

export default config;
