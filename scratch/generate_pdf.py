import os
import re
import markdown
import subprocess
import time

DOCS_DIR = r"D:\Matsya_AI\documentation"
OUTPUT_MD = r"D:\Matsya_AI\PROJECT_TECHNICAL_DOCUMENTATION.md"
OUTPUT_HTML = r"D:\Matsya_AI\scratch\documentation_render.html"
OUTPUT_PDF = r"D:\Matsya_AI\MatsyaAI_Technical_Documentation.pdf"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

DOCS_ORDER = [
    ("1. Project Overview", "PROJECT_OVERVIEW.md"),
    ("2. Technology Stack Analysis", "TECHNOLOGY_STACK.md"),
    ("3. System Architecture", "SYSTEM_ARCHITECTURE.md"),
    ("4. Algorithms and Core Logic", "ALGORITHMS_AND_LOGIC.md"),
    ("5. Database Analysis and Design", "DATABASE_DESIGN.md"),
    ("6. API Documentation", "API_DOCUMENTATION.md"),
    ("7. Project Folder Structure", "FOLDER_STRUCTURE.md"),
    ("8. Feature-by-Feature Technical Explanation", "FEATURE_IMPLEMENTATION.md"),
    ("9. Security Analysis", "SECURITY_ANALYSIS.md"),
    ("10. Installation and Execution Guide", "INSTALLATION_GUIDE.md"),
    ("11. Testing, Performance, and Observability", "TESTING_AND_PERFORMANCE.md"),
    ("12. Technical Strengths and Improvement Recommendations", "IMPROVEMENT_RECOMMENDATIONS.md"),
]

