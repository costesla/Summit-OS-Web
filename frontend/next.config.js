const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'export',
    trailingSlash: true,
    outputFileTracingRoot: path.join(__dirname),
};

module.exports = nextConfig;
