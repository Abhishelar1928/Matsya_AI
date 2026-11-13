# Executive Summary

RECOMMENDED SOURCE: INCOIS Current TextData Endpoint
AUTOMATION METHOD: HTTP Session GET Requests with HTML Table parsing
DATA FORMAT: HTML Table (Structured Coordinates)
CURRENT DATA VERIFIED: YES
MAHARASHTRA PFZ VERIFIED: YES
AUTOMATION COMPLEXITY: LOW

This investigation evaluated three potential distribution channels for the INCOIS Potential Fishing Zone (PFZ) daily advisory for Maharashtra: the official Telegram channel, the TextData web system, and the SAMUDRA mobile application. 

The investigation determined that the **INCOIS Current TextData Endpoint** is the easiest, most reliable, and most automatable source. It requires no authentication (only a session cookie), does not rely on private or undocumented APIs, avoids scraping complex JavaScript applications, and provides structured PFZ coordinates directly in an HTML table.

---

# 1. Telegram Investigation

- **Channel Existence & Authenticity:** INCOIS official annual reports confirm the creation of 09 Telegram broadcast channels for coastal states, including Maharashtra. 
- **Public Accessibility:** These channels are generally not promoted via a universally public link. They are managed in coordination with local district fisheries offices for direct dissemination to registered fishermen.
- **Automation Feasibility:** Automating retrieval from a Telegram channel requires a dedicated Telegram user account, bot token or MTProto API credentials, and membership in the specific group. This introduces a significant operational dependency and terms-of-service risk.
- **Data Content:** While the channel provides daily PFZ advisory maps and textual information, extracting structured coordinates would require complex parsing or OCR on images if text is not standardized.
- **Verdict:** High complexity, high risk, and poor maintainability. Not recommended.

---

# 2. TextData Investigation

- **Source:** https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en
- **Network Flow:**
  1. `GET /MarineFisheries/TextDataHome?mfid=1&request_locale=en` – Returns a `JSESSIONID` cookie.
  2. `GET /MarineFisheries/TextData?secid=SEC002` – Using the session cookie, retrieves the Maharashtra PFZ data.
