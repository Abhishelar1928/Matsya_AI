import fs from 'node:fs'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// ---------------------------------------------------------------------------
// Development HTTPS (phone testing). Phones only allow GPS + service workers on
// trusted HTTPS. If certs exist (bash scripts/dev-https/generate-dev-certs.sh)
// the dev server switches to HTTPS automatically; set VITE_HTTPS=0 to opt out.
// ---------------------------------------------------------------------------
const certDir = path.resolve(__dirname, 'certs')
const certFile = path.join(certDir, 'server.crt')
const keyFile = path.join(certDir, 'server.key')
const useHttps = process.env.VITE_HTTPS !== '0' && fs.existsSync(certFile) && fs.existsSync(keyFile)

/** Serves the public dev-CA certificate so a phone can download and install it. Dev server only. */
function devCaDownload(): Plugin {
  return {
    name: 'matsya-dev-ca-download',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url?.split('?')[0]
        if (url !== '/dev-ca.crt' && url !== '/dev-ca.der.crt') return next()
        const file = path.join(certDir, url === '/dev-ca.crt' ? 'ca.crt' : 'ca.der.crt')
        if (!fs.existsSync(file)) { res.statusCode = 404; res.end('Dev CA not generated'); return }
        res.setHeader('Content-Type', 'application/x-x509-ca-cert')
        res.setHeader('Content-Disposition', `attachment; filename="matsya-dev-ca${url === '/dev-ca.crt' ? '' : '.der'}.crt"`)
        res.end(fs.readFileSync(file))
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    devCaDownload(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'icons.svg'],
      manifest: {
        name: 'MatsyaAI Maharashtra',
        short_name: 'MatsyaAI',
        description: 'Marine decision support and offline expedition navigation for Maharashtra fishermen.',
        theme_color: '#0a1628',
        background_color: '#071220',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        lang: 'en',
        icons: [
          { src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
        ],
      },
      workbox: {
        // App shell: everything Vite emits is precached so the app opens offline.
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/docs/, /^\/dev-ca/],
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
        runtimeCaching: [
          {
            // Offline basemap (PMTiles, needs Range requests) + bathymetry contours.
            urlPattern: /\/api\/v1\/offline-assets\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'matsya-offline-assets',
              rangeRequests: true,
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 8, maxAgeSeconds: 60 * 24 * 3600 },
            },
          },
          {
            // Planning-map tiles seen while online are kept for a week.
            urlPattern: /^https:\/\/tile\.openstreetmap\.org\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'matsya-osm-tiles',
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 600, maxAgeSeconds: 7 * 24 * 3600 },
            },
          },
          {
            urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\//,
            handler: 'StaleWhileRevalidate',
            options: { cacheName: 'matsya-fonts', expiration: { maxEntries: 10, maxAgeSeconds: 365 * 24 * 3600 } },
          },
          {
            // Dashboard data: serve live when possible, last good copy when offline.
            urlPattern: /\/api\/v1\/(map|health|sources)/,
            handler: 'NetworkFirst',
            options: { cacheName: 'matsya-api', networkTimeoutSeconds: 8, expiration: { maxEntries: 10, maxAgeSeconds: 24 * 3600 } },
          },
        ],
      },
      devOptions: {
        // Service worker in `vite dev` too, since Docker runs the dev server.
        enabled: true,
        type: 'module',
        navigateFallback: 'index.html',
      },
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    https: useHttps ? { cert: fs.readFileSync(certFile), key: fs.readFileSync(keyFile) } : undefined,
    // Docker on Windows/macOS bind mounts do not forward file-change events; poll instead.
    watch: process.env.VITE_POLL === '1' ? { usePolling: true, interval: 300 } : undefined,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
