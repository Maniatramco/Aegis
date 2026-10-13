import type { Metadata } from "next";
import "./globals.css";
import "./responsive.css";
import "./readability.css";
export const metadata: Metadata = {
  title: "Aegis · AI Data Platform",
  description: "AI data workspace for datasets, agents, chat, extraction, and review.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
