# 4. Algorithms and Core Logic

This document provides a rigorous mathematical and algorithmic analysis of every computational technique implemented in the MatsyaAI Maharashtra codebase. Only algorithms verified in actual source code are included.

---

## 4.1 Summary of Implemented Algorithms

| # | Algorithm Name | Category | Primary Source File & Function | Time Complexity | Space Complexity |
| :- | :--- | :--- | :--- | :--- | :--- |
| **1** | Haversine Great-Circle Distance | Geodesy / Spatial Math | `backend/app/ml/dataset_builder.py` (`_haversine`)<br/>`backend/app/services/ml/feature_builder.py` (`_haversine_distance`) | $\mathcal{O}(1)$ | $\mathcal{O}(1)$ |
| **2** | DMS to Decimal Degrees Conversion | Geodetic Parsing | `backend/app/services/ingestion/incois_pfz_provider.py` (`parse_dms`) | $\mathcal{O}(K)$ | $\mathcal{O}(1)$ |
| **3** | Spatial Visitor PDF Kerning Reconstruction | Text Mining / Document Parsing | `backend/app/services/ingestion/imd_marine_provider.py` (`extract_structured_lines`, `_clean_token_spacing`) | $\mathcal{O}(N \log N)$ | $\mathcal{O}(N)$ |
| **4** | Meteorological Severity Classification | Rule-Based NLP / Classifier | `backend/app/services/ingestion/imd_marine_provider.py` (`classify_severity`) | $\mathcal{O}(M)$ | $\mathcal{O}(1)$ |
| **5** | Deterministic SHA-256 Batch Deduplication | Cryptographic Hashing | `backend/app/services/ingestion/incois_pfz_provider.py` (`ingest_latest_maharashtra_pfz`) | $\mathcal{O}(L)$ | $\mathcal{O}(1)$ |
| **6** | Causal Lookback Rolling-Window Feature Generation | Feature Engineering / Time Series | `ml/features/causal_dataset.py` (`build_causal_dataset`) | $\mathcal{O}(G \cdot T)$ | $\mathcal{O}(G \cdot T)$ |
| **7** | Spatial Point-in-Polygon Marine Masking & Grid Generation | Computational Geometry | `backend/scripts/generate_spatial_grid.py` (`generate_canonical_grid`)<br/>`backend/app/ml/inference.py` (`_generate_grid`) | $\mathcal{O}(P)$ | $\mathcal{O}(P)$ |
| **8** | Nearest-Neighbor Spatial Regridding | Geospatial Interpolation | `backend/app/services/ml/feature_builder.py` (`map_cmems_to_canonical`) | $\mathcal{O}(C \cdot G)$ | $\mathcal{O}(C)$ |
| **9** | Multi-Tier Safety Gate Evaluation Hierarchy | Decision Logic / Safety Protocol | `backend/app/ml/safety_gate.py` (`_determine_safety`, `apply`) | $\mathcal{O}(P \cdot W)$ | $\mathcal{O}(P)$ |
| **10** | Source-Level Freshness & Age Calculation | Temporal Auditing | `backend/app/services/freshness/source_tracker.py` (`get_all_freshness`) | $\mathcal{O}(S)$ | $\mathcal{O}(S)$ |

---

## 4.2 Detailed Algorithm Specifications

### 1. Haversine Great-Circle Distance
- **Category:** Geodesy / Geospatial Mathematics
- **Mathematical Concept:**
  Given two points on a spherical Earth of radius $R \approx 6371.0\text{ km}$, with latitudes $\phi_1, \phi_2$ and longitudes $\lambda_1, \lambda_2$ in radians:
  $$\Delta \phi = \phi_2 - \phi_1, \quad \Delta \lambda = \lambda_2 - \lambda_1$$
  $$a = \sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)$$
  $$c = 2 \cdot \text{atan2}\left(\sqrt{a}, \sqrt{1-a}\right)$$
  $$d = R \cdot c$$