def build_consolidated_markdown():
    print("Building consolidated master markdown...")
    header = """# MatsyaAI Maharashtra — Comprehensive Technical Documentation

> **Role & Perspective:** Senior Software Architect, Full-Stack Developer, and Technical Documentation Engineer  
> **Target Project:** MatsyaAI Maharashtra (Marine Decision-Support & Fishing Activity Forecast Platform)  
> **Repository Root:** `D:\\Matsya_AI\\`  
> **Document Status:** Complete Consolidated Master Technical Specification  
> **Evaluation & Baseline Date:** 2026-11-13  

---

# Table of Contents
1. [Project Overview](#1-project-overview)
2. [Technology Stack Analysis](#2-technology-stack-analysis)
3. [System Architecture](#3-system-architecture)
4. [Algorithms and Core Logic](#4-algorithms-and-core-logic)
5. [Database Analysis and Design](#5-database-analysis-and-design)
6. [API Documentation](#6-api-documentation)
7. [Project Folder Structure](#7-project-folder-structure)
8. [Feature-by-Feature Technical Explanation](#8-feature-by-feature-technical-explanation)
9. [Security Analysis](#9-security-analysis)
10. [Installation and Execution Guide](#10-installation-and-execution-guide)
11. [Testing, Performance, and Observability](#11-testing-performance-and-observability)
12. [Technical Strengths and Improvement Recommendations](#12-technical-strengths-and-improvement-recommendations)

---
"""
    sections = [header]
    for title, fname in DOCS_ORDER:
        fpath = os.path.join(DOCS_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                # Remove redundant leading title if it matches # 1. etc.
                sections.append(f"\n\n---\n\n{content}")
        else:
            print(f"Warning: File {fpath} not found.")

    full_md = "".join(sections)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(full_md)
    print(f"Consolidated markdown written to {OUTPUT_MD} ({len(full_md)} characters)")
    return full_md

def convert_md_to_html(md_text):
    print("Converting Markdown to rich HTML...")
    # Convert markdown to html using python-markdown extensions
    html_content = markdown.markdown(
        md_text,
        extensions=[
            "extra",
            "tables",
            "fenced_code",
            "toc",
            "nl2br",
            "sane_lists"
        ]
    )

    # Transform <pre><code class="language-mermaid"> into <div class="mermaid">
    html_content = re.sub(
        r'<pre><code class="language-mermaid">([\s\S]*?)</code></pre>',
        r'<div class="mermaid">\1</div>',
        html_content
    )

    # HTML Document Wrapper with KaTeX, Mermaid.js, and Print CSS
    template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>MatsyaAI Maharashtra — Comprehensive Technical Documentation</title>
  
  <!-- KaTeX for LaTeX Math rendering -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"></script>

  <!-- Mermaid.js for Architecture & Flowchart Diagrams -->
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>

  <style>
    @page {{
      size: A4 portrait;
      margin: 18mm 16mm 18mm 16mm;
      @bottom-right {{
        content: counter(page);
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-size: 9pt;
        color: #64748b;
      }}
      @bottom-left {{
        content: "MatsyaAI Maharashtra — Technical Specification";
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-size: 9pt;
        color: #64748b;
      }}
    }}

    body {{
      font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Inter', Roboto, Helvetica, Arial, sans-serif;
      font-size: 10pt;
      line-height: 1.55;
      color: #1e293b;
      background: #ffffff;
      margin: 0;
      padding: 0;
    }}

    /* Cover Page */
    .cover-page {{
      text-align: center;
      padding: 120px 20px 80px 20px;
      page-break-after: always;
    }}
    .cover-icon {{
      font-size: 64pt;
      margin-bottom: 10px;
    }}
    .cover-title {{
      font-size: 30pt;
      font-weight: 900;
      color: #0369a1;
      margin: 0 0 10px 0;
      letter-spacing: -0.5px;
    }}
    .cover-subtitle {{
      font-size: 15pt;
      font-weight: 600;
      color: #0284c7;
      margin: 0 0 35px 0;
    }}
    .cover-desc {{
      font-size: 11pt;
      color: #475569;
      max-width: 650px;
      margin: 0 auto 50px auto;
      line-height: 1.6;
    }}
    .cover-meta {{
      display: inline-block;
      text-align: left;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 18px 28px;
      font-size: 10pt;
      color: #334155;
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
    }}
    .cover-meta div {{
      margin: 6px 0;
    }}
    .cover-meta strong {{
      color: #0f172a;
    }}

    /* Section Headings */
    h1 {{
      font-size: 20pt;
      font-weight: 800;
      color: #0369a1;
      border-bottom: 2px solid #0284c7;
      padding-bottom: 6px;
      margin-top: 36px;
      margin-bottom: 16px;
      page-break-before: always;
      page-break-after: avoid;
    }}
    .cover-page h1 {{
      page-break-before: avoid;
    }}
    h2 {{
      font-size: 14pt;
      font-weight: 700;
      color: #0f172a;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 4px;
      margin-top: 24px;
      margin-bottom: 12px;
      page-break-after: avoid;
    }}
    h3 {{
      font-size: 12pt;
      font-weight: 700;
      color: #1e293b;
      margin-top: 18px;
      margin-bottom: 8px;
      page-break-after: avoid;
    }}
    h4 {{
      font-size: 10.5pt;
      font-weight: 600;
      color: #334155;
      margin-top: 14px;
      margin-bottom: 6px;
      page-break-after: avoid;
    }}

    /* Paragraphs and Text */
    p {{
      margin-top: 0;
      margin-bottom: 10px;
      text-align: justify;
    }}

    /* Blockquotes */
    blockquote {{
      margin: 14px 0;
      padding: 10px 16px;
      background: #f0f9ff;
      border-left: 4px solid #0284c7;
      color: #0369a1;
      font-size: 9.5pt;
      border-radius: 0 6px 6px 0;
    }}
    blockquote p:last-child {{
      margin-bottom: 0;
    }}

    /* Tables */
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0;
      font-size: 8.5pt;
      page-break-inside: avoid;
    }}
    th {{
      background: #f1f5f9;
      color: #0f172a;
      font-weight: 700;
      text-align: left;
      padding: 8px 10px;
      border: 1px solid #cbd5e1;
    }}
    td {{
      padding: 6px 10px;
      border: 1px solid #e2e8f0;
      vertical-align: top;
    }}
    tr:nth-child(even) td {{
      background: #f8fafc;
    }}

    /* Code Blocks */
    pre {{
      background: #0f172a;
      color: #e2e8f0;
      padding: 12px 14px;
      border-radius: 6px;
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 8pt;
      line-height: 1.45;
      overflow-x: auto;
      margin: 14px 0;
      page-break-inside: avoid;
    }}
    code {{
      font-family: 'Consolas', 'Courier New', monospace;
      font-size: 8.5pt;
      background: #f1f5f9;
      color: #0f172a;
      padding: 2px 5px;
      border-radius: 4px;
      border: 1px solid #e2e8f0;
    }}
    pre code {{
      background: transparent;
      color: inherit;
      padding: 0;
      border: none;
      font-size: 8pt;
    }}

    /* Mermaid Diagrams */
    .mermaid {{
      text-align: center;
      margin: 20px auto;
      background: #ffffff;
      padding: 12px;
      border-radius: 8px;
      border: 1px solid #e2e8f0;
      page-break-inside: avoid;
      max-width: 95%;
    }}
    .mermaid svg {{
      max-height: 480px !important;
      width: auto !important;
      height: auto !important;
    }}

    /* Lists */
    ul, ol {{
      margin-top: 0;
      margin-bottom: 12px;
      padding-left: 22px;
    }}
    li {{
      margin-bottom: 4px;
    }}

    hr {{
      border: none;
      border-top: 1px solid #e2e8f0;
      margin: 24px 0;
    }}
  </style>
