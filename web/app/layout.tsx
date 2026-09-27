import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Da Vinci: recursive improvement CAD harness",
  description:
    "Interactive VTOL aircraft iterations with estimated range, speed, payload and independent physics evaluation.",
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
