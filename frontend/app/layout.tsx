import type { Metadata } from "next";
import { Silkscreen, VT323 } from "next/font/google";
import "./globals.css";

// Silkscreen stays legible at the tiny sizes this UI uses pixel text at;
// Press Start 2P (the previous font) turns to mush below ~12px
const pixelFont = Silkscreen({
  variable: "--font-pixel",
  weight: ["400", "700"],
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
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
