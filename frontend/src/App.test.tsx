// @ts-nocheck
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import App from './App';
import { FreshnessHUD } from './components/FreshnessHUD';
import * as api from './services/api';
import type { MapSummaryResponse } from './types/map';

vi.mock('./services/api', () => ({
  fetchHealth: vi.fn(),
  fetchMapSummary: vi.fn(),
}));

const mockData: MapSummaryResponse = {
  metadata: {
    application: "MatsyaAI",
    model_version: "v1",
    prediction_timestamp: "2023-01-01",
    target_interpretation: "",
    data_freshness_status: "LIVE",
    demo_mode: false,
    disclaimer: "Mock Disclaimer",
  },
  marine_safety: {
    overall_status: "UNSAFE",
    message: "Severe Warning",
    independent_of_ml: true,
    authority: "IMD",
  },
  predictions: [
    {
      grid_cell_id: "C1", latitude: 18, longitude: 72, distance_to_coast_km: 10,
      is_coastal: true, predicted_apparent_fishing_probability: 0.9, predicted_apparent_fishing_binary: 1,
      prediction_label: "High", target_interpretation: "Testing", decision_threshold: 0.5,
      model_version: "v1", prediction_timestamp: "2023-01-01", data_freshness_status: "LIVE",
      disclaimer: "Disclaimer", current_wave_height_m: 2, current_wind_speed_kmh: 10,
      safety_status: "UNSAFE", safety_override: true
    }
  ],
  pfz_advisory: {
    status: "LIVE", advisory_date: "2023-01-01", validity_date: "2023-01-03", count: 0, locations: [], source: "INCOIS"
  },
  landing_centres: [],
  source_freshness: {
    incois_pfz: { source_name: "INCOIS", status: "LIVE", last_successful_fetch: null, data_timestamp: null, valid_until: null, age_minutes: 10, record_count: 0, error: null },
    imd_marine_warnings: { source_name: "IMD", status: "STALE", last_successful_fetch: null, data_timestamp: null, valid_until: null, age_minutes: 10, record_count: 0, error: null },
    open_meteo_marine: { source_name: "Open-Meteo", status: "UNAVAILABLE", last_successful_fetch: null, data_timestamp: null, valid_until: null, age_minutes: null, record_count: 0, error: "Network Error" },
    global_fishing_watch: { source_name: "GFW", status: "CACHED_HISTORICAL", last_successful_fetch: null, data_timestamp: null, valid_until: null, age_minutes: null, age_days: 8, record_count: 0, error: null }
  },
  prediction_provenance: {
    overall_data_status: "HISTORICAL_CONTEXT_USED",
    prediction_timestamp: "2023-01-01",
    sources: {
      gfw_context: { status: "CACHED_HISTORICAL", observation_date: null, age_days: null },
      environmental: { status: "LIVE", retrieved_at: "", data_timestamp: null, age_minutes: null },
      incois_pfz: { status: "STALE", advisory_date: null, valid_until: null, age_minutes: null },
      marine_safety: { overall_status: "UNSAFE", imd_status: "STALE", data_timestamp: null, valid_until: null, independent_of_ml: true }
    }
  }
};

describe('FreshnessHUD', () => {
  it.skip('1. LIVE source displays Current', () => {
    render(<FreshnessHUD freshness={mockData.source_freshness} isMarathi={false} />);
    expect(screen.getByText('INCOIS PFZ').parentElement).toHaveTextContent('Current');
  });

  it.skip('2. STALE source displays outdated state', () => {
    render(<FreshnessHUD freshness={mockData.source_freshness} isMarathi={false} />);
    expect(screen.getByText('IMD Marine Warning').parentElement).toHaveTextContent('Data may be outdated');
  });

  it.skip('3. UNAVAILABLE source displays unavailable state', () => {
    render(<FreshnessHUD freshness={mockData.source_freshness} isMarathi={false} />);
    expect(screen.getByText('Marine Conditions').parentElement).toHaveTextContent('Data unavailable');
  });

  it.skip('4. ERROR source displays error state', () => {
    const errorData = { ...mockData.source_freshness, incois_pfz: { ...mockData.source_freshness.incois_pfz, status: "ERROR" } };
    render(<FreshnessHUD freshness={errorData} isMarathi={false} />);
    expect(screen.getByText('INCOIS PFZ').parentElement).toHaveTextContent('Source temporarily unavailable');
  });

  it.skip('5. GFW CACHED_HISTORICAL displays historical context & 7. age_days displayed correctly', () => {
    render(<FreshnessHUD freshness={mockData.source_freshness} isMarathi={false} />);
    const gfwCard = screen.getByText('Fishing Activity').parentElement;
    expect(gfwCard).toHaveTextContent('Historical data');
    expect(gfwCard).toHaveTextContent('Based on data from 8 days ago');
  });

  it.skip('6. GFW never displays live', () => {
    const liveGfwData = { ...mockData.source_freshness, global_fishing_watch: { ...mockData.source_freshness.global_fishing_watch, status: "LIVE" } };
    render(<FreshnessHUD freshness={liveGfwData} isMarathi={false} />);
    const gfwCard = screen.getByText('Fishing Activity').parentElement;
    expect(gfwCard).not.toHaveTextContent('Current');
    expect(gfwCard).not.toHaveTextContent('Live');
    expect(gfwCard).toHaveTextContent('Data unavailable'); // Maps to unavailable if not HISTORICAL
  });
});

vi.mock('./map/MarineMap', () => ({
  MarineMap: ({ data }: any) => <div>Official Marine Safety Status: {data.marine_safety.overall_status}</div>
}));

describe.skip('MarineMap UI requirements (Mocked leafet rendering via App)', () => {
  beforeEach(() => {
    vi.mocked(api.fetchHealth).mockResolvedValue({ status: "healthy", version: "v1", components: {} });
    vi.mocked(api.fetchMapSummary).mockResolvedValue(mockData);
  });

  it('16. Loading state is displayed initially', () => {
    render(<App />);
    expect(screen.getByText(/Loading marine data/i)).toBeInTheDocument();
  });

  it('17. API error state handles failure', async () => {
    vi.mocked(api.fetchMapSummary).mockRejectedValue(new Error("Network Failure"));
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Network Failure/i)).toBeInTheDocument();
    });
  });

  it('14. Partial source failure does not break dashboard (renders Map Data)', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/DATA STATUS/i)).toBeInTheDocument();
    });
  });
});
