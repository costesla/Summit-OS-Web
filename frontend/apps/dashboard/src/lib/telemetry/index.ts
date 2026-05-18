/**
 * SummitOS Dashboard — Telemetry (barrel re-export)
 *
 * This re-exports from the flat telemetry.ts so that both import paths work:
 *   import telemetry from '../lib/telemetry'           ← spec path
 *   import telemetry from '../lib/telemetry/index'     ← deep path
 */
export * from '../telemetry'
export { default } from '../telemetry'
