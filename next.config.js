/** @type {import('next').NextConfig} */
const nextConfig = {
    output: "standalone",
    serverExternalPackages: ["@googlemaps/google-maps-services-js"],
};

module.exports = nextConfig;