- **How It Works:** Transforms degree coordinates to radians, calculates the chord length between the points along the spherical surface, and scales by Earth's mean radius.
- **Why Used:** Computes exact distance from each 0.25° marine grid cell centroid to the nearest coastal landing centre (`distance_to_coast_km`), establishing coastal proximity (`is_coastal = 1.0` if $d \le 50\text{ km}$) and fuel travel constraints.
- **Input:** `(lat1: float, lon1: float, lat2: float, lon2: float)`
- **Output:** `distance_km: float`
- **Step-by-Step Execution:**
  1. Convert latitude and longitude deltas to radians using `math.radians()`.
  2. Compute haversine formula component $a$.
  3. Compute angular distance $c$ using `math.atan2` and `math.sqrt`.
  4. Multiply $c$ by Earth radius $6371.0\text{ km}$.
- **Complexity:** Time: $\mathcal{O}(1)$, Space: $\mathcal{O}(1)$.
- **Source Code Location:**
  - `backend/app/ml/dataset_builder.py` (lines 44–58)
  - `backend/app/services/ml/feature_builder.py` (lines 50–57)

---

### 2. DMS to Decimal Degrees Coordinate Conversion
- **Category:** Geodetic String Parsing & Normalization
- **Mathematical Concept:**
  $$\text{Decimal Degrees} = \text{Degrees} + \frac{\text{Minutes}}{60} + \frac{\text{Seconds}}{3600}$$
  If cardinal direction is South ('S') or West ('W'):
  $$\text{Decimal Degrees} = -1 \cdot \text{Decimal Degrees}$$
- **How It Works:** Extracts numeric degree, minute, and second tokens from unstructured government HTML strings (e.g., `'15 45 28 N'`, `'15°45\'28"N'`, `'71 56 39 E'`), accommodates prefix or suffix cardinal letters, computes fractional degrees, and applies polarity.
- **Why Used:** INCOIS PFZ bulletins publish coordinates in varied legacy human-readable DMS notation. This algorithm normalizes them into standard WGS-84 decimal coordinates for PostGIS geometry creation.
- **Input:** Raw string `dms_str` (e.g., `"15 45 28 N"`)
- **Output:** `Optional[float]` in range $[-180.0, 180.0]$
- **Step-by-Step Execution:**
  1. Pad cardinal letters `[NSEW]` with spaces using regex `re.sub(r'([NSEWnsew])', r' \1 ', dms_str)`.
  2. Strip non-alphanumeric symbols using `re.sub(r'[^0-9NSEWnsew\. ]', ' ', clean_str)`.
  3. Split into whitespace tokens. Verify at least 4 tokens exist.
  4. Identify cardinal direction token (whether located at index 0 or index 3).
  5. Parse degree, minute, and second floats.
  6. Apply conversion formula and invert sign for South/West.
- **Complexity:** Time: $\mathcal{O}(K)$ where $K$ is string length ($\le 50$ chars), Space: $\mathcal{O}(1)$.
- **Source Code Location:**
  - `backend/app/services/ingestion/incois_pfz_provider.py` (lines 140–184)

---

### 3. Spatial Visitor PDF Kerning Reconstruction & Line Sorting
- **Category:** Document Parsing & Computational Typography
- **Mathematical Concept:** 2D Cartesian transformation matrix coordinate extraction:
  In PDF rendering, text transformation matrix $tm$ yields coordinates:
  $$x = tm[4], \quad y = tm[5]$$
  Sorting elements by primary vertical position $y$ and secondary horizontal position $x$:
  $$\text{key} = (\text{round}(y, 1), \text{round}(x, 1))$$
- **How It Works:** When extracting text from IMD's `fisherman.pdf`, font kerning causes single characters to be printed as isolated tokens separated by tabs or spaces (e.g., `"T h u r s d a y"`). The algorithm intercepts text chunks with their physical page $(x, y)$ coordinates via PyPDF2's `visitor_text` callback, sorts lines in reading order, and iteratively collapses kerned character tokens using regular expressions.
- **Why Used:** Standard PyPDF2 `extract_text()` outputs unreadable fragmented tokens that break regex matchers for dates, wind speeds, and coastal warning headers.
- **Input:** Raw PDF bytes `pdf_bytes`
- **Output:** Ordered, cleaned list of plain-text lines `List[str]`
- **Step-by-Step Execution:**
  1. Instantiate `PyPDF2.PdfReader`.
  2. For each page, register a visitor callback that captures text alongside matrix coordinates $tm[5]$ (vertical $y$) and $tm[4]$ (horizontal $x$).
  3. Sort collected elements top-to-bottom by $y$ coordinate.
  4. Group elements within vertical distance $\Delta y \le 5\text{ pt}$ into single lines.
  5. Sort horizontal chunks within each line by $x$ coordinate.
  6. Execute `_clean_token_spacing` iteratively: `re.sub(r'(?<=[A-Za-z0-9])[\t ](?=[A-Za-z0-9])', '', s)` until string stabilizes.
