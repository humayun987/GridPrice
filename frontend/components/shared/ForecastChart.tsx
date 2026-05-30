"use client";

import dynamic from "next/dynamic";
import { ForecastBlock } from "@/lib/types";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

interface Props {
  data: ForecastBlock[];
  showCI?: boolean;
  showHistorical?: boolean;
  title?: string;
  height?: string;
}

export default function ForecastChart({ data, showCI = true, showHistorical = true, title = "", height = "420px" }: Props) {
  if (!data.length) return null;

  const blocks = data.map((d) => d.block);
  const predicted = data.map((d) => d.predicted_price);
  const lowerCI = data.map((d) => d.lower_ci);
  const ciDiff = data.map((d) => d.upper_ci - d.lower_ci);
  const actual = data.map((d) => d.actual_price ?? null);

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      backgroundColor: "#18181b",
      borderColor: "#27272a",
      textStyle: { color: "#fff", fontSize: 12 },
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex;
        const d = data[idx];
        if (!d) return "";
        const fmt = (v: number) => `\u20B9${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
        let html = `<div style="font-weight:600;margin-bottom:6px">Block ${d.block} &nbsp;·&nbsp; ${d.datetime_block}</div>`;
        html += `<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="width:10px;height:10px;border-radius:50%;background:#10b981;display:inline-block"></span><span style="color:#a1a1aa">P50 Forecast:</span><span style="font-weight:600">${fmt(d.predicted_price)}</span></div>`;
        if (showCI) {
          html += `<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="width:10px;height:10px;border-radius:2px;background:rgba(161,161,170,0.4);display:inline-block"></span><span style="color:#a1a1aa">P90 Upper:</span><span style="font-weight:600">${fmt(d.upper_ci)}</span></div>`;
          html += `<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="width:10px;height:10px;border-radius:2px;background:rgba(161,161,170,0.4);display:inline-block"></span><span style="color:#a1a1aa">P10 Lower:</span><span style="font-weight:600">${fmt(d.lower_ci)}</span></div>`;
        }
        if (showHistorical && d.actual_price != null) {
          html += `<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><span style="width:10px;height:10px;border-radius:50%;background:#27272a;display:inline-block"></span><span style="color:#a1a1aa">Actual:</span><span style="font-weight:600">${fmt(d.actual_price)}</span></div>`;
        }
        return html;
      },
    },
    legend: {
      bottom: 0,
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { color: "#71717a", fontSize: 12 },
    },
    grid: { top: 20, left: 70, right: 30, bottom: 75 },
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
        },
        {
          name: "P90 (Upper Band)",
          type: "line",
          data: ciDiff,
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(161,161,170,0.18)" },
          stack: "ci",
          symbol: "none",
        },
        {
          name: "P10 (Lower Band)",
          type: "line",
          data: lowerCI,
          lineStyle: { color: "#a1a1aa", width: 1, type: "dashed" },
          symbol: "none",
        },
      ] : []),
      ...(showHistorical ? [
        {
          name: "Actual Price",
          type: "line",
          data: actual,
          lineStyle: { color: "#27272a", width: 2 },
          itemStyle: { color: "#27272a" },
          symbol: "circle",
          symbolSize: 4,
          connectNulls: false,
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
        z: 10,
      },
    ],
  };

  return (
    <div>
      {title && <p className="text-sm font-semibold text-zinc-700 mb-4">{title}</p>}
      <ReactECharts option={option} style={{ height, width: "100%" }} opts={{ renderer: "canvas" }} />
    </div>
  );
}
