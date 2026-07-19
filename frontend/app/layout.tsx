import type { Metadata } from "next";
import { Chakra_Petch, VT323 } from "next/font/google";
import "./globals.css";

// Chakra Petch: squared-off techno letterforms — retro-futurist attitude
// without literal pixels, crisp at every size
const pixelFont = Chakra_Petch({
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
