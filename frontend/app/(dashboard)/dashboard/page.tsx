"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useSession } from "next-auth/react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { generateMockForecast, MOCK_REGIONS } from "@/lib/mockData";
import { ForecastBlock } from "@/lib/types";
import { ExportModal } from "@/components/shared/ExportModal";
import { RefreshCw, Download, TrendingUp, TrendingDown, Activity, Zap, Target, AlertCircle, WifiOff } from "lucide-react";
import dynamic from "next/dynamic";
import type { Market } from "@/components/shared/ExportModal";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const MARKETS = ["GDAM", "DAM", "RTM"];
const BASE_URL = process.env.NEXT_PUBLIC_API_URL;

const days = Array.from({ length: 7 }, (_, i) => {
  const d = new Date();
  d.setDate(d.getDate() - i);
  return {
    label: d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }),
    date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`,
  };
});

// function getTomorrow(): string {
//   const d = new Date();
//   d.setDate(d.getDate() + 1);
//   return d.toISOString().split("T")[0];
// }

// function getToday(): string {
//   return new Date().toISOString().split("T")[0];
// }

function getTomorrow(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function getToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function DashboardPage() {
  const { data: session } = useSession();
  const accessToken = useMemo(() => (session as any)?.accessToken as string | undefined, [session]);
  const [selectedMarket, setSelectedMarket] = useState("GDAM");
  const [selectedRegion, setSelectedRegion] = useState("Telangana");
  const [showCI, setShowCI] = useState(true);
  const [availableCILevels, setAvailableCILevels] = useState<number[]>([]);
  const [selectedCILevel, setSelectedCILevel] = useState<number | null>(null);
  const [forecastData, setForecastData] = useState<ForecastBlock[]>([]);
  const [demandRatios, setDemandRatios] = useState<(number | null)[]>([]);
  const [loading, setLoading] = useState(false);
  const [dataSource, setDataSource] = useState<"real" | "unavailable">("unavailable");
  const [refreshing, setRefreshing] = useState(false);
  const [auditDay, setAuditDay] = useState(0);
  const [auditData, setAuditData] = useState<ForecastBlock[]>([]);
  const [auditAvailable, setAuditAvailable] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [chartInstance, setChartInstance] = useState<any>(null);
  const [forecastChartInstance, setForecastChartInstance] = useState<any>(null);
  const [auditChartInstance, setAuditChartInstance] = useState<any>(null);
  const loadForecast = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);

    const headers = {
      Authorization: `Bearer ${accessToken}`,
    };

    const tomorrow = getTomorrow();
    const today = getToday();

    try {
      // fetch forecast first
      const foreRes = await fetch(
        `${BASE_URL}/api/forecasts?market=${selectedMarket}&region=${selectedRegion}&forecast_date=${tomorrow}`,
        { headers }
      );
      const fore = await foreRes.json();

      if (fore.available && fore.blocks.length > 0) {
        setForecastData(fore.blocks);
        setDataSource("real");
      } else if (fore.available === false) {
        setForecastData([]);
        setDataSource("unavailable");
      } else {
        setForecastData([]);
        setDataSource("unavailable");
      }

      // fetch historical separately so one failure does not kill forecast
      try {
        const histRes = await fetch(
          `${BASE_URL}/api/historical?market=${selectedMarket}&region=${selectedRegion}&price_date=${today}`,
          { headers }
        );
        const hist = await histRes.json();

        if (hist.available && hist.blocks.length > 0) {
          setDemandRatios(hist.blocks.map((b: any) => b.demand_ratio ?? null));
        } else {
          setDemandRatios([]);
        }
      } catch {
        setDemandRatios([]);
      }
    } catch {
      setForecastData([]);
      setDataSource("unavailable");
      setDemandRatios([]);
    } finally {
      setLoading(false);
    }
  }, [accessToken, selectedMarket, selectedRegion]);

  useEffect(() => { loadForecast(); }, [loadForecast]);

  // Auto-poll every 5 min when no forecast yet — stops once data arrives
  useEffect(() => {
    if (dataSource !== "unavailable") return; // already have data, don't poll

    const interval = setInterval(() => {
      loadForecast();
    }, 5 * 60 * 1000); // 5 minutes

    return () => clearInterval(interval);
  }, [dataSource, loadForecast]);

  const loadCILevels = useCallback(async () => {
    if (!accessToken) return;

    try {
      const res = await fetch(
        `${BASE_URL}/api/ci-levels?market=${selectedMarket}&region=${selectedRegion}`,
        {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        }
      );

      const data = await res.json();

      const levels = data.levels ?? [];

      setAvailableCILevels(levels);

      if (levels.length > 0) {
        setSelectedCILevel(levels[0]);
      } else {
        setSelectedCILevel(null);
      }
    } catch {
      setAvailableCILevels([]);
      setSelectedCILevel(null);
    }
  }, [accessToken, selectedMarket, selectedRegion]);

  useEffect(() => {
    loadCILevels();
  }, [loadCILevels]);


  const loadAuditData = useCallback(async () => {
    if (!accessToken) return;
    setAuditLoading(true);

    const headers = {
      Authorization: `Bearer ${accessToken}`,
    };

    const selectedDate = days[auditDay].date;

    try {
      const [histRes, foreRes] = await Promise.all([
        fetch(`${BASE_URL}/api/historical?market=${selectedMarket}&region=${selectedRegion}&price_date=${selectedDate}`, { headers }),
        fetch(`${BASE_URL}/api/forecasts?market=${selectedMarket}&region=${selectedRegion}&forecast_date=${selectedDate}`, { headers }),
      ]);

      const hist = await histRes.json();
      const fore = await foreRes.json();

      if (hist.available && fore.available) {
        const merged: ForecastBlock[] = fore.blocks.map((f: any, i: number) => ({
          ...f,
          actual_price: hist.blocks[i]?.actual_price ?? undefined,
        }));
        setAuditData(merged);
        setAuditAvailable(true);
      } else {
        setAuditData([]);
        setAuditAvailable(false);
      }
    } catch {
      setAuditData([]);
      setAuditAvailable(false);
    } finally {
      setAuditLoading(false);
    }
  }, [accessToken, auditDay, selectedMarket, selectedRegion]);
  useEffect(() => { loadAuditData(); }, [loadAuditData]);

  const handleAdminRefresh = async () => {
    if (!accessToken) return;
    setRefreshing(true);
    try {
      const res = await fetch(
        `${BASE_URL}/api/refresh?market=${selectedMarket}&region=${selectedRegion}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        }
      );
      const result = await res.json();
      if (result.status === "success") {
        await loadForecast();
      }
    } catch {
      // silently fail
    }
    setRefreshing(false);
  };

  // ── Stats ──────────────────────────────────────────────
  // const avg = forecastData.length ? Math.round(forecastData.reduce((s, d) => s + d.predicted_price, 0) / forecastData.length) : 0;
  // const max = forecastData.length ? Math.max(...forecastData.map((d) => d.predicted_price)) : 0;
  // const min = forecastData.length ? Math.min(...forecastData.map((d) => d.predicted_price)) : 0;
  // const peakBlock = forecastData.length ? forecastData.reduce((a, b) => a.predicted_price > b.predicted_price ? a : b).block : 0;
  const validForecasts = forecastData.filter(
    d => d.predicted_price != null
  );

  const avg = validForecasts.length
    ? Math.round(
      validForecasts.reduce(
        (s, d) => s + d.predicted_price,
        0
      ) / validForecasts.length
    )
    : 0;

  const max = validForecasts.length
    ? Math.max(...validForecasts.map(d => d.predicted_price))
    : 0;

  const min = validForecasts.length
    ? Math.min(...validForecasts.map(d => d.predicted_price))
    : 0;

  const peakBlock = validForecasts.length
    ? validForecasts.reduce(
      (a, b) =>
        a.predicted_price > b.predicted_price ? a : b
    ).block
    : 0;
  const fmt = (v: number) => `₹${v.toLocaleString("en-IN")}`;
  const todayStr = new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  const tomorrowS = new Date();
  tomorrowS.setDate(tomorrowS.getDate() + 1);
  const tomorrowStr = tomorrowS.toLocaleDateString("en-IN", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  // ── D+1 Forecast Chart ─────────────────────────────────
  const blocks = forecastData.map((d) => d.block);
  const predicted = forecastData.map((d) => d.predicted_price);
  // const lowerCI = forecastData.map((d) => d.lower_ci);
  // const ciDiff = forecastData.map((d) => (d.upper_ci ?? 0) - (d.lower_ci ?? 0));

  // CI handling
  // Current backend returns exactly one CI band via lower_ci / upper_ci.
  // When ML starts returning multiple confidence intervals,
  // use selectedCILevel to pick the correct interval from
  // d.confidence_intervals[selectedCILevel].

  const lowerCI = forecastData.map((d) => {
    if (availableCILevels.length <= 1) {
      return d.lower_ci ?? 0;
    }

    // TODO: future implementation
    // return d.confidence_intervals?.[selectedCILevel!]?.lower ?? 0;

    return d.lower_ci ?? 0;
  });

  const upperCI = forecastData.map((d) => {
    if (availableCILevels.length <= 1) {
      return d.upper_ci ?? 0;
    }

    // TODO: future implementation
    // return d.confidence_intervals?.[selectedCILevel!]?.upper ?? 0;

    return d.upper_ci ?? 0;
  });

  const ciDiff = upperCI.map((upper, idx) => upper - lowerCI[idx]);

  const forecastOption = useMemo(() => ({
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      backgroundColor: "#18181b",
      borderColor: "#27272a",
      textStyle: { color: "#fff", fontSize: 12 },
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex;
        const d = forecastData[idx];
        if (!d) return "";
        // const f = (v: number) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
        const f = (v: number | null | undefined) =>
          v == null
            ? "N/A"
            : `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
        let html = `<div style="font-weight:600;margin-bottom:6px">Block ${d.block} · ${d.datetime_block}</div>`;
        html += `<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="width:10px;height:10px;border-radius:50%;background:#10b981;display:inline-block"></span><span style="color:#a1a1aa">P50 Forecast:</span><span style="font-weight:600">${f(d.predicted_price)}</span></div>`;
        if (showCI) {
          // Current backend exposes a single CI band via
          // lower_ci / upper_ci.
          // Future: read values from confidence_intervals[selectedCILevel].
          html += `<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="color:#a1a1aa">P90:</span><span style="font-weight:600">${f(d.upper_ci ?? 0)}</span></div>`;
          html += `<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="color:#a1a1aa">P10:</span><span style="font-weight:600">${f(d.lower_ci ?? 0)}</span></div>`;
        }
        const dr = demandRatios[idx];
        if (dr != null) html += `<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="color:#a1a1aa">Demand Ratio:</span><span style="font-weight:600">${dr}</span></div>`;
        return html;
      },
    },
    legend: { bottom: 0, textStyle: { color: "#71717a", fontSize: 12 } },
    grid: { top: 20, left: 70, right: 70, bottom: 75 },
    xAxis: {
      type: "category",
      data: blocks,
      axisLabel: { color: "#71717a", fontSize: 11, interval: 7 },
      axisLine: { lineStyle: { color: "#e4e4e7" } },
      axisTick: { show: false },
      name: "Time Block (15-min Intervals)",
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: { color: "#71717a", fontSize: 11 },
    },
    yAxis: [
      {
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
      {
        type: "value",
        axisLabel: { color: "#93c5fd", fontSize: 11 },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        name: "Demand/Supply Ratio",
        nameLocation: "middle",
        nameGap: 55,
        nameTextStyle: { color: "#93c5fd", fontSize: 11 },
      },
    ],
    series: [
      ...(showCI ? [
        {
          name: "CI_base",
          type: "line",
          data: lowerCI,
          lineStyle: { opacity: 0 },
          areaStyle: { color: "transparent" },
          stack: "ci",
          symbol: "none",
          silent: true,
          legendHoverLink: false,
          yAxisIndex: 0,
        },
        {
          name: "P90 (Upper Band)",
          type: "line",
          data: ciDiff,
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(161,161,170,0.18)" },
          stack: "ci",
          symbol: "none",
          yAxisIndex: 0,
        },
        {
          name: "P10 (Lower Band)",
          type: "line",
          data: lowerCI,
          lineStyle: { color: "#a1a1aa", width: 1, type: "dashed" },
          symbol: "none",
          yAxisIndex: 0,
        },
      ] : []),
      {
        name: "P50 Forecast",
        type: "line",
        data: predicted,
        lineStyle: { color: "#10b981", width: 2.5 },
        itemStyle: { color: "#10b981" },
        symbol: "circle",
        symbolSize: 5,
        yAxisIndex: 0,
        z: 10,
      },
      ...(demandRatios.length > 0 ? [{
        name: "Demand Ratio",
        type: "line",
        data: demandRatios,
        lineStyle: { color: "#3b82f6", width: 1.5, type: "dashed" },
        itemStyle: { color: "#3b82f6" },
        symbol: "none",
        yAxisIndex: 1,
      }] : []),
    ],
  }), [forecastData, demandRatios, showCI, blocks, predicted, lowerCI, ciDiff, availableCILevels, selectedCILevel]);

  // ── Audit Chart ────────────────────────────────────────
  const auditBlocks = auditData.filter((d) => d.actual_price != null);
  const mae = auditBlocks.length ? Math.round(auditBlocks.reduce((s, d) => s + Math.abs(d.predicted_price - (d.actual_price ?? 0)), 0) / auditBlocks.length) : 0;
  const mape = auditBlocks.length ? (auditBlocks.reduce((s, d) => s + Math.abs((d.predicted_price - (d.actual_price ?? 0)) / (d.actual_price ?? 1)), 0) / auditBlocks.length * 100).toFixed(1) : "0";
  const worstBlock = auditBlocks.length ? auditBlocks.reduce((a, b) => Math.abs(a.predicted_price - (a.actual_price ?? 0)) > Math.abs(b.predicted_price - (b.actual_price ?? 0)) ? a : b) : null;

  const auditOption = useMemo(() => ({
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
        const f = (v: number) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
        const err = d.actual_price ? Math.abs(((d.predicted_price - d.actual_price) / d.actual_price) * 100).toFixed(1) : "0";
        return `<div style="font-weight:600;margin-bottom:6px">Block ${d.block} · ${d.datetime_block}</div>
          <div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="color:#a1a1aa">Actual:</span><span style="font-weight:600">${f(d.actual_price ?? 0)}</span></div>
          <div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="color:#a1a1aa">Predicted:</span><span style="font-weight:600">${f(d.predicted_price)}</span></div>
          <div style="margin-top:4px;color:#f59e0b;font-size:11px">Error: ${err}%</div>`;
      },
    },
    legend: { bottom: 0, textStyle: { color: "#71717a", fontSize: 12 } },
    grid: { top: 20, left: 70, right: 30, bottom: 75 },
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
  }), [auditBlocks]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-zinc-900">Price Discovery Corridor (D+1)</h1>
          {/* <p className="text-zinc-500 text-sm mt-0.5">{todayStr}</p> */}
          <p className="text-zinc-500 text-sm mt-0.5">{tomorrowStr}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* <Button variant="outline" size="sm" onClick={loadForecast} className="text-zinc-600 border-zinc-200 gap-1.5 h-8 text-xs">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
          </Button> */}
          {(session as any)?.role === "admin" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleAdminRefresh}
              disabled={refreshing}
              className="text-emerald-600 border-emerald-200 hover:bg-emerald-50 gap-1.5 h-8 text-xs"
            >
              <Zap size={12} className={refreshing ? "animate-pulse" : ""} />
              {refreshing ? "Refreshing..." : "Refresh Forecast"}
            </Button>
          )}
          <Button variant="outline" onClick={() => setIsExportOpen(true)} size="sm" className="text-zinc-600 border-zinc-200 gap-1.5 h-8 text-xs">
            <Download size={12} /> Export
          </Button>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <Tabs value={selectedMarket} onValueChange={setSelectedMarket}>
          <TabsList className="bg-zinc-100 h-8">
            {MARKETS.map((m) => (
              <TabsTrigger key={m} value={m} className="text-xs font-medium px-4 h-7 text-zinc-500 data-[state=active]:bg-emerald-500 data-[state=active]:text-white data-[state=active]:shadow-sm transition-all">{m}</TabsTrigger>
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
          <button
            onClick={() => setShowCI(!showCI)}
            className={`text-xs px-3 py-1.5 rounded-md border transition-all ${showCI
              ? "bg-zinc-900 text-white border-zinc-900"
              : "bg-white text-zinc-400 border-zinc-200"
              }`}
          >
            Confidence Interval
          </button>

          {showCI && availableCILevels.length === 1 && (
            <Badge
              variant="outline"
              className="text-xs border-zinc-200"
            >
              {Math.round(availableCILevels[0] * 100)}% CI
            </Badge>
          )}

          {showCI && availableCILevels.length > 1 && (
            <Select
              value={String(selectedCILevel)}
              onValueChange={(v) => setSelectedCILevel(Number(v))}
            >
              <SelectTrigger className="w-24 h-8 text-xs border-zinc-200">
                <SelectValue />
              </SelectTrigger>

              <SelectContent>
                {availableCILevels.map((level) => (
                  <SelectItem
                    key={level}
                    value={String(level)}
                  >
                    {Math.round(level * 100)}% CI
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Avg Price", value: forecastData.length ? fmt(avg) : "—", sub: "Rs/MWh", Icon: Activity, color: "text-zinc-600" },
          { label: "Peak Price", value: forecastData.length ? fmt(max) : "—", sub: forecastData.length ? `Block ${peakBlock}` : "—", Icon: TrendingUp, color: "text-red-500" },
          { label: "Off-Peak", value: forecastData.length ? fmt(min) : "—", sub: "Rs/MWh", Icon: TrendingDown, color: "text-emerald-500" },
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
        ) : forecastData.length === 0 ? (
          <div className="h-96 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3 text-center">
              <WifiOff size={32} className="text-zinc-300" />
              <p className="text-zinc-500 font-medium">No forecast available</p>
              <p className="text-zinc-400 text-sm">No data found for {selectedMarket} · {selectedRegion} · Tomorrow</p>
              {/* <p className="text-zinc-300 text-xs">Only GDAM · Telangana is currently supported</p> */}
            </div>
          </div>
        ) : (
          <div>
            <p className="text-sm font-semibold text-zinc-700 mb-4">
              {selectedMarket} · {selectedRegion} · Day-ahead forecast
              {dataSource === "real" && <span className="ml-2 text-xs font-normal text-emerald-500">· Live data</span>}
              {dataSource === "unavailable" && <span className="ml-2 text-xs font-normal text-amber-500">· No data available</span>}
            </p>
            <ReactECharts option={forecastOption} notMerge={true} lazyUpdate={false} style={{ height: "420px", width: "100%" }} opts={{ renderer: "canvas" }} onChartReady={(chart) => setForecastChartInstance(chart)} />
          </div>
        )}
      </Card>

      {/* Badges */}
      <div className="flex items-center gap-2">
        {/* {dataSource === "real" && <Badge variant="outline" className="text-xs text-emerald-600 border-emerald-200 bg-emerald-50">Live data from database</Badge>} */}
        {dataSource === "unavailable" && <Badge variant="outline" className="text-xs text-zinc-400 border-zinc-200">No data for selected market/region </Badge>}
        <Badge variant="outline" className="text-xs text-emerald-600 border-emerald-200 bg-emerald-50">96 blocks · 15-min intervals</Badge>
      </div>

      {/* Performance Audit */}
      <div className="pt-2 border-t border-zinc-100">
        <div className="mb-4">
          <h2 className="text-base font-bold text-zinc-900">Performance Audit</h2>
          <p className="text-zinc-500 text-sm mt-0.5">Compare forecast accuracy against actual market prices</p>
        </div>

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

        {auditLoading ? (
          <div className="h-48 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : !auditAvailable ? (
          <Card className="p-10 border-zinc-100 shadow-none">
            <div className="flex flex-col items-center gap-3 text-center">
              <WifiOff size={28} className="text-zinc-300" />
              <p className="text-zinc-500 font-medium">No audit data available</p>
              <p className="text-zinc-400 text-sm">Both forecast and actual prices are required for {days[auditDay]?.label}</p>
              <p className="text-zinc-300 text-xs">Data is available for dates where both scraping and pipeline have run</p>
            </div>
          </Card>
        ) : (
          <>
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
            <Card className="p-6 border-zinc-100 shadow-none">
              <p className="text-sm font-semibold text-zinc-700 mb-4">
                Actual vs Predicted · {days[auditDay]?.label} · {selectedMarket}
              </p>
              <ReactECharts option={auditOption} style={{ height: "320px", width: "100%" }} opts={{ renderer: "canvas" }} onChartReady={(chart) => setAuditChartInstance(chart)} />
            </Card>
          </>
        )}
      </div>
      <ExportModal
        isOpen={isExportOpen}
        onClose={() => setIsExportOpen(false)}
        defaultMarket={selectedMarket as Market}   // also fix this (see Bug 4)
        defaultDate={getTomorrow()}
        chartInstances={{
          forecast: forecastChartInstance,
          audit: auditChartInstance,
        }}
      />
    </div>
  );
}