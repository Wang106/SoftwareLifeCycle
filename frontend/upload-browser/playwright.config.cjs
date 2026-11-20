'use strict';
const path=require('node:path'),original=require('../e2e/playwright.config.cjs');
module.exports={...original,testDir:__dirname,testMatch:['private-upload.spec.ts'],outputDir:path.resolve(__dirname,'../browser-results/upload/artifacts'),reporter:[['list'],['json',{outputFile:path.resolve(__dirname,'../browser-results/upload/results.json')}]]};
