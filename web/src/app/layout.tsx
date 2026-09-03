import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { AuthProvider } from "@/lib/auth";
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
  // The product page is white to the top edge, so the browser chrome matches
  // the canvas rather than the homepage's black nav.
  themeColor: "#ffffff",
  width: "device-width",
  initialScale: 1,
};

/**
 * The root carries only what every page shares: the font and the session.
 * Chrome differs by area — the marketing pages have the top bar and footer,
 * the app has the dock — so each route group brings its own layout.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
