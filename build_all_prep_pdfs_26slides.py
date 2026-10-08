import sys
import os
import reportlab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

sys.stdout.reconfigure(encoding='utf-8')

from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#6B7280"))
        
        if self._pageNumber > 1:
            self.drawString(54, 750, "SENOVA AI Dashboard — Complete Master Presentation Guide (26 Slides)")
            self.setStrokeColor(colors.HexColor("#E5E7EB"))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)
            
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 36, page_text)
        self.drawString(54, 36, "CONFIDENTIAL — For Internal Presentation & Viva Voce Defense")
        self.setStrokeColor(colors.HexColor("#E5E7EB"))
        self.setLineWidth(0.5)
        self.line(54, 48, 558, 48)
        
        self.restoreState()

def create_pdf(filename, lang='EN'):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    c_primary = colors.HexColor("#0B192C")     # Deep Navy
    c_secondary = colors.HexColor("#0D9488")   # Teal
    c_dark = colors.HexColor("#111827")        # Charcoal
    c_bg_light = colors.HexColor("#F8FAFC")    # Off-white
    c_accent_bg = colors.HexColor("#EFF6FF")   # Light blue
    c_border = colors.HexColor("#CBD5E1")      # Slate border
    c_speaking = colors.HexColor("#065F46")    # Dark Green
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=c_primary,
        spaceAfter=4
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#4B5563"),
        spaceAfter=12
    )
    
    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=c_primary,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )
    
    h2_style = ParagraphStyle(
        'SlideHeader',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14.5,
        textColor=c_secondary,
        spaceBefore=7,
        spaceAfter=2,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.8,
        leading=12.5,
        textColor=c_dark,
        spaceAfter=2
    )
    
    bold_body = ParagraphStyle('BoldBody', parent=body_style, fontName='Helvetica-Bold')
    script_style = ParagraphStyle('SpeakingScript', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=8.8, leading=13, textColor=c_speaking)
    qa_question = ParagraphStyle('QAQuestion', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.8, leading=12.5, textColor=colors.HexColor("#991B1B"), spaceAfter=1)
    qa_answer = ParagraphStyle('QAAnswer', parent=styles['Normal'], fontName='Helvetica', fontSize=8.8, leading=12.5, textColor=c_dark, spaceAfter=3)

    story = []
    
    if lang == 'EN':
        story.append(Paragraph("SENOVA AI Dashboard — Complete 26-Slide Presentation & Viva Guide", title_style))
        story.append(Paragraph("Mapped 1-to-1 with 'SENOVA_AI_Dashboard_Phase2_v4_Master.pptx' (Preserving All Original Screenshots & Charts) | 15-Minute Timer", subtitle_style))
    else:
        story.append(Paragraph("SENOVA AI Dashboard — Master 26-Slide Presentation Prep Guide (Hinglish)", title_style))
        story.append(Paragraph("'SENOVA_AI_Dashboard_Phase2_v4_Master.pptx' Ka Exact 26-Slide Oral Speaking Script, Challenges & Viva Defense | 15-Min Timer", subtitle_style))
    
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_primary, spaceBefore=0, spaceAfter=8))

    # Time Map Table
    time_map_data = [
        ["Slide Range", "Section / Topic Focus", "Time Limit", "Key Oral Presentation Goal"],
        ["Slide 01–04", "Front Page, Intro, Problem Statement & Objectives", "2.0 mins", "Explain SME spreadsheet pain, 100% deterministic math & zero-formula vision"],
        ["Slide 05–08", "Literature Survey, Architecture, Methodology & Pipeline", "2.5 mins", "Show Clean Decoupled Architecture (Pandas vs Narrative) & 5-stage flow"],
        ["Slide 09–11", "Algorithms (265 Aliases, MAD, Forecast, ABC) & Milestones", "2.5 mins", "Demonstrate math formulas, 265 aliases and 199 unit tests (100% pass)"],
        ["Slide 12–20", "Live Implementation Modules 1 to 9 (Original Screenshots)", "4.5 mins", "Walk through real screenshots: Ingestion, Forecast, Chart Studio, PDF"],
        ["Slide 21–23", "Challenges Faced, Pros & Cons, and Future Scope", "2.0 mins", "Share 4-failure redesign story, 1-2 honest limits, and Desktop App roadmap"],
        ["Slide 24–26", "Conclusion, References, and Thank You / Q&A", "1.5 mins", "Simple powerful closing, invite examiners to live demo and viva defense"]
    ]
    t_map = Table(time_map_data, colWidths=[65, 185, 75, 174])
    t_map.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_primary),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light])
    ]))
    story.append(t_map)
    story.append(Spacer(1, 8))

    slides_26_en = [
        ("Slide 01", "Front Page — Department & Team Introduction", "0:00 - 0:30 min",
         "Department header (GEC Raichur), project title, guide Prof. Mamatha, and team members Shrihari, Basvaraj, Navin Chavan.",
         "Formally begins the presentation and sets an academic, institutional tone.",
         "\"Good morning respected guide and examiners. We present SENOVA AI Dashboard—an autonomous financial intelligence platform engineered for retail SMEs to deliver zero-formula financial analytics with 100% mathematical precision.\"",
         [("Q: What is the primary purpose of SENOVA?", "A: To provide small and medium enterprises with an autonomous, audit-proof 'Digital CFO' that eliminates spreadsheet formula fatigue and calculation hallucinations.")]),

        ("Slide 02", "Introduction — Executive Overview & System Purpose", "0:30 - 1:00 min",
         "Overview of SENOVA, SME spreadsheet bottlenecks, decoupled compute paradigm, and Digital CFO impact.",
         "Gives examiners a high-level summary of the entire product before entering technical layers.",
         "\"Small retail businesses generate thousands of daily transaction rows across Tally, Vyapar, and Shopify, but lack dedicated data teams. Power BI is too complex, while pure AI models hallucinate on math. SENOVA solves this by separating 100% accurate Python calculations from narrative AI summaries.\"",
         [("Q: Why call it an autonomous Digital CFO?", "A: It automatically ingests raw sales files, detects anomalies, calculates profit-and-loss, forecasts 30-day cash flow, and generates formal accounting PDF reports without human formula writing.")]),

        ("Slide 03", "Problem Statement — The SME Spreadsheet Dilemma", "1:00 - 1:30 min",
         "The 3 core barriers: Manual VLOOKUP fatigue in Excel, steep DAX learning curve in Power BI, and 5-15% arithmetic math error in pure LLMs.",
         "Justifies the research and engineering necessity of developing SENOVA.",
         "\"Why do existing tools fail small businesses? Excel requires manual formulas that break easily. Power BI requires expensive licenses and steep DAX modeling. And generative LLMs produce 5-15% arithmetic errors, which is unacceptable in accounting where even 1% deviation causes audit failure.\"",
         [("Q: Why do pure LLMs fail at basic arithmetic?", "A: LLMs are probabilistic token predictors, not mathematical state engines. When adding long lists of numbers, they predict the most likely text sequence rather than evaluating exact arithmetic logic.")]),

        ("Slide 04", "Objectives & Scope — Core Project Deliverables", "1:30 - 2:00 min",
         "6 key deliverables: Zero-setup ingestion, 265-alias schema matching, 100% deterministic math, MAD anomaly detection, 30-day forecasting, and CA-grade PDF export.",
         "Clearly defines the project boundaries and what SENOVA accomplishes.",
         "\"Our project accomplishes six key deliverables: 5-second file upload with auto-sniffing, header canonicalization using 265 exact aliases, guaranteed 100% accurate Python math, robust MAD anomaly alerts, recency-weighted forecasting, and publication-grade vector PDF exports.\"",
         [("Q: What is the role of human confirmation in your objectives?", "A: When column matching confidence is below 90%, the system prompts the user with confidence badges and dropdown overrides rather than making unsafe automated guesses.")]),

        ("Slide 05", "Literature Survey — Research Works & Benchmark", "2:00 - 2:30 min",
         "Academic citations (McKinney, Kandel, Heer, Petropoulos, Paparrizos) and commercial benchmark matrix.",
         "Anchors the project in computer science literature and proves superiority over existing tools.",
         "\"Our research builds on foundational works: Wes McKinney on Pandas data structures, Petropoulos on forecasting, and Paparrizos on anomaly detection benchmarks. In our comparative benchmark, SENOVA delivers 5-second setup and 100% math accuracy, outperforming both Excel and Power BI.\"",
         [("Q: Which paper influenced your anomaly detection engine?", "A: Paparrizos et al. (2022) 'TSB-UAD Benchmark' demonstrated that Median Absolute Deviation (MAD) is far superior to standard deviation for skewed retail sales distributions.")]),

        ("Slide 06", "System Architecture — Decoupled Client-Server Stack", "2:30 - 3:00 min",
         "5-layer Clean Layered Architecture: React 18 Presentation, Firebase Auth Guard, FastAPI REST API, Pandas Analytics Engine, and ReportLab PDF Engine.",
         "Demonstrates modern, modular software engineering architecture.",
         "\"Our system employs a Clean Layered Architecture: React 18 delivers a responsive UI, Firebase handles zero-knowledge OAuth, FastAPI powers the REST endpoints, Pandas executes deterministic calculations, and ReportLab compiles multi-page accounting reports.\"",
         [("Q: Why choose FastAPI over Flask or Django?", "A: FastAPI supports native Python async/await, Pydantic type validation, automatic OpenAPI Swagger documentation, and sub-millisecond route latency.")]),

        ("Slide 07", "Core Methodology — Strict Decoupled Computation", "3:00 - 3:30 min",
         "Layer 1 (Deterministic Compute Engine in Pandas) vs Layer 2 (Narrative Analytics Engine reading pre-aggregated JSON objects).",
         "Explains our primary technical contribution: eliminating calculation hallucinations by design.",
         "\"The core methodology of SENOVA is Axiomatic Compute Separation. Layer 1 executes all calculations using Pandas with 100% mathematical certainty. Layer 2 receives read-only numbers and converts them into executive narrative stories. The narrative layer cannot alter numbers, guaranteeing zero math errors.\"",
         [("Q: Can the narrative engine modify the calculated total revenue?", "A: No! Layer 2 receives read-only immutable JSON objects from Layer 1. It has no permission or computational capability to alter numbers.")]),

        ("Slide 08", "System Pipeline — 5-Stage Data Lifecycle Flowchart", "3:30 - 4:00 min",
         "5-stage visual flowchart: Ingest & Sniff → Canonicalize (265 Aliases) → Human Confirmation → Compute & MAD → Deliver & PDF.",
         "Shows the complete step-by-step path of data from raw spreadsheet upload to live UI and PDF.",
         "\"Here is our end-to-end data lifecycle: Raw files are auto-sniffed for delimiter and encoding, mapped against 265 aliases, confirmed by the user if confidence is low, processed by Pandas and MAD engines, cached in memory, and delivered in under 300 milliseconds.\"",
         [("Q: What happens if a file has non-standard encodings?", "A: The sniffer automatically tries UTF-8, UTF-8-SIG (with BOM), and falls back to Latin-1/CP1252, ensuring legacy Windows POS exports never crash the system.")]),

        ("Slide 09", "Algorithms (1/2) — Schema Matching & MAD Anomaly Detection", "4:00 - 4:45 min",
         "265-alias O(1) hash map + 66 fuzzy keywords (`guess_canonical_column()`) and MAD Anomaly Detection formula (`_anomaly_insights()`).",
         "Provides exact mathematical formulas and backend implementation details.",
         "\"We use two key algorithms: First, an O(1) hash map of 265 column aliases with 66 priority fuzzy keywords to standardize retail headers. Second, Median Absolute Deviation (MAD) anomaly detection—calculated as z = 0.6745 * (x - median) / MAD—which is mathematically immune to retail sales outliers.\"",
         [("Q: Why use MAD instead of standard deviation?", "A: Standard deviation squares differences, meaning a single massive order distorts the entire baseline. Median and MAD provide robust, outlier-resistant baselines.")]),

        ("Slide 10", "Algorithms (2/2) — Seasonal Forecasting & ABC Pareto Inventory", "4:45 - 5:30 min",
         "Recency-Weighted Least Squares Forecasting (`compute_forecast()`) and ABC Pareto Inventory Classification (`_classify_abc()`).",
         "Explains how statistical algorithms directly optimize retailer cash flow and inventory reorders.",
         "\"For forecasting, we fit a trend line using recency-weighted least squares with a 14-day exponential half-life, adjusted by weekday seasonality multipliers. For inventory, we classify SKUs into ABC Pareto tiers (80/20 rule) and compute restock priority scores based on sales velocity and lead-time cover.\"",
         [("Q: How does recency weighting help in retail forecasting?", "A: Retail demand changes rapidly. Giving higher exponential weight to the recent 14 days ensures projections capture current buying momentum rather than outdated historical noise.")]),

        ("Slide 11", "Project Status — Phase 2 Milestones & 199 Unit Tests", "5:30 - 6:00 min",
         "100% verified Phase 2 milestones, 199 unit tests passing across all backend modules, and 50,000-row stress testing.",
         "Proves software engineering rigor, test coverage, and enterprise readiness.",
         "\"Slide 11 reviews our project milestones. All Phase 2 features are 100% completed and verified with 199 automated unit tests across validation, P&L math, and cache concurrency. In stress tests on 50,000 transaction rows, the system delivered sub-300ms query response times.\"",
         [("Q: What did your accuracy audit tests verify?", "A: They audited P&L gross-to-net derivation, verified that GST is never counted as income, and ensured discount deductions match accounting standards.")]),

        ("Slide 12", "Module 1: Secure Firebase Authentication (Screenshot)", "6:00 - 6:30 min",
         "Screenshot of Login/Signup screen showing Google OAuth, email/password, zero password storage on backend, and Bearer JWT token verification.",
         "Proves enterprise authentication compliance and tenant isolation.",
         "\"Module 1 handles security via Firebase Authentication. We enforce zero-knowledge credential handling—passwords stay on Firebase servers, while our backend validates incoming Bearer JWT tokens to isolate each user's financial data.\"",
         [("Q: What happens if an API request is made without a token?", "A: The FastAPI middleware instantly rejects the request with HTTP 401 Unauthorized before any data or compute pipeline is touched.")]),

        ("Slide 13", "Module 2: 4-Step Pipeline Ingestion (Screenshot)", "6:30 - 7:00 min",
         "Screenshot of Upload screen showing 4-step visual stepper (Upload → Confirm → Validate → Dashboard) and delimiter auto-sniffing.",
         "Demonstrates the frictionless user onboarding flow.",
         "\"Module 2 provides a 4-step visual ingestion stepper. The Python backend automatically sniffs whether the file is comma, tab, or pipe separated, tries UTF-8 and Latin-1 encodings, and performs pre-flight row validation in under 500ms.\"",
         [("Q: Can the user upload Excel files directly?", "A: Yes, SENOVA natively supports both CSV and XLSX/XLS spreadsheet formats.")]),

        ("Slide 14", "Module 3: Human-in-Loop Mapping (Screenshot)", "7:00 - 7:30 min",
         "Screenshot of Confirm Columns screen with green exact match badges, amber check badges, live row preview, and dynamic unit price math.",
         "Highlights human-in-the-loop safety.",
         "\"Module 3 shows Human-in-the-Loop mapping. Headers matched with high confidence get green badges; ambiguous columns get amber badges. If Unit Price is missing, SENOVA dynamically computes it as Line Total divided by Quantity.\"",
         [("Q: What prevents duplicate mapping of the same column?", "A: The React mapping UI disables previously selected canonical fields in other dropdowns, preventing duplicate mapping collisions.")]),

        ("Slide 15", "Module 4: Overview & Findings Dashboard (Screenshot)", "7:30 - 8:00 min",
         "Screenshot of Overview screen showing top KPI metric cards, dynamic time slicing (Today/7D/30D/Month/All), and 'What Changed' anomaly cards.",
         "Shows primary operational dashboard for merchants.",
         "\"Module 4 is the main Overview Dashboard. It presents top KPI cards, instant time-range filtering, and automated anomaly cards—for example, flagging a 37% revenue drop on May 14th with recommended root-cause actions.\"",
         [("Q: How is sub-second UI performance achieved on 50,000 sales rows?", "A: Processed dataframes are cached in a thread-safe LRU (Least Recently Used) in-memory cache, enabling instant slicing without re-parsing raw files.")]),

        ("Slide 16", "Module 5: 30-Day Revenue Forecasting (Screenshot)", "8:00 - 8:30 min",
         "Screenshot of 30-day forecast chart with 7/14/30-day horizons, 80% shaded statistical confidence band, and 85.5% backtest accuracy score.",
         "Demonstrates predictive cash flow intelligence.",
         "\"Module 5 provides multi-horizon cash flow forecasting. It plots projected daily revenue alongside an 80% shaded statistical confidence band and displays real-time backtest accuracy against recent actual sales.\"",
         [("Q: How is backtest accuracy calculated on this screen?", "A: We hold back the last 7 days of actual sales, run the forecast model on prior data, compare predictions against actuals, and display MAPE percentage accuracy.")]),

        ("Slide 17", "Module 6: Chart Studio & Drill-Down Drawer (Screenshot)", "8:30 - 9:00 min",
         "Screenshot of Chart Studio with 8 modalities, dual-axis gross profit margin % curve, and slide-out granular transaction audit drawer.",
         "Shows drill-down capability from macro charts to single transaction receipts.",
         "\"Module 6 is our Interactive Chart Studio. Users can switch between 8 chart views, overlay profit margin curves on top of revenue bars, and click any bar to slide out a complete audit ledger of individual transactions.\"",
         [("Q: What is the benefit of the Dual-Axis view?", "A: It lets owners spot high-revenue categories that have dangerously low gross profit margins, preventing unlucrative volume growth.")]),

        ("Slide 18", "Module 7: Inventory Intelligence (Screenshot)", "9:00 - 9:30 min",
         "Screenshot of Inventory Intel dashboard showing ABC Pareto split cards, stock ageing tracker, dead stock table, and reorder priority scores.",
         "Shows how working capital is freed up by eliminating dead stock.",
         "\"Module 7 delivers Inventory Intelligence. It categorizes items into ABC Pareto classes, calculates days since last sale to isolate dead stock, and provides weighted priority scores to guide working capital reinvestment.\"",
         [("Q: What is 'Days of Cover'?", "A: Days of Cover calculates how many days current inventory will last based on average daily sales velocity before running out of stock.")]),

        ("Slide 19", "Module 8: Formal Financial Report Ledger (Screenshot)", "9:30 - 10:00 min",
         "Screenshot of formal P&L statement (Gross Sales → Net Turnover → COGS → Gross Profit), category breakdown, and tax GST memo separation.",
         "Shows accounting-compliant formats for CAs and banks.",
         "\"Module 8 renders a formal accounting P&L statement. It cleanly deducts discounts from gross sales to yield net revenue, breaks down COGS, and isolates collected GST as memo items to prevent tax distortion.\"",
         [("Q: Why is tax GST separation critical in retail P&L?", "A: Collected GST is a liability owed to the government, not revenue. Including tax in turnover distorts gross profit margins and leads to tax filing errors.")]),

        ("Slide 20", "Module 9: CA-Grade Vector PDF Generation (Screenshot)", "10:00 - 10:30 min",
         "Screenshot of sample generated PDF built with ReportLab engine—featuring selectable text, clean tables, sanitized currency glyphs ('Rs.'), and printable A4 page budget.",
         "Shows publication-ready PDF delivery.",
         "\"Module 9 compiles publication-ready PDF reports using the ReportLab engine. Unlike tools that export blurry screenshots, SENOVA generates true vector documents with selectable text, clean tables, and sanitized currency glyphs ready for bank loans.\"",
         [("Q: Why build a custom ReportLab pipeline instead of using html2pdf?", "A: Browser-based html2pdf tools render slow raster screenshots, fail on multi-page page breaks, and create huge file sizes. ReportLab produces crisp, 500KB vector PDFs instantly.")]),

        ("Slide 21", "Challenges Faced — The Real Development Journey", "10:30 - 11:30 min",
         "The 4 major challenges overcome: Architecture redesign (failed 4 times → 5th Clean Decoupled iteration), Pandas arithmetic edge cases, Ingestion variations, Firebase rate limits + active challenges (unmapped columns & DB card limits).",
         "Shows authentic software engineering struggle and problem-solving maturity.",
         "\"Building SENOVA presented four major engineering hurdles: First, our system architecture failed 4 times due to tight coupling; only on the 5th iteration did we successfully arrive at our Clean Decoupled Architecture. Second, Pandas groupby math had edge-case discrepancies with discounts and zero-sales days, which we solved via 199 unit tests. Third, heterogeneous POS headers required our 265-alias dictionary. And fourth, our current active challenge is handling unmapped operational columns and cloud database persistence.\"",
         [("Q: Why did the architecture fail in earlier iterations?", "A: In iterations 1 to 4, file parsing, business calculations, and UI state were tightly coupled. Any change in column names broke the dashboard. Decoupling compute into independent domain services solved this completely.")]),

        ("Slide 22", "Pros and Cons — Comprehensive System Evaluation", "11:30 - 12:15 min",
         "Balances 6 major software strengths (100% deterministic math, 265 aliases, sub-second cache, 8 chart modalities, vector PDF, security) against 2 honest limitations (fixed 6-field canonical scope, English-centric aliases).",
         "Demonstrates academic maturity by discussing software limitations honestly.",
         "\"Evaluating SENOVA: Our pros include 100% deterministic math accuracy, 265 POS aliases, sub-second query performance, and CA-grade PDF generation. On the cons side, our analytics currently focus strictly on the 6 core financial fields, and our alias lookup is English-centric, requiring manual mapping for regional Hinglish headers.\"",
         [("Q: Why restrict to 6 core canonical fields currently?", "A: To guarantee 100% mathematical auditability for core P&L accounting before expanding into peripheral operational attributes.")]),

        ("Slide 23", "Future Scope — Product Roadmap & Expansion", "12:15 - 13:00 min",
         "Details 3 clear expansion goals: Packaging as a native Desktop Application (Electron/Tauri) for offline retail counters, 2-Tier Hybrid AI (FastEmbed + Gemini Flash), and PostgreSQL + Cloudflare R2 persistence.",
         "Presents an exciting commercial product roadmap for retail deployment.",
         "\"Our future roadmap focuses on three areas: First, converting SENOVA into a native Desktop Application via Electron or Tauri for offline retail counters with direct Tally sync. Second, integrating a 2-Tier Hybrid AI engine with local FastEmbed and Gemini Flash to automatically classify unstructured notes. And third, migrating to PostgreSQL and Cloudflare R2 for multi-year historical ledgers.\"",
         [("Q: Why build a desktop application?", "A: Many small retail counters in Tier-2 and Tier-3 cities experience intermittent internet. An offline-first desktop app allows them to run daily analytics locally without cloud dependency.")]),

        ("Slide 24", "Conclusion & Technical Impact (Simplified & Powerful)", "13:00 - 13:45 min",
         "4 simple, powerful takeaways: Zero-Formula Simplicity, 100% Deterministic Math, Production Reliability (199 tests), and True Digital CFO Impact for SMEs.",
         "Leaves examiners with a memorable, confident closing statement.",
         "\"In conclusion, SENOVA AI Dashboard proves that small business financial intelligence can be completely automated with zero formula setup and 100% mathematical precision. By decoupling deterministic Python math from narrative AI, we give small enterprise owners institutional-grade financial clarity. Thank you!\"",
         [("Q: What is the main takeaway of your project?", "A: That financial intelligence can be democratized for small business owners without sacrificing mathematical auditability or computational rigor.")]),

        ("Slide 25", "References — Formal Research Citations", "13:45 - 14:00 min",
         "Lists formal IEEE and ACM citations referenced in the final thesis report.",
         "Provides academic evidence for examiners.",
         "\"Here are the formal research citations from our project report, spanning data wrangling, time-series forecasting, and robust anomaly detection.\"",
         [("Q: What is the latest reference you cited?", "A: Parciak et al. (2024) on Schema Matching with Large Language Models, which directly informed our future 2-Tier Hybrid AI roadmap.")]),

        ("Slide 26", "Thank You & Q&A — Viva Voce Closing", "14:00 - 15:00 min",
         "Closing slide with live demo URL (senova-ai-dashboard.vercel.app) and invitation for examiner questions.",
         "Transitions smoothly into the viva questioning and live software demonstration.",
         "\"Thank you respected guide and examiners. Our live web dashboard is deployed and ready for live demonstration. We now welcome your questions.\"",
         [("Q: Ready for live demo?", "A: Yes! We have sample Tally, Vyapar, and Shopify CSV files ready to demonstrate live ingestion and drill-down analytics.")])
    ]

    # For Hinglish, duplicate slide by slide structure
    slides_26_hinglish = [
        ("Slide 01", "Front Page — Department & Team Intro", "0:00 - 0:30 min",
         "Department header (GEC Raichur), Project title, Guide (Prof. Mamatha Madam), aur teeno team members ke USN.",
         "Presentation ko formal tarike se shuru karne aur examiners ko project ka context batane ke liye.",
         "\"Good morning guide and examiners. Aaj hum SENOVA AI Dashboard present kar rahe hain—yeh small businesses ke liye ek autonomous financial decision engine hai jo zero-formula setup ke saath 100% accurate math analytics deta hai.\"",
         [("Q: SENOVA ka main aim kya hai?", "A: Small business owners ko ek automated 'Digital CFO' dena jisse unhe Excel me manual formula na lagane padein aur zero math error mile.")]),

        ("Slide 02", "Introduction — Product Purpose & Overview", "0:30 - 1:00 min",
         "SENOVA kya karta hai, SME data problem, Decoupled Compute paradigm, aur Digital CFO impact ka clean summary.",
         "Examiners ko technical details se pehle poore product ka quick overview dene ke liye.",
         "\"Small retail shops roz hazaron sales rows Tally ya Vyapar se generate karti hain par unke paas data team nahi hoti. Power BI bohot complex hai aur normal ChatGPT math galat karta hai. SENOVA 100% accurate Python math ko AI text se alag karke isko solve karta hai.\"",
         [("Q: Digital CFO kya kaam karta hai?", "A: Sales CSV read karta hai, profit margins calculate karta hai, sales drop pakadta hai aur formal financial PDF reports automatically compile karta hai.")]),

        ("Slide 03", "Problem Statement — Existing Tools Kyun Fail Hote Hain", "1:00 - 1:30 min",
         "3 bade barriers: Excel me manual VLOOKUP ka headache, Power BI me DAX complexity, aur ChatGPT me 5-15% arithmetic math error.",
         "Examiners ko yeh prove karne ke liye ki purane software me kya kami hai aur SENOVA kyu zaroori hai.",
         "\"Purane tools SMEs ke liye fail kyu hote hain? Excel me manual formulas lagana mushkil hai aur ek galti se pura data kharab hota hai. Power BI bohot mehnga aur complex hai. Aur normal ChatGPT math me hallucinate karta hai (5-15% error), jo accounting me audit fail kara deta hai.\"",
         [("Q: ChatGPT math me galti kyu karta hai?", "A: LLMs word predictor hote hain, calculator nahi. Jab hazaron numbers add karte hain toh wo answer calculate karne ki bajaye guess karte hain.")]),

        ("Slide 04", "Objectives & Scope — Project Ke 6 Main Goals", "1:30 - 2:00 min",
         "6 core deliverables: 5-sec ingestion, 265 aliases, 100% deterministic math, MAD anomaly, 30-day forecast, aur CA-grade PDF export.",
         "Project ke exact scope aur boundaries ko examiners ke samne clear karne ke liye.",
         "\"Humari project ke 6 main goals hain: bina template CSV upload, 265 header aliases se auto mapping, guaranteed 100% accurate Python math, MAD sales anomaly alerts, seasonal forecasting, aur print-ready PDF reports.\"",
         [("Q: Data privacy kaise maintain hoti hai?", "A: Firebase Auth se verified JWT Bearer tokens lagte hain, aur har file caller ki UID se bind hoti hai taaki koi doosra user data na dekh sake.")]),

        ("Slide 05", "Literature Survey — Research Papers & Benchmark", "2:00 - 2:30 min",
         "5 academic papers (Wes McKinney, Kandel, Heer, Petropoulos, Paparrizos) aur benchmark matrix (Excel vs Power BI vs SENOVA).",
         "Project ki research credibility prove karne aur commercial tools se better benchmark dikhane ke liye.",
         "\"Humara project established research papers par based hai—Wes McKinney ke Pandas paper se le kar Paparrizos ke anomaly detection benchmark tak. Benchmark table dikhata hai ki SENOVA 5-second setup aur 100% math accuracy ke saath Excel aur Power BI dono se superior hai.\"",
         [("Q: Forecasting ke liye kaunsa paper refer kiya?", "A: Petropoulos et al. (2022) International Journal of Forecasting, jisme prove kiya gaya hai ki recency weighting micro-retail ke liye deep learning se better perform karti hai.")]),

        ("Slide 06", "System Architecture — Decoupled Client-Server Stack", "2:30 - 3:00 min",
         "5-layer Clean Architecture (React UI, Firebase Auth, FastAPI REST Controller, Pandas Services, ReportLab PDF) aur Axiomatic 2-Layer Compute Separation.",
         "Software engineering standards aur zero math hallucination guarantee explain karne ke liye.",
         "\"SENOVA Clean Layered Architecture use karta hai. Sabse main innovation hai Decoupled Computation: Layer 1 saari calculation Pandas me exact 100% accuracy ke saath karta hai. Layer 2 sirf pre-computed summary padhkar text alerts banata hai, jisse math hallucination impossible ho jati hai.\"",
         [("Q: Codebase me kaunsa architecture pattern use hua hai?", "A: Clean Layered Architecture / Service-Oriented Architecture (SOA)—jisme API routes, domain calculation services aur presentation completely separated hain.")]),

        ("Slide 07", "Core Methodology — Strict Decoupled Computation", "3:00 - 3:30 min",
         "Layer 1 (Pandas/Python) deterministic compute vs Layer 2 (Narrative Engine) read-only executive text generation.",
         "Examiners ko math aur text ke beech ka firewall samjhane ke liye.",
         "\"Methodology me hum strict computation firewall follow karte hain: Pandas math rollups execute karta hai. Narrative AI engine ko sirf numbers padhne ki ijazat hai, badalne ki nahi. Isse audit-proof numbers guarantee hote hain.\"",
         [("Q: Kya narrative engine total revenue change kar sakta hai?", "A: Bilkul nahi! Narrative engine read-only JSON object receive karta hai, calculations alter karne ka code hi exist nahi karta.")]),

        ("Slide 08", "System Pipeline — 5-Stage Data Lifecycle Flowchart", "3:30 - 4:00 min",
         "5 stages: Ingest & Sniff → Canonicalize (265 Aliases) → Human Confirmation → Compute & MAD → Deliver & PDF.",
         "Raw CSV upload se le kar final dashboard render hone tak ka visual process flow samjhane ke liye.",
         "\"Yeh humara 5-stage data pipeline hai: Raw CSV upload hoti hai, sniffer delimiter auto-detect karta hai, 265 aliases se column match hote hain, user low confidence match confirm karta hai, Pandas math execute hota hai aur LRU cache se UI pe sub-second me show hota hai.\"",
         [("Q: Agar file alag encoding me ho toh kya hota hai?", "A: Auto-sniffer pehle UTF-8, phir UTF-8-SIG aur end me Latin-1/CP1252 try karta hai, jisse koi bhi purani Tally file crash nahi hoti.")]),

        ("Slide 09", "Algorithms (1/2) — 265 Aliases & MAD Anomaly Detection", "4:00 - 4:45 min",
         "265-alias O(1) hash map + 66 fuzzy keywords (`guess_canonical_column()`) aur MAD Anomaly Detection formula (`_anomaly_insights()`).",
         "Backend ke algorithmic logic aur mathematical formulas ko explain karne ke liye.",
         "\"Hum do core algorithms use karte hain: Pehla, 265 column aliases ka O(1) hash dictionary messy headers ko match karne ke liye. Dusra, Median Absolute Deviation (MAD) anomaly detection formula (z = 0.6745 * (x - median) / MAD) jo sudden sales drop ko pakadta hai.\"",
         [("Q: Standard Deviation ki jagah MAD kyu use kiya?", "A: Standard deviation mean aur square difference use karta hai jo sudden sales spike se distort ho jata hai. Median aur MAD extreme outliers ke khilaf robust hote hain.")]),

        ("Slide 10", "Algorithms (2/2) — Seasonal Forecasting & ABC Pareto Inventory", "4:45 - 5:30 min",
         "Recency-Weighted Least Squares Forecasting (`compute_forecast()`) aur ABC Pareto Inventory Classification (`_classify_abc()`).",
         "Future revenue prediction aur godown dead stock management explain karne ke liye.",
         "\"Forecasting ke liye hum recency-weighted least squares regression fit karte hain 14-day exponential decay aur weekday seasonality ke saath. Inventory ke liye ABC Pareto analysis (top 80% sales = Class A) aur priority scoring se dead stock isolate karte hain.\"",
         [("Q: ABC analysis se shopkeeper ko kya fayda hota hai?", "A: Dukandar ka paisa Class A (top 80% bikne wale items) par invest hota hai aur Class C ke slow-moving dead stock ko discount karke capital free ho jata hai.")]),

        ("Slide 11", "Project Status — Phase 2 Milestones & 199 Unit Tests", "5:30 - 6:00 min",
         "Verified complete modules, 100% test pass rate across 199 automated unit tests (pytest), aur 50,000-row stress testing benchmarks.",
         "Software engineering quality, test coverage aur production readiness prove karne ke liye.",
         "\"Slide 11 humare development standards ko dikhati hai. Phase 2 ke saare modules 100% complete hain aur 199 unit tests se verified hain. 50,000 transaction rows par stress test karne par bhi system ne under 300ms query response time diya.\"",
         [("Q: Concurrency test me kya check kiya?", "A: Check kiya ki jab multiple users ek saath file upload karte hain toh in-memory LRU cache thread-safe rehta hai aur purane files ko clean evict karta hai.")]),

        ("Slide 12", "Module 1: Secure Firebase Authentication (Screenshot)", "6:00 - 6:30 min",
         "Login/Signup screen screenshot showing Google OAuth, email/password, zero password storage on backend, aur Bearer JWT token verification.",
         "Security compliance aur tenant data isolation dikhane ke liye.",
         "\"Module 1 Firebase Auth se security handle karta hai. Zero-knowledge authentication hai—passwords Firebase server par rehte hain, aur humara backend incoming Bearer JWT tokens verify karke har user ka financial data separate rakhta hai.\"",
         [("Q: Agar bina token ke koi API call kare toh kya hoga?", "A: FastAPI middleware turant HTTP 401 Unauthorized return kar dega bina kisi compute pipeline ko touch kiye.")]),

        ("Slide 13", "Module 2: 4-Step Pipeline Ingestion (Screenshot)", "6:30 - 7:00 min",
         "Upload screen screenshot showing 4-step visual stepper (Upload → Confirm → Validate → Dashboard) aur delimiter auto-sniffing.",
         "User ke liye file upload kitna aasan aur automated hai yeh dikhane ke liye.",
         "\"Module 2 me 4-step visual stepper hai. Python backend automatic sniff karta hai ki file comma, tab ya pipe separated hai, UTF-8 aur Latin-1 encoding try karta hai, aur under 500ms file validate karta hai.\"",
         [("Q: User Excel file direct upload kar sakta hai?", "A: Ji haan, SENOVA CSV aur XLSX dono formats ko seamlessly support karta hai.")]),

        ("Slide 14", "Module 3: Human-in-Loop Mapping (Screenshot)", "7:00 - 7:30 min",
         "Confirm Columns screen screenshot with green exact match badges, amber check badges, live row preview, aur dynamic unit price math.",
         "System automated hokar bhi user ke control me rehta hai yeh dikhane ke liye.",
         "\"Module 3 me Human-in-the-Loop column mapping hai. Exact matches ko green badge milta hai, ambiguous columns ko amber badge. Agar Unit Price missing hai, toh SENOVA dynamically Total ÷ Quantity karke compute kar leta hai.\"",
         [("Q: User 2 alag columns ko ek saath 'Revenue' map kar de toh kya hoga?", "A: React UI dropdown me select hue fields ko baki dropdowns me disable kar deta hai jisse duplicate collision prevent ho jata hai.")]),

        ("Slide 15", "Module 4: Overview & Findings Dashboard (Screenshot)", "7:30 - 8:00 min",
         "Live Overview dashboard screenshot: KPIs, dynamic time slicing (Today/7D/30D/Month/All), aur 'What Changed' anomaly cards.",
         "Business owner ka main daily operational view dikhane ke liye.",
         "\"Module 4 main Overview Dashboard hai. Yahan main KPIs, instant time slicing (7D, 30D, Month) aur automatic anomaly cards dikhte hain—jaise 14 May ko 37% revenue drop hua toh system root-cause recommendation ke saath alert kar deta hai.\"",
         [("Q: 50,000 transaction rows par instant dynamic filtering kaise hoti hai?", "A: Processed dataframes memory me thread-safe LRU (Least Recently Used) cache me stored hote hain, isliye dynamic filter bina file dobara parse kiye instant ho jata hai.")]),

        ("Slide 16", "Module 5: 30-Day Revenue Forecasting (Screenshot)", "8:00 - 8:30 min",
         "30-day forecast screenshot: 7/14/30-day view, 80% shaded confidence band, aur 85.5% backtest accuracy score.",
         "Future cash flow aur sales prediction capabilities dikhane ke liye.",
         "\"Module 5 future cash flow forecasting karta hai. Yeh daily projected revenue ko 80% confidence band ke saath plot karta hai aur recent actual sales ke against real-time backtest accuracy percentage (jaise 85.5%) display karta hai.\"",
         [("Q: Screen par backtest accuracy kaise calculate hoti hai?", "A: System pichle 7 dino ki sales ko side me rakh kar purane data par model run karta hai, prediction ko actual sales se compare karta hai aur MAPE accuracy show karta hai.")]),

        ("Slide 17", "Module 6: Chart Studio & Drill-Down Drawer (Screenshot)", "8:30 - 9:00 min",
         "Chart Studio screenshot with 8 modalities, dual-axis gross profit margin curve, aur slide-out transaction ledger drawer.",
         "Summary chart se direct single-receipt transaction register tak drill-down audit capability dikhane ke liye.",
         "\"Module 6 Interactive Chart Studio hai. Users 8 chart modalities me switch kar sakte hain, revenue bar ke upar profit margin % curve dekh sakte hain, aur kisi bhi bar par click karke slide-out drawer me saari individual transactions check kar sakte hain.\"",
         [("Q: Dual-Axis view ka kya real-world business use hai?", "A: Isse shop owner dekh sakta hai ki kis category me revenue bohot high hai par profit margin dangerous level tak kam hai, taaki low-margin loss sales se bacha ja sake.")]),

        ("Slide 18", "Module 7: Inventory Intelligence (Screenshot)", "9:00 - 9:30 min",
         "Inventory Intel dashboard screenshot: ABC Pareto split cards, stock ageing tracker, dead stock table, aur reorder priority score.",
         "Working capital optimization aur stockout prevention capability highlight karne ke liye.",
         "\"Module 7 Inventory Intelligence deta hai. Items ko ABC Pareto classes me divide karta hai, last sale ke baad ke din track karke dead stock isolate karta hai, aur priority scores ke basis par stock reorder karne ki advice deta hai.\"",
         [("Q: 'Days of Cover' kya indicate karta hai?", "A: Days of Cover yeh batata hai ki daily sales velocity ke hisaab se abhi jo stock godown me hai wo kitne dino me khatam ho jayega (out of stock hoga).")]),

        ("Slide 19", "Module 8: Formal Financial Report Ledger (Screenshot)", "9:30 - 10:00 min",
         "Formal P&L statement screenshot: Gross Sales → Net Turnover → COGS → Gross Profit breakdown, category ledger, aur tax GST memo isolation.",
         "CA aur bank verification ke liye formal financial accounting standard formats dikhane ke liye.",
         "\"Module 8 formal accounting P&L statement render karta hai. Gross sales me se discounts subtract karke net turnover nikalta hai, COGS breakdown deta hai, aur collected GST ko separate memo item rakhta hai taaki tax distortion na ho.\"",
         [("Q: Retail P&L me tax GST isolation kyu zaroori hai?", "A: Collected GST government ka paisa hai, dukandar ka revenue nahi. Agar tax ko revenue me ginte hain toh gross profit galat dikhta hai aur tax audit fail ho jata hai.")]),

        ("Slide 20", "Module 9: CA-Grade Vector PDF Generation (Screenshot)", "10:00 - 10:30 min",
         "ReportLab vector PDF screenshot: Real selectable text & tables, sanitized currency glyphs ('Rs.'), printable A4 pagination, 50,000+ row capacity.",
         "Blurry screenshot PDF ki jagah high-quality publication-ready accounting reports deliver karne ke liye.",
         "\"Module 9 ReportLab engine se publication-ready PDF compile karta hai. Browser ke blurry screenshot PDF ke bajaye SENOVA crisp vector PDF banata hai jisme text search ho sakta hai aur bank loans ya tax filing ke liye ready rehta hai.\"",
         [("Q: Browser html2pdf ki jagah custom ReportLab pipeline kyu banaya?", "A: Browser tools blurry image PDF banate hain, multi-page layout break karte hain aur file size bohot badi kar dete hain. ReportLab fast, crisp 500KB vector PDF banata hai.")]),

        ("Slide 21", "Challenges Faced — Real Development Journey", "10:30 - 11:30 min",
         "4 bade challenges: Architecture redesign (4 baar fail hua → 5th Clean Decoupled iteration me succeed hua), Pandas math edge cases, Ingestion variations, Firebase rate limits + active challenges.",
         "Yeh presentation ki sabse powerful slide hai jo aapki real engineering struggle aur problem-solving skills prove karegi.",
         "\"SENOVA build karte waqt humne 4 bade challenges face kiye: Pehla, humara system architecture 4 baar fail hua tight-coupling ki wajah se; 5th iteration me humne Clean Decoupled Architecture bana kar succeed kiya. Dusra, Pandas me discounts aur 0-sales days ke calculation edge cases the jise 199 unit tests se solve kiya. Teesra, alag-alag POS headers ka issue tha jise 265 aliases se solve kiya. Aur chautha, abhi hum unmapped columns aur cloud database persistence par kaam kar rahe hain.\"",
         [("Q: Pehle 4 iterations me architecture kyu fail hua?", "A: UI, file parser aur calculation sab aapas me tightly mixed the. Ek bhi column badalta tha toh pura dashboard crash ho jata tha. Calculations ko independent domain services me decouple karke yeh solve hua.")]),

        ("Slide 22", "Pros and Cons — Realistic Software Evaluation", "11:30 - 12:15 min",
         "6 core strengths (100% deterministic math, 265 aliases, sub-second cache, 8 charts, vector PDF, security) vs 2 genuine limitations (fixed 6-field canonical scope, English-centric aliases).",
         "Software ki honest limitations accept karke examiners ke samne maturity dikhane ke liye.",
         "\"Pros me: 100% accurate math, 265 header aliases, sub-second LRU cache aur CA-grade PDF export. Cons me: Abhi system 6 core financial fields par focus karta hai (extra operational fields ignore hote hain), aur aliases English-centric hain jisse Hinglish headers manual map karne padte hain.\"",
         [("Q: Abhi sirf 6 core fields hi kyu liye?", "A: Taaki core P&L aur financial accounting 100% audit-proof rahe, bina kisi unnecessary attribute ke calculations ko complicate kiye.")]),

        ("Slide 23", "Future Scope — Product Roadmap & Expansion", "12:15 - 13:00 min",
         "3 Future milestones: Desktop App (Electron/Tauri) offline retail counter ke liye, 2-Tier Hybrid AI (FastEmbed + Gemini Flash), aur PostgreSQL + Cloudflare R2 storage.",
         "Product ka next commercial development roadmap present karne ke liye.",
         "\"Future Scope me hum 3 cheezon par kaam karenge: Pehla, SENOVA ko Electron ya Tauri se native Desktop Application banana taaki local shopkeepers bina internet ke offline counter PC par chala sakein. Dusra, 2-Tier Hybrid AI se unstructured notes parse karna. Aur teesra, PostgreSQL aur Cloudflare R2 par multi-year historical data store karna.\"",
         [("Q: Desktop application banane ki kya zaroorat hai?", "A: Tier-2 aur Tier-3 cities me dukandaron ke paas internet issue hota hai. Offline desktop app unhe local counter par direct Tally sync ke saath fast billing analytics dega.")]),

        ("Slide 24", "Conclusion & Technical Impact (Simplified & Powerful)", "13:00 - 13:45 min",
         "4 simple & powerful points: Zero-Formula Simplicity, 100% Math Truth, Production Reliability (199 tests), aur True Digital CFO Impact for SMEs.",
         "Presentation ko strong, confident aur clear closing note par finish karne ke liye.",
         "\"Conclusion me, SENOVA AI Dashboard ne prove kiya hai ki small business financial intelligence ko bina kisi formula aur 100% mathematical precision ke saath fully automate kiya ja sakta hai. Python math ko AI text se decouple karke hum small business owners ko ek institutional-grade Digital CFO dete hain. Thank you!\"",
         [("Q: Project ka final takeaway kya hai?", "A: Ki financial intelligence ko bina mathematical accuracy khoye har small retailer ke liye accessible banaya ja sakta hai.")]),

        ("Slide 25", "References — Formal Research Citations", "13:45 - 14:00 min",
         "Formal IEEE aur ACM research citations jo final project report me diye gaye hain.",
         "Project ki theoretical authenticity prove karne ke liye.",
         "\"Yeh research papers hain jo humne literature survey, forecasting aur anomaly detection me cite kiye hain.\"",
         [("Q: Sabse latest research kaunsi refer ki?", "A: Parciak et al. (2024) Schema Matching with LLMs, jo humare future 2-Tier AI roadmap ka base hai.")]),

        ("Slide 26", "Thank You & Q&A — Viva Voce Closing", "14:00 - 15:00 min",
         "Thank you slide with live deployed URL (senova-ai-dashboard.vercel.app) aur examiners ke viva questions ke liye welcome note.",
         "Presentation se direct live demo aur viva examination question-answer round me enter karne ke liye.",
         "\"Thank you respected guide and examiners. Humara live web dashboard ready hai demonstration ke liye. Ab aapke sawaal welcome hain.\"",
         [("Q: Live demo dikha sakte ho?", "A: Ji bilkul! Humare paas Tally aur Shopify ki sample files ready hain live upload aur drill-down charts dikhane ke liye.")])
    ]

    target_slides = slides_26_en if lang == 'EN' else slides_26_hinglish

    for num, title, t_alloc, kya_hai, kyun_hai, script, qa_list in target_slides:
        flowables = []
        flowables.append(Paragraph(f"<b>{num} ({t_alloc})</b> — {title}", h2_style))
        flowables.append(HRFlowable(width="100%", thickness=0.8, color=c_secondary, spaceBefore=2, spaceAfter=3))
        
        if lang == 'EN':
            lbl_kya = "<b>Slide Overview:</b>"
            lbl_kyun = "<b>Why It Matters:</b>"
            lbl_script = "<b>Oral Speaking Script (30-40 sec delivery):</b>"
            lbl_qa = "<b>Viva / Examiner Q&A Defense:</b>"
        else:
            lbl_kya = "<b>Slide Mein Kya Hai:</b>"
            lbl_kyun = "<b>Kyun Hai (Purpose):</b>"
            lbl_script = "<b>Orally Muh Se Kya Bolna Hai (30-40 sec Script):</b>"
            lbl_qa = "<b>Viva / Examiner Expected Q&A:</b>"

        flowables.append(Paragraph(f"{lbl_kya} {kya_hai}", body_style))
        flowables.append(Paragraph(f"{lbl_kyun} {kyun_hai}", body_style))
        
        # Script callout box
        script_box = Table([[Paragraph(f"{lbl_script}<br/><i>{script}</i>", script_style)]], colWidths=[490])
        script_box.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), c_accent_bg),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#93C5FD")),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        flowables.append(script_box)
        flowables.append(Spacer(1, 3))
        
        # Q&A Block
        flowables.append(Paragraph(lbl_qa, bold_body))
        for q, a in qa_list:
            flowables.append(Paragraph(q, qa_question))
            flowables.append(Paragraph(a, qa_answer))
            
        flowables.append(Spacer(1, 6))
        story.append(KeepTogether(flowables))

    # Page Break for Strategy Section
    story.append(PageBreak())
    if lang == 'EN':
        story.append(Paragraph("<b>Presentation Mastery & Viva Defense Strategy</b>", h1_style))
        tips_data = [
            ["Strategy", "Execution Guidelines"],
            ["Time Management", "Spend strictly 30-40 seconds per slide. You have 26 slides, so keep the pace crisp and confident."],
            ["Body Language", "Look directly into the eyes of the external examiners. Point to the screenshots on the screen."],
            ["Math Defense Key", "Whenever asked about accuracy: 'AI does NOT do arithmetic calculation. Pandas executes 100% deterministic math.'"],
            ["Architecture Defense", "Proudly share: 'Our architecture failed 4 times due to tight coupling; on the 5th iteration we achieved Clean Decoupled Architecture.'"],
            ["Demo Readiness", "Keep https://senova-ai-dashboard.vercel.app open with a pre-loaded sample file ready to show instantly."]
        ]
    else:
        story.append(Paragraph("<b>Presentation Mastery & Viva Defense Tips (Hinglish)</b>", h1_style))
        tips_data = [
            ["Strategy", "Execution Guidelines"],
            ["Time Control", "Har slide par strictly 30-40 seconds spend karein. Pacing steady aur confident rakhein."],
            ["Eye Contact", "External Examiners ki taraf dekh kar bolo, TV screen ya laptop screen ko zyada der mat ghooro."],
            ["Math Defense Key", "Jab bhi calculation accuracy par sawaal aaye, bolo: 'AI calculation nahi karta, Pandas 100% accurate math karta hai.'"],
            ["Architecture Struggle", "Examiners ke samne openly bolo: 'Humein Clean Architecture banane me 4 baar failure mila, 5th iteration me perfect decoupling achieve hui.' Examiners bohot impress honge!"],
            ["Live Demo Ready", "Laptop me browser tab me https://senova-ai-dashboard.vercel.app pehle se open karke ready rakho."]
        ]

    t_tips = Table(tips_data, colWidths=[130, 364])
    t_tips.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_secondary),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light])
    ]))
    story.append(t_tips)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"26-Slide PDF built successfully: {filename}")

if __name__ == "__main__":
    create_pdf("SENOVA_Presentation_Prep_Guide_EN.pdf", lang='EN')
    create_pdf("SENOVA_Presentation_Prep_Guide_Hinglish.pdf", lang='Hinglish')
