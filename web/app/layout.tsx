import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Da Vinci · Autonomous engineering",
  description:
    "A self-improving CAD workbench with traceable geometry, tools, and agent policies.",
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
