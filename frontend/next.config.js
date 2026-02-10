const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'export',
    outputFileTracingRoot: path.join(__dirname),
};

module.exports = nextConfig;
