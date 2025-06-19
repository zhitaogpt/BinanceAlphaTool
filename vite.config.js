import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import monkey from 'vite-plugin-monkey';
import { resolve } from 'path';

const isProduction = process.env.NODE_ENV === 'production';

export default defineConfig({
  build: {
    minify: 'terser',
    sourcemap: false,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        format: 'iife',
        inlineDynamicImports: true,
        manualChunks: undefined,
        preserveModules: false,
        entryFileNames: 'binance-alpha-tool.user.js',
        chunkFileNames: '[name].js',
        assetFileNames: '[name][extname]',
        globals: {
          window: 'window',
          document: 'document',
        },
      },
    },
    terserOptions: {
      compress: {
        drop_console: false,
        drop_debugger: true,
        pure_funcs: [],
      },
      mangle: {
        toplevel: true,
        properties: false,
        reserved: [
          'Vue',
          'createApp',
          'ref',
          'reactive',
          'onMounted',
          'onUnmounted',
        ],
      },
      format: {
        comments: false,
      },
    },
  },
  plugins: [
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => false,
        },
      },
    }),
    monkey({
      entry: isProduction ? 'src/main.js' : 'src/injectDev.js',
      userscript: {
        name: 'Binance Alpha Trading Tool',
        description: 'Advanced Trading Automation Tool for Binance',
        icon: 'https://www.binance.com/favicon.ico',
        namespace: 'binance-alpha-tool',
        homepage: 'https://github.com/your-repo/binance-alpha-tool',
        author: 'Trading Automation Team',
        match: [
          'https://*/*'
        ],
        'run-at': 'document-start',
        grant: [
          'unsafeWindow',
          'GM_addElement',
          'GM_setValue',
          'GM_getValue',
          'GM_deleteValue',
          'GM_listValues',
          'GM_xmlhttpRequest',
          'GM_registerMenuCommand'
        ],
        inject: {
          into: 'page',
          mode: 'immediate',
        },
        downloadURL: 'https://raw.githubusercontent.com/your-repo/binance-alpha-tool/main/binance-alpha-tool.user.js',
        updateURL: 'https://raw.githubusercontent.com/your-repo/binance-alpha-tool/main/binance-alpha-tool.user.js',
        compatible: 'firefox, chrome, safari',
      },
      build: {
        target: 'esnext',
        externalGlobals: {},
        external: [],
        cssCodeSplit: false,
        manualChunks: undefined,
      },
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
      '@package.json': resolve(__dirname, './package.json'),
    },
  },
  server: {
    port: 3000,
    hmr: {
      port: 24678,
    },
    headers: {
      // 添加 CSP 头以允许开发服务器脚本
      'Content-Security-Policy': 'script-src * \'unsafe-inline\' \'unsafe-eval\''
    }
  },
  define: {
    'process.env': {}
  }
});