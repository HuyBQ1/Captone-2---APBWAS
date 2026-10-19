import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins: [react()], server: { proxy: { '/api': 'http://127.0.0.1:8000' } }, build: {rollupOptions:{output:{manualChunks(id){
 if(id.includes('node_modules')){
   if(id.includes('recharts')||id.includes('d3-'))return 'charts';
   if(id.includes('@xyflow'))return 'workflow';
   if(id.includes('framer-motion'))return 'motion';
   if(id.includes('react-markdown')||id.includes('remark')||id.includes('micromark')||id.includes('mdast')||id.includes('hast')||id.includes('unified'))return 'markdown';
 }
}}}} });
