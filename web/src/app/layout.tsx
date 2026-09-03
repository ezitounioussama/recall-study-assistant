import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { GlobalNav, Footer } from "@/components/ui/nav";
import "./globals.css";

/**
 * The spec's sanctioned SF Pro substitute. Only the four weights the type
 * ladder uses are requested — 300 / 400 / 600 / 700, with 500 deliberately
 * absent — so nothing is downloaded that the design system forbids.
 */
const inter = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "600", "700"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Recall — study from your own notes",
  description:
    "Upload your material, ask it questions and get answers cited back to the source, then review what matters on a spaced-repetition schedule.",
  authors: [{ name: "Oussama Ezitouni" }],
};

export const viewport: Viewport = {
  // The global nav is true black and sits at the very top, so the mobile
  // browser chrome should match it rather than flashing white on scroll.
  themeColor: "#000000",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <GlobalNav />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
