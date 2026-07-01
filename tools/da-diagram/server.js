#!/usr/bin/env node
/**
 * da-diagram — interactive topology viewer for Dynamic Architecture flows.
 *
 * Usage (from anywhere):
 *   node tools/da-diagram/server.js --agent-dir ./agent [--port 7070]
 *
 * Or from agent/:
 *   node ../tools/da-diagram/server.js [--port 7070]
 */

const express = require('express');
const http = require('http');
const { WebSocketServer } = require('ws');
const fs = require('fs');
const path = require('path');
const { execSync, spawn } = require('child_process');

// ── CLI args ──────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
let agentDir = process.cwd();
let port = 7070;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--agent-dir') agentDir = path.resolve(args[++i]);
  if (args[i] === '--port')      port = parseInt(args[++i]);
}

const FLOWS_DIR = path.join(agentDir, 'flows');
const GATES_DIR = path.join(agentDir, 'gates');
const ADRS_DIR  = path.join(agentDir, 'adrs');
const KATA_DIR  = path.join(agentDir, 'katas');
const SKILLS_DIR= path.join(agentDir, 'skills');

// ── Helpers ───────────────────────────────────────────────────────────────────

function readJSON(p) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; }
}

function readText(p) {
  try { return fs.readFileSync(p, 'utf8'); } catch { return null; }
}

function listDirs(dir) {
  try {
    return fs.readdirSync(dir, { withFileTypes: true })
      .filter(d => d.isDirectory())
      .map(d => d.name);
  } catch { return []; }
}

/** Opis gate kind — mirrors Rust gate_kind() in da-core/compose.rs */
function gateKind(spec) {
  const arch = (spec.archetype || '').replace(/^Custom\(|\)$/g, '');
  if (arch === 'TransactionCoordination') {
    const is2pc = (spec.inputs || []).some(inp =>
      inp.split(/[^a-z]/i).some(tok =>
        ['commit', 'compensate', 'prepare', 'rollback', 'abort'].includes(tok.toLowerCase())
      )
    );
    return is2pc ? 'sync' : 'sentinel';
  }
  return 'gate';
}

/** Parse FA diary.md into structured iteration list */
function parseDiary(text) {
  if (!text) return [];
  const sections = [];
  let cur = null;
  for (const line of text.split('\n')) {
    if (line.startsWith('## ')) {
      if (cur) sections.push(cur);
      cur = { header: line.slice(3).trim(), lines: [] };
    } else if (cur) {
      cur.lines.push(line);
    }
  }
  if (cur) sections.push(cur);
  return sections;
}

/** Parse ADR markdown — extract title and gate names mentioned */
function parseADR(name, text) {
  if (!text) return null;
  const titleMatch = text.match(/^#\s+(.+)/m);
  const statusMatch = text.match(/^status:\s*(\w+)/im);
  const title = titleMatch ? titleMatch[1].replace(/^ADR-\d+[:\s]+/, '') : name;
  const status = statusMatch ? statusMatch[1] : 'active';

  // extract gate names: kebab-case words that appear in the graph
  const gateRefs = [...new Set(
    [...text.matchAll(/`([a-z][a-z0-9-]+(?:-[a-z][a-z0-9-]+)+)`/g)].map(m => m[1])
  )];

  return { name, title, status, text, gateRefs };
}

/** git log for a file */
function gitLog(filePath) {
  try {
    const log = execSync(
      `git log --oneline --follow --pretty=format:"%h|||%s|||%cr" -- "${filePath}"`,
      { cwd: agentDir, encoding: 'utf8', stdio: ['pipe', 'pipe', 'ignore'] }
    ).trim();
    if (!log) return [];
    return log.split('\n').map(l => {
      const [hash, msg, when] = l.split('|||');
      return { hash, msg, when };
    });
  } catch { return []; }
}

// ── Express app ───────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// List available flows
app.get('/api/flows', (req, res) => {
  res.json(listDirs(FLOWS_DIR));
});

// Full data for a flow
app.get('/api/flow/:name', (req, res) => {
  const name = req.params.name;
  const flowDir = path.join(FLOWS_DIR, name);

  // Graph (connections)
  const graph = readJSON(path.join(flowDir, 'graph.json')) || { gates: [], connections: [] };

  // Gate specs (inputs/outputs/archetype)
  const gateSpecs = {};
  for (const g of graph.gates || []) {
    const spec = readJSON(path.join(GATES_DIR, g.name, 'spec.json'));
    if (spec) {
      gateSpecs[g.name] = {
        ...spec,
        archetype: g.archetype,
        kind: gateKind({ ...spec, archetype: g.archetype }),
      };
    } else {
      // gate exists in graph but no spec yet
      gateSpecs[g.name] = {
        name: g.name,
        archetype: g.archetype,
        inputs: [],
        outputs: [],
        kind: gateKind(g),
        pending: true,
      };
    }
  }

  // External loci — derive from graph.sources + connections
  // These are untrusted external actors, rendered as distinct nodes in the UI
  const sources = graph.sources || [];
  for (const locusName of sources) {
    gateSpecs[locusName] = {
      name: locusName,
      kind: 'external',
      inputs: [],
      outputs: graph.connections
        .filter(c => c.from === locusName)
        .map(c => c.pulse_type),
      pending: false,
      external: true,
    };
  }

  // FA diary
  const diaryText = readText(path.join(flowDir, 'diary.md'));
  const diary = parseDiary(diaryText);

  // Kata
  const kataText = readText(path.join(KATA_DIR, `${name}.md`)) || '';

  res.json({ name, graph, gateSpecs, diary, kata: kataText });
});

// All ADRs
app.get('/api/adrs', (req, res) => {
  const adrs = [];
  try {
    const files = fs.readdirSync(ADRS_DIR).filter(f => f.endsWith('.md')).sort();
    for (const f of files) {
      const text = readText(path.join(ADRS_DIR, f));
      const parsed = parseADR(f.replace(/\.md$/, ''), text);
      if (parsed) adrs.push(parsed);
    }
  } catch { /* no adrs dir */ }
  res.json(adrs);
});

// Git history for a flow graph
app.get('/api/history/:name', (req, res) => {
  const p = path.join(FLOWS_DIR, req.params.name, 'graph.json');
  res.json(gitLog(p));
});

// Get a specific git revision of graph.json
app.get('/api/history/:name/:hash', (req, res) => {
  try {
    const rel = path.relative(agentDir, path.join(FLOWS_DIR, req.params.name, 'graph.json'));
    const out = execSync(`git show ${req.params.hash}:"${rel}"`,
      { cwd: agentDir, encoding: 'utf8', stdio: ['pipe', 'pipe', 'ignore'] });
    res.json(JSON.parse(out));
  } catch (e) {
    res.status(404).json({ error: e.message });
  }
});

// Save kata changes
app.post('/api/kata/:name', (req, res) => {
  const { text } = req.body;
  const p = path.join(KATA_DIR, `${req.params.name}.md`);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, text, 'utf8');
  res.json({ ok: true });
});

