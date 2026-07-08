"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import { ExportModal } from "@/components/shared/ExportModal";
import { useSession } from "next-auth/react";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MOCK_REGIONS } from "@/lib/mockData";
import { WifiOff } from "lucide-react";
import dynamic from "next/dynamic";
import type { Market } from "@/components/shared/ExportModal";
const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const MARKETS = ["GDAM", "DAM", "RTM"];
const COLORS: Record<string, string> = { GDAM: "#10b981", DAM: "#3b82f6", RTM: "#f59e0b" };
const BASE_URL = process.env.NEXT_PUBLIC_API_URL;

const DATE_OPTIONS = Array.from({ length: 8 }, (_, i) => {
  const d = new Date();
  d.setDate(d.getDate() - i);
  return {
    label: i === 0 ? "Today" : d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }),
    date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`,
  };
});

interface MarketData {
  available: boolean;
  blocks: { block: number; datetime_block: string; actual_price: number }[];
  message?: string;
}

export default function ComparePage() {
  const { data: session } = useSession();
  const accessToken = useMemo(() => (session as any)?.accessToken as string | undefined, [session]);

  const [selectedRegion, setSelectedRegion] = useState("Telangana");
  const [selectedDateIdx, setSelectedDateIdx] = useState(0);
  const [activeMarkets, setActiveMarkets] = useState(["GDAM", "DAM", "RTM"]);
  const [marketData, setMarketData] = useState<Record<string, MarketData>>({});
  const [loading, setLoading] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [chartInstance, setChartInstance] = useState<any>(null);
  const loadData = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);

    const headers = { Authorization: `Bearer ${accessToken}` };
    const selectedDate = DATE_OPTIONS[selectedDateIdx].date;

    const results = await Promise.all(
      MARKETS.map(async (market) => {
        try {
          const res = await fetch(
            `${BASE_URL}/api/historical?market=${market}&region=${selectedRegion}&price_date=${selectedDate}`,
            { headers }
          );
          const json = await res.json();
          return { market, data: json as MarketData };
        } catch {
          return { market, data: { available: false, blocks: [], message: "Failed to fetch" } };
        }
      })
    );

    const newData: Record<string, MarketData> = {};
    results.forEach(({ market, data }) => { newData[market] = data; });
    setMarketData(newData);
    setLoading(false);
  }, [accessToken, selectedRegion, selectedDateIdx]);

  useEffect(() => { loadData(); }, [loadData]);

  const toggle = (m: string) => setActiveMarkets((prev) =>
    prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]
  );

  const hasAnyData = MARKETS.some((m) => marketData[m]?.available);

  const avgs = MARKETS.reduce((acc, m) => {
    const blocks = marketData[m]?.blocks ?? [];
    acc[m] = blocks.length ? Math.round(blocks.reduce((s, b) => s + b.actual_price, 0) / blocks.length) : null;
    return acc;
  }, {} as Record<string, number | null>);

  const chartOption = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      backgroundColor: "#18181b",
      borderColor: "#27272a",
      textStyle: { color: "#fff", fontSize: 12 },
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex;
        let html = `<div style="font-weight:600;margin-bottom:6px">Block ${idx + 1}</div>`;
        params.forEach((p: any) => {
          if (p.value != null) {
            html += `<div style="display:flex;gap:8px;align-items:center;margin:3px 0">
              <span style="width:10px;height:10px;border-radius:50%;background:${p.color};display:inline-block"></span>
              <span style="color:#a1a1aa">${p.seriesName}:</span>
              <span style="font-weight:600">₹${Number(p.value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
            </div>`;
          }
        });
        return html;
      },
    },
    legend: { bottom: 0, textStyle: { color: "#71717a", fontSize: 12 } },
    grid: { top: 20, left: 70, right: 30, bottom: 75 },
    xAxis: {
      type: "category",
      data: Array.from({ length: 96 }, (_, i) => i + 1),
      axisLabel: { color: "#71717a", fontSize: 11, interval: 7 },
      axisLine: { lineStyle: { color: "#e4e4e7" } },
      axisTick: { show: false },
      name: "Time Block (15-min Intervals)",
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: { color: "#71717a", fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#71717a", fontSize: 11, formatter: (v: number) => `₹${(v / 1000).toFixed(0)}k` },
      splitLine: { lineStyle: { color: "#f4f4f5", type: "dashed" } },
      axisLine: { show: false },
      axisTick: { show: false },
      name: "Price (Rs/MWh)",
      nameLocation: "middle",
      nameGap: 55,
      nameTextStyle: { color: "#71717a", fontSize: 11 },
    },
    series: MARKETS
      .filter((m) => activeMarkets.includes(m) && marketData[m]?.available)
      .map((market) => ({
        name: market,
        type: "line",
        data: marketData[market].blocks.map((b) => b.actual_price),
        lineStyle: { color: COLORS[market], width: 2 },
        itemStyle: { color: COLORS[market] },
        symbol: "circle",
        symbolSize: 4,
      })),
  }), [marketData, activeMarkets]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-zinc-900">
            Market Comparison
          </h1>
          <p className="text-zinc-500 text-sm mt-0.5">
            Compare GDAM, DAM and RTM actual prices side by side
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => setIsExportOpen(true)}
          className="text-zinc-600 border-zinc-200 gap-1.5 h-8 text-xs"
        >
          <Download size={12} />
          Export
        </Button>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <Select value={selectedRegion} onValueChange={setSelectedRegion}>
          <SelectTrigger className="w-44 h-8 text-xs border-zinc-200">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MOCK_REGIONS.map((r) => (
              <SelectItem key={r} value={r} className="text-sm">{r}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-2 ml-auto">
          {MARKETS.map((m) => {
            const hasData = marketData[m]?.available;
            const isActive = activeMarkets.includes(m);
            return (
              <button
                key={m}
                onClick={() => hasData && toggle(m)}
                disabled={!hasData}
                className="text-xs px-3 py-1.5 rounded-md border font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                style={{
                  background: isActive && hasData ? COLORS[m] : "white",
                  color: isActive && hasData ? "white" : "#71717a",
                  borderColor: isActive && hasData ? COLORS[m] : "#e4e4e7",
                }}
              >
                {m}
              </button>
            );
          })}
        </div>
      </div>

      {/* Date selector */}
      <div className="flex items-center gap-2 flex-wrap">
        {DATE_OPTIONS.map((opt, i) => (
          <button
            key={opt.date}
            onClick={() => setSelectedDateIdx(i)}
            className={`text-xs px-3 py-1.5 rounded-md border transition-all font-medium ${selectedDateIdx === i ? "bg-zinc-900 text-white border-zinc-900" : "bg-white text-zinc-500 border-zinc-200 hover:border-zinc-300"}`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-4">
        {MARKETS.map((m) => {
          const available = marketData[m]?.available;
          return (
            <Card
              key={m}
              className={`p-4 border-zinc-100 shadow-none transition-opacity ${activeMarkets.includes(m) ? "opacity-100" : "opacity-40"}`}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS[m] }} />
                  <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">{m}</span>
                </div>
                {!available && (
                  <span className="text-xs text-zinc-300 font-medium">No data</span>
                )}
              </div>
              {available ? (
                <>
                  <p className="text-xl font-bold text-zinc-900">
                    ₹{avgs[m]?.toLocaleString("en-IN") ?? "—"}
                  </p>
                  <p className="text-xs text-zinc-400">Avg Rs/MWh · {selectedRegion}</p>
                </>
              ) : (
                <>
                  <p className="text-xl font-bold text-zinc-300">—</p>
                  <p className="text-xs text-zinc-300">
                    {DATE_OPTIONS[selectedDateIdx].label} · {selectedRegion}
                  </p>
                </>
              )}
            </Card>
          );
        })}
      </div>

      {/* Chart */}
      <Card className="p-6 border-zinc-100 shadow-none">
        {loading ? (
          <div className="h-96 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-7 h-7 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-zinc-400 text-sm">Loading market data...</p>
            </div>
          </div>
        ) : !hasAnyData ? (
          <div className="h-96 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3 text-center">
              <WifiOff size={32} className="text-zinc-300" />
              <p className="text-zinc-500 font-medium">No data available</p>
              <p className="text-zinc-400 text-sm">
                No market data found for {selectedRegion} · {DATE_OPTIONS[selectedDateIdx].label}
              </p>
              <p className="text-zinc-300 text-xs">
                Try selecting a different date or region
              </p>
            </div>
          </div>
        ) : (
          <div className="chart-grid-background rounded-lg overflow-hidden">
            <ReactECharts
              option={chartOption}
              notMerge={true}
              lazyUpdate={false}
              style={{ height: "420px", width: "100%" }}
              opts={{ renderer: "canvas" }}
              onChartReady={(chart) => setChartInstance(chart)}
            />
          </div>
        )}
      </Card>

      {/* Availability summary */}
      <div className="flex items-center gap-2 flex-wrap">
        {MARKETS.map((m) => (
          <span
            key={m}
            className={`text-xs px-2.5 py-1 rounded-md border font-medium ${marketData[m]?.available
              ? "text-emerald-600 border-emerald-200 bg-emerald-50"
              : "text-zinc-300 border-zinc-100 bg-zinc-50"
              }`}
          >
            {m}: {marketData[m]?.available ? "Available" : "No data"}
          </span>
        ))}
        <span className="text-xs text-zinc-400 ml-1">
          · {DATE_OPTIONS[selectedDateIdx].label} · {selectedRegion}
        </span>
      </div>
      <ExportModal
        isOpen={isExportOpen}
        onClose={() => setIsExportOpen(false)}
        defaultMarket={activeMarkets[0] as Market}
        defaultStartDate={DATE_OPTIONS[selectedDateIdx].date}
        defaultEndDate={DATE_OPTIONS[selectedDateIdx].date}
        chartInstances={{
          historical: chartInstance,
        }}
      />
    </div>
  );
}