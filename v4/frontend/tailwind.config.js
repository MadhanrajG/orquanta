/** @type {import('tailwindcss').Config} */
export default {
    content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
    theme: {
        extend: {
            colors: {
                brand: {
                    50: '#f0f4ff', 100: '#e0e9ff', 200: '#c7d7fe',
                    300: '#a4bffd', 400: '#7a9bfa', 500: '#5271f5',
                    600: '#3a52eb', 700: '#2e3fd8', 800: '#2833b0',
                    900: '#27318b', 950: '#1a1f55',
                },
                surface: {
                    900: '#0a0b14', 800: '#0f1120', 700: '#151829',
                    600: '#1c2038', 500: '#242845',
                },
            },
            fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
            animation: {
                'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                'fade-in': 'fadeIn 0.4s ease-out',
                'slide-up': 'slideUp 0.3s ease-out',
            },
            keyframes: {
                fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
                slideUp: { '0%': { transform: 'translateY(12px)', opacity: '0' }, '100%': { transform: 'translateY(0)', opacity: '1' } },
            },
            backgroundImage: {
                'grid-pattern': "linear-gradient(rgba(82,113,245,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(82,113,245,0.07) 1px, transparent 1px)",
            },
            backgroundSize: { 'grid-pattern': '40px 40px' },
        },
    },
    plugins: [],
}
