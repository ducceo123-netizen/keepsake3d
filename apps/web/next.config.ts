import type { NextConfig } from "next";
const staticExport = process.env.KEEPSAKE_STATIC_EXPORT === "1";
const nextConfig: NextConfig = {
  devIndicators: false,
  ...(staticExport ? { output: "export" as const, trailingSlash: true } : {}),
  ...(!staticExport
    ? {
        async rewrites() {
          return [
            {
              source: "/api/v1/:path*",
              destination: `${process.env.API_ORIGIN || "http://127.0.0.1:8000"}/api/v1/:path*`,
            },
          ];
        },
        async headers() {
          return [
            {
              source: "/:path*",
              headers: [
                { key: "X-Content-Type-Options", value: "nosniff" },
                { key: "Referrer-Policy", value: "no-referrer" },
                {
                  key: "Permissions-Policy",
                  value: "camera=(), microphone=(), geolocation=()",
                },
              ],
            },
          ];
        },
      }
    : {}),
};
export default nextConfig;
