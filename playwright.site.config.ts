import {defineConfig} from '@playwright/test';
import base from './playwright.config';
export default defineConfig({
  ...base,
  testMatch: ['landing.spec.ts', 'product-demo.spec.ts', 'recorded-evidence.spec.ts', 'sensor-gallery.spec.ts', 'gripper-gallery.spec.ts', 'vtol-gallery.spec.ts', 'surface-gallery.spec.ts'],
  use: {...base.use, baseURL:'http://127.0.0.1:3225'},
  webServer: {
    command:'node_modules/.bin/next start web --hostname 127.0.0.1 --port 3225',
    url:'http://127.0.0.1:3225/demo',
    timeout:30000,
    reuseExistingServer:false,
  },
});
