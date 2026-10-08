import type { Metadata } from "next";
import "./globals.css";
import "./responsive.css";
import "./readability.css";
export const metadata: Metadata = {
  title: "Aegis · Document intelligence",
  description: "Secure, evidence-led document intelligence workspace",
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
