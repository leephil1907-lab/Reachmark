import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
const root = fileURLToPath(new URL('.', import.meta.url));
export default defineConfig(({mode}) => ({
  root, base: mode === 'production' ? '/static/site/' : '/',
  plugins:[react()], envPrefix:'VITE_',
  build:{outDir:resolve(root,'../../static/site'),emptyOutDir:true,sourcemap:false,cssCodeSplit:true,rollupOptions:{output:{manualChunks:{motion:['framer-motion'],icons:['lucide-react']}}}},
  server:{host:'0.0.0.0',port:5173,strictPort:true}
}));
