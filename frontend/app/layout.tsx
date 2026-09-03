import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/navbar";
import { TickerStrip } from "@/components/tickerstrip";
import { LanguageProvider } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "W3EX · Web3 Market Terminal",
  description: "AI-native crypto market terminal — real-time quotes, multi-route execution, paper mode",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        <LanguageProvider>
          <Navbar />
          <TickerStrip />
          <main className="mx-auto max-w-[1600px] px-4 pb-10 pt-28 md:px-6">{children}</main>
        </LanguageProvider>
      </body>
    </html>
  );
}
