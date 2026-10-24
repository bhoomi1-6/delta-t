import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Flowboard | Your workspace",
  description: "A focused dashboard for tasks, information and AI suggestions.",
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
