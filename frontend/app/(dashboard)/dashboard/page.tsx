"use client";

import { useState, useEffect, useCallback } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import ForecastChart from "@/components/shared/ForecastChart";
import { generateMockForecast, MOCK_REGIONS } from "@/lib/mockData";
import { ForecastBlock } from "@/lib/types";
import { RefreshCw, Download, TrendingUp, TrendingDown, Activity, Zap, Target, AlertCircle } from "lucide-react";
import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const MARKETS = ["GDAM", "DAM", "RTM"];

function getLast7Days(): { label: string; date: string }[] {
  const days = [];
  for (let i = 1; i <= 7; i++) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    days.push({
      label: d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }),
      date: d.toISOString().split("T")[0],
    });
  }
  return days;
}

export default function DashboardPage() {
  const [selectedMarket, setSelectedMarket] = useState("GDAM");
  const [selectedRegion, setSelectedRegion] = useState("Telangana");
  const [showCI, setShowCI] = useState(true);
  const [showHistorical, setShowHistorical] = useState(true);
  const [data, setData] = useState<ForecastBlock[]>([]);
  const [loading, setLoading] = useState(false);
  const [auditDay, setAuditDay] = useState(0);
  const [auditData, setAuditData] = useState<ForecastBlock[]>([]);
  const days = getLast7Days();

  const loadForecast = useCallback(() => {
    setLoading(true);
    setTimeout(() => {
      setData(generateMockForecast(selectedMarket));
      setLoading(false);
    }, 400);
  }, [selectedMarket, selectedRegion]);

  useEffect(() => { loadForecast(); }, [loadForecast]);

  useEffect(() => {
    setAuditData(generateMockForecast(selectedMarket));
  }, [auditDay, selectedMarket]);

  const avg = data.length ? Math.round(data.reduce((s, d) => s + d.predicted_price, 0) / data.length) : 0;
  const max = data.length ? Math.max(...data.map((d) => d.predicted_price)) : 0;
  const min = data.length ? Math.min(...data.map((d) => d.predicted_price)) : 0;
  const peakBlock = data.length ? data.reduce((a, b) => a.predicted_price > b.predicted_price ? a : b).block : 0;

  const auditBlocks = auditData.filter((d) => d.actual_price != null);
  const mae = auditBlocks.length ? Math.round(auditBlocks.reduce((s, d) => s + Math.abs(d.predicted_price - (d.actual_price ?? 0)), 0) / auditBlocks.length) : 0;
  const mape = auditBlocks.length ? (auditBlocks.reduce((s, d) => s + Math.abs((d.predicted_price - (d.actual_price ?? 0)) / (d.actual_price ?? 1)), 0) / auditBlocks.length * 100).toFixed(1) : "0";
  const worstBlock = auditBlocks.length ? auditBlocks.reduce((a, b) => Math.abs(a.predicted_price - (a.actual_price ?? 0)) > Math.abs(b.predicted_price - (b.actual_price ?? 0)) ? a : b) : null;

  const auditOption = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      backgroundColor: "#18181b",
      borderColor: "#27272a",
      textStyle: { color: "#fff", fontSize: 12 },
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex;
        const d = auditBlocks[idx];
        if (!d) return "";
        const fmt = (v: number) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
        const err = d.actual_price ? Math.abs(((d.predicted_price - d.actual_price) / d.actual_price) * 100).toFixed(1) : "0";
        return `<div style="font-weight:600;margin-bottom:6px">Block ${d.block} · ${d.datetime_block}</div>
          <div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="width:10px;height:2px;background:#27272a;display:inline-block"></span><span style="color:#a1a1aa">Actual:</span><span style="font-weight:600">${fmt(d.actual_price ?? 0)}</span></div>
          <div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="width:10px;height:2px;border-top:2px dashed #10b981;display:inline-block"></span><span style="color:#a1a1aa">Predicted:</span><span style="font-weight:600">${fmt(d.predicted_price)}</span></div>
          <div style="margin-top:4px;color:#f59e0b;font-size:11px">Error: ${err}%</div>`;
      },
    },
    legend: { bottom: 0, textStyle: { color: "#71717a", fontSize: 12 } },
    grid: { top: 20, left: 70, right: 30, bottom: 55 },
    xAxis: {
      type: "category",
      data: auditBlocks.map((d) => d.block),
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
      axisLabel: { color: "#71717a", fontSize: 11, formatter: (v: number) => `₹${(v / 1000).toFixed(0)}k` },
      splitLine: { lineStyle: { color: "#f4f4f5", type: "dashed" } },
      axisLine: { show: false },
      axisTick: { show: false },
      name: "Price (Rs/MWh)",
      nameLocation: "middle",
      nameGap: 55,
      nameTextStyle: { color: "#71717a", fontSize: 11 },
    },
    series: [
      {
        name: "Actual Price",
        type: "line",
        data: auditBlocks.map((d) => d.actual_price),
        lineStyle: { color: "#27272a", width: 2.5 },
        itemStyle: { color: "#27272a" },
        symbol: "circle",
        symbolSize: 4,
      },
      {
        name: "Predicted Price",
        type: "line",
        data: auditBlocks.map((d) => d.predicted_price),
        lineStyle: { color: "#10b981", width: 2, type: "dashed" },
        itemStyle: { color: "#10b981" },
        symbol: "circle",
        symbolSize: 4,
      },
    ],
  };

  const fmt = (v: number) => `₹${v.toLocaleString("en-IN")}`;
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-zinc-900">Price Discovery Corridor (D+1)</h1>
          <p className="text-zinc-500 text-sm mt-0.5">{today}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadForecast} className="text-zinc-600 border-zinc-200 gap-1.5 h-8 text-xs">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
          </Button>
          <Button variant="outline" size="sm" className="text-zinc-600 border-zinc-200 gap-1.5 h-8 text-xs">
            <Download size={12} /> Export
          </Button>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <Tabs value={selectedMarket} onValueChange={setSelectedMarket}>
          <TabsList className="bg-zinc-100 h-8">
            {MARKETS.map((m) => (
              <TabsTrigger key={m} value={m} className="text-xs font-medium px-4 h-7">{m}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
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
          <button onClick={() => setShowCI(!showCI)} className={`text-xs px-3 py-1.5 rounded-md border transition-all ${showCI ? "bg-zinc-900 text-white border-zinc-900" : "bg-white text-zinc-400 border-zinc-200"}`}>
            Confidence Interval
          </button>
          <button onClick={() => setShowHistorical(!showHistorical)} className={`text-xs px-3 py-1.5 rounded-md border transition-all ${showHistorical ? "bg-zinc-900 text-white border-zinc-900" : "bg-white text-zinc-400 border-zinc-200"}`}>
            Historical Overlay
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Avg Price", value: fmt(avg), sub: "Rs/MWh", Icon: Activity, color: "text-zinc-600" },
          { label: "Peak Price", value: fmt(max), sub: `Block ${peakBlock}`, Icon: TrendingUp, color: "text-red-500" },
          { label: "Off-Peak", value: fmt(min), sub: "Rs/MWh", Icon: TrendingDown, color: "text-emerald-500" },
          { label: "Market", value: selectedMarket, sub: selectedRegion, Icon: Zap, color: "text-blue-500" },
        ].map(({ label, value, sub, Icon, color }) => (
          <Card key={label} className="p-4 border-zinc-100 shadow-none">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-zinc-400 font-medium uppercase tracking-wider">{label}</span>
              <Icon size={14} className={color} />
            </div>
            <p className="text-xl font-bold text-zinc-900">{value}</p>
            <p className="text-xs text-zinc-400 mt-0.5">{sub}</p>
          </Card>
        ))}
      </div>

      {/* Forecast Chart */}
      <Card className="p-6 border-zinc-100 shadow-none">
        {loading ? (
          <div className="h-96 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-7 h-7 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-zinc-400 text-sm">Loading forecast...</p>
            </div>
          </div>
        ) : (
          <ForecastChart data={data} showCI={showCI} showHistorical={showHistorical} title={`${selectedMarket} · ${selectedRegion} · Day-ahead forecast`} height="420px" />
        )}
      </Card>

      <div className="flex items-center gap-2">
        <Badge variant="outline" className="text-xs text-zinc-400 border-zinc-200">Mock data · Connect backend for live forecasts</Badge>
        <Badge variant="outline" className="text-xs text-emerald-600 border-emerald-200 bg-emerald-50">96 blocks · 15-min intervals</Badge>
      </div>

      {/* Performance Audit */}
      <div className="pt-2 border-t border-zinc-100">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-bold text-zinc-900">Performance Audit</h2>
            <p className="text-zinc-500 text-sm mt-0.5">Compare forecast accuracy against actual market prices</p>
          </div>
        </div>

        {/* Day selector */}
        <div className="flex items-center gap-2 mb-5 flex-wrap">
          {days.map((day, i) => (
            <button
              key={day.date}
              onClick={() => setAuditDay(i)}
              className={`text-xs px-3 py-1.5 rounded-md border transition-all font-medium ${auditDay === i ? "bg-zinc-900 text-white border-zinc-900" : "bg-white text-zinc-500 border-zinc-200 hover:border-zinc-300"}`}
            >
              {day.label}
            </button>
          ))}
        </div>

        {/* Audit stats */}
        <div className="grid grid-cols-3 gap-4 mb-4">
          <Card className="p-4 border-zinc-100 shadow-none">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-zinc-400 font-medium uppercase tracking-wider">MAE</span>
              <Target size={14} className="text-blue-500" />
            </div>
            <p className="text-xl font-bold text-zinc-900">₹{mae.toLocaleString("en-IN")}</p>
            <p className="text-xs text-zinc-400 mt-0.5">Mean absolute error</p>
          </Card>
          <Card className="p-4 border-zinc-100 shadow-none">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-zinc-400 font-medium uppercase tracking-wider">MAPE</span>
              <Activity size={14} className="text-emerald-500" />
            </div>
            <p className="text-xl font-bold text-zinc-900">{mape}%</p>
            <p className="text-xs text-zinc-400 mt-0.5">Mean absolute % error</p>
          </Card>
          <Card className="p-4 border-zinc-100 shadow-none">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-zinc-400 font-medium uppercase tracking-wider">Worst Block</span>
              <AlertCircle size={14} className="text-amber-500" />
            </div>
            <p className="text-xl font-bold text-zinc-900">Block {worstBlock?.block ?? "—"}</p>
            <p className="text-xs text-zinc-400 mt-0.5">{worstBlock ? `${worstBlock.datetime_block} · highest deviation` : "No data"}</p>
          </Card>
        </div>

        {/* Audit chart */}
        <Card className="p-6 border-zinc-100 shadow-none">
          <p className="text-sm font-semibold text-zinc-700 mb-4">
            Actual vs Predicted · {days[auditDay]?.label} · {selectedMarket}
          </p>
          <ReactECharts option={auditOption} style={{ height: "320px", width: "100%" }} opts={{ renderer: "canvas" }} />
        </Card>
      </div>
    </div>
  );
}
