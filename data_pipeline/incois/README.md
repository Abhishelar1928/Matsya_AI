# Data Pipeline — INCOIS

Ingestion workers for INCOIS oceanographic data.

## Planned Providers

- **INCOISOceanProvider**: SST, Chlorophyll, SST Anomaly, Wind, Wave, Currents
- **INCOISPFZProvider**: Potential Fishing Zone data

## Status

🔲 Not yet implemented (Milestone 3)

## Notes

- INCOIS ERDDAP should be used for programmatic access where applicable
- Geographic and temporal subsetting must be used to avoid downloading global datasets
- PFZ access mechanism must be verified before production integration
