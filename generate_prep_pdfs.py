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
            self.drawString(54, 750, "SENOVA AI Dashboard — Final Phase 2 Defense & Presentation Guide")
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
        fontSize=11,
        leading=15,
        textColor=c_secondary,
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=c_dark,
        spaceAfter=3
    )
    
    bold_body = ParagraphStyle('BoldBody', parent=body_style, fontName='Helvetica-Bold')
    script_style = ParagraphStyle('SpeakingScript', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=9, leading=13.5, textColor=c_speaking)
    qa_question = ParagraphStyle('QAQuestion', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=13, textColor=colors.HexColor("#991B1B"), spaceAfter=2)
    qa_answer = ParagraphStyle('QAAnswer', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=13, textColor=c_dark, spaceAfter=4)

    story = []
    
    if lang == 'EN':
        story.append(Paragraph("SENOVA AI Dashboard — Final Presentation & Viva Prep Guide", title_style))
        story.append(Paragraph("Mapped 1-to-1 with 'SENOVA_AI_Dashboard_Phase2_Final.pptx' (Madam's Approved Structure) | 15-Minute Timer Plan", subtitle_style))
    else:
        story.append(Paragraph("SENOVA AI Dashboard — Final Presentation Prep Guide (Hinglish)", title_style))
        story.append(Paragraph("Naye 19-Slide PPT ('SENOVA_AI_Dashboard_Phase2_Final.pptx') Ka Exact Oral Script & Viva Guide | 15-Min Timer", subtitle_style))
    
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_primary, spaceBefore=0, spaceAfter=10))

    # Time Map Table
    time_map_data = [
        ["Slide #", "Madam's Topic", "Time Allocation", "Key Speaking Focus"],
        ["Slide 1–4", "Front Page, Intro, Problem & Objectives", "2.5 mins", "Hook examiners, explain SME spreadsheet pain & zero-formula vision"],
        ["Slide 5–7", "Literature Survey, Clean Architecture & Flowchart", "3.0 mins", "Show 5th iteration Clean Decoupled Architecture & 5-stage pipeline"],
        ["Slide 8–10", "Algorithms (265 Aliases, MAD, Forecast, ABC) & Milestones", "3.0 mins", "Show technical rigor, exact math formulas, 199 unit tests passing"],
        ["Slide 11–13", "Results & Live UI Walkthrough (3 Screens)", "3.5 mins", "Show working system (Upload, Forecast, Studio drill-down drawer, PDF)"],
        ["Slide 14–16", "Challenges Faced, Pros & Cons, Future Scope", "2.0 mins", "Share real 4-failure redesign story, honest limits & desktop roadmap"],
        ["Slide 17–19", "Conclusion, References & Thank You / Q&A", "1.0 min", "Simple powerful closing, answer viva questions with confidence"]
    ]
    t_map = Table(time_map_data, colWidths=[65, 175, 80, 184])
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
    story.append(Spacer(1, 10))

    # --- SLIDES DATA (EN) ---
    slides_en = [
        ("Slide 1", "Front Page — Project Title & Team Credentials", "0:00 - 0:30 min",
         "Displays Department header (GEC Raichur), Project title, guide (Prof. Mamatha), and team USNs (Shrihari, Basvaraj, Navin Chavan).",
         "Establishes a dignified academic tone and introduces the core theme of deterministic financial intelligence.",
         "\"Respected guide and examiners, good morning. We present SENOVA AI Dashboard—an autonomous financial intelligence platform built for small retailers to deliver zero-formula financial analytics with 100% mathematical precision.\"",
         [("Q: What is the core ambition of SENOVA?", "A: To provide small and medium retail businesses with an automated, audit-proof 'Digital CFO' that eliminates spreadsheet formulas and math errors entirely.")]),

        ("Slide 2", "Introduction — Executive Overview & Product Purpose", "0:30 - 1:15 min",
         "Summarizes what SENOVA does, the SME data bottleneck, decoupled compute paradigm, and Digital CFO impact.",
         "Gives examiners an instant high-level picture before diving into technical details.",
         "\"Small retail enterprises generate thousands of sales rows daily from Tally, Vyapar, and Shopify, but lack data teams. Power BI is too complex, while pure AI models hallucinate on arithmetic. SENOVA solves this through a strict two-layer architecture separating 100% accurate Python math from narrative text stories.\"",
         [("Q: What is a Digital CFO?", "A: An automated pipeline that acts as a financial executive—canonicalizing messy headers, calculating gross-to-net P&L, detecting revenue drops, and compiling audit-ready PDF reports.")]),

        ("Slide 3", "Problem Statement — The SME Spreadsheet Dilemma", "1:15 - 1:50 min",
         "Breaks down the 3 existing barriers: Manual VLOOKUP fatigue in Excel, steep DAX learning curve in Power BI, and 5-15% math error rate in pure LLMs.",
         "Proves why existing market software fails and why building SENOVA was necessary.",
         "\"Why do existing tools fail small businesses? Excel requires manual VLOOKUPs and breaks easily. Power BI requires expensive licenses and steep DAX modeling. And pure generative AI models produce 5-15% arithmetic errors, which is fatal in accounting where even 1% error causes audit failure.\"",
         [("Q: Why do pure LLMs fail at arithmetic?", "A: LLMs predict words probabilistically; they do not possess an internal calculator or mathematical state machine. Adding long numeric series causes floating point hallucinations.")]),

        ("Slide 4", "Objective & Scope — Deliverables of the Project", "1:50 - 2:20 min",
         "Outlines 6 clear deliverables: Zero-setup ingestion, 265-alias matching, 100% deterministic math, MAD anomaly detection, 30-day forecasting, and CA-grade PDF export.",
         "Clarifies the precise engineering boundaries and scope of the project.",
         "\"Our project delivers six core objectives: 5-second file upload with auto-sniffing, header canonicalization using 265 exact aliases, guaranteed 100% accurate Python math, robust MAD anomaly alerts, recency-weighted forecasting, and publication-grade vector PDF exports.\"",
         [("Q: How does your scope handle data privacy?", "A: Firebase Auth injects verified Bearer JWT tokens, and every file is bound strictly to the caller UID so cross-tenant data access is blocked.")]),

        ("Slide 5", "Literature Survey — Research Works & Benchmark", "2:20 - 3:00 min",
         "Cites 5 foundational research papers (McKinney Pandas, Kandel Data Wrangling, Heer Visual Dynamics, Petropoulos Forecasting, Paparrizos Anomaly Benchmark) and benchmark matrix.",
         "Demonstrates strong academic grounding and compares setup time, accuracy, and reporting against commercial tools.",
         "\"Our literature survey grounds SENOVA in established computer science research—from Wes McKinney's work on columnar structures to Paparrizos' benchmark on anomaly detection. In our benchmark, SENOVA delivers 5-second setup and 100% math accuracy, outperforming both Excel and Power BI.\"",
         [("Q: Which paper guided your forecasting model?", "A: Petropoulos et al. (2022) in the International Journal of Forecasting proved that recency weighting and weekday seasonal factors outperform heavy neural nets on micro-retail series.")]),

        ("Slide 6", "Methodology & Architecture — Clean Layered Architecture", "3:00 - 3:45 min",
         "Explains the 5-layer Clean Architecture (Presentation, Security, FastAPI REST Controller, Domain Services with Pandas, ReportLab PDF Engine) and Axiomatic 2-Layer Compute Separation.",
         "Highlights software engineering best practices and the complete prevention of math hallucinations.",
         "\"SENOVA uses a Clean Layered Architecture. Crucially, we enforce an Axiomatic Compute Separation: Layer 1 runs deterministic Pandas math as the sole source of truth. Layer 2 receives read-only JSON summaries to write business alerts. The narrative layer cannot alter numbers, guaranteeing zero math errors.\"",
         [("Q: What architecture pattern is used in your backend?", "A: Clean Layered Architecture / Service-Oriented Architecture (SOA) with strict Separation of Concerns between API controllers, domain calculation services, and presentation.")]),

        ("Slide 7", "System Pipeline — 5-Stage End-to-End Data Lifecycle", "3:45 - 4:15 min",
         "Shows 5-stage pipeline: Ingest & Sniff → Canonicalize (265 Aliases) → Human Confirmation Guard → Compute & MAD → Deliver & PDF.",
         "Gives examiners a crystal-clear visual of how raw CSV data flows into the final dashboard and PDF.",
         "\"Here is our end-to-end data lifecycle: Raw spreadsheets are auto-sniffed for delimiter and encoding, mapped against 265 aliases, confirmed by the user if confidence is low, processed by Pandas and MAD engines, cached in memory, and delivered in under 300 milliseconds.\"",
         [("Q: What happens if a file has non-standard encodings?", "A: The sniffer automatically tries UTF-8, UTF-8-SIG, and falls back to Latin-1/CP1252, ensuring legacy Windows POS exports never crash the system.")]),

        ("Slide 8", "Algorithms (1/2) — Schema Canonicalization & MAD Anomaly", "4:15 - 5:00 min",
         "Deep-dive into 265-alias O(1) hash map + 66 fuzzy keywords (`guess_canonical_column()`) and MAD Anomaly Detection formula (`_anomaly_insights()`).",
         "Demonstrates algorithmic depth and mathematical formulas.",
         "\"We engineered two core algorithms: First, an O(1) hash dictionary of 265 exact aliases with 66 priority fuzzy keywords to standardize retail headers. Second, Median Absolute Deviation (MAD) anomaly detection—calculated as z = 0.6745 * (x - median) / MAD—which is mathematically immune to retail sales spikes.\"",
         [("Q: Why use MAD instead of standard deviation?", "A: Standard deviation squares differences, meaning a single massive order distorts the entire baseline. Median and MAD provide robust, outlier-resistant baselines.")]),

        ("Slide 9", "Algorithms (2/2) — Seasonal Forecasting & ABC Pareto Inventory", "5:00 - 5:45 min",
         "Deep-dive into Recency-Weighted Least Squares Forecasting (`compute_forecast()`) and ABC Pareto Inventory Classification (`_classify_abc()`).",
         "Explains how mathematical models directly solve working capital and stockout issues.",
         "\"For forecasting, we fit a trend line using recency-weighted least squares with a 14-day exponential half-life, adjusted by weekday seasonality multipliers. For inventory, we classify SKUs into ABC Pareto tiers (80/20 rule) and compute restock priority scores based on sales velocity and lead-time cover.\"",
         [("Q: How does ABC classification help the retailer?", "A: It directs the merchant's limited working capital toward Class A items (the top 80% revenue drivers) while flagging slow-moving Class C stock to avoid locked capital.")]),

        ("Slide 10", "Work Completed — 199 Unit Tests & Stress Benchmarks", "5:45 - 6:30 min",
         "Displays verified completed modules, 100% pass rate across 199 unit tests (pytest), and sub-300ms latency on 50,000-row stress datasets.",
         "Provides concrete engineering proof that the software is robust and production-tested.",
         "\"Slide 10 demonstrates our software engineering rigor. All core modules are 100% completed and verified with 199 automated unit tests across validation, P&L math, and cache concurrency. In stress tests on 50,000 transaction rows, the system delivered sub-300ms query response times.\"",
         [("Q: What did your concurrency tests verify?", "A: They verified that our bounded LRU cache is thread-safe and properly evicts oldest frames when multiple users upload files concurrently.")]),

        ("Slide 11", "Results & Screenshots (1) — Ingestion, Mapping & Security", "6:30 - 7:30 min",
         "Features the live 4-step stepper, Confirm Columns screen with green/amber confidence badges, live screenshot of `03_electronics_shopify_orders.csv`, and Firebase Auth.",
         "Shows visual evidence of working software and explains human-in-the-loop validation.",
         "\"Here is our live Ingestion & Column Mapping screen. The system matches 'COD' to Payment Mode with a green badge. Notice that non-standard fields like 'Currency', 'Order Status', and 'Notes' are safely identified as unrecognised and set to ignore, allowing error-free validation.\"",
         [("Q: Why not guess unrecognised columns automatically?", "A: In accounting, wrong guesses cause incorrect financial ledgers. Setting ambiguous columns to 'Ignore' and letting the human confirm is our core safety principle.")]),

        ("Slide 12", "Results & Screenshots (2) — Overview KPIs, Anomaly & Forecast", "7:30 - 8:30 min",
         "Shows Overview KPI cards, dynamic time slicing (Today, 7D, 30D, Month, All Time), 'What Changed' anomaly cards with root-cause recommendations, and 30-day forecast chart with 80% confidence bands.",
         "Demonstrates executive business intelligence in action.",
         "\"This is our live Overview & Forecast screen. Store owners get instant KPI summaries and automated anomaly cards—for instance, flagging a 37% revenue drop on May 14th with root-cause advice. The forecast chart projects future cash flow with 80% statistical confidence bands and an 85.5% backtest accuracy score.\"",
         [("Q: What does the backtest accuracy score show?", "A: It compares the model's projections against the most recent 7 days of actual sales to give the merchant an honest measure of prediction reliability.")]),

        ("Slide 13", "Results & Screenshots (3) — Chart Studio, Drill-Down Drawer & PDF", "8:30 - 9:30 min",
         "Shows Chart Studio with 8 modalities (Dual-Axis Combo, Treemap, Pareto, Heatmap), slide-out granular drill-down ledger drawer, formal P&L statement, and CA-grade vector PDF export.",
         "Shows end-to-end drill-down audit capability from macro chart down to single receipts.",
         "\"Slide 13 shows our Chart Studio and Audit Drawer. Users can view 8 chart types, overlay profit margin curves on top of revenue bars, and click any bar to slide out an instant transaction register. With one click, ReportLab generates a multi-page CA-grade vector PDF ready for bank loans.\"",
         [("Q: Why vector PDF instead of browser screenshots?", "A: Vector PDFs have selectable text, real tables, sanitized currency glyphs, and remain crystal clear when printed on A4 paper for audits.")]),

        ("Slide 14", "Challenges Faced — The Real Engineering Journey", "9:30 - 10:45 min",
         "Shares the 4 major challenges overcome: Architecture redesign (failed 4 times → 5th Clean Decoupled iteration), Pandas arithmetic edge cases, Ingestion variations, Firebase rate limits + active challenges (unmapped columns & DB card limits).",
         "This is the most impressive slide! It proves deep personal engineering grit and honesty.",
         "\"Building SENOVA presented four major engineering hurdles: First, our system architecture failed 4 times due to tight coupling; only on the 5th iteration did we successfully arrive at our Clean Decoupled Architecture. Second, Pandas groupby math had edge-case discrepancies with discounts and zero-sales days, which we solved via 199 unit tests. Third, heterogeneous POS headers required our 265-alias dictionary. And fourth, our current active challenge is handling unmapped operational columns and cloud database persistence.\"",
         [("Q: Why did the architecture fail in earlier iterations?", "A: In iterations 1 to 4, file parsing, business calculations, and UI state were tightly coupled. Any change in column names broke the dashboard. Decoupling compute into independent domain services solved this completely.")]),

        ("Slide 15", "Pros and Cons — Comprehensive System Evaluation", "10:45 - 11:30 min",
         "Balances 6 major software strengths (100% deterministic math, 265 aliases, sub-second cache, 8 chart modalities, vector PDF, security) against 2 honest limitations (fixed 6-field canonical scope, English-centric aliases).",
         "Demonstrates academic maturity by discussing software limitations honestly.",
         "\"Evaluating SENOVA: Our pros include 100% deterministic math accuracy, 265 POS aliases, sub-second query performance, and CA-grade PDF generation. On the cons side, our analytics currently focus strictly on the 6 core financial fields, and our alias lookup is English-centric, requiring manual mapping for regional Hinglish headers.\"",
         [("Q: Why restrict to 6 core canonical fields currently?", "A: To guarantee 100% mathematical auditability for core P&L accounting before expanding into peripheral operational attributes.")]),

        ("Slide 16", "Future Scope — Product Roadmap & Commercialization", "11:30 - 12:15 min",
         "Details 3 clear expansion goals: Packaging as a native Desktop Application (Electron/Tauri) for offline retail counters, 2-Tier Hybrid AI (FastEmbed + Gemini Flash), and PostgreSQL + Cloudflare R2 persistence.",
         "Presents an exciting commercial product roadmap for retail deployment.",
         "\"Our future roadmap focuses on three areas: First, converting SENOVA into a native Desktop Application via Electron or Tauri for offline retail counters with direct Tally sync. Second, integrating a 2-Tier Hybrid AI engine with local FastEmbed and Gemini Flash to automatically classify unstructured notes. And third, migrating to PostgreSQL and Cloudflare R2 for multi-year historical ledgers.\"",
         [("Q: Why build a desktop application?", "A: Many small retail counters in Tier-2 and Tier-3 cities experience intermittent internet. An offline-first desktop app allows them to run daily analytics locally without cloud dependency.")]),

        ("Slide 17", "Conclusion — Summary of Technical Breakthroughs", "12:15 - 13:00 min",
         "Presents 3 simple, powerful takeaways: Zero-formula simplicity, 100% mathematical truth, and true Digital CFO impact for SMEs.",
         "Delivers a memorable, confident closing statement.",
         "\"In conclusion, SENOVA AI Dashboard proves that small business financial intelligence can be completely automated with zero formula setup and 100% mathematical precision. By decoupling deterministic Python math from narrative AI, we give small enterprise owners institutional-grade financial clarity. Thank you!\"",
         [("Q: What is the main takeaway of your project?", "A: That financial intelligence can be democratized for small business owners without sacrificing mathematical auditability or computational rigor.")]),

        ("Slide 18", "References — Formal Academic Citations", "13:00 - 13:15 min",
         "Lists formal IEEE and ACM citations referenced in the final thesis report.",
         "Provides academic evidence for examiners.",
         "\"Here are the formal research citations from our project report, spanning data wrangling, time-series forecasting, and robust anomaly detection.\"",
         [("Q: What is the latest reference you cited?", "A: Parciak et al. (2024) on Schema Matching with Large Language Models, which directly informed our future 2-Tier Hybrid AI roadmap.")]),

        ("Slide 19", "Thank You & Q&A — Viva Voce Closing", "13:15 - 15:00 min",
         "Closing slide with live demo URL (senova-ai-dashboard.vercel.app) and invitation for examiner questions.",
         "Transitions smoothly into the viva questioning and live software demonstration.",
         "\"Thank you respected guide and examiners. Our live web dashboard is deployed and ready for live demonstration. We now welcome your questions.\"",
         [("Q: Ready for live demo?", "A: Yes! We have sample Tally, Vyapar, and Shopify CSV files ready to demonstrate live ingestion and drill-down analytics.")])
    ]

    # --- SLIDES DATA (HINGLISH) ---
    slides_hinglish = [
        ("Slide 1", "Front Page — Project Title & Team Intro", "0:00 - 0:30 min",
         "Is slide par Department header (GEC Raichur), Project title ('SENOVA AI Dashboard'), Guide (Prof. Mamatha Madam), aur teeno team members ke USN hain.",
         "Presentation ko formal tarike se shuru karne aur examiners ko project ka context batane ke liye.",
         "\"Good morning guide and examiners. Aaj hum SENOVA AI Dashboard present kar rahe hain—yeh small businesses ke liye ek autonomous financial decision engine hai jo zero-formula setup ke saath 100% accurate math analytics deta hai.\"",
         [("Q: SENOVA ka main aim kya hai?", "A: Small business owners ko ek automated 'Digital CFO' dena jisse unhe Excel me manual formula na lagane padein aur zero math error mile.")]),

        ("Slide 2", "Introduction — Product Purpose & High-Level Summary", "0:30 - 1:15 min",
         "SENOVA kya karta hai, SME data problem, Decoupled Compute paradigm, aur Digital CFO impact ka clean summary.",
         "Examiners ko technical details se pehle poore product ka quick overview dene ke liye.",
         "\"Small retail shops roz hazaron sales rows Tally ya Vyapar se generate karti hain par unke paas data team nahi hoti. Power BI bohot complex hai aur normal ChatGPT math galat karta hai. SENOVA 100% accurate Python math ko AI text se alag karke isko solve karta hai.\"",
         [("Q: Digital CFO kya kaam karta hai?", "A: Sales CSV read karta hai, profit margins calculate karta hai, sales drop pakadta hai aur formal financial PDF reports automatically compile karta hai.")]),

        ("Slide 3", "Problem Statement — Existing Tools Kyun Fail Hote Hain", "1:15 - 1:50 min",
         "3 bade barriers: Excel me manual VLOOKUP ka headache, Power BI me DAX complexity, aur ChatGPT me 5-15% arithmetic math error.",
         "Examiners ko yeh prove karne ke liye ki purane software me kya kami hai aur SENOVA kyu zaroori hai.",
         "\"Purane tools SMEs ke liye fail kyu hote hain? Excel me manual formulas lagana mushkil hai aur ek galti se pura data kharab hota hai. Power BI bohot mehnga aur complex hai. Aur normal ChatGPT math me hallucinate karta hai (5-15% error), jo accounting me audit fail kara deta hai.\"",
         [("Q: ChatGPT math me galti kyu karta hai?", "A: LLMs word predictor hote hain, calculator nahi. Jab hazaron numbers add karte hain toh wo answer calculate karne ki bajaye guess karte hain.")]),

        ("Slide 4", "Objective & Scope — Project Ke 6 Main Goals", "1:50 - 2:20 min",
         "6 core deliverables: 5-sec ingestion, 265 aliases, 100% deterministic math, MAD anomaly, 30-day forecast, aur CA-grade PDF export.",
         "Project ke exact scope aur boundaries ko examiners ke samne clear karne ke liye.",
         "\"Humari project ke 6 main goals hain: bina template CSV upload, 265 header aliases se auto mapping, guaranteed 100% accurate Python math, MAD sales anomaly alerts, seasonal forecasting, aur print-ready PDF reports.\"",
         [("Q: Data privacy kaise maintain hoti hai?", "A: Firebase Auth se verified JWT Bearer tokens lagte hain, aur har file caller ki UID se bind hoti hai taaki koi doosra user data na dekh sake.")]),

        ("Slide 5", "Literature Survey — Research Papers & Benchmark", "2:20 - 3:00 min",
         "5 academic papers (Wes McKinney, Kandel, Heer, Petropoulos, Paparrizos) aur benchmark matrix (Excel vs Power BI vs SENOVA).",
         "Project ki research credibility prove karne aur commercial tools se better benchmark dikhane ke liye.",
         "\"Humara project established research papers par based hai—Wes McKinney ke Pandas paper se le kar Paparrizos ke anomaly detection benchmark tak. Benchmark table dikhata hai ki SENOVA 5-second setup aur 100% math accuracy ke saath Excel aur Power BI dono se superior hai.\"",
         [("Q: Forecasting ke liye kaunsa paper refer kiya?", "A: Petropoulos et al. (2022) International Journal of Forecasting, jisme prove kiya gaya hai ki recency weighting micro-retail ke liye deep learning se better perform karti hai.")]),

        ("Slide 6", "Methodology & Architecture — Clean Layered Architecture", "3:00 - 3:45 min",
         "5-layer Clean Architecture (React UI, Firebase Auth, FastAPI REST Controller, Pandas Services, ReportLab PDF) aur Axiomatic 2-Layer Compute Separation.",
         "Software engineering standards aur zero math hallucination guarantee explain karne ke liye.",
         "\"SENOVA Clean Layered Architecture use karta hai. Sabse main innovation hai Decoupled Computation: Layer 1 saari calculation Pandas me exact 100% accuracy ke saath karta hai. Layer 2 sirf pre-computed summary padhkar text alerts banata hai, jisse math hallucination impossible ho jati hai.\"",
         [("Q: Codebase me kaunsa architecture pattern use hua hai?", "A: Clean Layered Architecture / Service-Oriented Architecture (SOA)—jisme API routes, domain calculation services aur presentation completely separated hain.")]),

        ("Slide 7", "System Pipeline — 5-Stage Data Lifecycle Flowchart", "3:45 - 4:15 min",
         "5 stages: Ingest & Sniff → Canonicalize (265 Aliases) → Human Confirmation → Compute & MAD → Deliver & PDF.",
         "Raw CSV upload se le kar final dashboard render hone tak ka visual process flow samjhane ke liye.",
         "\"Yeh humara 5-stage data pipeline hai: Raw CSV upload hoti hai, sniffer delimiter auto-detect karta hai, 265 aliases se column match hote hain, user low confidence match confirm karta hai, Pandas math execute hota hai aur LRU cache se UI pe sub-second me show hota hai.\"",
         [("Q: Agar file alag encoding me ho toh kya hota hai?", "A: Auto-sniffer pehle UTF-8, phir UTF-8-SIG aur end me Latin-1/CP1252 try karta hai, jisse koi bhi purani Tally file crash nahi hoti.")]),

        ("Slide 8", "Algorithms (1/2) — 265 Aliases & MAD Anomaly Detection", "4:15 - 5:00 min",
         "265-alias O(1) hash map + 66 fuzzy keywords (`guess_canonical_column()`) aur MAD Anomaly Detection formula (`_anomaly_insights()`).",
         "Backend ke algorithmic logic aur mathematical formulas ko explain karne ke liye.",
         "\"Hum do core algorithms use karte hain: Pehla, 265 column aliases ka O(1) hash dictionary messy headers ko match karne ke liye. Dusra, Median Absolute Deviation (MAD) anomaly detection formula (z = 0.6745 * (x - median) / MAD) jo sudden sales drop ko pakadta hai.\"",
         [("Q: Standard Deviation ki jagah MAD kyu use kiya?", "A: Standard deviation mean aur square difference use karta hai jo sudden sales spike se distort ho jata hai. Median aur MAD extreme outliers ke khilaf robust hote hain.")]),

        ("Slide 9", "Algorithms (2/2) — Seasonal Forecasting & ABC Pareto Inventory", "5:00 - 5:45 min",
         "Recency-Weighted Least Squares Forecasting (`compute_forecast()`) aur ABC Pareto Inventory Classification (`_classify_abc()`).",
         "Future revenue prediction aur godown dead stock management explain karne ke liye.",
         "\"Forecasting ke liye hum recency-weighted least squares regression fit karte hain 14-day exponential decay aur weekday seasonality ke saath. Inventory ke liye ABC Pareto analysis (top 80% sales = Class A) aur priority scoring se dead stock isolate karte hain.\"",
         [("Q: ABC analysis se shopkeeper ko kya fayda hota hai?", "A: Dukandar ka paisa Class A (top 80% bikne wale items) par invest hota hai aur Class C ke slow-moving dead stock ko discount karke capital free ho jata hai.")]),

        ("Slide 10", "Work Completed — 199 Unit Tests & Benchmarks", "5:45 - 6:30 min",
         "Verified complete modules, 100% test pass rate across 199 automated unit tests (pytest), aur 50,000-row stress testing benchmarks.",
         "Software engineering quality, test coverage aur production readiness prove karne ke liye.",
         "\"Slide 10 humare development standards ko dikhati hai. Phase 2 ke saare modules 100% complete hain aur 199 unit tests se verified hain. 50,000 transaction rows par stress test karne par bhi system ne under 300ms query response time diya.\"",
         [("Q: Concurrency test me kya check kiya?", "A: Check kiya ki jab multiple users ek saath file upload karte hain toh in-memory LRU cache thread-safe rehta hai aur purane files ko clean evict karta hai.")]),

        ("Slide 11", "Results & Screenshots (1) — Ingestion, Mapping & Screenshot", "6:30 - 7:30 min",
         "Live 4-step stepper, Confirm Columns screen with green/amber badges, live screenshot of `03_electronics_shopify_orders.csv`, aur Firebase Auth.",
         "Live software ka proof dikhane aur unmapped columns par system ka safe behavior demonstrate karne ke liye.",
         "\"Yeh humara live Ingestion aur Column Mapping screen hai. Screenshot me dekhiye 'Payment Method' COD ko green badge ke saath auto-map kar liya hai, aur extra columns jaise Currency, Order Status aur Notes ko safely ignore set kiya hai taaki math kharab na ho.\"",
         [("Q: Unmapped columns ko khud se guess kyu nahi kiya?", "A: Accounting me galat guess karne se balance sheet kharab ho sakti hai. Ambiguous columns ko ignore set karke user ko confirm karne dena safe engineering hai.")]),

        ("Slide 12", "Results & Screenshots (2) — Overview KPIs, Anomaly & Forecast", "7:30 - 8:30 min",
         "Live Overview dashboard: KPIs, dynamic time slicing, 'What Changed' anomaly cards, aur 30-day forecast chart with 80% confidence bands.",
         "Business owner ka daily executive view demonstrate karne ke liye.",
         "\"Yeh live Overview Dashboard hai. Shop owner ko ek screen par saare KPIs milte hain aur automatic anomaly cards aate hain—jaise 14 May ko 37% revenue drop hua toh system root-cause check suggest karta hai. Forecast screen par 80% confidence band aur 85.5% backtest accuracy dikhti hai.\"",
         [("Q: Backtest accuracy score ka kya matlab hai?", "A: System pichle 7 dino ki actual sales se model ko test karta hai taaki shopkeeper ko pata rahe ki prediction kitne percent accurate hai.")]),

        ("Slide 13", "Results & Screenshots (3) — Chart Studio, Drawer & PDF", "8:30 - 9:30 min",
         "Chart Studio (8 Modalities), slide-out drill-down transaction drawer, formal P&L statement, aur CA-Grade ReportLab vector PDF export.",
         "Visual chart se direct single receipt audit tak drill-down feature explain karne ke liye.",
         "\"Module 13 me humara Chart Studio hai. Users 8 charts dekh sakte hain, revenue bar par margin % curve overlay kar sakte hain, aur bar click karke slide-out drawer me ek-ek receipt audit kar sakte hain. Saath hi ReportLab se 1-click formal vector PDF report download hoti hai.\"",
         [("Q: Screenshot PDF ki jagah Vector PDF kyu banaya?", "A: Vector PDF me selectable text aur proper tables hoti hain jo bank loan aur tax audit ke liye print karne par crystal clear rehti hain.")]),

        ("Slide 14", "Challenges Faced — Real Development Journey", "9:30 - 10:45 min",
         "4 bade challenges: Architecture redesign (4 baar fail hua → 5th Clean Decoupled iteration me succeed hua), Pandas math edge cases, Ingestion variations, Firebase rate limits + active challenges.",
         "Yeh presentation ki sabse powerful slide hai jo aapki real engineering struggle aur problem-solving skills prove karegi.",
         "\"SENOVA build karte waqt humne 4 bade challenges face kiye: Pehla, humara system architecture 4 baar fail hua tight-coupling ki wajah se; 5th iteration me humne Clean Decoupled Architecture bana kar succeed kiya. Dusra, Pandas me discounts aur 0-sales days ke calculation edge cases the jise 199 unit tests se solve kiya. Teesra, alag-alag POS headers ka issue tha jise 265 aliases se solve kiya. Aur chautha, abhi hum unmapped columns aur cloud database persistence par kaam kar rahe hain.\"",
         [("Q: Pehle 4 iterations me architecture kyu fail hua?", "A: UI, file parser aur calculation sab aapas me tightly mixed the. Ek bhi column badalta tha toh pura dashboard crash ho jata tha. Calculations ko independent domain services me decouple karke yeh solve hua.")]),

        ("Slide 15", "Pros and Cons — Realistic Software Evaluation", "10:45 - 11:30 min",
         "6 core strengths (100% deterministic math, 265 aliases, sub-second cache, 8 charts, vector PDF, security) vs 2 genuine limitations (fixed 6-field canonical scope, English-centric aliases).",
         "Software ki honest limitations accept karke examiners ke samne maturity dikhane ke liye.",
         "\"Pros me: 100% accurate math, 265 header aliases, sub-second LRU cache aur CA-grade PDF export. Cons me: Abhi system 6 core financial fields par focus karta hai (extra operational fields ignore hote hain), aur aliases English-centric hain jisse Hinglish headers manual map karne padte hain.\"",
         [("Q: Abhi sirf 6 core fields hi kyu liye?", "A: Taaki core P&L aur financial accounting 100% audit-proof rahe, bina kisi unnecessary attribute ke calculations ko complicate kiye.")]),

        ("Slide 16", "Future Scope — Product Roadmap & Expansion", "11:30 - 12:15 min",
         "3 Future milestones: Desktop App (Electron/Tauri) offline retail counter ke liye, 2-Tier Hybrid AI (FastEmbed + Gemini Flash), aur PostgreSQL + Cloudflare R2 storage.",
         "Product ka next commercial development roadmap present karne ke liye.",
         "\"Future Scope me hum 3 cheezon par kaam karenge: Pehla, SENOVA ko Electron ya Tauri se native Desktop Application banana taaki local shopkeepers bina internet ke offline counter PC par chala sakein. Dusra, 2-Tier Hybrid AI se unstructured notes parse karna. Aur teesra, PostgreSQL aur Cloudflare R2 par multi-year historical data store karna.\"",
         [("Q: Desktop application banane ki kya zaroorat hai?", "A: Tier-2 aur Tier-3 cities me dukandaron ke paas internet issue hota hai. Offline desktop app unhe local counter par direct Tally sync ke saath fast billing analytics dega.")]),

        ("Slide 17", "Conclusion — Summary of Impact", "12:15 - 13:00 min",
         "3 simple & powerful points: Zero-formula simplicity, 100% math truth, aur true Digital CFO impact for SMEs.",
         "Presentation ko strong, confident aur clear closing note par finish karne ke liye.",
         "\"Conclusion me, SENOVA AI Dashboard ne prove kiya hai ki small business financial intelligence ko bina kisi formula aur 100% mathematical precision ke saath fully automate kiya ja sakta hai. Python math ko AI text se decouple karke hum small business owners ko ek institutional-grade Digital CFO dete hain. Thank you!\"",
         [("Q: Project ka final takeaway kya hai?", "A: Ki financial intelligence ko bina mathematical accuracy khoye har small retailer ke liye accessible banaya ja sakta hai.")]),

        ("Slide 18", "References — Formal Research Citations", "13:00 - 13:15 min",
         "Formal IEEE aur ACM research citations jo final project report me diye gaye hain.",
         "Project ki theoretical authenticity prove karne ke liye.",
         "\"Yeh research papers hain jo humne literature survey, forecasting aur anomaly detection me cite kiye hain.\"",
         [("Q: Sabse latest research kaunsi refer ki?", "A: Parciak et al. (2024) Schema Matching with LLMs, jo humare future 2-Tier AI roadmap ka base hai.")]),

        ("Slide 19", "Thank You & Q&A — Viva Voce Closing", "13:15 - 15:00 min",
         "Thank you slide with live deployed URL (senova-ai-dashboard.vercel.app) aur examiners ke viva questions ke liye welcome note.",
         "Presentation se direct live demo aur viva examination question-answer round me enter karne ke liye.",
         "\"Thank you respected guide and examiners. Humara live web dashboard ready hai demonstration ke liye. Ab aapke sawaal welcome hain.\"",
         [("Q: Live demo dikha sakte ho?", "A: Ji bilkul! Humare paas Tally aur Shopify ki sample files ready hain live upload aur drill-down charts dikhane ke liye.")])
    ]

    target_slides = slides_en if lang == 'EN' else slides_hinglish

    for num, title, t_alloc, kya_hai, kyun_hai, script, qa_list in target_slides:
        flowables = []
        flowables.append(Paragraph(f"<b>{num} ({t_alloc})</b> — {title}", h2_style))
        flowables.append(HRFlowable(width="100%", thickness=0.8, color=c_secondary, spaceBefore=2, spaceAfter=4))
        
        if lang == 'EN':
            lbl_kya = "<b>Slide Breakdown:</b>"
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
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        flowables.append(script_box)
        flowables.append(Spacer(1, 4))
        
        # Q&A Block
        flowables.append(Paragraph(lbl_qa, bold_body))
        for q, a in qa_list:
            flowables.append(Paragraph(q, qa_question))
            flowables.append(Paragraph(a, qa_answer))
            
        flowables.append(Spacer(1, 8))
        story.append(KeepTogether(flowables))

    # Page Break for Strategy Section
    story.append(PageBreak())
    if lang == 'EN':
        story.append(Paragraph("<b>Presentation Mastery & Viva Defense Strategy</b>", h1_style))
        tips_data = [
            ["Strategy", "Execution Guidelines"],
            ["Time Management", "Stick strictly to 40-45 seconds per slide. Do not spend more than 1.5 minutes on Slides 1-3."],
            ["Body Language", "Look directly into the eyes of the external examiners. Do not keep staring at the screen."],
            ["Math Defense Key", "Whenever asked about accuracy: 'AI does NOT do calculation. Pandas does 100% deterministic math.'"],
            ["Architecture Defense", "Proudly share: 'Our architecture failed 4 times due to tight coupling; on the 5th iteration we achieved Clean Decoupled Architecture.'"],
            ["Demo Readiness", "Keep https://senova-ai-dashboard.vercel.app open with a pre-loaded sample file ready to show instantly."]
        ]
    else:
        story.append(Paragraph("<b>Presentation Mastery & Viva Defense Tips (Hinglish)</b>", h1_style))
        tips_data = [
            ["Strategy", "Execution Guidelines"],
            ["Time Control", "Har slide par 40-45 seconds se zyada mat lein. Pehli 3 slides 2-2.5 minute me wrap karein."],
            ["Eye Contact", "External Examiners ki taraf dekh kar bolo, sirf TV screen ya laptop screen ko mat ghooro."],
            ["Math Defense Key", "Jab bhi calculation accuracy par sawaal aaye, bolo: 'AI calculation nahi karta, Pandas 100% accurate math karta hai.'"],
            ["Architecture Struggle", "Examiners ke samne openly bolo: 'Humein Clean Architecture banane me 4 baar failure mila, 5th iteration me perfect decoupling achieve hui.' Yeh sunkar examiners bohot impress honge!"],
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
    print(f"PDF built successfully: {filename}")

if __name__ == "__main__":
    create_pdf("SENOVA_Presentation_Prep_Guide_EN.pdf", lang='EN')
    create_pdf("SENOVA_Presentation_Prep_Guide_Hinglish.pdf", lang='Hinglish')
