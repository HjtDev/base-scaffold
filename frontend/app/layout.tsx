import type { Metadata } from "next";
import Script from "next/script";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "myproject",
  description: "base-scaffold frontend",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* Optional self-hosted Umami analytics — see README.md "Analytics (optional)".
            Renders nothing unless NEXT_PUBLIC_UMAMI_WEBSITE_ID was set at BUILD time
            (frontend/Dockerfile.prod); read inline, not hoisted, matching the lazy-env
            rule in frontend/lib/api-client.ts. */}
        {process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID && (
          <Script
            src={process.env.NEXT_PUBLIC_UMAMI_SCRIPT_URL}
            data-website-id={process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID}
            strategy="afterInteractive"
          />
        )}
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