// Toggle ADR active status (rename file to .md.disabled or back)
app.post('/api/adrs/:name/toggle', (req, res) => {
  const base = path.join(ADRS_DIR, req.params.name);
  const active = `${base}.md`;
  const disabled = `${base}.md.disabled`;
  if (fs.existsSync(active)) {
    fs.renameSync(active, disabled);
    res.json({ status: 'disabled' });
  } else if (fs.existsSync(disabled)) {
    fs.renameSync(disabled, active);
    res.json({ status: 'active' });
  } else {
    res.status(404).json({ error: 'not found' });
  }
});

// ── WebSocket: stream `da` runs ───────────────────────────────────────────────

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });

wss.on('connection', ws => {
  let child = null;

  ws.on('message', raw => {
    const msg = JSON.parse(raw);

    if (msg.type === 'run') {
      if (child) { child.kill(); child = null; }

      const { flow, backend, model, adrs, evalScript, loopMax, extraArgs } = msg;

      const cmd = [
        'da',
        '--kata', path.join(KATA_DIR, `${flow}.md`),
        '--backend', backend || 'ollama',
        ...(model ? ['--model', model] : []),
        ...(adrs && fs.existsSync(path.join(agentDir, adrs)) ? ['--adrs', adrs] : []),
        ...(evalScript ? ['--eval', evalScript, '--loop', String(loopMax || 3)] : []),
        ...(extraArgs || []),
      ];

      ws.send(JSON.stringify({ type: 'start', cmd: cmd.join(' ') }));

      child = spawn(cmd[0], cmd.slice(1), { cwd: agentDir });

      const fwd = (stream, channel) => {
        stream.on('data', d => ws.send(JSON.stringify({ type: channel, text: d.toString() })));
      };
      fwd(child.stdout, 'stdout');
      fwd(child.stderr, 'stderr');

      child.on('close', code => {
        ws.send(JSON.stringify({ type: 'done', code }));
        child = null;
      });
    }

    if (msg.type === 'kill' && child) {
      child.kill();
      child = null;
      ws.send(JSON.stringify({ type: 'killed' }));
    }
  });

  ws.on('close', () => { if (child) child.kill(); });
});

// ── File watcher — push graph updates to all clients ─────────────────────────

try {
  const chokidar = require('chokidar');
  const watcher = chokidar.watch(
    [path.join(FLOWS_DIR, '**', 'graph.json'), path.join(GATES_DIR, '**', 'spec.json')],
    { ignoreInitial: true }
  );
  watcher.on('change', file => {
    const msg = JSON.stringify({ type: 'file_changed', path: file });
    wss.clients.forEach(c => { if (c.readyState === 1) c.send(msg); });
  });
} catch { /* chokidar optional */ }

// ── Start ─────────────────────────────────────────────────────────────────────

server.listen(port, () => {
  console.log(`da-diagram  http://localhost:${port}`);
  console.log(`agent dir:  ${agentDir}`);
});
