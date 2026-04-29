/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        gold: {
          300: '#fde68a',
          400: '#f5c842',
          500: '#e6b800',
          600: '#cc9f00',
        },
        terminal: {
          bg:     '#080c14',
          surface:'#0d1424',
          card:   '#0f1929',
          border: '#1a2535',
          'border-strong': '#253347',
          muted:  '#2d3f57',
          base:   '#b0c4d8',       // text-terminal-base
          'text-dim':  '#4b5e75',  // text-terminal-text-dim
          'text-muted':'#6b7d95',  // text-terminal-text-muted
          'text-base': '#b0c4d8',  // text-terminal-text-base (alias)
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      keyframes: {
        'flash-up': {
          '0%':   { color: '#22c55e', textShadow: '0 0 12px rgba(34,197,94,0.6)' },
          '60%':  { color: '#4ade80' },
          '100%': { color: '#f5c842' },
        },
        'flash-down': {
          '0%':   { color: '#ef4444', textShadow: '0 0 12px rgba(239,68,68,0.6)' },
          '60%':  { color: '#f87171' },
          '100%': { color: '#f5c842' },
        },
        'fade-in': {
          '0%':   { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          '0%':   { opacity: '0', transform: 'translateX(-8px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
      animation: {
        'flash-up':   'flash-up 0.8s ease-out forwards',
        'flash-down': 'flash-down 0.8s ease-out forwards',
        'fade-in':    'fade-in 0.3s ease-out',
        'slide-in':   'slide-in 0.25s ease-out',
      },
    },
  },
  plugins: [],
}
