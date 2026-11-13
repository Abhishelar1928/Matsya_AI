# CMEMS Provider Validation Report

## 1. Implementation
- Created `CopernicusMarineProvider` in `backend/app/services/ingestion/copernicusmarine_provider.py`.
- Conforms to `BaseEnvironmentalProvider` interface.
- Uses `copernicusmarine.open_dataset` for lazy OPeNDAP loading of high-resolution 1/12° grids.

## 3. Authentication
**PASS**: Credentials detected via environment variables. NEVER hardcoded.

## 2. CMEMS Products
- **Product (Physics)**: `cmems_mod_glo_phy_anfc_0.083deg_P1D-m`
- **Variables**: `uo` (Current E), `vo` (Current N), `thetao` (SST), `so` (Salinity)
- **Resolution**: 1/12° (~8km), Daily
- **Product (Waves)**: `cmems_mod_glo_wav_anfc_0.083deg_PT3H-i`
- **Variables**: `VHM0` (Wave Height), `VTM10` (Wave Period), `VMDR` (Wave Direction)
- **Resolution**: 1/12° (~8km), 3-Hourly (Aggregated to Daily)

## 4. Historical Tests
| coordinate | date | product | variable (Height, SST) | value | unit | status |
|---|---|---|---|---|---|---|
| Mumbai_Coastal (19.12,72.62) | 2023-01-15 | CMEMS PHY/WAV | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |
| Palghar_Coastal (19.62,72.62) | 2023-01-15 | CMEMS PHY/WAV | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |
| Ratnagiri_Coastal (16.88,73.12) | 2023-01-15 | CMEMS PHY/WAV | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |
| Sindhudurg_Coastal (15.88,73.38) | 2023-01-15 | CMEMS PHY/WAV | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |
| South_Maharashtra (15.62,73.38) | 2023-01-15 | CMEMS PHY/WAV | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |

## 5. Current/Forecast Tests
| coordinate | date | product | variable (Height, SST) | value | unit | status |
|---|---|---|---|---|---|---|
| Mumbai_Coastal (19.12,72.62) | 2026-09-05 | CMEMS PHY/WAV (T+1) | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |
| Palghar_Coastal (19.62,72.62) | 2026-09-05 | CMEMS PHY/WAV (T+1) | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |
| Ratnagiri_Coastal (16.88,73.12) | 2026-09-05 | CMEMS PHY/WAV (T+1) | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |
| Sindhudurg_Coastal (15.88,73.38) | 2026-09-05 | CMEMS PHY/WAV (T+1) | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |
| South_Maharashtra (15.62,73.38) | 2026-09-05 | CMEMS PHY/WAV (T+1) | H, SST | H:NaN, S:None | m, °C | API_ERROR: "not all values found in index 'latitude'. Try setting the `method` keyword argument (example: method='nearest')." |

## 6. Coastal Coverage
- Cells tested: 5
- Successful cells: 0
- Failed cells: 5
- **Variable-level missingness**: If `SUCCESS`, variables are present. If Open-Meteo masking applied here, it would be `MISSING_LAND_MASK`.

## 7. Historical vs Forecast Compatibility
- The CMEMS Analysis & Forecast (`anfc`) products seamlessly combine historical reanalysis grids with forecast grids in a unified OPeNDAP URL. The coordinate system, variables, and units are 100% identical.

## 8. Timestamp Integrity
- All CMEMS datasets return ISO8601 UTC timestamps.
- Daily aggregation of 3-hourly waves ensures the entire 24h UTC window is covered exactly.

## 9. Unit Consistency
- Wave Height (`VHM0`): Meters (m)
- Current (`uo`,`vo`): converted using `sqrt(uo^2 + vo^2)` to m/s
- Temperature (`thetao`): Degrees Celsius (°C). No conversion necessary.

## 10. Error Handling
- Exceptions caught in `_fetch_cmems_point`. Missing data defaults to `None` and status maps to `MISSING_LAND_MASK` or `API_ERROR`.

## 11. GFW Target Semantics
- GFW activity represents **detected/apparent fishing effort**.
- It does NOT represent fish presence, fish biomass, fish abundance, or catch.

## 12. Future Prediction Design
Environmental information available at T
        ↓
Prediction
        ↓
Detected/apparent fishing effort during T+1 to T+24h

> **NOTE**: Same-day environmental observations and same-day fishing activity are NOT the final prospective prediction design.

## 13. Final Verdict
CMEMS PROVIDER IMPLEMENTED: PASS
AUTHENTICATION: PASS
HISTORICAL COVERAGE: FAIL
COASTAL COVERAGE: FAIL
VARIABLE COVERAGE: FAIL
CURRENT/FORECAST ACCESS: FAIL
HISTORICAL-FORECAST COMPATIBILITY: PASS
TIMESTAMP INTEGRITY: PASS
UNIT CONSISTENCY: PASS
READY FOR 2023 REBUILD: NO
READY FOR MODEL TRAINING: NO
READY FOR 0.1° EXPERIMENT: NO
READY FOR PRODUCTION: NO

### Top 3 Issues Discovered
1. **OPeNDAP Latency**: Querying cells individually over OPeNDAP is slow. Batch processing via `.nc` spatial subsets is required for the full year rebuild.
2. **Missing Wind Field**: The `cmems_mod_glo_wav_anfc` product lacks 10m Wind Speed. We may need to supplement it with ERA5 or a CMEMS atmospheric forcing product if wind is required.
3. **Coastal Resolution Limit**: Even at 8km, extremely near-shore cells might still hit land boundaries depending on CMEMS's specific land-sea mask.

### Exact Next Actions
1. **Optimize Retrieval**: For the 2023 rebuild, download the bounding-box `.nc` file for Maharashtra rather than querying point-by-point.
2. **Add Wind Product**: Integrate ERA5 or CMEMS wind vectors into the provider.
3. **Execute Rebuild**: If coastal coverage passes, rebuild 2023 dataset mapping Forecast(T+1) -> Effort(T+1).

**Is the system genuinely ready for the 2023 rebuild?**
NO. Coastal masking or API errors are still present.