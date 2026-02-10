"use client";

import { useEffect, useState, ReactNode } from "react";
import { PublicClientApplication, EventType, EventMessage, AuthenticationResult } from "@azure/msal-browser";
import { MsalProvider } from "@azure/msal-react";
import { msalConfig } from "@/lib/authConfig";

export function AuthProvider({ children }: { children: ReactNode }) {
    const [instance, setInstance] = useState<PublicClientApplication | null>(null);

    useEffect(() => {
        const initializeMsal = async () => {
            // Initialize MSAL instance only on client side
            const msalInstance = new PublicClientApplication(msalConfig);
            await msalInstance.initialize();

            // Optional: Set up active account on page load
            const accounts = msalInstance.getAllAccounts();
            if (accounts.length > 0) {
                msalInstance.setActiveAccount(accounts[0]);
            }

            msalInstance.addEventCallback((event: EventMessage) => {
                if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
                    const payload = event.payload as AuthenticationResult;
                    const account = payload.account;
                    msalInstance.setActiveAccount(account);
                }
            });

            setInstance(msalInstance);
        };

        initializeMsal();
    }, []);

    if (!instance) {
        return <div>Loading Authentication...</div>;
    }

    return <MsalProvider instance={instance}>{children}</MsalProvider>;
}
