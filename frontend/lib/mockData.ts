import { ForecastBlock } from "./types";

export function generateMockForecast(market: string = "GDAM"): ForecastBlock[] {
  const multiplier = market === "GDAM" ? 1.0 : market === "DAM" ? 0.95 : 1.08;
  const blocks: ForecastBlock[] = [];

  for (let i = 1; i <= 96; i++) {
    const hour = Math.floor((i - 1) / 4);
    const minute = ((i - 1) % 4) * 15;
    let base = 3800;

    if (hour >= 6 && hour < 9) base = 7000 + Math.sin(((hour - 6) / 3) * Math.PI) * 3000;
    else if (hour >= 18 && hour < 22) base = 8500 + Math.sin(((hour - 18) / 4) * Math.PI) * 1500;
    else if (hour >= 0 && hour < 5) base = 3500 + Math.random() * 400;
    else base = 3600 + Math.random() * 800;

    base = Math.round(base * multiplier);
    const spread = Math.round(base * 0.22);
    const noise = Math.round((Math.random() - 0.5) * 150);
    const timeStr = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;

    blocks.push({
      block: i,
      datetime_block: timeStr,
      predicted_price: base + noise,
      lower_ci: base - spread,
      upper_ci: base + spread,
      actual_price: i <= 48 ? base + Math.round((Math.random() - 0.5) * spread * 0.4) : undefined,
    });
  }
  return blocks;
}

export const MOCK_REGIONS = [
  "Telangana", "Maharashtra", "Karnataka",
  "Tamil Nadu", "Andhra Pradesh", "Gujarat",
  "Rajasthan", "Uttar Pradesh",
];
