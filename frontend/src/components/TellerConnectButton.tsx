'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { ShieldCheck, ExternalLink, Check, Loader2, RefreshCw } from 'lucide-react';

const AZURE_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://summitos-api.azurewebsites.net/api';

interface TellerConnectButtonProps {
    applicationId: string;
    environment?: 'production' | 'development' | 'sandbox';
    onTokenReceived?: (token: string) => void;
}

declare global {
    interface Window {
        TellerConnect: any;
    }
}

const TellerConnectButton: React.FC<TellerConnectButtonProps> = ({ applicationId, environment = 'production', onTokenReceived }) => {
    const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
    const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'success' | 'error'>('idle');
    const [token, setToken] = useState<string | null>(null);

    useEffect(() => {
        // Load Teller SDK dynamically
        if (window.TellerConnect) {
            setStatus('ready');
            return;
        }

        const script = document.createElement('script');
        script.src = 'https://cdn.teller.io/connect/connect.js';
        script.async = true;
        script.onload = () => setStatus('ready');
        script.onerror = () => setStatus('error');
        document.head.appendChild(script);
    }, []);

    const updateKeyVault = async (accessToken: string) => {
        setSyncStatus('syncing');
        try {
            const response = await fetch(`${AZURE_BASE}/copilot/banking/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: accessToken })
            });

            if (response.ok) {
                setSyncStatus('success');
            } else {
                setSyncStatus('error');
            }
        } catch (err) {
            console.error('Failed to sync token to backend:', err);
            setSyncStatus('error');
        }
    };

    const handleConnect = useCallback(() => {
        if (!window.TellerConnect) return;

        const teller = window.TellerConnect.setup({
            applicationId: applicationId,
            onSuccess: (enrollment: any) => {
                const accessToken = enrollment.accessToken;
                if (accessToken) {
                    setToken(accessToken);
                    updateKeyVault(accessToken); // AUTOMATION: Save to Key Vault immediately
                    if (onTokenReceived) onTokenReceived(accessToken);
                }
            },
            onExit: () => {
                console.log('Teller Connect closed');
            }
        });

        teller.open();
    }, [applicationId, onTokenReceived]);

    if (status === 'error') {
        return (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-mono">
                Failed to load Teller SDK. Please check your connection.
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {!token ? (
                <button
                    onClick={handleConnect}
                    disabled={status === 'loading'}
                    className={`group w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl font-bold text-sm transition-all duration-300
                        ${status === 'loading'
                            ? 'bg-white/5 text-gray-500 border border-white/10 cursor-not-allowed'
                            : 'bg-gradient-to-r from-cyan-600 to-cyan-500 text-white hover:from-cyan-500 hover:to-cyan-400 shadow-[0_0_20px_rgba(0,242,255,0.2)] border border-cyan-400/30'
                        }`}
                >
                    {status === 'loading' ? (
                        <Loader2 className="w-5 h-5 animate-spin" />
                    ) : (
                        <ShieldCheck className="w-5 h-5 group-hover:scale-110 transition-transform" />
                    )}
                    {status === 'loading' ? 'Initializing Teller...' : 'Link Chase Account'}
                    <ExternalLink className="w-3 h-3 ml-1 opacity-50" />
                </button>
            ) : (
                <div className={`p-5 rounded-2xl border backdrop-blur-xl transition-all duration-500 ${
                    syncStatus === 'success' ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-white/5 border-white/10'
                }`}>
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2">
                            {syncStatus === 'syncing' ? (
                                <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />
                            ) : syncStatus === 'success' ? (
                                <Check className="w-4 h-4 text-emerald-400" />
                            ) : (
                                <Check className="w-4 h-4 text-cyan-400" />
                            )}
                            <p className={`text-xs font-bold uppercase tracking-wider ${
                                syncStatus === 'success' ? 'text-emerald-400' : 'text-cyan-400'
                            }`}>
                                {syncStatus === 'syncing' ? 'Vault Syncing...' : 
                                 syncStatus === 'success' ? 'Vault Synchronized' : 'Enrolled'}
                            </p>
                        </div>
                    </div>
                    
                    <p className="text-[11px] text-gray-400 font-mono leading-relaxed">
                        {syncStatus === 'success' 
                            ? "Your production token has been securely stored in Azure Key Vault. The sync service is now active."
                            : "Account linked! We are securely synchronizing your credentials to Azure."}
                    </p>
                    
                    {syncStatus === 'error' && (
                        <p className="mt-3 text-[10px] text-rose-400 font-mono font-bold uppercase tracking-tighter">
                            ⚠️ Auto-sync failed. Please run the CLI command manually.
                        </p>
                    )}
                </div>
            )}
        </div>
    );
};

export default TellerConnectButton;
