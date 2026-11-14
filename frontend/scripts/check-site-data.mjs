// Checks the committed site data against its own build record, without the
// raw DOE/NCES files (for CI):
//   - public/data/build_inputs.json lists every file under public/data (but
//     itself) with its SHA-256, and each file on disk matches; no other file;
//   - public/audit.json is step 07's audit of exactly this build (its
//     audited_build.site_record_sha256 is the SHA-256 of build_inputs.json)
//     and every check in it passed.
// etl/00_check_for_updates.py --local-only checks more, but it needs the raw
// files and NCES's website.
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const publicDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'public')
const dataDir = join(publicDir, 'data')
const problems = []

// Git may check text files out with CRLF line ends (core.autocrlf); the ETL
// hashed them with LF, as they are in the repository.
function sha256(file) {
  const bytes = readFileSync(file)
  const raw = createHash('sha256').update(bytes).digest('hex')
  const lf = createHash('sha256').update(Buffer.from(bytes.toString('latin1').replace(/\r\n/g, '\n'), 'latin1')).digest('hex')
  return [raw, lf]
}

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((d) =>
    d.isDirectory() ? walk(join(dir, d.name)) : [relative(dataDir, join(dir, d.name)).split(sep).join('/')]
  )
}

const recordFile = join(dataDir, 'build_inputs.json')
const record = JSON.parse(readFileSync(recordFile, 'utf-8'))
const outputs = record.outputs ?? {}
const onDisk = new Set(walk(dataDir).filter((f) => f !== 'build_inputs.json'))

for (const [name, expected] of Object.entries(outputs)) {
  if (!onDisk.has(name)) {
    problems.push(`build_inputs.json lists ${name}, which is not in public/data`)
    continue
  }
  if (!sha256(join(dataDir, name)).includes(expected)) problems.push(`public/data/${name} does not match its SHA-256 in build_inputs.json`)
  onDisk.delete(name)
}
for (const name of onDisk) problems.push(`public/data/${name} is not in build_inputs.json`)

const audit = JSON.parse(readFileSync(join(publicDir, 'audit.json'), 'utf-8'))
const audited = audit.audited_build ?? {}
if (audited.site_record !== 'frontend/public/data/build_inputs.json') {
  problems.push(`audit.json audited ${audited.site_record ?? 'no site record'}, not frontend/public/data/build_inputs.json`)
}
if (!sha256(recordFile).includes(audited.site_record_sha256)) {
  problems.push('audit.json is not the audit of this build: its site_record_sha256 is not the SHA-256 of build_inputs.json')
}
const summary = audit.summary ?? {}
if (!(summary.total_checks > 0) || summary.failed !== 0 || summary.passed !== summary.total_checks) {
  problems.push(`audit.json does not record every check passed: ${JSON.stringify(summary)}`)
}

if (problems.length) {
  console.error('Site data check failed:\n  ' + problems.join('\n  '))
  process.exit(1)
}
console.log(
  `Site data matches its build record: ${Object.keys(outputs).length} files; ` +
    `audit.json is the audit of this build (${summary.passed}/${summary.total_checks} checks passed).`
)
