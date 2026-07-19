import type { Metadata } from "next";
import { Pixelify_Sans, VT323 } from "next/font/google";
import "./globals.css";

// Pixelify Sans: pixel DNA but rounded and modern — legible at small
// sizes where Press Start 2P / Silkscreen read as noise
const pixelFont = Pixelify_Sans({
  variable: "--font-pixel",
  weight: ["400", "500", "600", "700"],
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
