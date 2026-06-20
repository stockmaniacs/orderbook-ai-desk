import Link from "next/link";

const modules = [
  { href: "/order-tracking", label: "Order Tracking", desc: "NSE/BSE order book analysis" },
  { href: "/research", label: "Research", desc: "Fundamental research & concalls" },
  { href: "/subcontract", label: "Subcontract", desc: "Supply chain opportunity graph" },
  { href: "/tracker", label: "Master Tracker", desc: "Signal dashboard & alerts" },
  { href: "/technical", label: "Technical Analysis", desc: "Minervini, Stage, RS Rating" },
];

export default function Home() {
  return (
    <main className="max-w-4xl mx-auto px-6 py-16">
      <h1 className="text-3xl font-bold mb-2">Orderbook AI Desk</h1>
      <p className="text-gray-400 mb-12">AI-powered investment research · NSE / BSE</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {modules.map((m) => (
          <Link
            key={m.href}
            href={m.href}
            className="block p-6 bg-gray-900 border border-gray-800 rounded-xl hover:border-blue-500 transition-colors"
          >
            <div className="font-semibold text-lg mb-1">{m.label}</div>
            <div className="text-sm text-gray-400">{m.desc}</div>
          </Link>
        ))}
      </div>
    </main>
  );
}
