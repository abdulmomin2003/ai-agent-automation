import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "AI Sales Agent",
  description: "Upload documents and chat with your AI Sales Agent.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // We'll enforce dark mode for this premium look
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased bg-background text-foreground h-screen flex flex-col overflow-hidden`}>
        {children}
      </body>
    </html>
  );
}
