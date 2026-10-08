import sys
import os
import pptx
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

sys.stdout.reconfigure(encoding='utf-8')

def build_presentation():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_slide_layout = prs.slide_layouts[6] # Blank layout

    # Colors
    c_navy_dark = RGBColor(11, 25, 44)      # #0B192C
    c_navy_light = RGBColor(30, 41, 59)     # #1E293B
    c_teal = RGBColor(13, 148, 136)         # #0D9488
    c_blue = RGBColor(37, 99, 235)          # #2563EB
    c_amber = RGBColor(217, 119, 6)         # #D97706
    c_red = RGBColor(220, 38, 38)           # #DC2626
    c_green = RGBColor(16, 185, 129)        # #10B981
    c_card_bg = RGBColor(248, 250, 252)     # #F8FAFC
    c_card_border = RGBColor(226, 232, 240) # #E2E8F0
    c_white = RGBColor(255, 255, 255)
    c_text_dark = RGBColor(15, 23, 42)      # #0F172A
    c_text_muted = RGBColor(100, 116, 139)  # #64748B
    c_purple = RGBColor(126, 34, 206)       # #7E22CE

    def add_header(slide, section_num, section_title, page_num, total_pages=18):
        # Top banner category pill
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(8.0), Inches(0.4))
        tf = cat_box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.text = f"{section_num.upper()}  ·  SENOVA AI DASHBOARD"
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = c_teal

        # Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.75), Inches(10.0), Inches(0.6))
        tf2 = title_box.text_frame
        tf2.word_wrap = True
        tf2.margin_left = tf2.margin_top = tf2.margin_right = tf2.margin_bottom = 0
        p2 = tf2.paragraphs[0]
        p2.text = section_title
        p2.font.size = Pt(22)
        p2.font.bold = True
        p2.font.color.rgb = c_navy_dark

        # Top line
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.4), Inches(11.733), Inches(0.02))
        line.fill.solid()
        line.fill.fore_color.rgb = c_card_border
        line.line.color.rgb = c_card_border

        # Footer
        footer_box = slide.shapes.add_textbox(Inches(0.8), Inches(7.05), Inches(11.733), Inches(0.3))
        tff = footer_box.text_frame
        tff.word_wrap = True
        tff.margin_left = tff.margin_top = tff.margin_right = tff.margin_bottom = 0
        pf = tff.paragraphs[0]
        pf.text = f"SENOVA AI Dashboard  ·  Phase 2 Progress Review  |  Slide {page_num} of {total_pages}"
        pf.font.size = Pt(9)
        pf.font.color.rgb = c_text_muted

    def add_card(slide, left, top, width, height, title, body_lines, accent_color=c_blue, bg_color=c_card_bg):
        # Card background shape
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        card.line.color.rgb = c_card_border
        card.line.width = Pt(1)

        # Top accent bar on card
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(0.08))
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent_color
        bar.line.fill.background()

        # Text inside card
        tb = slide.shapes.add_textbox(Inches(left + 0.25), Inches(top + 0.2), Inches(width - 0.5), Inches(height - 0.35))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        # Title
        p_title = tf.paragraphs[0]
        p_title.text = title
        p_title.font.size = Pt(13)
        p_title.font.bold = True
        p_title.font.color.rgb = c_navy_dark
        p_title.space_after = Pt(8)

        # Body items
        for item in body_lines:
            p = tf.add_paragraph()
            p.text = f"• {item}" if not item.startswith("  ") else item
            p.font.size = Pt(10)
            p.font.color.rgb = c_text_dark
            p.space_after = Pt(4)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 1: FRONT PAGE / TITLE SLIDE
    # ════════════════════════════════════════════════════════════════
    s1 = prs.slides.add_slide(blank_slide_layout)
    # Dark Navy Background
    bg1 = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = c_navy_dark
    bg1.line.fill.background()

    # Department & College Banner
    tb_college = s1.shapes.add_textbox(Inches(1.0), Inches(0.8), Inches(11.333), Inches(0.6))
    tf_c = tb_college.text_frame
    p_c = tf_c.paragraphs[0]
    p_c.text = "GOVERNMENT ENGINEERING COLLEGE, RAICHUR"
    p_c.font.size = Pt(13)
    p_c.font.bold = True
    p_c.font.color.rgb = c_teal
    p_c2 = tf_c.add_paragraph()
    p_c2.text = "DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING  ·  ACADEMIC YEAR 2026–2027"
    p_c2.font.size = Pt(10)
    p_c2.font.color.rgb = RGBColor(148, 163, 184)

    # Project Title
    tb_title = s1.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(11.333), Inches(1.8))
    tf_t = tb_title.text_frame
    p_t = tf_t.paragraphs[0]
    p_t.text = "SENOVA AI Dashboard"
    p_t.font.size = Pt(38)
    p_t.font.bold = True
    p_t.font.color.rgb = c_white
    p_sub = tf_t.add_paragraph()
    p_sub.text = "An Autonomous Financial Intelligence & Decision Engine with Deterministic Compute & Clean Architecture"
    p_sub.font.size = Pt(15)
    p_sub.font.color.rgb = RGBColor(203, 213, 225)
    p_sub.space_before = Pt(6)

    # Pill tags
    p_tags = tf_t.add_paragraph()
    p_tags.text = "★ Zero-Formula BI   |   100% Deterministic Python Math   |   Clean Layered Architecture"
    p_tags.font.size = Pt(11)
    p_tags.font.bold = True
    p_tags.font.color.rgb = c_teal
    p_tags.space_before = Pt(8)

    # Project Guide Card (Left)
    card_guide = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(4.3), Inches(4.5), Inches(2.2))
    card_guide.fill.solid()
    card_guide.fill.fore_color.rgb = c_navy_light
    card_guide.line.color.rgb = RGBColor(51, 65, 85)
    tb_g = s1.shapes.add_textbox(Inches(1.2), Inches(4.5), Inches(4.1), Inches(1.8))
    tf_g = tb_g.text_frame
    p_gh = tf_g.paragraphs[0]
    p_gh.text = "PROJECT GUIDE"
    p_gh.font.size = Pt(10)
    p_gh.font.bold = True
    p_gh.font.color.rgb = c_teal
    p_gn = tf_g.add_paragraph()
    p_gn.text = "Prof. Mamatha Madam"
    p_gn.font.size = Pt(15)
    p_gn.font.bold = True
    p_gn.font.color.rgb = c_white
    p_gn.space_before = Pt(4)
    p_gd = tf_g.add_paragraph()
    p_gd.text = "Associate Professor, Dept. of CSE\nGovernment Engineering College, Raichur"
    p_gd.font.size = Pt(10)
    p_gd.font.color.rgb = RGBColor(203, 213, 225)

    # Team Members Card (Right)
    card_team = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5.8), Inches(4.3), Inches(6.5), Inches(2.2))
    card_team.fill.solid()
    card_team.fill.fore_color.rgb = c_navy_light
    card_team.line.color.rgb = RGBColor(51, 65, 85)
    tb_tm = s1.shapes.add_textbox(Inches(6.0), Inches(4.5), Inches(6.1), Inches(1.8))
    tf_tm = tb_tm.text_frame
    p_tmh = tf_tm.paragraphs[0]
    p_tmh.text = "PRESENTED BY (FINAL YEAR B.E. STUDENTS)"
    p_tmh.font.size = Pt(10)
    p_tmh.font.bold = True
    p_tmh.font.color.rgb = c_teal
    p_tm1 = tf_tm.add_paragraph()
    p_tm1.text = "• Shrihari                (USN: 3GU23CS044)\n• Basvaraj               (USN: 3GU24CS400)\n• Navin Chavan       (USN: 3GU24CS404)"
    p_tm1.font.size = Pt(12)
    p_tm1.font.bold = True
    p_tm1.font.color.rgb = c_white
    p_tm1.space_before = Pt(6)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 2: INTRODUCTION
    # ════════════════════════════════════════════════════════════════
    s2 = prs.slides.add_slide(blank_slide_layout)
    add_header(s2, "01 · Introduction", "Executive Overview & Product Purpose", 2)
    add_card(s2, 0.8, 1.7, 5.7, 2.4, "🏛 What is SENOVA AI Dashboard?", [
        "Autonomous 'Digital CFO' built specifically for retail SMEs.",
        "Bridges the gap between raw spreadsheet dumps & strategic decisions.",
        "Zero-formula, zero-setup onboarding in less than 5 seconds.",
        "Transforms messy POS exports into audit-proof financial intelligence."
    ], c_blue)
    add_card(s2, 6.8, 1.7, 5.7, 2.4, "⚡ The SME Data Bottleneck", [
        "Small businesses run on daily CSV exports (Tally, Vyapar, Shopify).",
        "Manual Excel pivot tables cause severe operational fatigue.",
        "Power BI & Tableau have steep learning curves & require rigid schemas.",
        "Standard LLMs (ChatGPT) produce 5–15% arithmetic math hallucinations."
    ], c_amber)
    add_card(s2, 0.8, 4.4, 5.7, 2.4, "⚙ Decoupled Compute Paradigm", [
        "Layer 1 (Pandas/Python): Executes 100% deterministic math rollups.",
        "Layer 2 (Narrative AI): Generates plain-language executive alerts.",
        "Strict separation makes calculation hallucinations mathematically impossible.",
        "Numbers remain 100% auditable and accounting-compliant."
    ], c_teal)
    add_card(s2, 6.8, 4.4, 5.7, 2.4, "🎯 Production Digital CFO Impact", [
        "4-step ingestion pipeline with 265-alias schema matching.",
        "Median Absolute Deviation (MAD) robust outlier detection.",
        "30-day cash flow & seasonal forecasting with 80% confidence bands.",
        "CA-grade multi-page ReportLab vector PDF reports for bank/tax filing."
    ], c_green)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 3: PROBLEM STATEMENT
    # ════════════════════════════════════════════════════════════════
    s3 = prs.slides.add_slide(blank_slide_layout)
    add_header(s3, "02 · Problem Statement", "The SME Spreadsheet Dilemma: Why Existing Tools Fail", 3)
    add_card(s3, 0.8, 1.7, 3.7, 4.8, "The Manual Barrier\n(Excel / Google Sheets)", [
        "Small retailers spend 8–10 hours/week on manual spreadsheets.",
        "Requires complex VLOOKUPs, nested IFs, and manual pivot tables.",
        "One typo or formula error cascades through the entire financial ledger.",
        "Fails to provide automated business warnings or trend forecasts.",
        "Zero mobile-friendly or executive summary capability."
    ], c_red)
    add_card(s3, 4.8, 1.7, 3.7, 4.8, "The Complexity Barrier\n(Power BI / Tableau)", [
        "High subscription cost ($10–$20/user/month) prohibitive for SMEs.",
        "Steep learning curve requiring specialized DAX & data modeling skills.",
        "Breaks completely on non-standard, messy POS header variations.",
        "Requires rigid database setup and continuous IT maintenance.",
        "Produces passive visual charts rather than actionable text advice."
    ], c_amber)
    add_card(s3, 8.8, 1.7, 3.7, 4.8, "The Hallucination Barrier\n(Pure LLMs / AI Agents)", [
        "Generative LLMs are probabilistic word predictors, not calculators.",
        "Arithmetic error rate of 5–15% when summing thousands of ledger rows.",
        "In financial accounting, even 1% error leads to statutory audit failure.",
        "Cannot verify source receipts or guarantee audit trail.",
        "Black-box logic lacks deterministic, reproducible verification."
    ], c_purple)

    # Bottom summary callout
    callout3 = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(6.6), Inches(11.733), Inches(0.35))
    callout3.fill.solid()
    callout3.fill.fore_color.rgb = RGBColor(238, 242, 255)
    callout3.line.color.rgb = RGBColor(199, 210, 254)
    tb_c3 = s3.shapes.add_textbox(Inches(0.9), Inches(6.62), Inches(11.5), Inches(0.3))
    tf_c3 = tb_c3.text_frame
    p_c3 = tf_c3.paragraphs[0]
    p_c3.text = "🎯 Core Engineering Problem: How to deliver zero-formula, zero-setup business intelligence while guaranteeing 100% mathematical auditability?"
    p_c3.font.size = Pt(9.5)
    p_c3.font.bold = True
    p_c3.font.color.rgb = c_blue

    # ════════════════════════════════════════════════════════════════
    # SLIDE 4: OBJECTIVES
    # ════════════════════════════════════════════════════════════════
    s4 = prs.slides.add_slide(blank_slide_layout)
    add_header(s4, "03 · Objectives", "Core Objectives & Scope of SENOVA AI Dashboard", 4)
    add_card(s4, 0.8, 1.7, 3.7, 2.4, "1. Zero-Setup Ingestion", [
        "Ingest CSV, TSV, XLSX, and XLS exports from any retail POS system.",
        "Auto-sniff delimiters (commas, tabs, pipes) & encoding fallbacks.",
        "Perform pre-flight row validation in under 500ms."
    ], c_blue)
    add_card(s4, 4.8, 1.7, 3.7, 2.4, "2. 265-Alias Canonicalization", [
        "Map non-standard headers using 265 exact aliases + 66 fuzzy keywords.",
        "Human-in-the-Loop confirmation with visual confidence badges.",
        "Collision prevention to eliminate accidental column overwrites."
    ], c_teal)
    add_card(s4, 8.8, 1.7, 3.7, 2.4, "3. 100% Deterministic Math", [
        "Decouple Python arithmetic engine (Pandas) from text narrative layer.",
        "Enforce strict groupby calculations for gross-to-net P&L statements.",
        "Zero arithmetic hallucinations guaranteed across all financial metrics."
    ], c_green)
    add_card(s4, 0.8, 4.4, 3.7, 2.4, "4. MAD Anomaly Detection", [
        "Robust outlier detection using Median Absolute Deviation (z-score).",
        "Automatically handles sparse zero-sales trading days.",
        "Surfaces plain-language 'What Changed' cards with root-cause advice."
    ], c_amber)
    add_card(s4, 4.8, 4.4, 3.7, 2.4, "5. 30-Day Seasonal Forecast", [
        "Recency-weighted trend projection with 14-day exponential decay.",
        "Applies weekday seasonality multipliers + 80% confidence interval.",
        "Real-time backtest accuracy verification against recent sales."
    ], c_purple)
    add_card(s4, 8.8, 4.4, 3.7, 2.4, "6. CA-Grade PDF & Security", [
        "Compile printable, searchable A4 accounting registers via ReportLab.",
        "Secure Firebase Auth with JWT Bearer tokens & per-file ownership.",
        "Thread-safe bounded in-memory LRU cache delivering sub-300ms latency."
    ], c_navy_dark)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 5: LITERATURE SURVEY
    # ════════════════════════════════════════════════════════════════
    s5 = prs.slides.add_slide(blank_slide_layout)
    add_header(s5, "04 · Literature Survey", "Academic Research Works & Comparative Benchmarks", 5)
    add_card(s5, 0.8, 1.7, 5.7, 5.0, "Key Research Papers & Citations", [
        "1. McKinney, W. (2010) — Data Structures for Statistical Computing in Python:",
        "   Foundational paper on Pandas; establishes columnar split-apply-combine logic.",
        "2. Kandel, S. et al. (2011) — Research Directions in Data Wrangling:",
        "   Demonstrates that 80% of analyst time is wasted on data formatting; justifies our 265-alias auto-sniffer.",
        "3. Heer, J. & Shneiderman, B. (2012) — Interactive Dynamics for Visual Analysis:",
        "   Guided our Chart Studio architecture and slide-out drill-down drawer paradigm.",
        "4. Petropoulos, F. et al. (2022) — Forecasting: Theory and Practice:",
        "   Proves recency weighting & weekday seasonality outperform complex deep learning on retail micro-series.",
        "5. Paparrizos, J. et al. (2022) — TSB-UAD Benchmark for Anomaly Detection:",
        "   Validates Median Absolute Deviation (MAD) superiority over standard deviation for non-normal retail distributions."
    ], c_blue)
    add_card(s5, 6.8, 1.7, 5.7, 5.0, "System Benchmark: Existing vs SENOVA", [
        "Feature Matrix Comparison across industry solutions:",
        "• Setup Time: Excel (Hours) | Power BI (Days) | SENOVA (5 Seconds)",
        "• Math Accuracy: Excel (User error prone) | ChatGPT (85–95%) | SENOVA (100% Deterministic)",
        "• Learning Curve: Excel (Moderate) | Power BI (Steep/DAX) | SENOVA (Zero-Formula)",
        "• Audit-Proof PDF: Excel (Manual Print) | Power BI (Screenshot) | SENOVA (CA-Grade ReportLab Vector)",
        "• Anomaly Detection: Excel (None) | Power BI (Complex DAX) | SENOVA (Automated Plain-Language MAD)",
        "• Retail Header Aliases: Excel (None) | Power BI (Rigid) | SENOVA (265 Exact Aliases + Fuzzy Fallback)",
        "Takeaway: SENOVA bridges the critical research gap between automated usability and audit-proof accounting rigor."
    ], c_teal)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 6: METHODOLOGY & ARCHITECTURE
    # ════════════════════════════════════════════════════════════════
    s6 = prs.slides.add_slide(blank_slide_layout)
    add_header(s6, "05 · Methodology", "Clean Layered Architecture & Axiomatic Compute Separation", 6)
    add_card(s6, 0.8, 1.7, 3.7, 5.0, "Layered Architecture Style\n(Clean Architecture Pattern)", [
        "SENOVA employs a 5-layer decoupled architecture:",
        "1. Presentation Layer (React 18 + Vite):",
        "   Modular UI, Chart Studio, Drill-down drawer.",
        "2. Security & Guard (Firebase Auth):",
        "   JWT Bearer validation, per-user file ownership.",
        "3. REST Controller Layer (FastAPI):",
        "   Async endpoints, Pydantic type validation.",
        "4. Domain Services Layer (Pandas/NumPy):",
        "   Dedicated services for P&L, Forecasting, Inventory.",
        "5. Document Engine Layer (ReportLab):",
        "   Thread-safe multi-page vector PDF compiler."
    ], c_navy_dark)
    add_card(s6, 4.8, 1.7, 3.7, 5.0, "The 2-Layer Compute Separation\n(Axiomatic Safety Rule)", [
        "LAYER 1: Deterministic Engine (Pandas)",
        "• Sole source of mathematical truth.",
        "• Currency coercion & Date normalization.",
        "• Groupby aggregations, COGS, Net Turnover.",
        "• 100% audit-proof, reproducible arithmetic.",
        " ",
        "LAYER 2: Narrative Analytics Engine",
        "• Receives read-only pre-computed JSON objects.",
        "• Generates plain-language business warnings.",
        "• Flags margin drops, dead stock & anomalies.",
        "• Mathematically incapable of altering numbers."
    ], c_blue)
    add_card(s6, 8.8, 1.7, 3.7, 5.0, "Production Tech Stack\n(Enterprise Grade)", [
        "• Frontend Client: React 18, Vite, TailwindCSS, Recharts, Framer Motion",
        "• Backend Framework: Python 3.13, FastAPI, Uvicorn (Async/Await)",
        "• Data Compute: Pandas, NumPy, Python CSV Sniffer",
        "• Authentication: Firebase Auth (OAuth + Bearer JWT)",
        "• Caching Engine: Bounded LRU Thread-Safe Cache",
        "• Document Engine: ReportLab Platypus Engine",
        "• Deployment: Vercel (Client) + Render (API Server)"
    ], c_teal)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 7: FLOWCHART
    # ════════════════════════════════════════════════════════════════
    s7 = prs.slides.add_slide(blank_slide_layout)
    add_header(s7, "06 · System Pipeline", "5-Stage End-to-End Financial Data Lifecycle Flowchart", 7)
    add_card(s7, 0.8, 1.7, 2.2, 5.0, "Stage 1: Ingest & Sniff", [
        "Raw File Upload",
        "(CSV / XLSX / TSV)",
        " ",
        "Auto-Sniffer detects delimiter (comma, tab, pipe).",
        " ",
        "Encoding fallback: UTF-8 → UTF-8-SIG → Latin-1.",
        " ",
        "Pre-flight file size & row count validation."
    ], c_blue)
    add_card(s7, 3.2, 1.7, 2.2, 5.0, "Stage 2: Canonicalize", [
        "Schema Matcher",
        "(265 Exact Aliases)",
        " ",
        "O(1) hash map lookup against retail header alias dictionary.",
        " ",
        "Ordered fuzzy keyword substring matching fallback.",
        " ",
        "Assigns confidence: Exact, Fuzzy, or None."
    ], c_teal)
    add_card(s7, 5.6, 1.7, 2.2, 5.0, "Stage 3: Human Guard", [
        "Interactive Mapping",
        "(Human-in-the-Loop)",
        " ",
        "Green badge: Exact Match.",
        "Amber badge: Review needed.",
        " ",
        "Dynamic Unit Price math: Total ÷ Qty.",
        " ",
        "Collision prevention disables duplicate mapping."
    ], c_amber)
    add_card(s7, 8.0, 1.7, 2.2, 5.0, "Stage 4: Compute & MAD", [
        "Deterministic Engine",
        "(Pandas + NumPy)",
        " ",
        "Row cleaning & currency coercion.",
        " ",
        "P&L rollups & COGS derivation.",
        " ",
        "MAD Anomaly Detection with Sparse-Day filter.",
        " ",
        "Recency-weighted 30-day forecast."
    ], c_purple)
    add_card(s7, 10.4, 1.7, 2.1, 5.0, "Stage 5: Deliver & PDF", [
        "Dashboard & Report",
        "(Sub-Second Delivery)",
        " ",
        "Thread-safe LRU in-memory cache stores frame.",
        " ",
        "Live interactive React dashboard renders.",
        " ",
        "1-click CA-Grade ReportLab vector PDF export."
    ], c_green)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 8: ALGORITHMS (PART 1)
    # ════════════════════════════════════════════════════════════════
    s8 = prs.slides.add_slide(blank_slide_layout)
    add_header(s8, "07 · Algorithms & Techniques (1/2)", "Schema Canonicalization & Robust MAD Anomaly Detection", 8)
    add_card(s8, 0.8, 1.7, 5.7, 5.0, "01. Hash-Map Schema Matching with Fuzzy Fallback", [
        "Function: backend/app/utils/data_validator.py — guess_canonical_column()",
        "• What it does: Standardizes heterogeneous retail column names from Tally, Vyapar, Shopify, and Amazon into SENOVA's canonical schema.",
        "• Exact Hash Map Match: Performs an O(1) case-insensitive lookup across 265 pre-compiled retail header aliases.",
        "• Ordered Priority Fuzzy Fallback: If exact match misses, evaluates 66 priority-ordered keyword substrings (e.g. 'net amount' matches Line Total before 'amount').",
        "• Confidence Scoring: Returns ('exact', 100%) or ('fuzzy', 75%) or ('none', 0%) to trigger automated pass or human-in-the-loop review.",
        "• Business Impact: Eliminates hours of manual CSV reformatting while completely preventing broken ingestion."
    ], c_blue)
    add_card(s8, 6.8, 1.7, 5.7, 5.0, "02. MAD-Based Robust Anomaly Detection", [
        "Function: backend/app/services/insights_engine.py — _anomaly_insights()",
        "• What it does: Flags abnormal daily revenue drops or spikes without assuming a Gaussian/normal data distribution.",
        "• Algorithmic Formula:",
        "    Modified z-score = 0.6745 × (x - Median) ÷ MAD",
        "    where MAD = Median(|x_i - Median|)",
        "• Robust Property: Unlike standard deviation (which squares differences and is heavily skewed by single big sales), MAD is immune to retail outliers.",
        "• Sparse-Day Trading Mode: If non-trading (zero revenue) days exceed 25% of the window, analysis automatically filters to active trading days only.",
        "• Business Impact: Eliminates false alarms, alerting shop owners only to true operational drops (e.g. 14 May dropped 37%)."
    ], c_teal)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 9: ALGORITHMS (PART 2)
    # ════════════════════════════════════════════════════════════════
    s9 = prs.slides.add_slide(blank_slide_layout)
    add_header(s9, "07 · Algorithms & Techniques (2/2)", "Seasonal Revenue Forecasting & ABC Pareto Inventory", 9)
    add_card(s9, 0.8, 1.7, 5.7, 5.0, "03. Recency-Weighted Least Squares Forecasting", [
        "Function: backend/app/services/forecasting.py — compute_forecast()",
        "• What it does: Projects future cash flow 7, 14, or 30 days ahead with weekday seasonality and 80% statistical confidence bands.",
        "• Exponential Decay Weighting: Fits weighted least squares regression where sample weight w_i = exp(-ln(2) × age / 14 days). Recent 14 days carry double the mathematical weight of older sales.",
        "• Weekday Seasonality Multipliers: Computes median(actual ÷ trend) per weekday, normalized to average 1.0 (capturing weekend retail rushes).",
        "• Real-Time Backtest Accuracy: Holds back the most recent 7 actual days, evaluates model projection, and displays MAPE % accuracy (e.g. 85.5%).",
        "• Business Impact: Gives store owners inspectable cash flow forecasts aligned with weekly restocking cycles."
    ], c_purple)
    add_card(s9, 6.8, 1.7, 5.7, 5.0, "04. ABC Pareto Inventory Classification", [
        "Function: backend/app/services/inventory_intel.py — _classify_abc()",
        "• What it does: Categorizes inventory into Pareto tiers and computes SKU restock urgency scores.",
        "• Pareto Classification Logic:",
        "  - Class A (Top 80% Revenue): High-value focus items (approx. 20% of SKUs).",
        "  - Class B (Next 15% Revenue): Moderate volume items.",
        "  - Class C (Long Tail 5% Revenue): Slow movers and capital traps.",
        "• Multi-Factor Priority Score (0–100):",
        "    Score = 0.5 × sales_velocity + 0.3 × trend_factor + 0.2 × recency",
        "• Days of Cover: Computes stock on hand ÷ daily sales velocity to forecast exact stockout dates.",
        "• Business Impact: Identifies dead stock to free up locked working capital."
    ], c_green)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 10: WORK COMPLETED
    # ════════════════════════════════════════════════════════════════
    s10 = prs.slides.add_slide(blank_slide_layout)
    add_header(s10, "08 · Work Completed", "Phase 2 Engineering Milestones & Verification Standards", 10)
    add_card(s10, 0.8, 1.7, 3.7, 5.0, "Verified Modules (100% Complete)", [
        "✓ End-to-End Ingestion Pipeline (CSV, TSV, XLSX, XLS with encoding fallbacks).",
        "✓ 265 Exact Aliases + 66 Fuzzy Header Matcher.",
        "✓ Human-in-the-Loop Column Mapping UI with Green/Amber confidence badges.",
        "✓ 100% Deterministic Pandas Compute Engine.",
        "✓ MAD Anomaly Engine with Sparse-Day Mode.",
        "✓ 30-Day Seasonal Revenue Forecasting.",
        "✓ Interactive Chart Studio (8 Modalities).",
        "✓ Slide-out Granular Drill-Down Ledger Drawer.",
        "✓ ABC Pareto Inventory & Dead Stock Classifier.",
        "✓ Multi-Page CA-Grade ReportLab PDF Engine."
    ], c_green)
    add_card(s10, 4.8, 1.7, 3.7, 5.0, "199 Unit Tests (100% Pass Rate)", [
        "Automated Test Suite Coverage (pytest):",
        "• test_data_validator.py: 42 tests verifying header aliases, missing unit prices, date parsers.",
        "• test_accuracy_audit.py: 35 tests auditing P&L math, GST exclusion, discount subtractions.",
        "• test_insights_engine.py: 28 tests verifying MAD z-scores & sparse day anomaly filtering.",
        "• test_inventory_and_forecast.py: 31 tests auditing ABC cutoffs & least squares trend weights.",
        "• test_frame_cache_concurrency.py: 25 tests verifying thread safety under concurrent requests.",
        "• test_auth_routes.py: 38 tests auditing JWT bearer validation & enumeration protection."
    ], c_blue)
    add_card(s10, 8.8, 1.7, 3.7, 5.0, "Performance & Stress Benchmarks", [
        "Evaluated on 50,000+ Transaction Files:",
        "• File Ingestion & Pre-flight: <450ms for 50k rows.",
        "• P&L Aggregation Latency: <180ms.",
        "• Query Response (LRU Cached): <45ms.",
        "• End-to-End Analytics Response: <280ms average.",
        "• ReportLab PDF Compilation: <1.8s for 18-page formal accounting document.",
        "• Memory Footprint: Bounded LRU cache strictly limits RAM usage to under 150MB, stable on 512MB free instances."
    ], c_teal)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 11: RESULTS & SCREENSHOTS (1)
    # ════════════════════════════════════════════════════════════════
    s11 = prs.slides.add_slide(blank_slide_layout)
    add_header(s11, "09 · Results & Screenshots (1/3)", "Ingestion Stepper, Column Mapping & Security Setup", 11)
    
    add_card(s11, 0.8, 1.7, 4.8, 5.0, "Module Walkthrough & Live Behavior", [
        "1. Visual 4-Step Stepper:",
        "   Upload → Confirm Columns → Validate Rows → Build Dashboard.",
        "   Users are guided visually with real-time feedback.",
        "2. Human-in-the-Loop Column Mapping Screen:",
        "   - Green Badges: High confidence exact alias matches.",
        "   - Amber Badges: Substring fuzzy matches needing review.",
        "   - Live Row Preview: Sample row values displayed next to dropdowns so users never map blindly.",
        "   - Dynamic Math: If Unit Price is missing, automatically computed as Line Total ÷ Quantity.",
        "3. Security & Auth Guard:",
        "   - Firebase Auth with Google OAuth & Email/Password.",
        "   - Zero-knowledge credential handling.",
        "   - Per-file caller UID binding prevents data leakage."
    ], c_blue)

    # Insert user screenshot on right side
    user_img_path = r"C:\Users\LENOVO\.gemini\antigravity\brain\bed38e00-e2c0-47f5-82ee-11361a3e9edc\.user_uploaded\media_1788380781053.png"
    if os.path.exists(user_img_path):
        s11.shapes.add_picture(user_img_path, Inches(5.9), Inches(1.7), Inches(6.6), Inches(3.7))
        # Caption card below screenshot
        cap_box = s11.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5.9), Inches(5.5), Inches(6.6), Inches(1.2))
        cap_box.fill.solid()
        cap_box.fill.fore_color.rgb = c_card_bg
        cap_box.line.color.rgb = c_card_border
        tb_cap = s11.shapes.add_textbox(Inches(6.0), Inches(5.55), Inches(6.4), Inches(1.1))
        tf_cap = tb_cap.text_frame
        p_cap = tf_cap.paragraphs[0]
        p_cap.text = "Live Implementation Screenshot: Confirm Columns Screen (03_electronics_shopify_orders.csv)"
        p_cap.font.size = Pt(10)
        p_cap.font.bold = True
        p_cap.font.color.rgb = c_navy_dark
        p_cap2 = tf_cap.add_paragraph()
        p_cap2.text = "Shows matched payment mode ('COD' → Payment Mode) alongside unrecognised operational columns ('Currency', 'Order Status', 'Notes') gracefully set to 'Ignore this column'."
        p_cap2.font.size = Pt(9)
        p_cap2.font.color.rgb = c_text_muted

    # ════════════════════════════════════════════════════════════════
    # SLIDE 12: RESULTS & SCREENSHOTS (2)
    # ════════════════════════════════════════════════════════════════
    s12 = prs.slides.add_slide(blank_slide_layout)
    add_header(s12, "09 · Results & Screenshots (2/3)", "Overview Dashboard, Anomaly Findings & 30-Day Forecast", 12)
    add_card(s12, 0.8, 1.7, 3.7, 5.0, "Overview & Findings Screen", [
        "Executive KPI Metric Summary:",
        "• Total Revenue, Gross Profit, Net Margin %, COGS, Units Sold, and SKU Counts.",
        " ",
        "Dynamic Time Slicing:",
        "• Instant sub-second filtering across Today, 7 Days, 30 Days, This Month, and All Time.",
        " ",
        "Automated Narrative Anomaly Cards:",
        "• WATCH Cards: Highlights single-day drops (e.g. 14 May dropped -37% vs 14-day baseline).",
        "• GOOD Cards: Flags organic demand spikes.",
        "• Actionable Guidance: Plain-language recommendations (check supplier stockouts, marketing pause)."
    ], c_teal)
    add_card(s12, 4.8, 1.7, 3.7, 5.0, "30-Day Revenue Forecast Screen", [
        "Multi-Horizon Trend Projections:",
        "• Selectable forecast horizons: 7 Days, 14 Days, and 30 Days ahead.",
        " ",
        "80% Statistical Confidence Bands:",
        "• Shaded confidence intervals show optimistic and conservative cash flow expectations.",
        " ",
        "Backtest Accuracy Score (85.5%):",
        "• Live real-time validation against the most recent 7-day actual sales.",
        " ",
        "Fast-Moving SKUs Volume Ranking:",
        "• Bar chart displaying top SKU contributors to projected future revenue."
    ], c_purple)
    add_card(s12, 8.8, 1.7, 3.7, 5.0, "Inventory Intelligence Screen", [
        "ABC Pareto Classification Cards:",
        "• Class A: Top 80% revenue drivers.",
        "• Class B: Middle 15% revenue drivers.",
        "• Class C: Bottom 5% long-tail SKUs.",
        " ",
        "Dead Stock Identification Table:",
        "• Tracks days since last sale to isolate zero-velocity capital traps.",
        " ",
        "Restock Priority Scoring:",
        "• 0–100 score prioritizing reorders based on sales velocity and lead-time cover."
    ], c_green)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 13: RESULTS & SCREENSHOTS (3)
    # ════════════════════════════════════════════════════════════════
    s13 = prs.slides.add_slide(blank_slide_layout)
    add_header(s13, "09 · Results & Screenshots (3/3)", "Chart Studio, Drill-Down Drawer & CA-Grade Vector PDF", 13)
    add_card(s13, 0.8, 1.7, 3.7, 5.0, "Chart Studio (8 Modalities)", [
        "Versatile Visual Analytics:",
        "1. Vertical Bar Chart",
        "2. Horizontal Ranking Bar",
        "3. Donut Contribution Chart",
        "4. Combo Chart (Dual-Axis Revenue & Margin %)",
        "5. Pareto Chart (80/20 Distribution)",
        "6. Treemap (Hierarchical SKU Share)",
        "7. Heatmap Grid (Day-of-Week Density)",
        "8. Trend Line Chart (Moving Averages)",
        " ",
        "Dual-Axis Margin Curve:",
        "• Overlays profit margin % on revenue bars to spot unprofitable high-volume traps."
    ], c_blue)
    add_card(s13, 4.8, 1.7, 3.7, 5.0, "Slide-Out Drill-Down Drawer", [
        "Granular Transaction Audit:",
        "• Clicking any chart bar or category slides out an instant transaction register drawer.",
        " ",
        "Real-Time Item Ledger:",
        "• Displays transaction date, receipt invoice ID, SKU name, selling price, and transaction-level net profit.",
        " ",
        "Paginated Performance:",
        "• Smooth pagination handles 50,000+ transaction datasets without DOM lag.",
        " ",
        "Zero-Context Loss:",
        "• Owners inspect raw line items without losing their dashboard filter context."
    ], c_amber)
    add_card(s13, 8.8, 1.7, 3.7, 5.0, "Formal P&L & Vector PDF", [
        "CA-Grade Accounting Statement:",
        "• Gross Sales → Less Discounts → Net Turnover → COGS → Gross Profit.",
        "• Tax GST isolated as memo items to prevent income distortion.",
        " ",
        "ReportLab Vector PDF Engine:",
        "• True searchable vector text & tables (not blurry raster screenshots).",
        "• Sanitized currency glyphs ('Rs.') ensuring zero square/dot font rendering defects.",
        "• Multi-page A4 layout budgeted for bank loan applications and statutory tax filing."
    ], c_navy_dark)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 14: CHALLENGES FACED
    # ════════════════════════════════════════════════════════════════
    s14 = prs.slides.add_slide(blank_slide_layout)
    add_header(s14, "10 · Challenges Faced", "Real-World Engineering Challenges Overcome During Development", 14)
    add_card(s14, 0.8, 1.7, 5.7, 2.4, "1. Architecture Redesign (Failed 4 Times)", [
        "Challenge: The entire system architecture failed 4 times due to tight coupling between UI, file parsers, and calculation logic.",
        "Resolution: Rebuilt from scratch in the 5th iteration using a Clean Layered Architecture (Decoupled Compute Layer vs Narrative Layer).",
        "Impact: Achieved 100% test isolation, sub-300ms latency, and zero circular dependencies."
    ], c_red)
    add_card(s14, 6.8, 1.7, 5.7, 2.4, "2. Pandas Calculation Edge Cases & Math Errors", [
        "Challenge: Initial groupby arithmetic caused discrepancies with floating-point rounding, discount subtractions, and zero-sales days.",
        "Resolution: Engineered rigorous unit test audits (test_accuracy_audit.py) to lock deterministic rounding and GST separation.",
        "Impact: Passed 100% of 199 automated test cases with zero calculation errors."
    ], c_amber)
    add_card(s14, 0.8, 4.4, 5.7, 2.4, "3. Ingestion Header Variations & File Sniffing", [
        "Challenge: Diverse Indian POS systems (Tally, Vyapar, Shopify) used conflicting delimiters, non-UTF8 encodings, and non-standard column headers.",
        "Resolution: Engineered a 265-alias hash dictionary + 66 fuzzy keywords + auto-sniffer with Latin-1 encoding fallback.",
        "Impact: Eliminated upload crashes across retail CSV/XLSX dumps."
    ], c_blue)
    add_card(s14, 6.8, 4.4, 5.7, 2.4, "4. Current Active Challenges (Infrastructure & AI)", [
        "• Unmapped Operational Columns: Fields like 'Currency', 'Order Status', and 'Notes' (as seen in screenshot) are currently ignored.",
        "• Firebase Cloud DB Billing Barrier: Firebase Blaze requires international Visa credit card; free Spark tier limits persistence.",
        "• Active Resolution: Migrating session persistence to PostgreSQL + Cloudflare R2 and building 2-Tier FastEmbed + Gemini Flash."
    ], c_purple)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 15: PROS AND CONS
    # ════════════════════════════════════════════════════════════════
    s15 = prs.slides.add_slide(blank_slide_layout)
    add_header(s15, "11 · Pros and Cons", "Comprehensive System Evaluation & Realistic Constraints", 15)
    add_card(s15, 0.8, 1.7, 5.7, 5.0, "PROS (Core Software Strengths)", [
        "1. 100% Deterministic Math Precision:",
        "   Eliminates all AI hallucinations by enforcing Python/Pandas calculation truth.",
        "2. 265 Header Aliases + Auto Sniffer:",
        "   Instant O(1) detection of retail spreadsheets without templates or formula writing.",
        "3. High-Performance Sub-Second LRU Cache:",
        "   Enables instantaneous date slicing and chart filtering on 50,000+ transaction rows.",
        "4. Interactive Chart Studio & Drill-Down Drawer:",
        "   8 visual modalities with instant slide-out single-receipt audit registers.",
        "5. CA-Grade Vector PDF Generation:",
        "   ReportLab generates true searchable, multi-page vector accounting registers.",
        "6. Robust Security & Brute-Force Rate Limiting:",
        "   Firebase JWT token verification, token revocation checks, and enumeration defense."
    ], c_green)
    add_card(s15, 6.8, 1.7, 5.7, 5.0, "CONS (Honest Engineering Limitations)", [
        "1. Fixed 6-Field Canonical Scope:",
        "   Currently, the analytics pipeline requires mapping the 6 core financial fields (Date, Product, Quantity, Selling Price, Cost Price, Total). Non-canonical operational columns (like Order Status, Delivery Address, Notes) are ignored.",
        " ",
        "2. English-Centric Alias Dictionary:",
        "   The 265 pre-compiled aliases are optimized for standard English retail POS terms. Regional dialect or Hinglish column names (e.g. 'Baki Paisa', 'Jama Khata', 'Udhar') require manual dropdown selection by the user.",
        " ",
        "3. Ephemeral In-Memory Storage on Free Tier:",
        "   Without cloud database clustering, sessions rely on 120-minute temp upload lifecycles and in-memory LRU caching rather than permanent multi-year cloud storage."
    ], c_amber)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 16: FUTURE SCOPE
    # ════════════════════════════════════════════════════════════════
    s16 = prs.slides.add_slide(blank_slide_layout)
    add_header(s16, "12 · Future Scope", "Product Roadmap & Commercial Expansion", 16)
    add_card(s16, 0.8, 1.7, 3.7, 5.0, "1. Desktop Application\n(Offline POS Retail Counter)", [
        "• Packaging as Desktop Application:",
        "  Porting web SaaS into a native Desktop Application using Electron or Tauri.",
        "• Offline-First POS Integration:",
        "  Allows local shopkeepers with intermittent or no internet connectivity to run SENOVA directly on Windows/Linux store counter PCs.",
        "• Direct Hardware Tally Sync:",
        "  Directly hook into local Tally XML/ODBC ports without requiring manual CSV exports."
    ], c_blue)
    add_card(s16, 4.8, 1.7, 3.7, 5.0, "2. 2-Tier Hybrid AI Engine\n(Unstructured Column Match)", [
        "• Tier 1: Local FastEmbed:",
        "  10ms local embedding model to map ambiguous retail headers and regional Hinglish terms automatically.",
        "• Tier 2: Gemini Flash LLM:",
        "  Parses unstructured handwritten notes and supplier remarks ('damaged return', 'discounted clearance') into structured filters.",
        "• Zero-Math Policy Maintained:",
        "  AI extracts tags only; all financial arithmetic remains 100% in Pandas."
    ], c_purple)
    add_card(s16, 8.8, 1.7, 3.7, 5.0, "3. PostgreSQL & Cloudflare R2\n(Persistent Multi-Tenant Cloud)", [
        "• Database Migration:",
        "  Replacing single-session temp files with a persistent PostgreSQL workspace database.",
        "• Cloudflare R2 Object Storage:",
        "  S3-compatible persistent storage with zero egress fees, removing Firebase credit card billing bottlenecks.",
        "• Multi-Year Ledger Audits:",
        "  Allows business owners to compare Year-over-Year (YoY) financial growth across 5+ years of historical data."
    ], c_teal)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 17: CONCLUSION
    # ════════════════════════════════════════════════════════════════
    s17 = prs.slides.add_slide(blank_slide_layout)
    add_header(s17, "13 · Conclusion", "Summary of Technical Breakthroughs & Project Impact", 17)
    
    # 3 Simple, powerful summary cards
    add_card(s17, 0.8, 1.7, 3.7, 4.8, "1. Zero-Formula Simplicity", [
        "• Eliminated the formula barrier completely.",
        "• Shop owners don't need to learn complex Excel formulas, VLOOKUPs, or Power BI DAX code.",
        "• Upload a raw file → System automatically detects columns and generates actionable financial insights in under 5 seconds."
    ], c_blue)
    add_card(s17, 4.8, 1.7, 3.7, 4.8, "2. 100% Math Truth", [
        "• Solved the biggest flaw of modern AI tools: arithmetic hallucination.",
        "• By decoupling Python math from narrative AI text, our system guarantees 0% calculation error.",
        "• Verified across 199 unit tests with complete mathematical and accounting auditability."
    ], c_teal)
    add_card(s17, 8.8, 1.7, 3.7, 4.8, "3. True Digital CFO Impact", [
        "• Delivers institutional-grade financial intelligence to small retail businesses.",
        "• Automated anomaly detection, 30-day forecasting, and CA-grade vector PDF reports.",
        "• Democratizes business intelligence, giving every small shopkeeper an autonomous, audit-proof Digital CFO."
    ], c_green)

    # Bottom single-line memorable conclusion
    callout17 = s17.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(6.6), Inches(11.733), Inches(0.35))
    callout17.fill.solid()
    callout17.fill.fore_color.rgb = RGBColor(236, 253, 245)
    callout17.line.color.rgb = RGBColor(167, 243, 208)
    tb_c17 = s17.shapes.add_textbox(Inches(0.9), Inches(6.62), Inches(11.5), Inches(0.3))
    tf_c17 = tb_c17.text_frame
    p_c17 = tf_c17.paragraphs[0]
    p_c17.text = "\"SENOVA AI Dashboard proves that small business financial intelligence can be completely automated with zero formula setup and 100% mathematical precision.\""
    p_c17.font.size = Pt(9.5)
    p_c17.font.bold = True
    p_c17.font.color.rgb = c_teal

    # ════════════════════════════════════════════════════════════════
    # SLIDE 18: REFERENCES
    # ════════════════════════════════════════════════════════════════
    s18 = prs.slides.add_slide(blank_slide_layout)
    add_header(s18, "14 · References", "Academic Literature & Research Citations", 18)
    add_card(s18, 0.8, 1.7, 11.733, 5.0, "Formal Research Citations", [
        "[1] McKinney, W. (2010) — Data Structures for Statistical Computing in Python. Proc. 9th Python in Science Conf. (SciPy), pp. 51–56. https://doi.org/10.25080/Majora-92bf1922-00a",
        "[2] Kandel, S. et al. (2011) — Research Directions in Data Wrangling: Visualizations and Transformations for Usable and Credible Data. Information Visualization, 10(4), 271–288. https://doi.org/10.1177/1473871611415994",
        "[3] Heer, J. & Shneiderman, B. (2012) — Interactive Dynamics for Visual Analysis. ACM Queue, 10(2), 30–55. https://doi.org/10.1145/2133416.2146416",
        "[4] Yigitbasioglu, O. & Velcu, O. (2012) — A Review of Dashboards in Performance Management: Implications for Design and Research. Intl. J. Accounting Information Systems, 13(1), 41–59. https://doi.org/10.1016/j.accinf.2011.08.002",
        "[5] Wang, D. et al. (2019) — DataShot: Automatic Generation of Fact Sheets from Tabular Data. IEEE Trans. Visualization & Computer Graphics, 26(1), 895–905. https://doi.org/10.1109/TVCG.2019.2934398",
        "[6] Petropoulos, F. et al. (2022) — Forecasting: Theory and Practice. International Journal of Forecasting, 38(3), 705–871. https://doi.org/10.1016/j.ijforecast.2021.11.001",
        "[7] Paparrizos, J. et al. (2022) — TSB-UAD: An End-to-End Benchmark Suite for Univariate Time-Series Anomaly Detection. Proc. VLDB Endowment, 15(8), 1697–1711. https://doi.org/10.14778/3529337.3529354",
        "[8] Shi, B. et al. (2020) — Calliope: Automatic Visual Data Story Generation from a Spreadsheet. IEEE Trans. Visualization & Computer Graphics, 27(2), 453–463. https://doi.org/10.1109/TVCG.2020.3030403",
        "[9] Parciak, M. et al. (2024) — Schema Matching with Large Language Models: An Experimental Study. arXiv preprint arXiv:2407.10914. https://arxiv.org/abs/2407.10914",
        "[10] Lim, J. et al. (2024) — Dive into Time-Series Anomaly Detection: A Decade Review. ACM SIGKDD Explorations Newsletter, 26(1), 60–82. https://doi.org/10.1145/3682112.3682122"
    ], c_navy_dark)

    # ════════════════════════════════════════════════════════════════
    # SLIDE 19: THANK YOU & Q&A
    # ════════════════════════════════════════════════════════════════
    s19 = prs.slides.add_slide(blank_slide_layout)
    bg19 = s19.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
    bg19.fill.solid()
    bg19.fill.fore_color.rgb = c_navy_dark
    bg19.line.fill.background()

    tb_ty = s19.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(11.333), Inches(3.0))
    tf_ty = tb_ty.text_frame
    p_ty = tf_ty.paragraphs[0]
    p_ty.text = "Thank You!"
    p_ty.font.size = Pt(48)
    p_ty.font.bold = True
    p_ty.font.color.rgb = c_white
    p_ty.alignment = PP_ALIGN.CENTER

    p_qa = tf_ty.add_paragraph()
    p_qa.text = "Questions & Answers (Viva Voce)"
    p_qa.font.size = Pt(22)
    p_qa.font.color.rgb = c_teal
    p_qa.alignment = PP_ALIGN.CENTER
    p_qa.space_before = Pt(12)

    p_live = tf_ty.add_paragraph()
    p_live.text = "Live Dashboard Demo Ready: https://senova-ai-dashboard.vercel.app\nGovernment Engineering College, Raichur"
    p_live.font.size = Pt(13)
    p_live.font.color.rgb = RGBColor(148, 163, 184)
    p_live.alignment = PP_ALIGN.CENTER
    p_live.space_before = Pt(20)

    # Save Presentation
    output_path = "SENOVA_AI_Dashboard_Phase2_Final.pptx"
    prs.save(output_path)
    print(f"Presentation saved successfully to {output_path}")

if __name__ == "__main__":
    build_presentation()
