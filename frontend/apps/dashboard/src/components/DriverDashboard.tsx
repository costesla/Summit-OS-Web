import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
    LayoutDashboard, Route, Receipt, Zap, Wrench, TrendingUp,
    DollarSign, Car, ShieldAlert, CheckCircle, ExternalLink,
    ChevronDown, ChevronUp, Plus, Loader2, MapPin, Gauge, Battery, Link2
} from 'lucide-react';
import { isBackgroundableError, devDebugError, getAsyncExecutionLogs, pollJobStatus } from '../../../../src/lib/intelligenceUtils';
import { apiGet, apiPost } from '../lib/apiClient';
import PaymentTrackerPanel from './payments/PaymentTrackerPanel';
import TellerConnectButton from './TellerConnectButton';

const AZURE_BASE = import.meta.env.VITE_PUBLIC_API_BASE_URL || import.meta.env.VITE_API_BASE_URL || 'https://summitos-api.azurewebsites.net/api';
const VERSION = "2.0.0";

// Helper: today in Mountain Time
const getTodayMST = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'America/Denver' });

// Helper: first name of operator
const firstName = (name: string | null | undefined): string | null => {
    if (!name) return null;
    return name.trim().split(/\s+/)[0];
};

// Helper: scrub street number for visual privacy
const scrubAddress = (addr: string | null | undefined): string | null => {
    if (!addr) return null;
    return addr.replace(/^\d+\s+/, '');
};

// Helper: strip state/zip/country — "Street, City, State ZIP, Country" → "Street, City"
const formatLocation = (raw: string | null | undefined): string => {
    if (!raw) return 'Unknown';
    const parts = raw.split(',').map(p => p.trim()).filter(Boolean);
    return parts.slice(0, 2).join(', ');
};

// Revenue targets — derived from env var, never hardcoded separately
const MONTHLY_TARGET = parseInt(import.meta.env.VITE_REVENUE_TARGET_MONTHLY ?? '6500') || 6500;
const WEEKLY_TARGET  = Math.round(MONTHLY_TARGET / 4);
const DAILY_TARGET   = Math.round(WEEKLY_TARGET / 7);

// Helper: get payment status badge JSX
const getPaymentStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
        case 'paid':
            return <span className="px-2 py-0.5 rounded-full bg-[var(--accent-green)]/10 text-[var(--accent-green)] text-[9px] font-bold uppercase border border-[var(--accent-green)]/20">Paid</span>;
        case 'deferred':
            return <span className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-[9px] font-bold uppercase border border-amber-500/20">Deferred</span>;
        case 'credit':
            return <span className="px-2 py-0.5 rounded-full bg-[var(--accent-purple)]/10 text-[var(--accent-purple)] text-[9px] font-bold uppercase border border-[var(--accent-purple)]/20">Credit</span>;
        default:
            return <span className="px-2 py-0.5 rounded-full bg-white/5 text-[var(--text-muted)] text-[9px] font-bold uppercase border border-white/5">{status}</span>;
    }
};

// Helper: get client DisplayName from RideID or classification
const getClientDisplayName = (t: DatabaseTrip) => {
    const id = t.id || "";
    if (id.startsWith("INV-")) {
        const parts = id.split("-");
        if (parts.length >= 2) {
            const rawName = parts[1].toLowerCase();
            if (rawName === "jackie" || rawName === "jacquelyn") return "Jackie";
            return parts[1].charAt(0).toUpperCase() + parts[1].slice(1).toLowerCase();
        }
    }
    const classification = t.classification || "";
    if (classification && classification !== "Private_Booking" && classification !== "Manual_Entry") {
        return classification;
    }
    return "Private Client";
};

