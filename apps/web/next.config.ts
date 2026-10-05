import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Hide the Next.js dev-mode indicator (the floating "N" badge). It only ever
  // shows under `next dev`; production (`next start`) never renders it.
  devIndicators: false,
  // Keep production builds reliable on small Docker Desktop/WSL2 VMs. The
  // application is compact, so extra build workers add memory pressure without
  // materially improving throughput.
  experimental: {
    cpus: 1,
  },
  transpilePackages: ["@dw/ui", "@dw/contracts", "@dw/api-client"],
  // `app/pdfjs/[kind]/[file]` reads these at run time; a path read from fs
  // is not traced, so the standalone build is told to keep them.
  outputFileTracingIncludes: {
    "/pdfjs/[kind]/[file]": [
      "./node_modules/pdfjs-dist/cmaps/**",
      "./node_modules/pdfjs-dist/standard_fonts/**",
    ],
  },
};

export default nextConfig;
