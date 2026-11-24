import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceRoots = ['apps/web', 'packages/design-system'];
const ignored = new Set(['node_modules', '.next', 'out', 'public']);
const files = [];
function walk(directory) {
  if (!fs.existsSync(directory)) return;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (ignored.has(entry.name)) continue;
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) walk(filename);
    else if (/\.(css|tsx|jsx|ts|js)$/.test(filename)) files.push(filename);
  }
}
sourceRoots.forEach(directory => walk(path.join(root, directory)));
const errors = [];
const css = [];
for (const filename of files) {
  const source = fs.readFileSync(filename, 'utf8');
  const relative = path.relative(root, filename);
  if (filename.endsWith('.css')) css.push(source);
  if (!relative.endsWith('tokens.css')) {
    for (const [index, line] of source.split('\n').entries()) {
      if (/(?:^|[^\w])#[0-9a-f]{3,8}(?![\w-])/i.test(line)) {
        errors.push(`${relative}:${index + 1}: move hex colors into the shared token file`);
      }
    }
  }
  if (/\.(tsx|jsx)$/.test(filename)) {
    for (const match of source.matchAll(/<img\b[\s\S]*?>/g)) {
      if (!/\balt\s*=/.test(match[0])) errors.push(`${relative}: image is missing an alt attribute`);
    }
  }
}
const allCss = css.join('\n');
if (!/:focus-visible/.test(allCss)) errors.push('Shared styles must define a visible keyboard focus state');
if (!/prefers-reduced-motion/.test(allCss)) errors.push('Styles must honor prefers-reduced-motion');
if (!/@media/.test(allCss)) errors.push('Styles must include responsive media rules');
if (!files.some(filename => /[/\\]design-system[/\\]page\.tsx$/.test(filename))) errors.push('Missing /design-system development gallery');
const tokenPath = path.join(root, 'packages/design-system/tokens.css');
if (!fs.existsSync(tokenPath)) errors.push('Missing shared semantic token file');
else {
  const tokens = fs.readFileSync(tokenPath, 'utf8');
  for (const name of ['--ks-canvas', '--ks-primary', '--ks-focus', '--ks-font-display', '--ks-font-body']) {
    if (!tokens.includes(name)) errors.push(`Missing semantic token ${name}`);
  }
}
if (errors.length) {
  process.stderr.write(`Design governance failed:\n${errors.map(error => `- ${error}`).join('\n')}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`Design governance passed (${files.length} source files): shared colors, focus, reduced motion, responsive rules, image alt attributes and component gallery.\n`);
  process.stdout.write('Browser layout, keyboard interaction and contrast still require the browser checks.\n');
}