- **Complexity:** Time: $\mathcal{O}(N \log N)$ where $N$ is text chunk count per page, Space: $\mathcal{O}(N)$.
- **Source Code Location:**
  - `backend/app/services/ingestion/imd_marine_provider.py` (lines 127–182)

---

### 4. IMD Meteorological Bulletin Text Classification
- **Category:** Rule-Based Natural Language Classification
- **How It Works:** Maps unstructured advisory text across 7 coastal and high-sea bulletin sections into discrete safety classifications: `NORMAL`, `WARNING`, or `SEVERE`.
- **Classification Rules:**
  - `NORMAL`: Explicit match for `"nil"`, `"nil."`, `"normal"`, `"no warning"`.
  - `SEVERE`: Detected keywords: `"cyclon"`, `"gale"`, `"extremely severe"`, `"very severe"`, `"super cyclon"`, `"storm surge"`, `"hurricane"`, `"typhoon"`, OR sustained wind speeds $\ge 65\text{ kmph}$ with gusts $\ge 75\text{ kmph}$.
  - `WARNING`: Advisory keywords: `"squall"`, `"rough"`, `"warning"`, `"advised not to venture"`, `"gusting"`, `"caution"`, `"alert"`.
- **Why Used:** Distinguishes calm ocean conditions from advisory-level squalls and life-threatening cyclonic storms to drive the independent Safety Gate.
- **Input:** Cleaned section text string
- **Output:** String (`"NORMAL"`, `"WARNING"`, `"SEVERE"`)
- **Complexity:** Time: $\mathcal{O}(M)$ where $M$ is string length, Space: $\mathcal{O}(1)$.
- **Source Code Location:**
  - `backend/app/services/ingestion/imd_marine_provider.py` (lines 248–285)

---

### 5. Deterministic SHA-256 Batch Ingestion Deduplication
- **Category:** Cryptographic Hash-Based Idempotency
- **Mathematical Concept:**
  $$\text{Hash}_{\text{batch}} = \text{SHA256}\left(\text{"SEC002"} \parallel T_{\text{advisory}} \parallel T_{\text{validity}} \parallel \sum_{i=1}^N \left(\text{lat}_i \parallel \text{lon}_i\right)\right)$$
- **How It Works:** Concatenates sector code, advisory dates, and formatted coordinate strings into a canonical string. Calculates a 64-character hexadecimal SHA-256 digest. Checks the database for the existence of `hash_id = SHA256(Hash_batch || "_0")`. If found, skips insertion.
- **Why Used:** The ingestion daemon runs periodically (hourly/daily). Deduplication prevents table bloat and preserves referential integrity without relying on artificial auto-increment keys.
- **Input:** Extracted advisory records and timestamps
- **Output:** Hexadecimal hash string `str` (64 characters)
- **Complexity:** Time: $\mathcal{O}(L)$ where $L$ is total payload string length, Space: $\mathcal{O}(1)$.
- **Source Code Location:**
  - `backend/app/services/ingestion/incois_pfz_provider.py` (lines 520–534)

---

