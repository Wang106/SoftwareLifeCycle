'use strict';
const path = require('node:path');
const sampleApi = 'https://softwarelifecycle-api-test.onrender.com';
function validateWorkerConfig(config) {
  if (config.name !== 'softwarelifecycle') throw new Error('Unexpected Worker target');
  if (config.preview_urls !== true) {
    throw new Error('Worker Preview URLs must be explicitly enabled for branch verification');
  }
  if (!config.previews || config.previews.vars?.API_BASE_URL !== sampleApi) {
    throw new Error('Worker Previews require an explicit API_BASE_URL for the read-only sample API');
  }
  if (Object.keys(config.previews).some(key => key !== 'vars') ||
      Object.keys(config.previews.vars).some(key => key !== 'API_BASE_URL')) {
    throw new Error('Preview resources/routes/secrets require a separate reviewed configuration');
  }
  if (config.vars?.API_BASE_URL !== sampleApi ||
      config.routes?.length !== 1 || config.routes[0].pattern !== 'softwarelifecycle.whf969.com' ||
      config.routes[0].custom_domain !== true) throw new Error('Unexpected production API/domain');
  if (config.assets?.binding !== 'ASSETS' ||
      !config.assets.directory?.replaceAll('\\', '/').endsWith('.open-next/assets') ||
      !config.main?.replaceAll('\\', '/').endsWith('.open-next/worker.js')) {
    throw new Error('OpenNext entry point and assets must stay at the top level');
  }
}
function readWorkerConfig(configPath = path.resolve(__dirname, '../wrangler.jsonc')) {
  return require('wrangler').unstable_readConfig({config:configPath});
}
if (require.main === module) {
  try {
    validateWorkerConfig(readWorkerConfig());
    const root = readWorkerConfig(path.resolve(__dirname, '../../wrangler.jsonc'));
    validateWorkerConfig(root);
    if (root.build?.command !== 'cd frontend && npm ci && npx opennextjs-cloudflare build') {
      throw new Error('Root deployment must build the frontend OpenNext Worker');
    }
    console.log('Worker configuration passed: root and frontend production targets and explicit read-only Preview API');
  } catch (error) {
    console.error('Invalid Worker configuration:', error.message);
    process.exitCode = 1;
  }
}
module.exports = {validateWorkerConfig, readWorkerConfig};