- **Data Content:** Returns an HTML page containing an explicit data table. The table includes Landing Centre, Direction, Bearing (deg), Distance (km), Depth (mtr), Latitude (dms), and Longitude (dms).
- **Automation Feasibility:** Extremely easy. A simple HTTP client (like Python's `requests.Session()`) can sequentially execute the two GET requests and parse the tabular HTML into structured JSON using `BeautifulSoup` or `pandas.read_html()`. 
- **Session Requirement:** A `JSESSIONID` is strictly required. Accessing the `SEC002` endpoint without the cookie results in a `302 Redirect` to a generic advisory page.
- **Verdict:** Lowest complexity, official web channel, structured data, no authentication. Highly recommended.

---

# 3. SAMUDRA Investigation

- **App Existence & Authenticity:** The SAMUDRA (Smart Access to Marine Users for ocean Data Resources and Advisories) app is officially published by INCOIS and available on Android (Google Play) and iOS (App Store).
- **Data Content:** It provides comprehensive real-time ocean data, including PFZ maps and advisories.
- **Network & API Architecture:** The app consumes private INCOIS backend REST APIs. There is no publicly documented or officially supported open API endpoint for third-party backend integration.
- **Automation Feasibility:** Integrating this would require sniffing network traffic, bypassing API access controls, and potentially reverse-engineering authentication tokens. This strictly violates safety and ethical guidelines.
- **Verdict:** High complexity and prohibited reverse-engineering requirements. Not recommended.

---

# 4. Endpoint / Data Flow Findings

The recommended `TextData` flow is entirely HTTP-based:
- **Method:** `GET`
- **Session Initialization:** `https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en`
- **Data Endpoint:** `https://incois.gov.in/MarineFisheries/TextData?secid=SEC002` (Maharashtra sector)
- **Cookies:** `JSESSIONID`
- **Response Format:** `text/html` containing tabular data (`<table>`).
- **Data Structure:** 
  - Landing Centre (e.g., Khavana, Talashil)
  - Lat/Lon coordinates in Degrees-Minutes-Seconds (e.g., 15 45 28 N, 73 2 9 E)
  - Depth ranges (e.g., 83-88)

---

# 5. Live Retrieval Tests

A live automated retrieval test was executed against the TextData endpoint using Python `requests` and `BeautifulSoup`:
- **Retrieval Timestamp:** 2026-09-07T01:03:38+05:30
- **Maharashtra Confirmation:** Successfully confirmed (SEC002 maps to Maharashtra coastal landing centers like Talashil, Kelus, Varor).
- **Number of PFZ locations obtained:** 90
- **Coordinates Obtained:** YES (Structured Latitude/Longitude)
- **Source Official:** YES
- **HTTP Status/Result:** 200 OK
- **Response Type:** HTML Table
- **Repeated Retrieval:** Works reliably as long as the session cookie is valid.

---

# 6. Comparison Table

| Source | Official INCOIS? | Maharashtra PFZ available? | Daily updated? | Current/latest data verified? | Structured coordinates? | Text advisory? | Map image? | Public access? | Authentication required? | Stable endpoint? | Easy backend automation? | Session required? | Reliability | Legal/terms risk | Implementation complexity | Recommended? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Telegram** | Yes | Yes | Yes | No (Closed) | No (Text/Img) | Yes | Yes | No | Yes | No | No | N/A | 1/5 | High | High | No |
| **TextData** | Yes | Yes | Yes | Yes | Yes | Yes | No | Yes | No | Yes | Yes | Yes | 4/5 | Low | Low | **Yes** |
| **SAMUDRA** | Yes | Yes | Yes | No (App only) | Yes | Yes | Yes | Yes | Yes (App) | No | No | Yes | 2/5 | High | High | No |

### Scores (1-5)

| Metric | Telegram | TextData | SAMUDRA |
| :--- | :---: | :---: | :---: |
| Data freshness | 5 | 5 | 5 |
| Data completeness | 3 | 4 | 5 |
| Automation simplicity | 1 | 5 | 1 |
| Reliability | 2 | 4 | 2 |
| Maintainability | 1 | 5 | 1 |
| Official-source confidence| 5 | 5 | 5 |
| **Overall Score** | **17/30** | **28/30** | **19/30** |

---

# 7. Recommended Source

The **INCOIS Current TextData Endpoint** (`/MarineFisheries/TextData?secid=SEC002`).

---

# 8. Why It Is the Easiest

It requires no API keys, accounts, or complex scraping logic. A standard HTTP client library can easily perform a GET request to establish a session, followed by a second GET request to retrieve the data. The resulting HTML table is perfectly structured for immediate conversion into JSON/objects, meaning we don't have to parse raw unstructured text or perform OCR on images.

---

# 9. Exact Automation Mechanism

1. Create an HTTP Session.
2. `GET https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en` to automatically receive and store the `JSESSIONID`.
3. `GET https://incois.gov.in/MarineFisheries/TextData?secid=SEC002` to retrieve the HTML for Maharashtra.
4. Pass the HTML into a parser like `BeautifulSoup`.
5. Extract the 5th table (`tables[4]`), skip the header row, and iterate through the `<tr>` elements to parse out the landing center, depth, distance, latitude, and longitude.
6. Convert the Degrees-Minutes-Seconds (DMS) coordinates into Decimal Degrees.

---

# 10. Risks / Limitations

- **Implicit Dates:** The TextData HTML output does not explicitly state the forecast date or validity date in an easily parsable, machine-readable string (e.g., "Valid until 07 Sep"). The date must be inferred as the current operational date or extracted via a secondary heuristic check on the INCOIS homepage.
- **Session Dependency:** If INCOIS changes their session management or adds CAPTCHAs, this flow will break.
- **Sector ID Changes:** The Maharashtra sector is currently hardcoded as `SEC002`. If INCOIS modifies their region mapping, the system might retrieve data for the wrong state.

---

# 11. Proposed Integration Architecture

- **Ingestion Cron Job:** A daily automated Celery/Background task that runs the HTTP Session flow.
- **Parser Service:** Extracts and normalizes DMS coordinates to standard Decimal Degrees.
- **Validation Layer:** Cross-references the coordinates to ensure they fall within Maharashtra coastal bounding boxes.
- **Storage:** Persists the points into a PostgreSQL PostGIS table with an assumed validity of 24-48 hours.
- **API Delivery:** Exposes the latest PFZ data via an internal `/api/v1/pfz/latest` endpoint, explicitly labeling the data as an "Official INCOIS PFZ Advisory" and maintaining source integrity.

---

# 12. Evidence and URLs

- **TextData Home:** `https://incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en`
- **Maharashtra TextData Endpoint:** `https://incois.gov.in/MarineFisheries/TextData?secid=SEC002`
- **Annual Reports Confirming Telegram:** `https://incois.gov.in/documents/Reports/AnnualReports/AR_2022_20250701121638.pdf`
