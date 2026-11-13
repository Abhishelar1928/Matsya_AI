# INCOIS PFZ Integration

This document outlines the architecture, data flow, and operational details of the INCOIS Potential Fishing Zone (PFZ) ingestion system.

## Official Source
The system automatically fetches daily advisory data from the official INCOIS web portals.
- **Session Init**: `https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en`
- **Maharashtra PFZ Data**: `https://incois.gov.in/MarineFisheries/TextData?secid=SEC002`

## Session Flow
INCOIS requires a strict session flow:
1. The provider initiates an HTTP GET request to `TextDataHome` to retrieve a valid `JSESSIONID` cookie.
2. The provider then requests the `TextData?secid=SEC002` endpoint, passing the `JSESSIONID`.
3. If the session is missing or invalid, INCOIS redirects the request to a generic advisory page. The provider actively rejects these redirects and marks the status as `STALE`.

## SEC002 Maharashtra Mapping
The internal sector ID `SEC002` explicitly maps to the Maharashtra coastal sector.

## Table Structure & HTML Parsing
The raw data is served as an HTML table. The provider uses `BeautifulSoup` to locate the table containing specific headers (e.g., "Landing Centre", "Direction", "Latitude (dms)"). It then extracts:
- Landing Centre
- Direction
- Bearing (deg)
- Distance (km)
- Depth (mtr)
- Latitude (dms)
- Longitude (dms)

## Coordinate Conversion
The provider utilizes a robust Degrees-Minutes-Seconds (DMS) parser to convert raw strings (e.g., `15 45 28 N`) into standard Decimal Degrees.
- All non-numeric/non-directional characters are stripped to handle malformed spacing or extraneous symbols (e.g., `15°45'28"N`).
- Coordinates are validated to ensure they fall within valid global bounds (-90 to 90, -180 to 180).
- An additional layer verifies that the coordinates fall roughly within the Maharashtra coastal region (Lat: 15-21, Lon: 72-75).

## Date & Validity Handling
INCOIS tabular text data does not reliably attach a clean machine-readable date to every row. 
- The provider applies Regex pattern matching over the HTML page text to detect formats like `DD MMM YYYY` (e.g., `07 Sep 2026`).
- If a date is discovered, it is assigned as the `advisory_date`.
- If no date is discovered, the provider strictly assigns `None` rather than assuming the `retrieval_date` represents the advisory date. This prevents Matsya AI from blindly trusting stale data.

## Freshness Rules & Protection
The provider automatically rejects data when:
- The HTTP request fails after multiple retries.
- The request is redirected (indicating an expired/invalid session).
- No JSESSIONID cookie is provided.
- The PFZ table cannot be discovered.
- The parsed coordinates are invalid or out of geographic bounds.
- All records fail validation.

## Database Schema
**Table**: `incois_pfz_advisories`
**Model**: `INCOISPFZAdvisory`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Primary key |
| `source` | String | Fixed: 'INCOIS' |
| `source_type` | String | Fixed: 'OFFICIAL_PFZ_ADVISORY' |
| `sector` | String | Fixed: 'Maharashtra' |
| `landing_centre` | String | Landing centre name |
| `direction` | String | Compass direction |
| `bearing_degrees` | Integer | Bearing angle |
| `distance_km` | String | Distance string |
| `depth_min_m` | Integer | Minimum depth |
| `depth_max_m` | Integer | Maximum depth |
| `latitude` | Float | Decimal Latitude |
| `longitude` | Float | Decimal Longitude |
| `geom` | Geometry | PostGIS POINT(lon lat) SRID 4326 |
| `advisory_date` | DateTime | Discovered date (or Null) |
| `validity_date` | DateTime | Validity date (or Null) |
| `retrieved_at` | DateTime | Timestamp of ingestion |
| `hash_id` | String | SHA256 deterministic hash |

A deterministic `hash_id` (comprising landing centre, coordinates, and advisory date) guarantees idempotent ingestion runs, preventing duplicate records.

## API Response
**Endpoint**: `GET /api/v1/pfz/latest`

Returns the most recently successfully ingested dataset:
```json
{
  "source": "INCOIS",
  "source_type": "OFFICIAL_PFZ_ADVISORY",
  "sector": "Maharashtra",
  "status": "SUCCESS",
  "advisory_date": "2026-09-07T00:00:00Z",
  "validity_date": null,
  "retrieved_at": "2026-09-07T01:30:00Z",
  "count": 90,
  "locations": [
    {
      "landing_centre": "Talashil",
      "direction": "SW",
      "bearing_degrees": 210,
      "distance_km": "25",
      "depth_min_m": 45,
      "depth_max_m": 50,
      "latitude": 15.7577,
      "longitude": 73.0358
    }
  ]
}
```

## Retry Behavior
INCOIS portals can sometimes yield `503 Service Unavailable` on rapid WFS requests. While the TextData endpoint is generally stable, the provider employs exponential backoff.
- **Max Retries**: 3
- **Backoff Time**: 5 seconds * attempt number
- **Timeout**: 30 seconds

## Known Limitations
- The internal HTML layout of `incois.gov.in` dictates the success of `BeautifulSoup` parsing. If they completely overhaul their DOM, the script must be updated.
- `SEC002` is currently hardcoded for Maharashtra. INCOIS may eventually alter their internal region mapping codes.
