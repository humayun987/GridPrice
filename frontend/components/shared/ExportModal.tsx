"use client";

import React, { useState, useCallback, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import apiClient from "@/lib/api";

// ─────────────────────── Types ───────────────────────

type ExportType = "forecast" | "historical" | "audit";
type FileFormat = "csv" | "xlsx" | "png";
export type Market = "DAM" | "GDAM" | "RTM";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Pre-fills the forecast date or the end of the range */
  defaultDate?: string;
  /** Pre-fills the market selector */
  defaultMarket?: Market;
  /** ECharts ref — required only for PNG export */
  chartInstances?: Partial<Record<ExportType, any>>;
  defaultStartDate?: string;
  defaultEndDate?: string;
}

interface ExportPayload {
  export_type: ExportType;
  market: Market;
  region: string;
  include_ci: boolean;
  export_date?: string;
  start_date?: string;
  end_date?: string;
}

// ─────────────────────── Constants ───────────────────

const ALL_MARKETS: Market[] = ["DAM", "GDAM", "RTM"];
const FORECAST_MARKET: Market = "GDAM"; // only market with ML forecasts
const MAX_DAYS = 30;
const REGION = "Telangana";

const TYPE_LABELS: Record<ExportType, string> = {
  forecast: "Forecast (D+1)",
  historical: "Historical",
  audit: "Audit",
};

const TYPE_DESCRIPTIONS: Record<ExportType, string> = {
  forecast: "Tomorrow's predicted MCP prices with CI bands. GDAM only.",
  historical: "Actual cleared prices from IEX. All markets. Date range up to 30 days.",
  audit: "Predicted vs actual side-by-side with error metrics. GDAM only. Date range up to 30 days.",
};

// ─────────────────────── Date Helpers ────────────────

const toDateStr = (d: Date) => d.toISOString().split("T")[0];

const today = () => toDateStr(new Date());

const daysAgo = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toDateStr(d);
};

const daysBetween = (start: string, end: string) => {
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  return Math.round((e - s) / 86_400_000) + 1;
};

// ─────────────────────── Error from Blob ─────────────

async function extractBlobError(err: any): Promise<string> {
  try {
    if (err?.response?.data instanceof Blob) {
      const text = await err.response.data.text();
      const json = JSON.parse(text);
      return json?.detail ?? "Export failed.";
    }
    return err?.response?.data?.detail ?? err?.message ?? "Export failed.";
  } catch {
    return "Export failed. Please try again.";
  }
}

// ─────────────────────── Component ───────────────────

