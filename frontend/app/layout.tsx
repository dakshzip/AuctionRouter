import type { Metadata } from "next";
import { Press_Start_2P, VT323 } from "next/font/google";
import "./globals.css";

const pixelFont = Press_Start_2P({
  variable: "--font-pixel",
  weight: "400",
  subsets: ["latin"],
});

const termFont = VT323({
  variable: "--font-term",
  weight: "400",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AuctionRouter",
  description:
    "Cost-aware multi-agent LLM orchestrator with auction-based routing and verification-based escalation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${pixelFont.variable} ${termFont.variable} h-full`}
    >
      <body className="crt min-h-full flex flex-col">{children}</body>
    </html>
  );
}
