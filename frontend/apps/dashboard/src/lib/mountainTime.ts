/**
 * Operating-timezone date helpers.
 *
 * The business runs in Mountain Time and every date the API stores or filters
 * on is a Mountain-Time calendar date. `new Date().toISOString()` yields a UTC
 * date, which is a DIFFERENT DAY from 6:00 PM Mountain until midnight — so any
 * field defaulted from it silently books evening work to tomorrow.
 *
 * Confirmed 2026-08-19: the Manual Ledger's date input pre-filled 2026-08-19
 * for an entry logged at 7:00 PM Mountain on 2026-08-18, while the dashboard
 * around it displayed 2026-08-18.
 *
 * 'sv-SE' is used because it formats as ISO-8601 (YYYY-MM-DD); the locale is a
 * formatting device, not a language choice. America/Denver resolves MST/MDT on
 * its own, so this stays correct across daylight-saving transitions.
 */

const OPERATING_TIME_ZONE = 'America/Denver'

/** Today's Mountain-Time calendar date as YYYY-MM-DD. */
export function todayInMountainTime(date: Date = new Date()): string {
  return date.toLocaleDateString('sv-SE', { timeZone: OPERATING_TIME_ZONE })
}

/** The current Mountain-Time month as YYYY-MM. */
export function currentMonthInMountainTime(date: Date = new Date()): string {
  return todayInMountainTime(date).slice(0, 7)
}