</head>
<body>

  <!-- Cover Page -->
  <div class="cover-page">
    <div class="cover-icon">🐟</div>
    <div class="cover-title">MatsyaAI Maharashtra</div>
    <div class="cover-subtitle">Marine Decision-Support & Fishing Activity Forecast Platform</div>
    <div class="cover-desc">
      A comprehensive technical manual covering system architecture, causal machine learning models, 
      geospatial PostGIS databases, document extraction pipelines, and independent maritime safety governance.
    </div>
    
    <div class="cover-meta">
      <div><strong>Role:</strong> Senior Software Architect, Full-Stack Developer & Technical Writer</div>
      <div><strong>Target Platform:</strong> Maharashtra Coast & EEZ (15.50°N – 20.00°N, 72.00°E – 74.00°E)</div>
      <div><strong>Core Technologies:</strong> FastAPI, React 19, Leaflet, PostgreSQL 16, PostGIS 3.4, XGBoost 3.2</div>
      <div><strong>Documentation Version:</strong> 1.0.0 (Production Verified)</div>
      <div><strong>Date:</strong> November 2026</div>
    </div>
  </div>

  <!-- Main Content -->
  <div class="main-content">
    {html_content}
  </div>

  <script>
    // Initialize Mermaid
    mermaid.initialize({{
      startOnLoad: true,
      theme: 'neutral',
      flowchart: {{ useMaxWidth: true, htmlLabels: true, curve: 'basis' }},
      sequence: {{ useMaxWidth: true, showSequenceNumbers: true }},
      er: {{ useMaxWidth: true }},
      securityLevel: 'loose'
    }});

    // Initialize KaTeX
    document.addEventListener("DOMContentLoaded", function() {{
      if (typeof renderMathInElement !== 'undefined') {{
        renderMathInElement(document.body, {{
          delimiters: [
            {{left: "$$", right: "$$", display: true}},
            {{left: "$", right: "$", display: false}},
            {{left: "\\\\(", right: "\\\\)", display: false}},
            {{left: "\\\\[", right: "\\\\]", display: true}}
          ],
          throwOnError: false
        }});
      }}
    }});
  </script>
</body>
</html>
"""

    os.makedirs(os.path.dirname(OUTPUT_HTML), exist_ok=True)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(template)
    print(f"Renderable HTML written to {OUTPUT_HTML} ({len(template)} characters)")
    return OUTPUT_HTML

def generate_pdf(html_path):
    print("Executing Microsoft Edge headless rendering to generate PDF...")
    args = [
        EDGE_EXE,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--virtual-time-budget=9000",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={OUTPUT_PDF}",
        f"file:///{html_path.replace(os.sep, '/')}"
    ]
    
    res = subprocess.run(args, capture_output=True, text=True)
    if os.path.exists(OUTPUT_PDF):
        size_kb = os.path.getsize(OUTPUT_PDF) / 1024.0
        print(f"SUCCESS: PDF successfully created at {OUTPUT_PDF} ({size_kb:.1f} KB)")
        
        # Verify page count with pymupdf
        try:
            import fitz
            doc = fitz.open(OUTPUT_PDF)
            print(f"Total Pages in PDF: {len(doc)}")
        except Exception as e:
            print("Note: PyMuPDF verification skipped:", e)
    else:
        print(f"ERROR: PDF was not created. Stderr: {res.stderr}")

if __name__ == "__main__":
    md_text = build_consolidated_markdown()
    html_path = convert_md_to_html(md_text)
    generate_pdf(html_path)
