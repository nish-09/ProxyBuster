import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import { AuthProvider } from "@/lib/auth-context";
import "./globals.css";

// A clean, rounded, friendly grotesque throughout — the Claymorphism treatment comes
// from soft extruded surfaces/shadows, not from a decorative or oversized typeface.
const clayFont = Plus_Jakarta_Sans({
  variable: "--font-clay",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "Proxy Busters",
  description: "Proxy-resistant college attendance platform",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${clayFont.variable} h-full`}>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- icon font not supported by next/font; App Router head is the correct place for it */}
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-full bg-background text-on-background font-body-lg antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
