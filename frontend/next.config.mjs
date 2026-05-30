/** @type {import('next').NextConfig} */
const nextConfig = {
  swcMinify: false,
  webpack: (config) => {
    config.cache = false;
    return config;
  },
};

export default nextConfig;