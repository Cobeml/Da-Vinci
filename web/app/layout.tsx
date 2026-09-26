import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Da Vinci: recursive improvement CAD harness",
  description:
    "Interactive robotic gripper iterations with measured mass, frame analysis and jaw travel controls.",
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
