import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Da Vinci — CAD workspace",
  description: "Local recursive improvement CAD harness",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
