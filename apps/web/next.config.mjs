const apiInternalBaseUrl = process.env.API_INTERNAL_BASE_URL ?? "http://localhost:8000";

const nextConfig = {
  ...(process.env.NEXT_STANDALONE === "true" ? { output: "standalone" } : {}),
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${apiInternalBaseUrl}/:path*`
      }
    ];
  }
};

export default nextConfig;
