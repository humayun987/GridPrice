import type { Metadata } from "next";
import "./globals.css";
import Providers from "@/components/shared/providers";
import { Toaster } from "sonner";

export const metadata: Metadata = {
  title: "tatva.gridprice",
  description: "Electricity market price forecasting platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <Providers>{children}</Providers>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
