import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins:[react()], build:{ outDir:'dist', emptyOutDir:true, sourcemap:false, cssCodeSplit:true, rollupOptions:{ output:{ manualChunks:{ motion:['framer-motion'], icons:['lucide-react'], router:['react-router-dom'] } } } } });
