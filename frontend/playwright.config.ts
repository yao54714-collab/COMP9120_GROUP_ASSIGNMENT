import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'../tests/browser',timeout:45000,workers:1,retries:0,
  reporter:[['list'],['json',{outputFile:'../test-results/browser.json'}]],
  outputDir:'../test-results/browser-artifacts',
  use:{baseURL:process.env.PAWCARE_TEST_URL||'http://127.0.0.1:8001',channel:'chrome',headless:true,
       viewport:{width:1440,height:1050},trace:'retain-on-failure',screenshot:'only-on-failure'}});
