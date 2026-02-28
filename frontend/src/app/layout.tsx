import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import SWRegistrar from "@/components/SWRegistrar";

const inter = Inter({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800", "900"],
});

export const metadata: Metadata = {
  title: "SilentVoice — Real-Time Sign Language Translator",
  description:
    "Two-way real-time sign language translation powered by AI. Supports ASL, ISL, and TSL with sub-200ms latency. Breaking communication barriers.",
  keywords: [
    "sign language", "ASL", "ISL", "TSL", "deaf", "accessibility",
    "AI", "translator", "real-time", "Indian Sign Language", "Tamil Sign Language",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} antialiased`}>
        <SWRegistrar />
        {children}
      </body>
    </html>
  );
}
