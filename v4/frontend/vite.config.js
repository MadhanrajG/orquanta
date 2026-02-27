import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
    plugins: [react()],
    css: {
        postcss: './postcss.config.js',
    },
    server: {
        port: 3000,
        host: true,
        proxy: {
            '/api': { target: 'http://localhost:8000', changeOrigin: true },
            '/auth': { target: 'http://localhost:8000', changeOrigin: true },
            '/ws': { target: 'ws://localhost:8000', ws: true, changeOrigin: true },
            '/providers': { target: 'http://localhost:8000', changeOrigin: true },
            '/goals': { target: 'http://localhost:8000', changeOrigin: true },
            '/jobs': { target: 'http://localhost:8000', changeOrigin: true },
            '/agents': { target: 'http://localhost:8000', changeOrigin: true },
            '/metrics': { target: 'http://localhost:8000', changeOrigin: true },
            '/health': { target: 'http://localhost:8000', changeOrigin: true },
        },
    },
    resolve: {
        alias: { '@': path.resolve(__dirname, './src') },
    },
})
