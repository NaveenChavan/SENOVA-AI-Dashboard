/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      // Tailwind's default breakpoints stop at 2xl (1536px). We add named
      // breakpoints for QHD/4K/8K desktops and large TVs used as monitors,
      // so layouts can cap width / increase density instead of stretching
      // into an unreadable single row of tiny cards.
      screens: {
        'xs': '400px',
        '3xl': '1920px', // Full HD / QHD desktops
        '4k': '2560px',  // 4K desktops
        '8k': '3840px',  // 4K UHD TVs used as monitors, true 8K scaled 2x
      },
    },
  },
  plugins: [],
}
