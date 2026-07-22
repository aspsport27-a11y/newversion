/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef7ff', 100: '#d9edff', 500: '#1877cc',
          600: '#1466b3', 700: '#115592', 900: '#0b3a63',
        },
      },
    },
  },
  plugins: [],
}
