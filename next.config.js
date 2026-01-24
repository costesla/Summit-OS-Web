/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'export',  // Enable static HTML export for Azure Static Web Apps
    images: {
        unoptimized: true  // Required for static export
    },
    trailingSlash: true,  // Better compatibility with static hosting
    serverExternalPackages: ["@googlemaps/google-maps-services-js"],
};

module.exports = nextConfig;
