/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: { 900: '#0f3460', 800: '#16213e', 700: '#1a1a2e' },
        accent: { pink: '#e94560', green: '#00c853', red: '#ff1744', amber: '#ffab00' },
      },
    },
  },
  plugins: [require('daisyui')],
  daisyui: {
    themes: [
      "dark",
      {
        draft: {
          "primary": "#e94560",
          "secondary": "#0f3460",
          "accent": "#00c853",
          "neutral": "#16213e",
          "base-100": "#1a1a2e",
          "base-200": "#16213e",
          "base-300": "#0f3460",
          "base-content": "#e0e0e0",
          "info": "#3abff8",
          "success": "#00c853",
          "warning": "#ffab00",
          "error": "#ff1744",
        },
      },
    ],
  },
}
