import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "delta-t | Your day, simulated",
  description: "Plan your day and explore what could happen with delta-t.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
