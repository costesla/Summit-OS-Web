#!/usr/bin/env node
/**
 * SummitOS Secret Scanner — CI Guard
 *
 * Fails CI if:
 *  1. .env files (with secrets) are staged for commit
 *  2. Common secret patterns appear in staged source files
 *
 * Usage:
 *   node scripts/scan-secrets.mjs                # scan staged files (CI / pre-commit)
 *   node scripts/scan-secrets.mjs --all          # scan entire working tree
 *
 * Add to CI:
 *   - name: Secret scan
 *     run: node frontend/apps/dashboard/scripts/scan-secrets.mjs --all
 */

import { execSync } from 'child_process'
import { readFileSync, readdirSync, statSync } from 'fs'
import { join, relative } from 'path'

const SCAN_ALL = process.argv.includes('--all')

// ─── Patterns that indicate a secret ─────────────────────────────────────────
const SECRET_PATTERNS = [
  { name: 'OpenAI API key',          regex: /sk-[a-zA-Z0-9]{20,}/ },
  { name: 'Azure Storage key',       regex: /AccountKey=[A-Za-z0-9+/=]{40,}/ },
  { name: 'Azure connection string', regex: /DefaultEndpointsProtocol=https;AccountName=/ },
  { name: 'SQL connection string',   regex: /Server=tcp:.*\.database\.windows\.net/ },
  { name: 'OAuth client secret',     regex: /OAUTH_CLIENT_SECRET\s*=\s*[^\s$]/ },
  { name: 'Generic API key',         regex: /API_KEY\s*=\s*[^\s$"']{8,}/ },
  { name: '.env assignment pattern', regex: /^[A-Z_]{4,}=(?!your_|<|PLACEHOLDER|CHANGE_ME).{8,}/m },
]

// ─── File patterns that should never be committed ─────────────────────────────
const FORBIDDEN_FILES = [
  /^\.env$/,
  /^\.env\..+(?<!\.template)$/,
]

// ─── Extensions to scan for secrets ──────────────────────────────────────────
const SCANNABLE_EXTS = new Set(['.ts', '.tsx', '.js', '.jsx', '.json', '.py', '.env'])

let violations = 0

function checkFile(filepath) {
  // 1. Check forbidden filenames
  const basename = filepath.split(/[\\/]/).pop() ?? ''
  for (const pattern of FORBIDDEN_FILES) {
    if (pattern.test(basename)) {
      console.error(`❌ FORBIDDEN FILE: ${filepath}`)
      violations++
      return
    }
  }

  // 2. Check secret patterns in scannable source files
  const ext = '.' + (basename.split('.').pop() ?? '')
  if (!SCANNABLE_EXTS.has(ext)) return

  let content
  try {
    content = readFileSync(filepath, 'utf-8')
  } catch {
    return
  }

  for (const { name, regex } of SECRET_PATTERNS) {
    if (regex.test(content)) {
      console.error(`❌ POSSIBLE SECRET [${name}]: ${filepath}`)
      violations++
    }
  }
}

// ─── Get files to scan ────────────────────────────────────────────────────────
function getStagedFiles() {
  try {
    const out = execSync('git diff --cached --name-only --diff-filter=ACM', { encoding: 'utf-8' })
    return out.trim().split('\n').filter(Boolean)
  } catch {
    return []
  }
}

function getAllFiles(dir, files = []) {
  const IGNORE = new Set(['node_modules', '.git', 'dist', '.next', '.venv'])
  for (const entry of readdirSync(dir)) {
    if (IGNORE.has(entry)) continue
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      getAllFiles(full, files)
    } else {
      files.push(relative(process.cwd(), full))
    }
  }
  return files
}

const files = SCAN_ALL ? getAllFiles('.') : getStagedFiles()

if (files.length === 0) {
  console.log('✅ Secret scan: no files to check.')
  process.exit(0)
}

console.log(`🔍 Scanning ${files.length} file(s) for secrets...`)
for (const f of files) checkFile(f)

if (violations > 0) {
  console.error(`\n🚨 ${violations} violation(s) found. Commit blocked.`)
  console.error('   Review the files above and remove secrets before committing.')
  console.error('   Use Azure Static Web App environment variables for runtime config.')
  process.exit(1)
} else {
  console.log(`✅ Secret scan passed — ${files.length} file(s) clean.`)
}
