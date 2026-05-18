#!/usr/bin/env node
/**
 * SummitOS Dashboard — Artifact Cleanliness Guard
 *
 * Fails if any build artifact exists OUTSIDE of dist/.
 * Run this in CI before a commit to guarantee no bundles are tracked.
 *
 * Usage:
 *   node scripts/check-clean-artifacts.mjs          # check entire tree
 *   node scripts/check-clean-artifacts.mjs --staged # check only git-staged files
 *
 * npm script: "check:clean"
 */

import { execSync } from 'child_process'
import { readdirSync, statSync } from 'fs'
import { join, relative, resolve } from 'path'

const STAGED_ONLY = process.argv.includes('--staged')
const ROOT = resolve('.')

// ─── Patterns that indicate a build artifact outside dist/ ───────────────────
const ARTIFACT_PATTERNS = [
  /^index-[a-zA-Z0-9_-]+\.(js|css)$/,   // Vite hashed bundles
  /\.tsbuildinfo$/,                        // TypeScript incremental cache
  /^tsconfig\..*\.tsbuildinfo$/,
]

// ─── Directories to skip entirely ────────────────────────────────────────────
const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', '.next', '.venv', '__pycache__'])

// ─── Directories that ARE allowed to contain these patterns ──────────────────
// (node_modules/.tmp is where we route tsbuildinfo via tsconfig)
const ALLOWED_PREFIXES = [
  'dist/',
  'dist\\',
  'node_modules/',
  'node_modules\\',
]

function isAllowed(relPath) {
  return ALLOWED_PREFIXES.some(p => relPath.startsWith(p))
}

function isArtifact(filename) {
  return ARTIFACT_PATTERNS.some(p => p.test(filename))
}

// ─── Get files to check ───────────────────────────────────────────────────────
function getStagedFiles() {
  try {
    const out = execSync('git diff --cached --name-only --diff-filter=ACM', { encoding: 'utf-8' })
    return out.trim().split('\n').filter(Boolean)
  } catch {
    return []
  }
}

function walkTree(dir, results = []) {
  for (const entry of readdirSync(dir)) {
    if (SKIP_DIRS.has(entry)) continue
    const full = join(dir, entry)
    const rel = relative(ROOT, full)
    if (statSync(full).isDirectory()) {
      walkTree(full, results)
    } else {
      results.push(rel)
    }
  }
  return results
}

const files = STAGED_ONLY ? getStagedFiles() : walkTree(ROOT)

let violations = 0

for (const f of files) {
  if (isAllowed(f)) continue
  const basename = f.split(/[\\/]/).pop() ?? ''
  if (isArtifact(basename)) {
    console.error(`❌ BUILD ARTIFACT outside dist/: ${f}`)
    violations++
  }
}

// Also confirm dist/ isn't being tracked in git (always check this)
try {
  const tracked = execSync('git ls-files dist/', { encoding: 'utf-8' }).trim()
  if (tracked.length > 0) {
    console.error('\n❌ dist/ contents are tracked in git:')
    tracked.split('\n').forEach(f => console.error(`   ${f}`))
    console.error('   Run: git rm --cached -r dist/')
    violations += tracked.split('\n').filter(Boolean).length
  }
} catch {
  // git not available — skip tracking check
}

if (violations > 0) {
  console.error(`\n🚨 ${violations} artifact violation(s) found.`)
  console.error('   Build artifacts must only live in dist/ and must not be committed.')
  console.error('   Fix: git rm --cached <file> for each listed file.')
  process.exit(1)
} else {
  console.log(`✅ Artifact check passed — no build outputs committed outside dist/.`)
}
