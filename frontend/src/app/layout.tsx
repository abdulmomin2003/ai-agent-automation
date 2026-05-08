import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "AI Agent Platform — Multi-Agent Automation",
  description: "Create and manage AI agents with voice calling, WhatsApp, email, and intelligent knowledge bases.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased bg-background text-foreground min-h-screen`}>
        {children}
      </body>
    </html>
  );
}
