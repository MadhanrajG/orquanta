/** @type {import('tailwindcss').Config} */
module.exports = {
    content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
    theme: {
        extend: {
            colors: {
                brand: {
                    50: '#F5F3FF', 100: '#EDE9FE', 200: '#DDD6FE',
                    300: '#C4B5FD', 400: '#7C6BF0', 500: '#6C5CE7',
                    600: '#5B4BD5', 700: '#4C3EC4', 800: '#3B30A6',
                    900: '#251E6A', 950: '#1A1447',
                },
                surface: {
                    900: '#FFFFFF', 800: '#F8FAFC', 700: '#FFFFFF',
                    600: '#F1F5F9', 500: '#E2E8F0',
                },
                navy: {
                    50: '#F0F4FF', 100: '#E0E7FF', 200: '#C7D2FE',
                    300: '#A5B4FC', 400: '#818CF8', 500: '#1E3A5F',
                    600: '#162D4A', 700: '#0C1A3A', 800: '#091428',
                    900: '#060E1C', 950: '#030710',
                },
                lavender: {
                    50: '#F5F3FF', 100: '#EDE9FE', 200: '#DDD6FE',
                    300: '#C4B5FD', 400: '#A78BFA', 500: '#7C6BF0',
                    600: '#6C5CE7', 700: '#5B4BD5', 800: '#4C3EC4',
                    900: '#3B30A6', 950: '#251E6A',
                },
                // Standard gray scale (NOT inverted)
                gray: {
                    50:  '#F9FAFB', 100: '#F3F4F6', 200: '#E5E7EB',
                    300: '#D1D5DB', 400: '#9CA3AF', 500: '#6B7280',
                    600: '#4B5563', 700: '#374151', 800: '#1F2937',
                    900: '#111827', 950: '#030712',
                },
            },
            fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
            animation: {
                'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                'fade-in': 'fadeIn 0.4s ease-out',
                'slide-up': 'slideUp 0.3s ease-out',
                'glow-breathe': 'glowBreathe 3s ease-in-out infinite',
                'telemetry-pulse': 'telemetryPulse 2s ease-in-out infinite',
                'glow-lavender': 'glowLavender 3s ease-in-out infinite',
            },
            keyframes: {
                fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
                slideUp: { '0%': { transform: 'translateY(12px)', opacity: '0' }, '100%': { transform: 'translateY(0)', opacity: '1' } },
                glowBreathe: {
                    '0%, 100%': { boxShadow: '0 0 8px rgba(124,107,240,0.1)' },
                    '50%': { boxShadow: '0 0 20px rgba(124,107,240,0.25)' },
                },
                telemetryPulse: {
                    '0%, 100%': { opacity: '1', transform: 'scale(1)' },
                    '50%': { opacity: '0.6', transform: 'scale(1.1)' },
                },
                glowLavender: {
                    '0%, 100%': { boxShadow: '0 0 8px rgba(124,107,240,0.1)' },
                    '50%': { boxShadow: '0 0 20px rgba(124,107,240,0.25)' },
                },
            },
            backgroundImage: {
                'grid-pattern': "linear-gradient(rgba(124,107,240,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(124,107,240,0.04) 1px, transparent 1px)",
            },
            backgroundSize: { 'grid-pattern': '40px 40px' },
        },
    },
    plugins: [],
}
