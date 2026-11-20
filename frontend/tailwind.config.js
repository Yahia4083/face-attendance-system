/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["IBM Plex Sans", "Segoe UI", "sans-serif"],
        display: ["IBM Plex Sans", "Segoe UI", "sans-serif"],
      },
      colors: {
        ink: "#142238",
        canvas: "#edf1f5",
        surface: "#ffffff",
        ocean: {
          50: "#eef5f8",
          100: "#d8e7ed",
          200: "#b5d1dc",
          300: "#86b3c4",
          400: "#4f8da5",
          500: "#286b88",
          600: "#174e6f",
          700: "#123d5b",
          800: "#102f48",
          900: "#0b2236",
        },
        signal: {
          50: "#edf8f7",
          100: "#d2eeeb",
          200: "#a9ddd8",
          300: "#73c3be",
          400: "#3da5a2",
          500: "#168487",
          600: "#106b70",
          700: "#10565b",
          800: "#10464a",
          900: "#0e3a3e",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 31, 48, 0.06)",
        elevated: "0 16px 36px rgba(9, 25, 42, 0.18)",
      },
    },
  },
  plugins: [],
};