// Helper: convert UTC ISO date string to MST/MDT local time HH:MM format
const formatToLocalTime = (utcString: string | null | undefined): string => {
    if (!utcString) return "";
    try {
        const date = new Date(utcString.endsWith("Z") ? utcString : utcString + "Z");
        return date.toLocaleTimeString('en-US', {
            timeZone: 'America/Denver',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
    } catch {
        return utcString.slice(11, 16);
    }
};

// Types & Interfaces
type Section = 'home' | 'trips' | 'financials' | 'charging' | 'tools';

interface TeslaStatus {
    is_charging: boolean;
    charging_state: string | null;
    current_soc: number | null;
    battery_range_mi: number | null;
    charge_power_kw: number;
    minutes_to_full: number | null;
    location: string | null;
    inside_temp: number | null;
    outside_temp: number | null;
    vehicle_asleep?: boolean;
    formatted_time?: string;
    charge_energy_added?: number | null;
    running_cost_estimate?: number | null;
    charging_rate_per_kwh?: number;
}

interface PreShiftCheckResponse {
    overall_status: 'PASS' | 'WARN' | 'FAIL' | 'N_A';
    overall_confidence: number | null;
    generated_at: string;
    tiers?: {
        tier1_trips?: { status: string; issues?: string[] };
        tier2_earnings?: { status: string; issues?: string[] };
        tier3_expenses?: { status: string; issues?: string[] };
        tier4_timeline?: { status: string; issues?: string[] };
    };
    systems?: {
        db?: { online: boolean; latency_ms: number };
        tessie?: { online: boolean; latency_ms: number };
        onedrive?: { online: boolean; latency_ms: number };
        bank?: { online: boolean; latency_ms: number };
    };
}

interface FinancialsSummaryResponse {
    success: boolean;
    date: string;
    gross_earnings: number;
    uber_earnings: number;
    private_income: number;
    expenses: number;
    opex_expenses?: number;
    capex_expenses?: number;
    net_profit: number;
    deferred_total: number;
    targets: {
        daily: number;
        weekly: number;
        monthly: number;
    };
    progress: {
        today: { actual: number; target: number };
        week: { actual: number; target: number };
        month: { actual: number; target: number };
    };
}

interface DatabaseTrip {
    id: string;
    type: 'Uber' | 'Private';
    fare: number;
    tip: number;
    fees: number;
    distance_miles: number;
    timestamp: string;
    classification: string | null;
    pickup_location: string | null;
    dropoff_location: string | null;
    tessie_drive_id?: string | null;
    tessie_label?: string | null;
}

interface TessieDrive {
    tessie_drive_id: string;
    date: string | null;
    time_mst: string | null;
    tag: string | null;
    distance_miles: number;
    energy_used_kwh: number;
    efficiency_wh_mi: number | null;
    average_speed_mph: number;
    start: string | null;
    end: string | null;
    starting_battery: number | null;
    ending_battery: number | null;
    duration_minutes: number;
    fare_matched?: boolean;
    driver_earnings?: number | null;
}

interface TessieCharge {
    tessie_charge_id: string | null;
    date: string | null;
    time_mst: string | null;
    energy_added_kwh: number;
    starting_soc: number | null;
    ending_soc: number | null;
    duration_minutes: number | null;
    location: string | null;
    charge_type: string | null;
    is_live?: boolean;
    charge_power_kw?: number;
    running_cost_estimate?: number | null;
    charging_rate_per_kwh?: number;
}

interface ExpenseItem {
    id: string;
    category: string;
    amount: number;
    note: string;
    timestamp: string;
    included_in_kpi?: number;
    expense_type?: 'OpEx' | 'CapEx';
}

// Main Component
const DriverDashboard: React.FC = () => {
    const todayMST = getTodayMST();
    const [selectedDate, setSelectedDate] = useState<string>(todayMST);
    const [section, setSection] = useState<Section>('home');
    const [tripsTab, setTripsTab] = useState<'ledger' | 'telemetry'>('ledger');
    
    // Core State
    const [azureUser, setAzureUser] = useState<{ name?: string; email?: string } | null>(null);
    const [teslaLive, setTeslaLive] = useState<TeslaStatus | null>(null);
    const [preShift, setPreShift] = useState<PreShiftCheckResponse | null>(null);
    const [summary, setSummary] = useState<FinancialsSummaryResponse | null>(null);
    const [trips, setTrips] = useState<DatabaseTrip[]>([]);
    const [drives, setDrives] = useState<TessieDrive[]>([]);
    const [charges, setCharges] = useState<TessieCharge[]>([]);
    const [loggedExpenses, setLoggedExpenses] = useState<{
        fastfood: ExpenseItem[];
        charging: ExpenseItem[];
        capital_maintenance: ExpenseItem[];
    }>({ fastfood: [], charging: [], capital_maintenance: [] });
    const [expenseLedgerTab, setExpenseLedgerTab] = useState<'opex' | 'capex'>('opex');
    
    // Loading States
    const [loadingSummary, setLoadingSummary] = useState(false);
    const [loadingPreShift, setLoadingPreShift] = useState(false);
    const [loadingTrips, setLoadingTrips] = useState(false);


    
    // Action States & Modals
    const [logs, setLogs] = useState<string[]>([]);
    const [status, setStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
    const [scrubConfirmOpen, setScrubConfirmOpen] = useState(false);
    const [isMobileQuickLogOpen, setIsMobileQuickLogOpen] = useState(false);
    const [lastSyncTime, setLastSyncTime] = useState<Date>(new Date());
    const [syncIntervalText, setSyncIntervalText] = useState("Just now");
    
    // Forms
    const [cashTipAmount, setCashTipAmount] = useState('');
    const [cashTipNote, setCashTipNote] = useState('');
    const [isLoggingTip, setIsLoggingTip] = useState(false);

    const [privatePaymentClient, setPrivatePaymentClient] = useState('');
    const [privatePaymentAmount, setPrivatePaymentAmount] = useState('');
    const [privatePaymentNote, setPrivatePaymentNote] = useState('');
    const [isLoggingPrivate, setIsLoggingPrivate] = useState(false);

    const [expenseAmount, setExpenseAmount] = useState('');
    const [expenseCategory, setExpenseCategory] = useState('Food');
    const [expenseNote, setExpenseNote] = useState('');
    const [expenseType, setExpenseType] = useState<'OpEx' | 'CapEx'>('OpEx');
    const [isLoggingExpense, setIsLoggingExpense] = useState(false);

    // Collapsible Panels
    const [expensesCollapsed, setExpensesCollapsed] = useState(true);
    const [unpaidCollapsed, setUnpaidCollapsed] = useState(true);
    const [paymentTrackerCollapsed, setPaymentTrackerCollapsed] = useState(false);
    const [paymentAnomalyCount, setPaymentAnomalyCount] = useState(0);

    const activePollRef = useRef<(() => void) | null>(null);

    // ─── Fetch Helper: All Data ───────────────────────────────────────────────────
    const fetchAllData = useCallback(async () => {
        setLoadingSummary(true);
        setLoadingPreShift(true);
        setLoadingTrips(true);

        try {
            // 1. Fetch Financials Summary
            const summaryRes = await apiGet<FinancialsSummaryResponse>(`/financials/summary?date=${selectedDate}`);
            setSummary(summaryRes);
        } catch (e) {
            console.error("Summary fetch error:", e);
        } finally {
            setLoadingSummary(false);
        }

        try {
            // 2. Fetch Pre-Shift Check Status
            const preShiftRes = await apiGet<PreShiftCheckResponse>(`/pre-shift-check?date=${selectedDate}`);
            setPreShift(preShiftRes);
        } catch (e) {
            console.error("Pre-shift check error:", e);
        } finally {
            setLoadingPreShift(false);
        }

        try {
            // 3. Fetch ledger trips and expenses (combines Uber + Private)
            const syncRes = await apiGet<{
                trips: DatabaseTrip[];
                expenses?: {
                    fastfood: ExpenseItem[];
                    charging: ExpenseItem[];
                    capital_maintenance: ExpenseItem[];
                };
            }>(`/driver/sync?date=${selectedDate}`);
            setTrips(syncRes.trips || []);
            if (syncRes.expenses) {
                setLoggedExpenses(syncRes.expenses);
            } else {
                setLoggedExpenses({ fastfood: [], charging: [], capital_maintenance: [] });
            }
        } catch (e) {
            console.error("Ledger fetch error:", e);
        } finally {
            setLoadingTrips(false);
        }

        try {
            // 4. Fetch Tessie Drives for telemetry
            const drivesRes = await apiGet<{ drives: TessieDrive[] }>(`/copilot/tessie/drives?days=2`);
            // Filter to selected date
            const filteredDrives = (drivesRes.drives || []).filter(d => d.date === selectedDate);
            setDrives(filteredDrives);
        } catch (e) {
            console.error("Drives fetch error:", e);
        }

        try {
            // 5. Fetch Tessie Charges for telemetry
            const chargesRes = await apiGet<{ sessions: TessieCharge[] }>(`/copilot/tessie/charges?days=2`);
            const filteredCharges = (chargesRes.sessions || []).filter(c => c.date === selectedDate);
            setCharges(filteredCharges);
        } catch (e) {
            console.error("Charges fetch error:", e);
        }

        setLastSyncTime(new Date());
    }, [selectedDate]);

    // Live status polling
    useEffect(() => {
        fetchAllData();
        const interval = setInterval(fetchAllData, 60_000);
        return () => clearInterval(interval);
    }, [fetchAllData]);



    // Update synced footer timing text
    useEffect(() => {
        const interval = setInterval(() => {
            const diffSec = Math.floor((new Date().getTime() - lastSyncTime.getTime()) / 1000);
            if (diffSec < 60) {
                setSyncIntervalText("Just now");
            } else {
                setSyncIntervalText(`${Math.floor(diffSec / 60)}m ago`);
            }
        }, 10_000);
        return () => clearInterval(interval);
    }, [lastSyncTime]);

    // Fetch live vehicle status (battery, temp, asleep/charging status)
    useEffect(() => {
        const fetchTeslaLive = async () => {
            try {
                const res = await apiGet<TeslaStatus>('/copilot/charging/live');
                setTeslaLive(res);
            } catch (e) {
                console.error("Tesla live status error:", e);
            }
        };
        fetchTeslaLive();
        const teslaInterval = setInterval(fetchTeslaLive, 30_000);
        return () => clearInterval(teslaInterval);
    }, []);

    // Get azure AD user identity
    useEffect(() => {
        fetch('/.auth/me')
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                const p = data?.clientPrincipal;
                if (p) setAzureUser({ name: p.userDetails });
            })
            .catch(() => {});
    }, []);

    // Cleanup async polling on unmount
    useEffect(() => () => {
        if (activePollRef.current) activePollRef.current();
    }, []);

    const cleanupActivePoll = () => {
        if (activePollRef.current) {
            activePollRef.current();
            activePollRef.current = null;
        }
    };

    // ─── Actions: Rebuild / Sync pipeline ──────────────────────────────────────────
    const runRebuild = async () => {
        cleanupActivePoll();
        setStatus('running');
        const initText = `> Launching Rebuild Day for ${selectedDate}...`;
        setLogs([initText]);
        try {
            const data = await apiPost<{ status: string; jobId?: string; success?: boolean; logs?: string[]; error?: string }>('/tools/rebuild-day', { date: selectedDate });
            if (data.status === 'accepted' && data.jobId) {
                const base = [initText];
                const initJ = getAsyncExecutionLogs(data.jobId);
                setLogs([...base, ...initJ]);
                const stop = pollJobStatus(
                    AZURE_BASE,
                    data.jobId,
                    jl => setLogs([...base, ...initJ, ...jl]),
                    () => {
                        setStatus('success');
                        setLogs(p => [...p, '> [SUCCESS] Rebuild day complete.']);
                        fetchAllData();
                    },
                    em => {
                        setStatus('error');
                        setLogs(p => [...p, `> [ERROR] ${em}`]);
                    }
                );
                activePollRef.current = stop;
            } else if (data.success) {
                setStatus('success');
                setLogs(p => [...p, ...(data.logs || []), '> [SUCCESS] Rebuild day complete.']);
                fetchAllData();
            } else {
                setStatus('error');
                setLogs(p => [...p, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            devDebugError(err);
            if (isBackgroundableError(err)) {
                setStatus('success');
                setLogs(p => [...p, '> [NOTICE] Pipeline sync running in background.', '> Please wait 60s and refresh.']);
                setTimeout(fetchAllData, 60_000);
            } else {
                const errMsg = err instanceof Error ? err.message : String(err);
                setStatus('error');
                setLogs(p => [...p, `> [CRITICAL] ${errMsg}`]);
            }
        }
    };

    // ─── Actions: Scrub Day ────────────────────────────────────────────────────────
    const runScrub = async () => {
        setScrubConfirmOpen(false);
        cleanupActivePoll();
        setStatus('running');
        const initText = `> Wiping pipeline-generated records for ${selectedDate}...`;
        setLogs([initText]);
        try {
            const data = await apiPost<{ success: boolean; logs?: string[]; error?: string }>('/tools/scrub-day', { date: selectedDate });
            if (data.success) {
                setStatus('success');
                setLogs(p => [...p, ...(data.logs || []), '> [SUCCESS] Day scrubbed clean.']);
                fetchAllData();
            } else {
                setStatus('error');
                setLogs(p => [...p, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            const errMsg = err instanceof Error ? err.message : String(err);
            setStatus('error');
            setLogs(p => [...p, `> [CRITICAL] ${errMsg}`]);
        }
    };

    // ─── Actions: Create Folders ───────────────────────────────────────────────────
    const runCreateFolders = async () => {
        cleanupActivePoll();
        setStatus('running');
        const initText = `> Creating OneDrive folder structure for ${selectedDate}...`;
        setLogs([initText]);
        try {
            const data = await apiPost<{ status: string; jobId?: string; success?: boolean; logs?: string[]; error?: string }>('/tools/create-folders', { date: selectedDate });
            if (data.status === 'accepted' && data.jobId) {
                const base = [initText];
                const initJ = getAsyncExecutionLogs(data.jobId);
                setLogs([...base, ...initJ]);
                const stop = pollJobStatus(
                    AZURE_BASE,
                    data.jobId,
                    jl => setLogs([...base, ...initJ, ...jl]),
                    () => {
                        setStatus('success');
                        setLogs(p => [...p, '> [SUCCESS] Folder structure created successfully.']);
                    },
                    em => {
                        setStatus('error');
                        setLogs(p => [...p, `> [ERROR] ${em}`]);
                    }
                );
                activePollRef.current = stop;
            } else if (data.success) {
                setStatus('success');
                setLogs(p => [...p, ...(data.logs || []), '> [SUCCESS] Folder structure created successfully.']);
            } else {
                setStatus('error');
                setLogs(p => [...p, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            const errMsg = err instanceof Error ? err.message : String(err);
            setStatus('error');
            setLogs(p => [...p, `> [CRITICAL] ${errMsg}`]);
        }
    };

    // ─── Actions: Save Day to Cloud ────────────────────────────────────────────────
    const runSaveDay = async () => {
        setStatus('running');
        setLogs(p => [...p, `> Saving manually logged day's data to cloud...`]);
        try {
            const data = await apiPost<{ success: boolean; results?: unknown; error?: string }>('/tools/save-day', {
                trips: trips.filter(t => t.id.startsWith("M-")),
                expenses: { fastfood: [], charging: [], capital_maintenance: [] }
            });
            if (data.success) {
                setStatus('success');
                setLogs(p => [...p, `> [SUCCESS] Day manually saved to cloud database.`]);
                fetchAllData();
            } else {
                setStatus('error');
                setLogs(p => [...p, `> [ERROR] ${data.error}`]);
            }
        } catch (err: unknown) {
            const errMsg = err instanceof Error ? err.message : String(err);
            setStatus('error');
            setLogs(p => [...p, `> [CRITICAL] ${errMsg}`]);
        }
    };

    // ─── Actions: Logging tips / private income from QuickLog ────────────────────────
    const handleLogCashTip = async (e: React.FormEvent) => {
        e.preventDefault();
        const amt = parseFloat(cashTipAmount);
        if (!amt) return;
        setIsLoggingTip(true);
        try {
            const timestamp = `${selectedDate}T${new Date().toTimeString().split(' ')[0]}`;
            await apiPost('/driver/sync', {
                trips: [{
                    id: `M-TIP-${Date.now()}`,
                    type: "Private",
                    fare: 0.0,
                    tip: amt,
                    distance_miles: 0,
                    timestamp,
                    classification: "Cash Tip",
                    pickup_location: "Cash Gratuity",
                    dropoff_location: "Cash Gratuity",
                    payment_status: "Paid"
                }]
            });
            setCashTipAmount('');
            setCashTipNote('');
            setIsMobileQuickLogOpen(false);
            fetchAllData();
        } catch (e) {
            console.error("Log cash tip failed:", e);
        } finally {
            setIsLoggingTip(false);
        }
    };

    const handleLogPrivatePayment = async (e: React.FormEvent) => {
        e.preventDefault();
        const amt = parseFloat(privatePaymentAmount);
        if (!amt) return;
        setIsLoggingPrivate(true);
        try {
            const timestamp = `${selectedDate}T${new Date().toTimeString().split(' ')[0]}`;
            await apiPost('/driver/sync', {
                trips: [{
                    id: `M-PRIV-${Date.now()}`,
                    type: "Private",
                    fare: amt,
                    tip: 0.0,
                    distance_miles: 0,
                    timestamp,
                    classification: privatePaymentClient || "Private",
                    pickup_location: privatePaymentNote || "Private Booking",
                    dropoff_location: privatePaymentNote || "Private Booking",
                    payment_status: "Paid"
                }]
            });
            setPrivatePaymentClient('');
            setPrivatePaymentAmount('');
            setPrivatePaymentNote('');
            setIsMobileQuickLogOpen(false);
            fetchAllData();
        } catch (e) {
            console.error("Log private payment failed:", e);
        } finally {
            setIsLoggingPrivate(false);
        }
    };

    const handleLogExpense = async (e: React.FormEvent) => {
        e.preventDefault();
        const amt = parseFloat(expenseAmount);
        if (!amt) return;
        setIsLoggingExpense(true);
        try {
            const timestamp = `${selectedDate}T${new Date().toTimeString().split(' ')[0]}`;
            const expenseItem = {
                id: `M-EXP-${Date.now()}`,
                category: expenseCategory,
                amount: amt,
                note: expenseNote,
                timestamp,
                expense_type: expenseType
            };

            await apiPost('/driver/sync', {
                trips: [],
                expenses: {
                    fastfood: expenseType === 'OpEx' ? [expenseItem] : [],
                    charging: [],
                    capital_maintenance: expenseType === 'CapEx' ? [expenseItem] : []
                }
            });

            setExpenseAmount('');
            setExpenseNote('');
            setIsMobileQuickLogOpen(false);
            fetchAllData();
        } catch (err) {
            console.error("Log expense failed:", err);
        } finally {
            setIsLoggingExpense(false);
        }
    };

    // ─── Calculations ─────────────────────────────────────────────────────────────
    const preShiftScore = preShift?.overall_confidence ?? 100;
    const healthBadgeColor = preShiftScore >= 70 ? 'border-[var(--accent-cyan)] text-[var(--accent-cyan)] bg-[var(--accent-cyan)]/5' : 'border-[var(--accent-red)] text-[var(--accent-red)] bg-[var(--accent-red)]/5 animate-pulse';

    const unpaidOtherInvoices = useMemo(() => {
        return trips.filter(t => t.type === 'Private' && t.fare > 0);
    }, [trips]);

    // Telemetry Timeline events combination
    const timelineEvents = useMemo(() => {
        const items: Array<{ time: string; type: 'Trip' | 'Charge' | 'Idle'; details: string; socChange?: string; stats: string }> = [];
        
        // Add Drives
        drives.forEach(d => {
            const timeStr = d.time_mst || "00:00";
            
            // Calculate energy used
            let kwhVal = d.energy_used_kwh;
            if (!kwhVal && d.starting_battery !== null && d.ending_battery !== null) {
                kwhVal = Math.max(0, ((d.starting_battery - d.ending_battery) / 100) * 75);
            }
            const kwh = kwhVal ? `${kwhVal.toFixed(1)} kWh` : "N/A kWh";

            // Calculate efficiency
            let effVal = d.efficiency_wh_mi;
            if (effVal === null && kwhVal && d.distance_miles > 0) {
                effVal = Math.round((kwhVal * 1000) / d.distance_miles);
            }
            const efficiency = effVal ? `${effVal} Wh/mi` : "N/A Wh/mi";

            const socStr = d.starting_battery !== null && d.ending_battery !== null ? `${d.starting_battery}% → ${d.ending_battery}%` : "";
            
            // Clean location addresses
            const startLoc = d.tag || scrubAddress(formatLocation(d.start)) || "Unknown Start";
            const endLoc = scrubAddress(formatLocation(d.end)) || "Unknown End";

            items.push({
                time: timeStr,
                type: 'Trip',
                details: `${startLoc} to ${endLoc}`,
                socChange: socStr,
                stats: `${d.distance_miles.toFixed(1)} mi · ${d.duration_minutes}m · ${kwh} · ${efficiency}`
            });
        });

        // Add Charges
        charges.forEach(c => {
            const timeStr = c.time_mst || "00:00";
            const duration = c.duration_minutes ? `${c.duration_minutes}m` : "N/A";
            const added = c.energy_added_kwh ? `+${c.energy_added_kwh.toFixed(1)} kWh` : "";
            const socStr = c.starting_soc !== null && c.ending_soc !== null ? `${c.starting_soc}% → ${c.ending_soc}%` : "";
            const cost = c.running_cost_estimate ? `$${c.running_cost_estimate.toFixed(2)}` : "";

            items.push({
                time: timeStr,
                type: 'Charge',
                details: `Charging Session at ${formatLocation(c.location) || "Supercharger"}`,
                socChange: socStr,
                stats: `${added} · ${duration} · ${cost}`
            });
        });

        // Sort chronological
        items.sort((a, b) => a.time.localeCompare(b.time));
        return items;
    }, [drives, charges]);

    // Filter and format private bookings for Ledger
    const privateBookings = useMemo(() => {
        return trips.filter(t => 
            t.type === 'Private' && 
            !t.id.startsWith('TESSIE-') &&
            t.classification !== 'Deadhead/Positioning' && 
            t.classification !== 'Positioning' && 
            t.classification !== 'Deadhead' && 
            t.classification !== 'Untagged' &&
            t.classification !== 'POI' &&
            t.classification !== 'Charging'
        );
    }, [trips]);

    // Sort and format Uber trips for Ledger
    const uberTrips = useMemo(() => {
        return trips.filter(t => t.type === 'Uber' && !t.id.startsWith('TESSIE-'))
                    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    }, [trips]);

    // Read live SQL summary metrics directly
    const grossEarnings = summary?.gross_earnings ?? 0;
    const uberEarnings = summary?.uber_earnings ?? 0;
    const privateIncome = summary?.private_income ?? 0;
    const netProfit = grossEarnings - (summary?.opex_expenses ?? 0);
    const deferredTotal = summary?.deferred_total ?? 0;

    // Use all loading states to satisfy TS
    const isAnyLoading = loadingSummary || loadingPreShift || loadingTrips;

    const navItems = [
        { id: 'home', label: 'Home', icon: <LayoutDashboard className="w-4 h-4" /> },
        { id: 'trips', label: 'Trips', icon: <Route className="w-4 h-4" />, badge: trips.length ? `${trips.length}` : undefined },
        { id: 'financials', label: 'Financials', icon: <Receipt className="w-4 h-4" />, badge: unpaidOtherInvoices.length ? `${unpaidOtherInvoices.length} unpaid` : undefined },
        { id: 'charging', label: 'Charging', icon: <Zap className="w-4 h-4" />, badge: charges.length ? `${charges.length}` : undefined },
        { id: 'tools', label: 'Tools', icon: <Wrench className="w-4 h-4" /> }
    ];

    const greeting = new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 17 ? 'afternoon' : 'evening';

    return (
        <div className="flex flex-col min-h-screen text-white bg-[var(--bg-void)]">
            
            {/* ─── TeslaLiveBar (Pinned top, sticky, full width) ────────────────────── */}
            <header className="sticky top-0 z-50 h-12 flex items-center justify-between px-4 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] backdrop-blur-md">
                <div className="flex items-center gap-3">
                    <span className="text-sm font-black tracking-tighter uppercase bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-blue-500 font-mono">Thor</span>
                    {isAnyLoading && <Loader2 className="w-3.5 h-3.5 text-[var(--accent-cyan)] animate-spin shrink-0" />}
                    <div className="h-4 w-[1px] bg-white/10 hidden md:block" />
                    {/* Live SOC inline progress bar */}
                    <div className="flex items-center gap-2 text-xs font-mono text-[var(--text-muted)]">
                        <Battery className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span className="font-bold text-white">{teslaLive?.current_soc ?? 78}%</span>
                        <div className="hidden sm:block w-16 h-1.5 bg-white/5 rounded-full overflow-hidden border border-white/5">
                            <div className="h-full bg-emerald-400 rounded-full" style={{ width: `${teslaLive?.current_soc ?? 78}%` }} />
                        </div>
                        <span className="hidden md:inline">({teslaLive?.battery_range_mi ?? 245} mi range)</span>
                    </div>
                </div>
                
                {/* Status elements */}
                <div className="flex items-center gap-3 text-xs font-mono">
                    {/* Live SQL Badge */}
                    <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[9px] font-black uppercase tracking-wider shrink-0 flex items-center gap-1 select-none">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        LIVE
                    </span>
                    {/* Global Date Picker */}
                    <input
                        type="date"
                        value={selectedDate}
                        onChange={(e) => setSelectedDate(e.target.value)}
                        className="px-2.5 py-1 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[var(--accent-cyan)] font-mono max-w-[120px] sm:max-w-none"
                    />
                    <div className="hidden md:flex items-center gap-1.5 text-[var(--text-muted)]">
                        <MapPin className="w-3 h-3 text-[var(--accent-cyan)]" />
                        <span>{teslaLive?.location ? scrubAddress(teslaLive.location) : "Home Garage"}</span>
                    </div>
                    <div className="hidden sm:flex items-center gap-1.5 text-[var(--text-muted)]">
                        <Gauge className="w-3 h-3 text-amber-400" />
                        <span>Cabin: {teslaLive?.inside_temp ?? 70}°F</span>
                    </div>
                    {/* Health Check Badge */}
                    <button onClick={() => setSection('tools')}
                        className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[10px] font-bold uppercase transition-all duration-300 ${healthBadgeColor}`}>
                        <div className={`w-1.5 h-1.5 rounded-full ${preShiftScore >= 70 ? 'bg-[var(--accent-cyan)]' : 'bg-[var(--accent-red)] animate-ping'}`} />
                        <span>SYS CHECK: {preShiftScore}/100</span>
                    </button>
                </div>
            </header>

            <div className="flex flex-1">
                {/* ─── Sidebar (200px width, sticky desktop, hidden mobile) ─────────────── */}
                <aside className="hidden md:flex fixed left-0 top-12 bottom-0 w-52 flex-col p-3 border-r border-[var(--border-subtle)] bg-[var(--bg-surface)] overflow-y-auto z-40">
                    <div className="mb-4 px-3 pt-2">
                        <span className="text-base font-black tracking-tight text-white uppercase font-mono">SummitOS <span className="text-[var(--accent-cyan)]">v2</span></span>
                    </div>
                    <div className="flex-1 space-y-1">
                        {navItems.map(n => (
                            <button key={n.id} onClick={() => setSection(n.id as Section)} 
                                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-200 font-semibold text-sm border
                                ${section === n.id 
                                    ? 'bg-[var(--accent-cyan)]/5 text-[var(--accent-cyan)] border-[var(--accent-cyan)]/20' 
                                    : 'text-[var(--text-muted)] hover:text-white hover:bg-white/5 border-transparent'}`}>
                                <span className={`shrink-0 ${section === n.id ? 'text-[var(--accent-cyan)]' : 'text-[var(--text-muted)]'}`}>{n.icon}</span>
                                <span className="flex-1">{n.label}</span>
                                {n.badge && (
                                    <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-mono font-bold ${n.badge.includes('unpaid') ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' : 'bg-white/5 text-[var(--text-muted)] border border-white/5'}`}>{n.badge}</span>
                                )}
                            </button>
                        ))}
                    </div>
                    {/* Synced footer */}
                    <div className="mt-auto px-3 py-2 pt-4 border-t border-white/5 flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                        <span className="text-[9px] font-mono text-[var(--text-muted)]">Pipeline synced · {syncIntervalText} · v{VERSION}</span>
                    </div>
                </aside>

                {/* ─── Main Content Area ──────────────────────────────────────────────── */}
                <main className="flex-1 md:pl-52 min-w-0 overflow-y-auto">
                    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">

                        {/* ─────────────────────────────────────────────────────────────
                            SECTION: HOME
                        ───────────────────────────────────────────────────────────── */}
                        {section === 'home' && (
                            <div className="space-y-6">
                                <div>
                                    <h1 className="text-2xl font-black tracking-tight">Good {greeting}{azureUser?.name ? `, ${firstName(azureUser.name)}` : ''}</h1>
                                    <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{selectedDate} · Operator Console</p>
                                </div>

                                {/* HealthAlertBanner */}
                                {preShift && (
                                    <div className={`p-4 rounded-2xl border ${preShiftScore < 70 ? 'border-[var(--accent-red)]/30 bg-[var(--accent-red)]/5 text-[var(--accent-red)]' : 'border-[var(--accent-cyan)]/25 bg-[var(--accent-cyan)]/5 text-[var(--accent-cyan)]'} flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3`}>
                                        <div className="flex items-center gap-3">
                                            {preShiftScore < 70
                                                ? <ShieldAlert className="w-5 h-5 text-[var(--accent-red)] shrink-0" />
                                                : <CheckCircle className="w-5 h-5 text-[var(--accent-cyan)] shrink-0" />}
                                            <div>
                                                <h4 className="text-xs font-bold uppercase tracking-wider font-mono">SYS CHECK Status: {preShiftScore < 70 ? "Attention Required" : "All Systems Nominal"}</h4>
                                                <p className="text-[10px] text-[var(--text-muted)] mt-0.5 font-mono">
                                                    Current Score: {preShiftScore}/100 · {preShiftScore < 70 ? `${Object.values(preShift.tiers || {}).filter(t => t?.status !== 'PASS').length} warning(s) found` : "No issues detected"}
                                                </p>
                                            </div>
                                        </div>
                                        <button onClick={() => setSection('tools')}
                                            className="px-3 py-1 bg-white/5 border border-white/10 hover:bg-white/10 rounded-lg text-[10px] font-bold uppercase font-mono tracking-wider text-white transition-all w-fit">
                                            Inspect check
                                        </button>
                                    </div>
                                )}

                                {/* StatGrid */}
                                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                                    <StatCard label="Gross Earnings" value={`$${grossEarnings.toFixed(2)}`} sub="Today's aggregate" icon={<TrendingUp className="w-4.5 h-4.5" />} color="cyan" highlight />
                                    <StatCard label="Uber Earnings" value={`$${uberEarnings.toFixed(2)}`} sub="Core rideshare" icon={<Car className="w-4.5 h-4.5" />} color="cyan" />
                                    <StatCard label="Private Income" value={`$${privateIncome.toFixed(2)}`} sub="Paid invoices only" icon={<DollarSign className="w-4.5 h-4.5" />} color="cyan" />
                                    <StatCard label="Daily OpEx" value={`$${summary?.opex_expenses?.toFixed(2) ?? '0.00'}`} sub="Charging & tolls" icon={<Zap className="w-4.5 h-4.5" />} color="red" />
                                    <StatCard label="CapEx & Maintenance" value={`$${summary?.capex_expenses?.toFixed(2) ?? '0.00'}`} sub="Asset investments" icon={<Wrench className="w-4.5 h-4.5" />} color="amber" />
                                    <StatCard label="Net Profit" value={`$${netProfit.toFixed(2)}`} sub="Gross - OpEx margin" icon={<TrendingUp className="w-4.5 h-4.5" />} color="cyan" highlight />
                                    <StatCard label="Unpaid/Deferred Total" value={`$${deferredTotal.toFixed(2)}`} sub="Outstanding balance" icon={<Receipt className="w-4.5 h-4.5" />} color="amber" />
                                </div>

                                {/* RevenueGoalTracker */}
                                <div className="p-5 rounded-2xl glass space-y-4">
                                    <div>
                                        <h3 className="text-sm font-bold uppercase tracking-wider text-white font-mono">Revenue Goal Progress</h3>
                                        <p className="text-[10px] text-[var(--text-muted)]">Real-time tracking vs targets</p>
                                    </div>
                                    <div className="space-y-4">
                                        <GoalProgressRow label="Today" actual={summary?.progress?.today?.actual ?? grossEarnings} target={summary?.targets?.daily ?? DAILY_TARGET} />
                                        <GoalProgressRow label="This Week" actual={summary?.progress?.week?.actual ?? 0} target={summary?.targets?.weekly ?? WEEKLY_TARGET} />
                                        <GoalProgressRow label="This Month" actual={summary?.progress?.month?.actual ?? 0} target={summary?.targets?.monthly ?? MONTHLY_TARGET} />
                                    </div>
                                </div>

                                {/* QuickLogRow */}
                                <div className="flex flex-wrap items-center gap-2 justify-between">
                                    <div className="flex flex-wrap gap-2">
                                        <button onClick={() => { setSection('financials'); setTimeout(() => document.getElementById("log-cash-tip-form")?.scrollIntoView({ behavior: 'smooth' }), 200); }} 
                                            className="px-4 py-2.5 rounded-xl border border-amber-500/20 bg-amber-500/10 text-amber-400 text-xs font-bold hover:bg-amber-500/20 transition-all">+ Log Cash Tip</button>
                                        <button onClick={() => { setSection('financials'); setTimeout(() => document.getElementById("log-private-payment-form")?.scrollIntoView({ behavior: 'smooth' }), 200); }} 
                                            className="px-4 py-2.5 rounded-xl border border-[var(--accent-purple)]/20 bg-[var(--accent-purple)]/10 text-[var(--accent-purple)] text-xs font-bold hover:bg-[var(--accent-purple)]/20 transition-all">+ Log Private Payment</button>
                                        <button onClick={() => { setSection('financials'); setTimeout(() => document.getElementById("log-expense-form")?.scrollIntoView({ behavior: 'smooth' }), 200); }} 
                                            className="px-4 py-2.5 rounded-xl border border-[var(--accent-cyan)]/20 bg-[var(--accent-cyan)]/10 text-[var(--accent-cyan)] text-xs font-bold hover:bg-[var(--accent-cyan)]/20 transition-all">+ Log Expense</button>
                                        <button onClick={() => { setSection('financials'); setTimeout(() => { document.getElementById("log-expense-form")?.scrollIntoView({ behavior: 'smooth' }); setExpenseCategory('Charging'); }, 200); }} 
                                            className="px-4 py-2.5 rounded-xl border border-rose-500/20 bg-rose-500/10 text-rose-400 text-xs font-bold hover:bg-rose-500/20 transition-all">Scan Receipt</button>
                                    </div>
                                    <button onClick={runSaveDay} 
                                        className="px-4 py-2.5 rounded-xl border border-white/5 bg-white/5 text-[var(--text-muted)] text-xs font-bold hover:bg-white/10 hover:text-white transition-all ml-auto">Save Day to Cloud</button>
                                </div>

                            </div>
                        )}

                        {/* ─────────────────────────────────────────────────────────────
                            SECTION: TRIPS
                        ───────────────────────────────────────────────────────────── */}
                        {section === 'trips' && (
                            <div className="space-y-6">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <h1 className="text-2xl font-black tracking-tight">Trips</h1>
                                        <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{selectedDate} · Rideshare Ledger</p>
                                    </div>
                                    {/* Tab switcher */}
                                    <div className="flex rounded-xl bg-white/5 border border-white/10 p-0.5">
                                        <button onClick={() => setTripsTab('ledger')} className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${tripsTab === 'ledger' ? 'bg-[var(--accent-cyan)] text-[#0a1628]' : 'text-[var(--text-muted)] hover:text-white'}`}>Ledger</button>
                                        <button onClick={() => setTripsTab('telemetry')} className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${tripsTab === 'telemetry' ? 'bg-[var(--accent-cyan)] text-[#0a1628]' : 'text-[var(--text-muted)] hover:text-white'}`}>Telemetry</button>
                                    </div>
                                </div>

                                {tripsTab === 'ledger' ? (
                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                        {/* Private Bookings column */}
                                        <div className="p-5 rounded-2xl glass space-y-4">
                                            <h3 className="text-sm font-bold uppercase tracking-wider text-white font-mono border-b border-white/5 pb-2">Private Bookings</h3>
                                            <div className="space-y-3 max-h-[480px] overflow-y-auto">
                                                {privateBookings.length === 0 ? (
                                                    <p className="text-center text-xs text-[var(--text-muted)] italic py-6">// no private bookings logged</p>
                                                ) : (() => {
                                                    const privateSlots: (DatabaseTrip | null)[] = [...privateBookings];
                                                    while (privateSlots.length < 3) {
                                                        privateSlots.push(null);
                                                    }
                                                    return privateSlots.map((t, idx) => {
                                                        if (!t) {
                                                            return (
                                                                <div key={`private-empty-${idx}`} className="p-3.5 rounded-xl border border-dashed border-white/10 flex items-center justify-center h-[90px] select-none">
                                                                    <span className="text-[10px] text-[var(--text-muted)] italic">// empty slot</span>
                                                                </div>
                                                            );
                                                        }
                                                        const clientName = getClientDisplayName(t);
                                                        return (
                                                            <div key={t.id} className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5 space-y-1.5 hover:bg-white/[0.03] transition-colors">
                                                                <div className="flex items-center justify-between">
                                                                    <span className="text-xs font-bold text-white">{clientName}</span>
                                                                    {getPaymentStatusBadge("Paid")}
                                                                </div>
                                                                <p className="text-[10px] text-[var(--text-muted)] font-mono truncate">{scrubAddress(t.pickup_location)} to {scrubAddress(t.dropoff_location)}</p>
                                                                <div className="flex items-center justify-between pt-1 font-mono">
                                                                    <span className="text-[10px] text-[#606060]">{formatToLocalTime(t.timestamp)}</span>
                                                                    <span className="text-sm font-black text-[var(--accent-cyan)]">${t.fare.toFixed(2)}</span>
                                                                </div>
                                                            </div>
                                                        );
                                                    });
                                                })()}
                                            </div>
                                        </div>

                                        {/* Uber Trips column */}
                                        <div className="p-5 rounded-2xl glass space-y-4">
                                            <h3 className="text-sm font-bold uppercase tracking-wider text-white font-mono border-b border-white/5 pb-2">Uber Trips</h3>
                                            <div className="space-y-3 max-h-[480px] overflow-y-auto">
                                                {uberTrips.length === 0 ? (
                                                    <p className="text-center text-xs text-[var(--text-muted)] italic py-6">// no Uber trips logged</p>
                                                ) : (() => {
                                                    const uberSlots: (DatabaseTrip | null)[] = [...uberTrips];
                                                    while (uberSlots.length < 3) {
                                                        uberSlots.push(null);
                                                    }
                                                    return uberSlots.map((t, idx) => {
                                                        if (!t) {
                                                            return (
                                                                <div key={`uber-empty-${idx}`} className="p-3.5 rounded-xl border border-dashed border-white/10 flex items-center justify-center h-[90px] select-none">
                                                                    <span className="text-[10px] text-[var(--text-muted)] italic">// empty slot</span>
                                                                </div>
                                                            );
                                                        }
                                                        return (
                                                            <div key={t.id} className="p-3.5 rounded-xl bg-white/[0.02] border border-white/5 space-y-1.5 hover:bg-white/[0.03] transition-colors">
                                                                <div className="flex items-center justify-between">
                                                                    <span className="text-xs font-bold text-white font-sans">Uber {idx + 1}</span>
                                                                    {t.tessie_drive_id ? (
                                                                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[8px] font-bold uppercase font-mono">Matched</span>
                                                                    ) : (
                                                                        <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[8px] font-bold uppercase font-mono">Unmatched</span>
                                                                    )}
                                                                </div>
                                                                <p className="text-[10px] text-[var(--text-muted)] font-mono truncate">Distance: {t.distance_miles.toFixed(1)} mi</p>
                                                                <div className="flex items-center justify-between pt-1 font-mono">
                                                                    <span className="text-[10px] text-[#606060]">{formatToLocalTime(t.timestamp)}</span>
                                                                    <span className="text-sm font-black text-white">${t.fare.toFixed(2)}</span>
                                                                </div>
                                                            </div>
                                                        );
                                                    });
                                                })()}
                                            </div>
                                        </div>
                                    </div>
                                ) : (
                                    /* Telemetry tab activity timeline */
                                    <div className="p-5 rounded-2xl glass space-y-4">
                                        <h3 className="text-sm font-bold uppercase tracking-wider text-white font-mono border-b border-white/5 pb-2">Activity Telemetry Timeline</h3>
                                        <div className="relative border-l border-white/5 pl-4 ml-2 space-y-6">
                                            {timelineEvents.length === 0 ? (
                                                <p className="text-xs text-[var(--text-muted)] italic py-4">// No drives or charging sessions logged for this day</p>
                                            ) : (
                                                timelineEvents.map((evt, i) => (
                                                    <div key={i} className="relative">
                                                        {/* Icon indicator */}
                                                        <div className={`absolute -left-[23px] top-0.5 w-3.5 h-3.5 rounded-full border-2 bg-[var(--bg-void)] ${evt.type === 'Charge' ? 'border-[var(--accent-cyan)] shadow-[0_0_10px_rgba(34,211,238,0.2)]' : 'border-white'}`} />
                                                        <div className="space-y-1">
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-[10px] font-mono text-[var(--text-muted)]">{evt.time}</span>
                                                                <span className={`text-xs font-bold ${evt.type === 'Charge' ? 'text-[var(--accent-cyan)]' : 'text-white'}`}>{evt.details}</span>
                                                                {evt.socChange && (
                                                                    <span className={`text-[9px] font-bold font-mono px-1.5 py-0.2 rounded ${evt.type === 'Charge' ? 'bg-[var(--accent-cyan)]/10 text-[var(--accent-cyan)]' : 'bg-rose-500/10 text-rose-400'}`}>{evt.socChange}</span>
                                                                )}
                                                            </div>
                                                            <p className="text-[10px] font-mono text-[#606060]">{evt.stats}</p>
                                                        </div>
                                                    </div>
                                                ))
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* ─────────────────────────────────────────────────────────────
                            SECTION: FINANCIALS
                        ───────────────────────────────────────────────────────────── */}
                        {section === 'financials' && (
                            <div className="space-y-6">
                                <div>
                                    <h1 className="text-2xl font-black tracking-tight">Financials</h1>
                                    <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{selectedDate} · Balance Sheet</p>
                                </div>

                                {/* Panel 2: Expenses & Capital Ledger (Collapsible) */}
                                <div className="rounded-2xl border border-white/5 bg-[var(--bg-surface)] overflow-hidden shadow-lg">
                                    <div className="p-4 flex items-center justify-between border-b border-white/5 cursor-pointer bg-white/[0.01]" onClick={() => setExpensesCollapsed(!expensesCollapsed)}>
                                        <div className="flex items-center gap-2">
                                            <Zap className="w-4 h-4 text-[var(--accent-red)]" />
                                            <h3 className="text-sm font-bold text-white">Expenses & Capital Ledger</h3>
                                        </div>
                                        {expensesCollapsed ? <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" />}
                                    </div>
                                    {!expensesCollapsed && (
                                        <div className="p-4 space-y-6">
                                            {/* Income Logging Forms */}
                                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pb-4 border-b border-white/5">
                                                <form id="log-cash-tip-form" onSubmit={handleLogCashTip} className="space-y-3 p-3 bg-white/[0.01] border border-white/5 rounded-xl">
                                                    <h4 className="text-[10px] font-bold font-mono text-[var(--text-muted)] uppercase tracking-wider">Log Cash Tip / Gratuity</h4>
                                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                                        <input type="number" placeholder="Amount ($)" step="0.01" value={cashTipAmount} onChange={e=>setCashTipAmount(e.target.value)} className="p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none" />
                                                        <input type="text" placeholder="Note (optional)" value={cashTipNote} onChange={e=>setCashTipNote(e.target.value)} className="p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none sm:col-span-2" />
                                                    </div>
                                                    <button type="submit" disabled={isLoggingTip} className="px-3.5 py-1.5 bg-amber-500 text-[#0a1628] rounded-lg text-xs font-bold flex items-center gap-2 disabled:opacity-50">
                                                        {isLoggingTip && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                                        Log Cash Tip
                                                    </button>
                                                </form>
                                                
                                                <form id="log-private-payment-form" onSubmit={handleLogPrivatePayment} className="space-y-3 p-3 bg-white/[0.01] border border-white/5 rounded-xl">
                                                    <h4 className="text-[10px] font-bold font-mono text-[var(--text-muted)] uppercase tracking-wider">Log Private Payment (Collected)</h4>
                                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                                        <input type="text" placeholder="Client Name" value={privatePaymentClient} onChange={e=>setPrivatePaymentClient(e.target.value)} className="p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none" />
                                                        <input type="number" placeholder="Amount ($)" step="0.01" value={privatePaymentAmount} onChange={e=>setPrivatePaymentAmount(e.target.value)} className="p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none" />
                                                        <input type="text" placeholder="Notes" value={privatePaymentNote} onChange={e=>setPrivatePaymentNote(e.target.value)} className="p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none" />
                                                    </div>
                                                    <button type="submit" disabled={isLoggingPrivate} className="px-3.5 py-1.5 bg-[var(--accent-purple)] text-white rounded-lg text-xs font-bold flex items-center gap-2 disabled:opacity-50">
                                                        {isLoggingPrivate && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                                        Log Private Payment
                                                    </button>
                                                </form>
                                            </div>

                                            {/* Unified Log Expense Form */}
                                            <form id="log-expense-form" onSubmit={handleLogExpense} className="space-y-3 p-4 bg-white/[0.02] border border-white/10 rounded-2xl">
                                                <h4 className="text-[11px] font-bold font-mono text-[var(--accent-cyan)] uppercase tracking-wider">Log Expense / Scan Receipt</h4>
                                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                                                    <div className="space-y-1">
                                                        <span className="text-[9px] font-mono text-[var(--text-muted)] font-bold uppercase">Amount ($)</span>
                                                        <input type="number" placeholder="0.00" step="0.01" value={expenseAmount} onChange={e=>setExpenseAmount(e.target.value)} className="w-full p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[var(--accent-cyan)]" />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <span className="text-[9px] font-mono text-[var(--text-muted)] font-bold uppercase">Category</span>
                                                        <select value={expenseCategory} onChange={e=>{
                                                            const val = e.target.value;
                                                            setExpenseCategory(val);
                                                            if (["Maintenance", "Tires", "Major Servicing"].includes(val)) {
                                                                setExpenseType("CapEx");
                                                            } else {
                                                                setExpenseType("OpEx");
                                                            }
                                                        }} className="w-full p-2 bg-[var(--bg-surface)] border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[var(--accent-cyan)] font-sans">
                                                            <option value="Food">Food / Meals</option>
                                                            <option value="Tolls">Tolls</option>
                                                            <option value="Charging">Charging</option>
                                                            <option value="Maintenance">Maintenance</option>
                                                            <option value="Tires">Tires</option>
                                                            <option value="Major Servicing">Major Servicing</option>
                                                            <option value="Other">Other / General</option>
                                                        </select>
                                                    </div>
                                                    <div className="space-y-1">
                                                        <span className="text-[9px] font-mono text-[var(--text-muted)] font-bold uppercase">Note / Details</span>
                                                        <input type="text" placeholder="Description" value={expenseNote} onChange={e=>setExpenseNote(e.target.value)} className="w-full p-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[var(--accent-cyan)]" />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <span className="text-[9px] font-mono text-[var(--text-muted)] font-bold uppercase">Expense Type</span>
                                                        <div className="flex rounded-lg bg-white/5 border border-white/10 p-0.5 w-full font-sans">
                                                            <button type="button" onClick={() => setExpenseType('OpEx')} className={`flex-1 py-1.5 rounded text-[10px] font-bold transition-all ${expenseType === 'OpEx' ? 'bg-[var(--accent-cyan)] text-[#0a1628]' : 'text-[var(--text-muted)] hover:text-white'}`}>OpEx</button>
                                                            <button type="button" onClick={() => setExpenseType('CapEx')} className={`flex-1 py-1.5 rounded text-[10px] font-bold transition-all ${expenseType === 'CapEx' ? 'bg-[var(--accent-purple)] text-white' : 'text-[var(--text-muted)] hover:text-white'}`}>CapEx</button>
                                                        </div>
                                                    </div>
                                                </div>
                                                <button type="submit" disabled={isLoggingExpense} className="px-4 py-2 bg-[var(--accent-cyan)] text-[#0a1628] rounded-xl text-xs font-black hover:bg-cyan-400 transition-all flex items-center gap-2 disabled:opacity-50">
                                                    {isLoggingExpense && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                                    Log Manual Expense
                                                </button>
                                            </form>

                                            {/* Dual Ledger Tab Switcher */}
                                            <div className="space-y-3">
                                                <div className="flex rounded-xl bg-white/5 border border-white/10 p-0.5 w-full sm:w-72 font-sans">
                                                    <button onClick={() => setExpenseLedgerTab('opex')} className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${expenseLedgerTab === 'opex' ? 'bg-[var(--accent-cyan)] text-[#0a1628]' : 'text-[var(--text-muted)] hover:text-white'}`}>
                                                        Daily Operations (OpEx)
                                                    </button>
                                                    <button onClick={() => setExpenseLedgerTab('capex')} className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${expenseLedgerTab === 'capex' ? 'bg-[var(--accent-cyan)] text-[#0a1628]' : 'text-[var(--text-muted)] hover:text-white'}`}>
                                                        Capital & Maintenance (CapEx)
                                                    </button>
                                                </div>

                                                {/* Ledger Table */}
                                                {expenseLedgerTab === 'opex' ? (
                                                    <div className="space-y-2">
                                                        {([...loggedExpenses.fastfood, ...loggedExpenses.charging].length === 0) ? (
                                                            <p className="text-center text-xs text-[var(--text-muted)] italic py-6">// no daily operational expenses logged</p>
                                                        ) : (
                                                            <div className="overflow-x-auto">
                                                                <table className="w-full text-left border-collapse text-xs">
                                                                    <thead>
                                                                        <tr className="border-b border-white/5 text-[var(--text-muted)] font-mono">
                                                                            <th className="py-2 pr-2">Category</th>
                                                                            <th className="py-2 px-2">Note / Merchant</th>
                                                                            <th className="py-2 px-2">Timestamp</th>
                                                                            <th className="py-2 pl-2 text-right">Amount</th>
                                                                        </tr>
                                                                    </thead>
                                                                    <tbody className="divide-y divide-white/5">
                                                                        {[...loggedExpenses.fastfood, ...loggedExpenses.charging]
                                                                            .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
                                                                            .map(exp => (
                                                                                <tr key={exp.id} className="hover:bg-white/[0.01]">
                                                                                    <td className="py-2.5 pr-2 font-semibold text-white">
                                                                                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border uppercase ${
                                                                                            exp.category.toLowerCase() === 'charging' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'
                                                                                        }`}>{exp.category}</span>
                                                                                    </td>
                                                                                    <td className="py-2.5 px-2 text-[var(--text-muted)] font-mono">{exp.note}</td>
                                                                                    <td className="py-2.5 px-2 text-[var(--text-muted)] font-mono">{exp.timestamp.slice(11, 16)}</td>
                                                                                    <td className="py-2.5 pl-2 text-right font-black text-white font-mono">${exp.amount.toFixed(2)}</td>
                                                                                </tr>
                                                                            ))
                                                                        }
                                                                    </tbody>
                                                                </table>
                                                            </div>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <div className="space-y-2">
                                                        {loggedExpenses.capital_maintenance.length === 0 ? (
                                                            <p className="text-center text-xs text-[var(--text-muted)] italic py-6">// no capital investments logged</p>
                                                        ) : (
                                                            <div className="overflow-x-auto">
                                                                <table className="w-full text-left border-collapse text-xs">
                                                                    <thead>
                                                                        <tr className="border-b border-white/5 text-[var(--text-muted)] font-mono">
                                                                            <th className="py-2 pr-2">Category</th>
                                                                            <th className="py-2 px-2">Note / Servicing Details</th>
                                                                            <th className="py-2 px-2">Timestamp</th>
                                                                            <th className="py-2 pl-2 text-right">Amount</th>
                                                                        </tr>
                                                                    </thead>
                                                                    <tbody className="divide-y divide-white/5">
                                                                        {[...loggedExpenses.capital_maintenance]
                                                                            .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
                                                                            .map(exp => (
                                                                                <tr key={exp.id} className="hover:bg-white/[0.01]">
                                                                                    <td className="py-2.5 pr-2 font-semibold text-white">
                                                                                        <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[9px] font-bold uppercase">{exp.category}</span>
                                                                                    </td>
                                                                                    <td className="py-2.5 px-2 text-[var(--text-muted)] font-mono">{exp.note}</td>
                                                                                    <td className="py-2.5 px-2 text-[var(--text-muted)] font-mono">{exp.timestamp.slice(0, 10)}</td>
                                                                                    <td className="py-2.5 pl-2 text-right font-black text-amber-400 font-mono">${exp.amount.toFixed(2)}</td>
                                                                                </tr>
                                                                            ))
                                                                        }
                                                                    </tbody>
                                                                </table>
                                                            </div>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Panel 3: Unpaid Invoices (Collapsible, other clients) */}
                                <div className="rounded-2xl border border-white/5 bg-[var(--bg-surface)] overflow-hidden shadow-lg">
                                    <div className="p-4 flex items-center justify-between border-b border-white/5 cursor-pointer bg-white/[0.01]" onClick={() => setUnpaidCollapsed(!unpaidCollapsed)}>
                                        <div className="flex items-center gap-2">
                                            <Receipt className="w-4 h-4 text-amber-500" />
                                            <h3 className="text-sm font-bold text-white">Unpaid Invoices</h3>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            {unpaidOtherInvoices.length > 0 && (
                                                <span className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] font-mono font-bold">{unpaidOtherInvoices.length} outstanding</span>
                                            )}
                                            {unpaidCollapsed ? <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" />}
                                        </div>
                                    </div>
                                    {!unpaidCollapsed && (
                                        <div className="p-4 divide-y divide-white/5">
                                            {unpaidOtherInvoices.length === 0 ? (
                                                <p className="text-center text-xs text-[var(--text-muted)] italic py-6">// No other unpaid invoices outstanding</p>
                                            ) : (
                                                unpaidOtherInvoices.map((inv, i) => {
                                                    const clientName = getClientDisplayName(inv);
                                                    const routeStr = `${scrubAddress(formatLocation(inv.pickup_location))} to ${scrubAddress(formatLocation(inv.dropoff_location))}`;
                                                    return (
                                                        <div key={i} className="py-3 flex items-center justify-between gap-4 font-mono text-xs hover:bg-white/[0.01] transition-colors rounded-lg px-2">
                                                            <div className="space-y-0.5 min-w-0 flex-1">
                                                                <span className="font-bold text-white font-sans">{clientName}</span>
                                                                <p className="text-[10px] text-[var(--text-muted)] truncate max-w-[320px]">{routeStr}</p>
                                                            </div>
                                                            <div className="flex items-center gap-3 shrink-0">
                                                                <span className="text-[9px] text-[#606060]">{inv.timestamp.slice(0, 10)}</span>
                                                                <span className="font-black text-amber-400 font-mono">${inv.fare.toFixed(2)}</span>
                                                                <span className="px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 text-[8px] font-bold border border-amber-500/20 uppercase font-mono">Deferred</span>
                                                            </div>
                                                        </div>
                                                    );
                                                })
                                            )}
                                        </div>
                                    )}
                                </div>

                                {/* Panel 4: Payment Tracker (Collapsible) */}
                                <div className="rounded-2xl border border-white/5 bg-[var(--bg-surface)] overflow-hidden shadow-lg">
                                    <div className="p-4 flex items-center justify-between border-b border-white/5 cursor-pointer bg-white/[0.01]" onClick={() => setPaymentTrackerCollapsed(!paymentTrackerCollapsed)}>
                                        <div className="flex items-center gap-2">
                                            <DollarSign className="w-4 h-4 text-[var(--accent-cyan)]" />
                                            <h3 className="text-sm font-bold text-white">Payment Tracker</h3>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            {paymentAnomalyCount > 0 && (
                                                <span className="px-2 py-0.5 rounded-full bg-[var(--accent-red)]/10 text-[var(--accent-red)] border border-[var(--accent-red)]/20 text-[10px] font-mono font-bold">{paymentAnomalyCount} flagged</span>
                                            )}
                                            {paymentTrackerCollapsed ? <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" />}
                                        </div>
                                    </div>
                                    {!paymentTrackerCollapsed && (
                                        <div className="p-4">
                                            <PaymentTrackerPanel selectedDate={selectedDate} onAnomalyCountChange={setPaymentAnomalyCount} />
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* ─────────────────────────────────────────────────────────────
                            SECTION: CHARGING
                        ───────────────────────────────────────────────────────────── */}
                        {section === 'charging' && (
                            <div className="space-y-6">
                                <div>
                                    <h1 className="text-2xl font-black tracking-tight">Charging</h1>
                                    <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{selectedDate} · Tessie charging sessions</p>
                                </div>

                                <div className="p-5 rounded-2xl glass space-y-4">
                                    <h3 className="text-sm font-bold uppercase tracking-wider text-white font-mono border-b border-white/5 pb-2">Charging Sessions</h3>
                                    
                                    <div className="space-y-3">
                                        {charges.length === 0 ? (
                                            <p className="text-center text-xs text-[var(--text-muted)] italic py-6">// No charging sessions logged for this day</p>
                                        ) : (
                                            charges.map((c, i) => (
                                                <div key={i} className="p-3.5 rounded-xl bg-white/[0.01] border border-white/5 flex items-center justify-between gap-4 font-mono text-xs">
                                                    <div>
                                                        <span className="font-bold text-[var(--accent-cyan)]">{formatLocation(c.location) || "Supercharger"}</span>
                                                        <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Start: {c.time_mst || "00:00"} · Duration: {c.duration_minutes != null ? `${c.duration_minutes}m` : 'N/A'}</p>
                                                    </div>
                                                    <div className="text-right">
                                                        <span className="font-bold text-white">+{c.energy_added_kwh.toFixed(1)} kWh</span>
                                                        {c.running_cost_estimate && (
                                                            <p className="text-[10px] text-emerald-400 font-bold mt-0.5">${c.running_cost_estimate.toFixed(2)}</p>
                                                        )}
                                                    </div>
                                                </div>
                                            ))
                                        )}
                                    </div>

                                    {/* Summary Row */}
                                    {charges.length > 0 && (
                                        <div className="pt-3 border-t border-white/5 flex justify-between font-mono text-xs font-bold text-white">
                                            <span>Total Energy Added</span>
                                            <div className="text-right">
                                                <span>{charges.reduce((s, c) => s + c.energy_added_kwh, 0).toFixed(1)} kWh</span>
                                                <p className="text-[10px] text-emerald-400 mt-0.5">
                                                    Total Cost: ${charges.reduce((s, c) => s + (c.running_cost_estimate || 0), 0).toFixed(2)}
                                                </p>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* ─────────────────────────────────────────────────────────────
                            SECTION: TOOLS
                        ───────────────────────────────────────────────────────────── */}
                        {section === 'tools' && (
                            <div className="space-y-6">
                                <div>
                                    <h1 className="text-2xl font-black tracking-tight">Tools</h1>
                                    <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{selectedDate} · Operations Console</p>
                                </div>

                                {/* Pre-Shift System Check */}
                                <div className={`p-5 rounded-2xl border glass space-y-4 relative overflow-hidden ${preShiftScore < 70 ? 'border-[var(--accent-red)]/40' : 'border-[var(--accent-cyan)]/20'}`}>
                                    {preShiftScore < 70 && <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--accent-red)]/5 blur-3xl rounded-full pointer-events-none" />}
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            {preShiftScore < 70
                                                ? <ShieldAlert className="w-5 h-5 text-[var(--accent-red)] shrink-0" />
                                                : <CheckCircle className="w-5 h-5 text-[var(--accent-cyan)] shrink-0" />}
                                            <div>
                                                <h3 className="text-sm font-bold text-white">Pre-Shift System Check</h3>
                                                <p className="text-[10px] text-[var(--text-muted)] font-mono">{preShift?.generated_at ? new Date(preShift.generated_at).toLocaleTimeString('en-US', { timeZone: 'America/Denver', hour: 'numeric', minute: '2-digit' }) : 'Not yet run'}</p>
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            <span className={`text-3xl font-black font-mono ${preShiftScore >= 70 ? 'text-[var(--accent-cyan)]' : 'text-[var(--accent-red)]'}`}>{preShiftScore}</span>
                                            <p className="text-[10px] text-[var(--text-muted)] font-mono">/100</p>
                                        </div>
                                    </div>
                                    {/* Tier breakdown */}
                                    {preShift?.tiers && (
                                        <div className="grid grid-cols-2 gap-2">
                                            {Object.entries(preShift.tiers).map(([key, tier]) => {
                                                const label = key.replace('tier', 'T').replace('_trips', ' · Trips').replace('_earnings', ' · Earnings').replace('_expenses', ' · Expenses').replace('_timeline', ' · Timeline');
                                                const pass = tier?.status === 'PASS';
                                                const warn = tier?.status === 'WARN';
                                                return (
                                                    <div key={key} className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-[10px] font-mono font-bold
                                                        ${pass ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-400' : warn ? 'border-amber-500/20 bg-amber-500/5 text-amber-400' : 'border-rose-500/20 bg-rose-500/5 text-rose-400'}`}>
                                                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${pass ? 'bg-emerald-400' : warn ? 'bg-amber-400' : 'bg-rose-400'}`} />
                                                        {label}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                    {/* Systems status */}
                                    {preShift?.systems && (
                                        <div className="flex flex-wrap gap-2 pt-1 border-t border-white/5">
                                            {Object.entries(preShift.systems).map(([sys, info]) => (
                                                <div key={sys} className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[10px] font-mono
                                                    ${info?.online ? 'border-emerald-500/15 bg-emerald-500/5 text-emerald-400' : 'border-rose-500/20 bg-rose-500/5 text-rose-400'}`}>
                                                    <span className={`w-1.5 h-1.5 rounded-full ${info?.online ? 'bg-emerald-400' : 'bg-rose-400 animate-pulse'}`} />
                                                    {sys.toUpperCase()} {info?.latency_ms != null ? `${info.latency_ms}ms` : ''}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {/* Card: Rebuild Day */}
                                    <ToolCard title="Rebuild Day" desc="Reprocess and re-match drives and private bookings for this operational window." action={runRebuild} loading={status === 'running'} />
                                    
                                    {/* Card: Scrub Day */}
                                    <ToolCard title="Scrub Day" desc="Wipe receipts extractions (TRIP- records) and un-pair drives for this date. Confirmation gate required." action={() => setScrubConfirmOpen(true)} destructive />
                                    
                                    {/* Card: Create Folders */}
                                    <ToolCard title="Create Folders" desc="Ensures OneDrive/Sharepoint folders exist for daily receipt uploads." action={runCreateFolders} />

                                    {/* Card: Save Day to Cloud */}
                                    <ToolCard title="Save Day to Cloud" desc="Saves all manually logged local trips and cash tips to Azure SQL database." action={runSaveDay} />
                                </div>

                                {/* Bank Connection (Teller sign-in) */}
                                <div className="p-5 rounded-2xl glass border border-white/8 space-y-4">
                                    <div className="flex items-center gap-3">
                                        <Link2 className="w-5 h-5 text-[var(--accent-cyan)] shrink-0" />
                                        <div>
                                            <h4 className="text-sm font-bold text-white">Bank Connection</h4>
                                            <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Link Chase accounts via Teller — powers the Payment Tracker's automatic sync.</p>
                                        </div>
                                    </div>
                                    {import.meta.env.VITE_TELLER_APPLICATION_ID ? (
                                        <TellerConnectButton applicationId={import.meta.env.VITE_TELLER_APPLICATION_ID} environment="production" />
                                    ) : (
                                        <p className="text-[10px] text-amber-400 font-mono">Set VITE_TELLER_APPLICATION_ID in the environment to enable bank linking.</p>
                                    )}
                                </div>

                                {/* Uber Activity Heatmap */}
                                <a href="/uber-heatmap.html" target="_blank" rel="noopener noreferrer"
                                    className="p-5 rounded-2xl glass border border-white/8 hover:border-[var(--accent-cyan)]/30 hover:bg-white/[0.02] flex items-center justify-between transition-all duration-200 group">
                                    <div className="flex items-center gap-3">
                                        <MapPin className="w-5 h-5 text-[var(--accent-cyan)]" />
                                        <div>
                                            <h4 className="text-sm font-bold text-white">Uber Activity Heatmap</h4>
                                            <p className="text-[10px] text-[var(--text-muted)] mt-0.5">Launches external map layer of pickup & dropoff density hotspots</p>
                                        </div>
                                    </div>
                                    <span className="flex items-center gap-1.5 text-xs font-semibold text-[#606060] group-hover:text-[var(--accent-cyan)] transition-all">
                                        Open Map <ExternalLink className="w-3.5 h-3.5" />
                                    </span>
                                </a>

                                {/* Intelligence Console */}
                                <div className="bg-black/40 rounded-2xl border border-[var(--border-subtle)] overflow-hidden shadow-xl">
                                    <div className="px-4 py-2 border-b border-white/5 bg-white/[0.02] flex items-center justify-between">
                                        <span className="text-[9px] font-mono text-[#606060] font-bold uppercase tracking-wider">Intelligence Console</span>
                                        <div className="flex gap-1">
                                            <div className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                                            <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                                            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                                        </div>
                                    </div>
                                    <div className="p-4 h-48 overflow-y-auto font-mono text-[10px] space-y-1.5 bg-black/60">
                                        {logs.length === 0 ? (
                                            <p className="text-[#606060] italic">// System idle. Launch rebuild or scrub operation for logs output...</p>
                                        ) : (
                                            logs.map((log, i) => (
                                                <p key={i} className={
                                                    log.includes('[ERROR]') || log.includes('[CRITICAL]') ? 'text-[var(--accent-red)] font-semibold' :
                                                    log.includes('[SUCCESS]') || log.includes('MATCH:') ? 'text-[var(--accent-green)] font-semibold' :
                                                    log.startsWith('>') ? 'text-[var(--accent-cyan)] font-bold border-t border-white/5 pt-1.5 mt-1.5' : 'text-[var(--text-muted)]'
                                                }>{log}</p>
                                            ))
                                        )}
                                        {status === 'running' && <span className="text-[var(--accent-cyan)] animate-pulse">_</span>}
                                    </div>
                                </div>
                            </div>
                        )}

                    </div>
                </main>
            </div>

            {/* ─── Mobile Bottom Tab Bar (< 768px view) ────────────────────────────── */}
            <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 h-16 flex items-center justify-around border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] backdrop-blur-md">
                {navItems.map(n => (
                    <button key={n.id} onClick={() => setSection(n.id as Section)} 
                        className={`flex flex-col items-center gap-1 px-3 py-1 min-w-[48px] transition-all relative ${section === n.id ? 'text-[var(--accent-cyan)]' : 'text-[var(--text-muted)]'}`}>
                        <span className="w-4 h-4">{n.icon}</span>
                        <span className="text-[9px] font-bold">{n.label}</span>
                        {section === n.id && <span className="w-1 h-1 rounded-full bg-[var(--accent-cyan)]" />}
                    </button>
                ))}
            </nav>

            {/* ─── Mobile Quick Log FAB & Action Sheet ─────────────────────────────── */}
            <div className="md:hidden fixed bottom-20 right-4 z-40">
                <button onClick={() => setIsMobileQuickLogOpen(true)}
                    className="w-11 h-11 rounded-full bg-[var(--accent-cyan)] text-[#0a1628] flex items-center justify-center shadow-lg active:scale-95 transition-all">
                    <Plus className="w-6 h-6" />
                </button>
            </div>

            {isMobileQuickLogOpen && (
                <div className="md:hidden fixed inset-0 z-50 flex items-end justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setIsMobileQuickLogOpen(false)}>
                    <div className="w-full max-w-sm rounded-t-2xl p-5 space-y-4 bg-[var(--bg-surface)] border-t border-white/10" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between border-b border-white/5 pb-2">
                            <span className="text-xs font-bold text-white uppercase tracking-wider">Quick Log Actions</span>
                            <button onClick={() => setIsMobileQuickLogOpen(false)} className="text-[var(--text-muted)] font-mono text-xs">Close</button>
                        </div>
                        <div className="grid grid-cols-1 gap-2.5">
                            <button onClick={() => { setSection('financials'); setIsMobileQuickLogOpen(false); setTimeout(() => document.getElementById("log-cash-tip-form")?.scrollIntoView({ behavior: 'smooth' }), 100); }} 
                                className="w-full py-3 rounded-xl border border-amber-500/20 bg-amber-500/10 text-amber-400 text-xs font-bold">+ Log Cash Tip</button>
                            <button onClick={() => { setSection('financials'); setIsMobileQuickLogOpen(false); setTimeout(() => document.getElementById("log-private-payment-form")?.scrollIntoView({ behavior: 'smooth' }), 100); }} 
                                className="w-full py-3 rounded-xl border border-[var(--accent-purple)]/20 bg-[var(--accent-purple)]/10 text-[var(--accent-purple)] text-xs font-bold">+ Log Private Payment</button>
                            <button onClick={() => { setSection('financials'); setIsMobileQuickLogOpen(false); setTimeout(() => document.getElementById("log-expense-form")?.scrollIntoView({ behavior: 'smooth' }), 100); }} 
                                className="w-full py-3 rounded-xl border border-[var(--accent-cyan)]/20 bg-[var(--accent-cyan)]/10 text-[var(--accent-cyan)] text-xs font-bold">+ Log Expense</button>
                            <button onClick={() => { setSection('financials'); setIsMobileQuickLogOpen(false); setTimeout(() => { document.getElementById("log-expense-form")?.scrollIntoView({ behavior: 'smooth' }); setExpenseCategory('Charging'); }, 100); }} 
                                className="w-full py-3 rounded-xl border border-rose-500/20 bg-rose-500/10 text-rose-400 text-xs font-bold">Scan Receipt</button>
                        </div>
                    </div>
                </div>
            )}

            {/* ─── Modals: Scrub Confirmation ──────────────────────────────────────── */}
            {scrubConfirmOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md">
                    <div className="w-full max-w-sm rounded-2xl border border-[var(--accent-red)]/20 p-6 space-y-4 bg-[var(--bg-surface)] shadow-2xl">
                        <div className="flex items-center gap-3">
                            <div className="p-2.5 rounded-xl bg-[var(--accent-red)]/10 border border-[var(--accent-red)]/20"><ShieldAlert className="w-5 h-5 text-[var(--accent-red)]" /></div>
                            <div>
                                <h2 className="text-base font-bold text-white">Scrub Day Operations</h2>
                                <p className="text-xs text-[var(--accent-red)] mt-0.5">Destructive Action</p>
                            </div>
                        </div>
                        <p className="text-xs text-[var(--text-muted)] font-mono leading-relaxed">
                            Are you absolutely sure you want to scrub <span className="font-bold text-white">{selectedDate}</span>? 
                            This deletes all receipt extractions (TRIP- records) and unlinks drives so the day can be reprocessed.
                        </p>
                        <div className="flex gap-2.5 pt-2">
                            <button onClick={() => setScrubConfirmOpen(false)} 
                                className="flex-1 py-2.5 rounded-xl text-xs font-bold border border-white/10 bg-white/5 text-[var(--text-muted)] hover:bg-white/10 transition-all">Cancel</button>
                            <button onClick={runScrub} 
                                className="flex-1 py-2.5 rounded-xl text-xs font-bold bg-[var(--accent-red)] text-white hover:bg-red-600 transition-all">Proceed Scrub</button>
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
};

// ─── Subcomponents ─────────────────────────────────────────────────────────────

// StatCard Subcomponent
const StatCard = ({ label, value, sub, icon, color, highlight = false }: {
    label: string; value: string | number; sub: string; icon: React.ReactNode; color: 'cyan' | 'amber' | 'red'; highlight?: boolean;
}) => {
    const cardBorder = highlight 
        ? 'border-[var(--accent-cyan)]/20 shadow-[0_0_20px_rgba(34,211,238,0.15)] bg-[var(--accent-cyan)]/5' 
        : 'border-white/8 glass bg-white/[0.02]';
    const iconColor = color === 'cyan' ? 'text-[var(--accent-cyan)] bg-[var(--accent-cyan)]/10' 
                    : color === 'amber' ? 'text-amber-400 bg-amber-500/10' 
                    : 'text-[var(--accent-red)] bg-[var(--accent-red)]/10';

    return (
        <div className={`relative rounded-2xl p-5 flex items-start gap-4 transition-all duration-300 hover:scale-[1.01] border ${cardBorder}`}>
            {highlight && <div className="absolute top-0 right-0 w-32 h-32 bg-[var(--accent-cyan)]/5 blur-[50px] rounded-full pointer-events-none" />}
            <div className={`p-2.5 rounded-xl shrink-0 ${iconColor}`}>{icon}</div>
            <div className="min-w-0">
                <p className="text-xs font-semibold tracking-wide text-[var(--text-muted)] mb-0.5 truncate">{label}</p>
                <p className={`text-2xl font-black tracking-tight ${highlight && color === 'cyan' ? 'text-[var(--accent-cyan)]' : 'text-white'}`}>{value}</p>
                <p className="text-[10px] font-mono text-[#606060] mt-0.5 truncate">{sub}</p>
            </div>
        </div>
    );
};

// GoalProgressRow Subcomponent
const GoalProgressRow = ({ label, actual, target }: { label: string; actual: number; target: number }) => {
    const percent = target > 0 ? Math.min(100, Math.floor((actual / target) * 100)) : 0;
    
    return (
        <div className="space-y-1 font-mono text-xs">
            <div className="flex items-center justify-between text-[var(--text-muted)]">
                <span className="font-bold text-white">{label}</span>
                <span>{percent}% (${actual.toFixed(0)} / ${target.toFixed(0)})</span>
            </div>
            <div className="w-full h-2.5 bg-white/5 rounded-full overflow-hidden border border-white/5 p-0.5">
                <div className={`h-full rounded-full transition-all duration-500 ${percent >= 100 ? 'bg-[var(--accent-cyan)] shadow-[0_0_8px_rgba(34,211,238,0.5)]' : 'bg-amber-400'}`} style={{ width: `${percent}%` }} />
            </div>
        </div>
    );
};

// ToolCard Subcomponent
const ToolCard = ({ title, desc, action, loading = false, destructive = false }: {
    title: string; desc: string; action: () => void; loading?: boolean; destructive?: boolean;
}) => {
    const btnCls = destructive 
        ? 'border-[var(--accent-red)]/20 bg-[var(--accent-red)]/10 text-[var(--accent-red)] hover:bg-[var(--accent-red)]/20' 
        : 'border-[var(--accent-cyan)]/20 bg-[var(--accent-cyan)]/10 text-[var(--accent-cyan)] hover:bg-[var(--accent-cyan)]/20';

    return (
        <div className="p-5 rounded-2xl glass flex flex-col justify-between gap-4 border border-white/8">
            <div className="space-y-1">
                <h4 className="text-sm font-bold text-white">{title}</h4>
                <p className="text-[10px] text-[var(--text-muted)] leading-relaxed">{desc}</p>
            </div>
            <button onClick={action} disabled={loading} 
                className={`w-full py-2.5 rounded-xl border text-xs font-bold transition-all flex items-center justify-center gap-2 ${btnCls}`}>
                {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {title}
            </button>
        </div>
    );
};

export default DriverDashboard;
