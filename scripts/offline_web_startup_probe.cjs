'use strict';
// Executed only inside the explicitly approved container. Tests inject fs/http.
// No HTML, response headers, process data or external errors leave this program.
const fs = require('node:fs');
const http = require('node:http');
const assert = (value) => { if (!value) throw new Error('rejected'); };
const receipt = (name) => process.stdout.write(JSON.stringify({case:name, passed:true}));
const fail = () => process.exit(2);
function read(path) {
  const fd = fs.openSync(path, 'r');
  try {
    const bytes = Buffer.alloc(65537);
    let total = 0;
    while (true) {
      const n = fs.readSync(fd, bytes, total, bytes.length - total, null);
      if (n === 0) break; // Only an explicit EOF completes the snapshot.
      total += n;
      assert(total < bytes.length); // 65,536 bytes plus one overflow sentinel.
    }
    return bytes.subarray(0,total).toString('utf8');
  } finally { fs.closeSync(fd); }
}
function processCheck() {
  assert(fs.readlinkSync('/proc/1/exe') === '/usr/local/bin/node');
  // Next changes process.title; Docker's inspected Path/Args bind the startup
  // command. Do not mistake the changed title for the original argv.
  const cmd = read('/proc/1/cmdline').replace(/\0+$/, '');
  assert(cmd === 'next-server (v16.4.2)');
  const status = Object.fromEntries(read('/proc/1/status').split('\n').filter(x => x.includes(':'))
    .map(x => [x.slice(0,x.indexOf(':')),x.slice(x.indexOf(':')+1).trim()]));
  for (const key of ['Uid','Gid']) assert(status[key].split(/\s+/).join(',') === '65532,65532,65532,65532');
  for (const key of ['CapInh','CapPrm','CapEff','CapBnd','CapAmb']) assert(/^0+$/.test(status[key]));
  assert(status.NoNewPrivs === '1' && status.Seccomp === '2');
  const listeners = [];
  for (const path of ['/proc/net/tcp','/proc/net/tcp6']) {
    for (const row of read(path).trim().split('\n').slice(1)) {
      const fields = row.trim().split(/\s+/); assert(fields.length >= 4);
      if (fields[3] === '0A') listeners.push(path + ':' + fields[1]);
    }
  }
  assert(JSON.stringify(listeners) === JSON.stringify(['/proc/net/tcp:0100007F:0BB8']));
  receipt('process');
}
function responseCheck(name, response, body) {
  assert(response.complete === true);
  const headers = response.headers;
  assert(!headers.location && !headers['content-encoding'] && !headers['set-cookie']);
  if (headers['content-length'] !== undefined) {
    assert(/^[0-9]+$/.test(headers['content-length']));
    assert(Number(headers['content-length']) === body.length);
  }
  const text = new TextDecoder('utf-8', {fatal:true}).decode(body);
  if (name === 'dashboard_unavailable') {
    assert(response.statusCode === 200 && /^text\/html(?:;|$)/.test(headers['content-type'] || ''));
    assert(/<!doctype html>/i.test(text) && /<\/html>/i.test(text));
    // These must exist in HTML markup, not merely serialized Flight/script data.
    // Streamed hidden fragments are server HTML, not proof of browser hydration.
    const markup = text.replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi,'')
      .replace(/<style\b[^>]*>[\s\S]*?<\/style\s*>/gi,'').replace(/<!--[\s\S]*?-->/g,'');
    assert(/<h1\b[^>]*>Lifecycle Dashboard<\/h1>/.test(markup));
    for (const value of ['Dashboard data unavailable. Try reading again later.',
                         'Current release data unavailable', 'Recent activity unavailable',
                         'Live dashboard unavailable', 'Read dashboard again']) {
      assert(markup.includes('>' + value + '<'));
    }
  } else {
    assert(name === 'login_disabled' && response.statusCode === 503);
    assert(headers['content-type'] === 'application/json');
    assert(headers['cache-control'] === 'private, no-store' && headers.pragma === 'no-cache');
    assert((headers.vary || '').split(',').map(v=>v.trim().toLowerCase()).includes('cookie'));
    assert(headers['referrer-policy'] === 'no-referrer' && headers['x-content-type-options'] === 'nosniff');
    // Fixed serialization also rejects duplicate keys, extra fields and coercion.
    assert(text === '{"error":"login_not_configured"}');
  }
}
function probe(name) {
  assert(['dashboard_unavailable','login_disabled'].includes(name));
  let total=0; const chunks=[];
  const timer = setTimeout(fail,20000); // absolute deadline, not reset by data
  const req = http.request({host:'127.0.0.1',port:3000,
    path:name === 'dashboard_unavailable' ? '/' : '/auth/login',
    method:name === 'dashboard_unavailable' ? 'GET' : 'POST',
    agent:false, maxHeaderSize:16384, headers:{Connection:'close','Accept-Encoding':'identity',
      Cookie:'slc_language=en',Accept:name === 'dashboard_unavailable' ? 'text/html' : 'application/json'}}, res => {
    res.on('error',fail); res.on('aborted',fail);
    res.on('data', chunk => {
      total += chunk.length;
      if (total > (name === 'dashboard_unavailable' ? 1048576 : 4096)) { req.destroy(); fail(); return; }
      chunks.push(chunk);
    });
    res.on('end', () => {
      try { responseCheck(name,res,Buffer.concat(chunks)); clearTimeout(timer); receipt(name); }
      catch { fail(); }
    });
  });
  req.on('error',fail); req.end();
}
try {
  const name = process.argv[1];
  if (name === 'process') processCheck(); else probe(name);
} catch { fail(); }