export function ExportModal({
  isOpen,
  onClose,
  defaultDate,
  defaultMarket = "GDAM",
  chartInstances,
  defaultStartDate,
  defaultEndDate,
}: ExportModalProps) {
  const [exportType, setExportType] = useState<ExportType>("forecast");
  const [fileFormat, setFileFormat] = useState<FileFormat>("csv");
  const [market, setMarket] = useState<Market>(defaultMarket);
  const [exportDate, setExportDate] = useState(defaultDate ?? today());
  const [startDate, setStartDate] = useState(defaultStartDate ?? daysAgo(7));
  const [endDate, setEndDate] = useState(defaultEndDate ?? daysAgo(1));
  const [includeCi, setIncludeCi] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setError(null);
      setSuccess(false);
      setIsLoading(false);
    }
  }, [isOpen]);

  // ── Export type change ────────────────────────────────────
  const handleTypeChange = useCallback((type: ExportType) => {
    setExportType(type);
    setError(null);
    setSuccess(false);
    // Forecast and audit are GDAM-only
    if (type === "forecast" || type === "audit") {
      setMarket(FORECAST_MARKET);
    }
  }, []);

  // ── Date range validation ─────────────────────────────────
  const rangeIsMultiDay = exportType !== "forecast";
  const rangeDays = rangeIsMultiDay ? daysBetween(startDate, endDate) : 1;
  const rangeValid =
    !rangeIsMultiDay ||
    (new Date(startDate) <= new Date(endDate) && rangeDays <= MAX_DAYS);

  const rangeLabel = rangeIsMultiDay
    ? rangeDays > 0
      ? `${rangeDays} day${rangeDays !== 1 ? "s" : ""}${rangeDays > MAX_DAYS ? " — exceeds 30-day max" : ""}`
      : "Invalid range"
    : null;

  const currentChart = chartInstances?.[exportType] ?? null;
  const pngAvailable = !!currentChart;

  const pngLabel =
    exportType === "forecast"
      ? "PNG Forecast"
      : exportType === "historical"
        ? "PNG Historical"
        : "PNG Audit";

  // ── Handlers ─────────────────────────────────────────────
  const handleDownload = async () => {
    setError(null);
    setSuccess(false);

    if (!rangeValid) {
      setError(
        rangeDays > MAX_DAYS
          ? `Date range is ${rangeDays} days — maximum allowed is ${MAX_DAYS}.`
          : "Start date must be before end date."
      );
      return;
    }

    if (fileFormat === "png") {
      handlePngExport();
      return;
    }

    setIsLoading(true);
    try {
      const payload: ExportPayload = {
        export_type: exportType,
        market,
        region: REGION,
        include_ci: includeCi,
      };

      if (exportType === "forecast") {
        payload.export_date = exportDate;
      } else {
        payload.start_date = startDate;
        payload.end_date = endDate;
      }

      const endpoint =
        fileFormat === "csv" ? "/api/export/csv" : "/api/export/xlsx";

      const response = await apiClient.post(endpoint, payload, {
        responseType: "blob",
      });

      // Build filename to match backend convention
      const filename =
        exportType === "forecast"
          ? `gridprice_${market}_${REGION}_forecast_${exportDate}.${fileFormat}`
          : `gridprice_${market}_${REGION}_${exportType}_${startDate}_to_${endDate}.${fileFormat}`;

      const url = URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      setSuccess(true);
      setTimeout(onClose, 1200);
    } catch (err: any) {
      setError(await extractBlobError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handlePngExport = () => {
    if (!currentChart) {
      setError(`Chart instance not available for ${exportType} PNG export.`);
      return;
    }

    try {
      const dataUrl = currentChart.getDataURL({
        type: "png",
        pixelRatio: 2,
        backgroundColor: "#0f0f1a",
      });

      const filename =
        exportType === "forecast"
          ? `gridprice_${market}_${REGION}_forecast_${exportDate}.png`
          : `gridprice_${market}_${REGION}_${exportType}_${startDate}_to_${endDate}.png`;

      const link = document.createElement("a");
      link.href = dataUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      setSuccess(true);
      setTimeout(onClose, 1200);
    } catch {
      setError("Failed to generate PNG from chart.");
    }
  };

  // ── Render helpers ────────────────────────────────────────
  const inputCls =
    "w-full bg-[#0a0f1e] border border-[#1e3a5f] rounded-md px-3 py-2 text-white text-sm " +
    "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent " +
    "placeholder-gray-600 [color-scheme:dark]";

  const pillBtn = (active: boolean, disabled = false) =>
    [
      "flex-1 py-2 px-2 rounded-md text-xs font-semibold tracking-wide transition-all duration-150 select-none",
      active
        ? "bg-blue-600 text-white shadow-md shadow-blue-900/40"
        : "bg-[#0a0f1e] text-gray-400 border border-[#1e3a5f] hover:border-blue-700 hover:text-gray-200",
      disabled ? "opacity-40 cursor-not-allowed pointer-events-none" : "cursor-pointer",
    ].join(" ");

  return (
    <Dialog open={isOpen} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        className="sm:max-w-[500px] bg-[#0d1117] border border-[#1e3a5f] text-white p-0 overflow-hidden"
        style={{ borderRadius: "12px" }}
      >
        <div className="flex flex-col bg-[#0d1117] p-2">
          {/* ── Header ── */}
          <div className="px-6 pt-5 pb-4 border-b border-[#1e3a5f]">
            <DialogTitle className="text-white text-base font-semibold tracking-wide flex items-center gap-2">
              <span className="text-blue-400">↓</span>
              Export Data
            </DialogTitle>
            <p className="text-gray-500 text-xs mt-1">
              {TYPE_DESCRIPTIONS[exportType]}
            </p>
          </div>

          <div className="px-6 py-5 space-y-5">

            {/* ── Export Type ── */}
            <div className="space-y-2">
              <Label className="text-gray-400 text-xs font-medium uppercase tracking-widest">
                Data Type
              </Label>
              <div className="flex gap-2">
                {(Object.keys(TYPE_LABELS) as ExportType[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => handleTypeChange(t)}
                    className={pillBtn(exportType === t)}
                  >
                    {TYPE_LABELS[t]}
                  </button>
                ))}
              </div>
            </div>

            {/* ── Market ── */}
            <div className="space-y-2">
              <Label className="text-gray-400 text-xs font-medium uppercase tracking-widest">
                Market
              </Label>
              <div className="flex gap-2">
                {ALL_MARKETS.map((m) => {
                  const locked = exportType === "forecast" || exportType === "audit";
                  const isActive = market === m;
                  return (
                    <button
                      key={m}
                      onClick={() => !locked && setMarket(m)}
                      className={pillBtn(isActive, locked && !isActive)}
                      title={
                        locked && !isActive
                          ? `${exportType} export is GDAM only`
                          : undefined
                      }
                    >
                      {m}
                    </button>
                  );
                })}
              </div>
              {(exportType === "forecast" || exportType === "audit") && (
                <p className="text-xs text-amber-500/80">
                  {exportType === "forecast"
                    ? "ML forecasts run only for GDAM."
                    : "Audit requires forecast data — GDAM only."}
                </p>
              )}
            </div>

            {/* ── Date Selection ── */}
            {exportType === "forecast" ? (
              <div className="space-y-2">
                <Label className="text-gray-400 text-xs font-medium uppercase tracking-widest">
                  Forecast Date
                </Label>
                <input
                  type="date"
                  value={exportDate}
                  onChange={(e) => setExportDate(e.target.value)}
                  className={inputCls}
                />
                <p className="text-xs text-gray-600">
                  Select the date whose D+1 forecast you want to export.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <Label className="text-gray-400 text-xs font-medium uppercase tracking-widest flex items-center justify-between">
                  <span>Date Range</span>
                  <span
                    className={`font-mono font-normal normal-case ${!rangeValid || rangeDays > MAX_DAYS
                      ? "text-red-400"
                      : "text-gray-500"
                      }`}
                  >
                    {rangeLabel}
                  </span>
                </Label>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <p className="text-xs text-gray-600 mb-1">From</p>
                    <input
                      type="date"
                      value={startDate}
                      max={endDate}
                      onChange={(e) => {
                        setStartDate(e.target.value);
                        setError(null);
                      }}
                      className={inputCls}
                    />
                  </div>
                  <div className="text-gray-600 text-sm mt-4">→</div>
                  <div className="flex-1">
                    <p className="text-xs text-gray-600 mb-1">To</p>
                    <input
                      type="date"
                      value={endDate}
                      min={startDate}
                      max={today()}
                      onChange={(e) => {
                        setEndDate(e.target.value);
                        setError(null);
                      }}
                      className={inputCls}
                    />
                  </div>
                </div>
                {rangeDays > MAX_DAYS && (
                  <p className="text-xs text-red-400">
                    Reduce range by {rangeDays - MAX_DAYS} day{rangeDays - MAX_DAYS !== 1 ? "s" : ""}.
                  </p>
                )}
              </div>
            )}

            {/* ── Include CI ── */}
            {(exportType === "forecast" || exportType === "audit") && (
              <div className="flex items-center gap-3 py-1">
                <Checkbox
                  id="include-ci"
                  checked={includeCi}
                  onCheckedChange={(v) => setIncludeCi(!!v)}
                  className="border-[#1e3a5f] data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
                />
                <Label
                  htmlFor="include-ci"
                  className="text-gray-300 text-sm cursor-pointer"
                >
                  Include confidence intervals{" "}
                  <span className="text-gray-500">(P10 / P90)</span>
                </Label>
              </div>
            )}

            {/* ── Format ── */}
            <div className="space-y-2">
              <Label className="text-gray-400 text-xs font-medium uppercase tracking-widest">
                Format
              </Label>
              <div className="flex gap-2">
                {(["csv", "xlsx", "png"] as FileFormat[]).map((f) => {
                  const disabled = f === "png" && !pngAvailable;
                  return (
                    <button
                      key={f}
                      onClick={() => !disabled && setFileFormat(f)}
                      className={pillBtn(fileFormat === f, disabled)}
                      title={
                        disabled
                          ? "PNG export requires the matching chart to be visible on screen"
                          : f === "png"
                            ? `Exports the current ${exportType} chart as an image`
                            : undefined
                      }
                    >
                      {f === "png" ? pngLabel : `.${f.toUpperCase()}`}
                    </button>
                  );
                })}
              </div>
              {fileFormat === "png" && (
                <p className="text-xs text-gray-500">
                  Captures the chart currently rendered on screen at 2× resolution.
                </p>
              )}
              {fileFormat === "xlsx" && (
                <p className="text-xs text-gray-500">
                  Formatted Excel workbook with brand header and colour-coded error cells.
                </p>
              )}
            </div>

            {/* ── Error / Success ── */}
            {error && (
              <div className="flex items-start gap-2 bg-red-950/40 border border-red-800/60 rounded-md px-4 py-3 text-red-300 text-sm">
                <span className="mt-0.5 shrink-0">✕</span>
                <span>{error}</span>
              </div>
            )}
            {success && (
              <div className="flex items-center gap-2 bg-green-950/40 border border-green-700/60 rounded-md px-4 py-3 text-green-300 text-sm">
                <span>✓</span>
                <span>Download started successfully.</span>
              </div>
            )}
          </div>

          {/* ── Footer ── */}
          <DialogFooter className="bg-[#0d1117] px-6 py-4 pb-6 border-t border-[#1e3a5f] flex gap-3">
            <Button
              variant="ghost"
              onClick={onClose}
              disabled={isLoading}
              className="flex-1 text-gray-400 hover:text-white hover:bg-[#1e3a5f]/40 border border-[#1e3a5f]"
            >
              Cancel
            </Button>
            <Button
              onClick={handleDownload}
              disabled={isLoading || !rangeValid}
              className="flex-1 bg-blue-600 hover:bg-blue-500 text-white font-semibold disabled:opacity-50"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Generating…
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <span>↓</span>
                  Download .{fileFormat.toUpperCase()}
                </span>
              )}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}