const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'standalone',
    outputFileTracingRoot: path.join(__dirname),
    async rewrites() {
        return [
            {
                source: '/api/dashboard-summary',
                destination: 'https://summitos-api.azurewebsites.net/api/dashboard-summary',
            },
        ];
    },
};

module.exports = nextConfig;
