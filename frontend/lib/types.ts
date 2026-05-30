export interface ForecastBlock {
  block: number;
  datetime_block: string;
  predicted_price: number;
  lower_ci: number;
  upper_ci: number;
  actual_price?: number;
  demand_ratio?: number;
}

export interface ForecastData {
  market: string;
  region: string;
  forecast_date: string;
  blocks: ForecastBlock[];
}

export interface UserRecord {
  id: string;
  email: string;
  role: string;
  status: string;
  organization_id: string | null;
}
