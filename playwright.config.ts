import {defineConfig,devices} from '@playwright/test';
export default defineConfig({testDir:'./e2e',timeout:60000,workers:1,fullyParallel:false,reporter:[['list'],['html',{open:'never'}]],use:{baseURL:process.env.E2E_URL||'http://127.0.0.1:5173',trace:'retain-on-failure'},projects:[{name:'chromium',use:{...devices['Desktop Chrome']}}]});