### 6. Causal Lookback Rolling-Window Feature Generation
- **Category:** Time-Series Feature Engineering / Causal Inference
- **Mathematical Concept:**
  Let $E_{i, t}$ represent apparent fishing hours in grid cell $i$ on date $t$. For prediction made at date $T$ predicting target $Y_{i, T} = \mathbf{1}(E_{i, T+1} > 1.0\text{ h})$:
  - **Lags:** $E_{i, T}, E_{i, T-1}, E_{i, T-2}, E_{i, T-3}$
  - **Trailing 7-Day Mean:** $\mu_{7}(i, T) = \frac{1}{7}\sum_{k=0}^6 E_{i, T-k}$
  - **Trailing 7-Day Max:** $\max_{7}(i, T) = \max_{k \in [0, 6]} E_{i, T-k}$
  - **Trailing 7-Day Standard Deviation:** $\sigma_{7}(i, T) = \sqrt{\frac{1}{7}\sum_{k=0}^6 \left(E_{i, T-k} - \mu_7\right)^2}$
  - **Trailing 7-Day Active Frequency:** $f_{7}(i, T) = \frac{1}{7}\sum_{k=0}^6 \mathbf{1}(E_{i, T-k} > 0)$
  - **Trailing 14-Day Mean:** $\mu_{14}(i, T) = \frac{1}{14}\sum_{k=0}^{13} E_{i, T-k}$
  - **Regional Fleet Effort at $T$:** $R_T = \sum_{j \in \text{All Cells}} E_{j, T}$
  - **Cyclical Day-of-Year Encoding:**
    $$\sin_{\text{doy}} = \sin\left(\frac{2\pi \cdot \text{DOY}}{365.25}\right), \quad \cos_{\text{doy}} = \cos\left(\frac{2\pi \cdot \text{DOY}}{365.25}\right)$$
- **Strict Anti-Leakage Invariant:**
  $$\forall \text{ features } f, \quad \text{temporal\_index}(f) \le T < T+1 = \text{target\_date}$$
- **Why Used:** Solves temporal leakage in fisheries forecasting. Proved zero future contamination by automated test suite (`ml/evaluation/leakage_validator.py`).
- **Input:** Chronologically sorted daily observations per grid cell
- **Output:** Feature DataFrame with 29 aligned predictor columns
- **Complexity:** Time: $\mathcal{O}(G \cdot T)$ where $G$ is cell count (171) and $T$ is time steps (350), Space: $\mathcal{O}(G \cdot T)$.
- **Source Code Location:**
  - `ml/features/causal_dataset.py` (lines 28–252)

---

### 7. Point-in-Polygon Marine Masking & Grid Generation
- **Category:** Computational Geometry / Spatial Indexing
- **How It Works:** Generates bounding polygons across the bounding box ($[15.50^\circ\text{N}, 20.00^\circ\text{N}] \times [72.00^\circ\text{E}, 74.00^\circ\text{E}]$) at step resolution $\Delta = 0.25^\circ$. Evaluates centroid and all four polygon corners using `global_land_mask.globe.is_ocean(lat, lon)`. A cell is classified as a valid marine cell if any evaluated coordinate lies in ocean waters.
- **Why Used:** Filters out Western Ghats / inland landmass points, producing the exact 171 canonical marine cells covering Maharashtra's coastal waters.
- **Input:** Min/Max Lat, Min/Max Lon, Resolution $\Delta$
- **Output:** List of 171 marine grid dictionaries with centroids and coastal distances
- **Complexity:** Time: $\mathcal{O}(P)$ where $P = \frac{\Delta \text{Lat}}{\text{res}} \times \frac{\Delta \text{Lon}}{\text{res}}$ point tests, Space: $\mathcal{O}(P)$.
- **Source Code Location:**
  - `backend/app/ml/inference.py` (lines 116–151)
  - `backend/scripts/generate_spatial_grid.py` (lines 28–58)

---

### 8. Nearest-Neighbor Spatial Regridding
- **Category:** Geospatial Data Resampling
- **Mathematical Concept:**
  $$\text{cell}^*(i) = \arg\min_{c \in \text{Grid}} \mathcal{H}\left(\text{lat}_{\text{obs}}, \text{lon}_{\text{obs}}, \text{lat}_c, \text{lon}_c\right)$$
  where $\mathcal{H}$ is the Haversine distance.
