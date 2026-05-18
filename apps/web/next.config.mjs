const nextConfig = {
  ...(process.env.NEXT_STANDALONE === "true" ? { output: "standalone" } : {})
};

export default nextConfig;
