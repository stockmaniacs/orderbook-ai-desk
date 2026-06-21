import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Orderbook AI Desk",
  description: "AI-powered investment research for NSE/BSE universe",
};

const NAV_LINKS = [
  { href: "/order-tracking", label: "Orders" },
  { href: "/research",       label: "Research" },
  { href: "/subcontract",    label: "Subcontract" },
  { href: "/tracker",        label: "Master Tracker" },
  { href: "/technical",      label: "Technical" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        <nav className="bg-gray-900 border-b border-gray-800 sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 flex items-center h-14 gap-6">
            <Link href="/" className="text-indigo-400 font-bold text-sm tracking-wide whitespace-nowrap">
              Orderbook AI
            </Link>
            <div className="flex items-center gap-1">
              {NAV_LINKS.map(({ href, label }) => (
                <Link
                  key={href}
                  href={href}
                  className="px-3 py-1.5 rounded-md text-sm text-gray-300 hover:text-white hover:bg-gray-800 transition-colors"
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
