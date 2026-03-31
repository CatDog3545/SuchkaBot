/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        tg: {
          bg: 'var(--tg-theme-bg-color)',
          text: 'var(--tg-theme-text-color)',
          hint: 'var(--tg-theme-hint-color)',
          link: 'var(--tg-theme-link-color)',
          button: 'var(--tg-theme-button-color)',
          buttonText: 'var(--tg-theme-button-text-color)',
          secondary: 'var(--tg-theme-secondary-bg-color)',
          header: 'var(--tg-theme-header-bg-color)',
          subtitle: 'var(--tg-theme-section-header-text-color)',
          section: 'var(--tg-theme-section-bg-color)',
          separator: 'var(--tg-theme-section-separator-color)',
        }
      }
    },
  },
  plugins: [],
}
