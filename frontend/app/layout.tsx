import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "delta-t",
  description: "Schedule risk simulation and repair",
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