- **How It Works:** Ingests native environmental data from external models with native grids (e.g., Copernicus 0.083° physics or Open-Meteo 0.08° wave grid). For each canonical grid cell, finds the closest external observation point and maps its physical parameters. Enforces temporal availability: $\text{source\_publication\_time} \le T$.
- **Why Used:** Harmonizes disparate external coordinate grids into the single standardized 0.25° canonical prediction grid.
- **Input:** Native observation array, canonical grid definition, prediction epoch $T$
- **Output:** Regridded feature vectors with strict provenance timestamps
- **Complexity:** Time: $\mathcal{O}(C \cdot G)$ where $C$ is external point count and $G$ is canonical cell count (171), Space: $\mathcal{O}(C)$.
- **Source Code Location:**
  - `backend/app/services/ml/feature_builder.py` (lines 70–120)

---

### 9. Multi-Tier Independent Safety Gate Evaluation
- **Category:** Rule-Based Decision Logic / Safety Protocol
- **Priority Hierarchy:**
  ```
  Tier 1: Restricted Zone Check (BLOCKED)
      ↓
  Tier 2: Active Severe Warning Check (UNSAFE)
      ↓
  Tier 3: Environmental Thresholds / Active Caution (CAUTION)
      ↓
  Tier 4: Authoritative Bulletin Confirms Normal (SAFE_CONFIRMED)
      ↓
  Tier 5: Fallthrough / Missing / Stale Warning Feed (NO_WARNING_DATA)
  ```
- **Mathematical Logic:**
  $$\text{Safety}(i) = \begin{cases}
  \text{UNSAFE}, & \text{if } \exists w \in W_{\text{active}} \mid \text{severity}(w) \in \{\text{SEVERE}\} \\
  \text{CAUTION}, & \text{if } \exists w \in W_{\text{active}} \mid \text{severity}(w) \in \{\text{WARNING}, \text{CAUTION}\} \\
  & \lor \left(\text{WaveHeight}_i > 4.0\text{ m}\right) \lor \left(\text{WindSpeed}_i > 50.0\text{ km/h}\right) \\
  \text{SAFE\_CONFIRMED}, & \text{if } \exists w \in W_{\text{active}} \mid \text{severity}(w) \in \{\text{NORMAL}, \text{NIL}\} \\
  & \land \left(\text{WaveHeight}_i \le 4.0\text{ m}\right) \land \left(\text{WindSpeed}_i \le 50.0\text{ km/h}\right) \\
  \text{NO\_WARNING\_DATA}, & \text{otherwise (warning feed missing, expired, or stale)}
  \end{cases}$$
- **Invariant:** The ML model output $\hat{P}(\text{Effort})$ **never** enters the safety function. A high prediction probability ($0.95$) inside a storm sector yields `UNSAFE` with `safety_override = True`.
- **Complexity:** Time: $\mathcal{O}(P \cdot W)$ where $P$ is cell count (171) and $W$ is active warnings count, Space: $\mathcal{O}(P)$.
- **Source Code Location:**
  - `backend/app/ml/safety_gate.py` (lines 46–151)

---

### 10. Source Freshness & Latency Age Calculation
- **Category:** Auditing & Observability
- **Mathematical Concept:**
  $$\text{Age}_{\text{minutes}} = \frac{T_{\text{now}} - T_{\text{actual\_data}}}{60}$$
  $$\text{Status} = \begin{cases}
  \text{LIVE}, & \text{if } T_{\text{now}} \le T_{\text{valid\_until}} \text{ (or } \text{Age} \le \text{Threshold}) \\
  \text{STALE}, & \text{if } T_{\text{now}} > T_{\text{valid\_until}} \\
  \text{CACHED\_HISTORICAL}, & \text{for GFW (due to inherent AIS archival publication latency)} \\
  \text{UNAVAILABLE}, & \text{if record count} = 0 \lor \text{fetch error}
  \end{cases}$$
- **How It Works:** Evaluates database state for each authoritative provider. Compares current UTC time against the actual publication or validity timestamps extracted from the bulletins. Computes real latency in minutes or days.
- **Why Used:** Prevents dangerous "false fresh" labels where an ingestion script successfully downloads a stale 3-day-old bulletin and flags it as current based on download time.
- **Complexity:** Time: $\mathcal{O}(S)$ where $S$ is tracked sources count (4), Space: $\mathcal{O}(S)$.
- **Source Code Location:**
  - `backend/app/services/freshness/source_tracker.py` (lines 43–470)
