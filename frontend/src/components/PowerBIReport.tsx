"use client";

import React from "react";
import dynamic from "next/dynamic";
import { models } from "powerbi-client";

const PowerBIEmbed = dynamic(
    () => import("powerbi-client-react").then((m) => m.PowerBIEmbed),
    { ssr: false }
);

interface PowerBIReportProps {
    reportId: string;
    groupId?: string; // Optional workspace ID
    accessToken: string;
}

export const PowerBIReport: React.FC<PowerBIReportProps> = ({ reportId, groupId, accessToken }) => {
    // Prevent SSR
    if (typeof window === 'undefined') {
        return <div className="h-[800px] w-full flex items-center justify-center text-gray-500">Loading...</div>;
    }

    return (
        <div className="h-[800px] w-full">
            <PowerBIEmbed
                embedConfig={{
                    type: "report",
                    id: reportId,
                    embedUrl: `https://app.powerbi.com/reportEmbed?reportId=${reportId}${groupId ? `&groupId=${groupId}` : ""}`,
                    accessToken,
                    tokenType: models.TokenType.Aad, // Use Aad for User Owns Data
                    settings: {
                        panes: {
                            filters: {
                                expanded: false,
                                visible: true,
                            },
                        },
                        background: models.BackgroundType.Transparent,
                    },
                }}
                eventHandlers={
                    new Map([
                        ["loaded", function () { console.log("Report loaded"); }],
                        ["rendered", function () { console.log("Report rendered"); }],
                        ["error", function (event) { console.error(event?.detail); }],
                    ])
                }
                cssClassName={"h-full w-full"}
                getEmbeddedComponent={(embeddedReport) => {
                    // You can access the report object here for further interactions
                    // (window as any).report = embeddedReport;
                }}
            />
        </div>
    );
};
