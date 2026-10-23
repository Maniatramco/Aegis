import type { Metadata } from "next";
import "./globals.css";
import "./responsive.css";
import "./readability.css";
import "./screen-heading.css";
import "./workspace-region.css";
import "./typography.css";
import "./workspace-tools.css";
import "./action-button.css";
import "./review-layout.css";
export const metadata: Metadata = {
  title: "Aegis · AI Data Platform",
  description: "AI data workspace for datasets, agents, chat, extraction, and review.",
  icons: { icon: "/aegis-platform-logo.png", apple: "/aegis-platform-logo.png" },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head><link rel="preload" href="/ags_assets/ags_fonts/inter-variable.woff2" as="font" type="font/woff2" crossOrigin="anonymous" /></head>
      <body>{children}</body>
    </html>
  );
}
