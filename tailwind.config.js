/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./static/**/*.{html,js}",
    "./static/views/**/*.html",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'kiro-primary': '#1E293B',
        'kiro-secondary': '#334155',
        'kiro-cta': '#22C55E',
        'kiro-bg': '#0F172A',
        'kiro-text': '#F8FAFC',
        'space-950': '#09090b',
        'space-900': '#0f0f11',
        'space-850': '#121214',
        'space-800': '#18181b',
        'space-border': '#27272a',
        'neon-purple': '#a855f7',
        'neon-cyan': '#06b6d4',
        'neon-green': '#22c55e',
        'neon-yellow': '#eab308',
        'neon-red': '#ef4444'
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
      }
    }
  },
  plugins: [
    require('daisyui')
  ],
  daisyui: {
    themes: ["dark"],
    darkTheme: "dark",
  }
}
