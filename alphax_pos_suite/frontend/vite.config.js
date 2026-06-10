import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// Build output goes into the Frappe app's public/ tree so it's served at:
//   /assets/alphax_pos_suite/dist/cashier/
// The Frappe page (alphax_pos_v2) loads the entry from there.
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: resolve(__dirname, '../alphax_pos_suite/alphax_pos_suite/public/dist/cashier'),
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html')
      },
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]'
      }
    }
  },
  base: '/assets/alphax_pos_suite/dist/cashier/',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
