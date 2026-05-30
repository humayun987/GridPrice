"use client";

import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { generateMockForecast, MOCK_REGIONS } from "@/lib/mockData";
import { ForecastBlock } from "@/lib/types";
import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const MARKETS = ["GDAM", "DAM", "RTM"];
const COLORS: Record<string, string> = { GDAM: "#10b981", DAM: "#3b82f6", RTM: "#f59e0b" };

export default function ComparePage() {
  const [selectedRegion, setSelectedRegion] = useState("Telangana");
  const [activeMarkets, setActiveMarkets] = useState(["GDAM", "DAM", "RTM"]);
  const [allData, setAllData] = useState<Record<string, ForecastBlock[]>>({});

  useEffect(() => {
    const d: Record<string, ForecastBlock[]> = {};
    MARKETS.forEach((m) => { d[m] = generateMockForecast(m); });
    setAllData(d);
  }, [selectedRegion]);

  const toggle = (m: string) => setActiveMarkets((prev) => prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]);

  const blocks = Array.from({ length: 96 }, (_, i) => i + 1);

  const option = {
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
              <span style="font-weight:600">\u20B9${Number(p.value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
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
      data: blocks,
      axisLabel: { color: "#71717a", fontSize: 11, interval: 7 },
      axisLine: { lineStyle: { color: "#e4e4e7" } },
      axisTick: { show: false },
      name: "Time Block",
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: { color: "#71717a", fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#71717a", fontSize: 11, formatter: (v: number) => `\u20B9${(v / 1000).toFixed(0)}k` },
      splitLine: { lineStyle: { color: "#f4f4f5", type: "dashed" } },
      axisLine: { show: false },
      axisTick: { show: false },
      name: "Price (Rs/MWh)",
      nameLocation: "middle",
      nameGap: 55,
      nameTextStyle: { color: "#71717a", fontSize: 11 },
    },
    series: MARKETS.filter((m) => activeMarkets.includes(m)).map((market) => ({
      name: market,
      type: "line",
      data: allData[market]?.map((d) => d.predicted_price) ?? [],
      lineStyle: { color: COLORS[market], width: 2 },
      itemStyle: { color: COLORS[market] },
      symbol: "circle",
      symbolSize: 4,
    })),
  };

  const avgs = MARKETS.reduce((acc, m) => {
    const d = allData[m];
    acc[m] = d?.length ? Math.round(d.reduce((s, x) => s + x.predicted_price, 0) / d.length) : 0;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-zinc-900">Market Comparison</h1>
        <p className="text-zinc-500 text-sm mt-0.5">Compare GDAM, DAM and RTM prices side by side</p>
      </div>

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

        <div className="flex items-center gap-2">
          {MARKETS.map((m) => (
            <button
              key={m}
              onClick={() => toggle(m)}
              className="text-xs px-3 py-1.5 rounded-md border font-medium transition-all"
              style={{
                background: activeMarkets.includes(m) ? COLORS[m] : "white",
                color: activeMarkets.includes(m) ? "white" : "#71717a",
                borderColor: activeMarkets.includes(m) ? COLORS[m] : "#e4e4e7",
              }}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {MARKETS.map((m) => (
          <Card key={m} className={`p-4 border-zinc-100 shadow-none transition-opacity ${activeMarkets.includes(m) ? "opacity-100" : "opacity-40"}`}>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: COLORS[m] }} />
              <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">{m}</span>
            </div>
            <p className="text-xl font-bold text-zinc-900">₹{avgs[m].toLocaleString("en-IN")}</p>
            <p className="text-xs text-zinc-400">Avg Rs/MWh · {selectedRegion}</p>
          </Card>
        ))}
      </div>

      <Card className="p-6 border-zinc-100 shadow-none">
        <ReactECharts option={option} style={{ height: "420px", width: "100%" }} opts={{ renderer: "canvas" }} />
      </Card>
    </div>
  );
}
