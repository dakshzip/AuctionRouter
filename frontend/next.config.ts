import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export — `npm run build` emits ./out, served by FastAPI
  // (and the Hugging Face Space image).
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
