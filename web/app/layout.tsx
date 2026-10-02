import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Da Vinci: recursive improvement CAD harness",
  description:
    "A local CAD harness for external and built-in agents: verified tests, iterative design, independent simulation and preserved evidence.",
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
