/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
        // Display face for hero/h1-scale headlines only — everything else
        // (body copy, controls, tables) stays on the sans family above so
        // the dense screens don't inherit a wider, louder letterform.
        display: ['Space Grotesk', 'Plus Jakarta Sans', 'system-ui', 'sans-serif'],
      },
      // Tailwind's default scale bottoms out at 0.75rem (11.25px at our 15px
      // root), which was too small to read comfortably in dense panels. Each
      // step is nudged up so `text-xs` is a genuinely readable 12.2px and
      // `text-sm` is 13.1px, without touching a single component.
      fontSize: {
        '2xs': ['0.75rem', { lineHeight: '1.35' }],
        xs: ['0.8125rem', { lineHeight: '1.45' }],
        sm: ['0.875rem', { lineHeight: '1.5' }],
        base: ['0.9375rem', { lineHeight: '1.55' }],
        lg: ['1.0625rem', { lineHeight: '1.45' }],
        xl: ['1.1875rem', { lineHeight: '1.35' }],
        '2xl': ['1.4375rem', { lineHeight: '1.3' }],
        '3xl': ['1.75rem', { lineHeight: '1.25' }],
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
