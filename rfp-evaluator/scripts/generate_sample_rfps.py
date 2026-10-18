from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, KeepTogether)
import os, sys
from pathlib import Path

# Usage: python scripts/generate_sample_rfps.py [output_dir]   (default: sample_rfps/)
OUT = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "sample_rfps")
os.makedirs(OUT, exist_ok=True)

BUYER = "Meridian Retail Group (fictional)"
RFP_REF = "MRG-RFP-2026-014"
RFP_TITLE = "Omnichannel Customer Service & Ticketing Platform"

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=18, leading=22, spaceAfter=4, alignment=0)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], fontSize=9.5, textColor=colors.HexColor("#555555"), leading=13)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=4,
                    textColor=colors.HexColor("#1F3A5F"), keepWithNext=1)
BODY = ParagraphStyle("BODY", parent=ss["Normal"], fontSize=9.8, leading=13.6, spaceAfter=5)
BUL = ParagraphStyle("BUL", parent=BODY, leftIndent=12, bulletIndent=2, spaceAfter=2)
CELL = ParagraphStyle("CELL", parent=ss["Normal"], fontSize=8.8, leading=11)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold")


def table(rows, widths, total_row=False):
    data = [[Paragraph(str(c), CELLB if i == 0 else CELL) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    st = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E3EAF3")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA7B5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if total_row:
        st.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F2F2F2")))
    t.setStyle(TableStyle(st))
    return t


def build(s):
    path = os.path.join(OUT, s["file"])
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{s['name']} - Response to {RFP_REF}", author=s["name"])
    story = []
    story.append(Paragraph(f"{s['name']}", H1))
    story.append(Paragraph(f"Proposal in response to <b>{RFP_REF}</b>: {RFP_TITLE}<br/>"
                           f"Submitted to: {BUYER}<br/>Submission date: {s['date']} &nbsp;|&nbsp; "
                           f"Proposal validity: {s['validity']}<br/>Contact: {s['contact']}", SUB))
    story.append(Spacer(1, 4))
    story.append(Paragraph("<i>Synthetic document created for a classroom exercise. All companies, people, "
                           "clients and figures are fictional.</i>", SUB))

    for sec in s["sections"]:
        story.append(Paragraph(sec[0], H2))
        for item in sec[1:]:
            if isinstance(item, str):
                story.append(Paragraph(item, BODY))
            elif item[0] == "bullets":
                for b in item[1]:
                    story.append(Paragraph(b, BUL, bulletText="•"))
                story.append(Spacer(1, 3))
            elif item[0] == "table":
                story.append(KeepTogether([table(item[1], item[2], item[3] if len(item) > 3 else False)]))
                story.append(Spacer(1, 5))

    def footer(c, d):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#777777"))
        c.drawString(18 * mm, 9 * mm, f"{s['name']} | {RFP_REF} | Confidential - synthetic sample")
        c.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {d.page}")
        c.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


REQ = ("Meridian Retail Group operates 140 stores and an e-commerce site across India and has issued "
       f"{RFP_REF} to replace its legacy email-based support desk with a cloud omnichannel platform covering "
       "email, web chat, WhatsApp and voice callback. Key requirements are integration with the existing "
       "SAP S/4HANA order system and Salesforce loyalty CRM, support for 350 agents (peak 600 in festive "
       "season), go-live within 6 months, data residency in India, and DPDP Act 2023 compliance.")

suppliers = []

# ---------------------------------------------------------------- 1. Apex
suppliers.append(dict(
    file="01_Apex_Systems_Proposal.pdf", name="Apex Systems Pvt. Ltd.", date="2026-09-22",
    validity="120 days", contact="Rohan Mehta, Bid Director (rohan.mehta@apexsystems.example)",
    sections=[
        ("1. Executive Summary",
         f"{REQ}",
         "Apex Systems proposes <b>ApexServe Enterprise</b>, a microservices-based contact centre platform "
         "hosted on AWS Mumbai (ap-south-1) with a hot standby in AWS Hyderabad (ap-south-2). Our design "
         "prioritises scalability, security and clean integration. We have deliberately priced for a "
         "premium, fully redundant architecture rather than a minimum-viable deployment."),
        ("2. Proposed Solution and Technical Architecture",
         "ApexServe is built as 22 containerised services on Kubernetes (EKS) with an event bus (Kafka) that "
         "decouples channels from the ticketing core. Each channel adapter scales independently; load tests "
         "in our lab sustained 1,200 concurrent agents and 9,000 messages per minute with p95 latency of "
         "340 ms.",
         ("bullets", [
             "<b>SAP S/4HANA integration:</b> certified SAP BTP connector using OData v4 for order lookup, "
             "returns and refund status; bidirectional, near real-time (under 5 seconds).",
             "<b>Salesforce integration:</b> MuleSoft-free native connector using Salesforce Platform Events; "
             "loyalty tier and lifetime value shown on every ticket.",
             "<b>Channels:</b> email, web chat widget, WhatsApp Business API (Meta BSP partner), voice "
             "callback via Exotel.",
             "<b>AI assist:</b> intent classification and reply suggestions; models hosted in-region, no "
             "customer data used for training.",
             "<b>Auto-scaling:</b> horizontal pod autoscaling sized for the 600-agent festive peak, with "
             "pre-warming two weeks before Diwali.",
         ])),
        ("3. Implementation Approach",
         "We follow a four-phase approach: Discover, Build, Migrate, Hypercare. Delivery is planned at "
         "<b>24 weeks</b>, which meets the 6-month window but leaves limited float. Our critical-path risk is "
         "SAP connector testing, which depends on Meridian providing a sandbox by Week 4.",
         ("table", [
             ["Milestone", "Week", "Deliverable"],
             ["M1 Discovery & design sign-off", "4", "Solution design document, integration specs"],
             ["M2 Core platform + email/chat", "10", "Tenant built, SSO, routing rules"],
             ["M3 SAP & Salesforce integrations", "15", "Tested connectors, UAT scripts"],
             ["M4 WhatsApp + voice, data migration", "19", "2.1 million legacy tickets migrated"],
             ["M5 Pilot (20 stores) and UAT", "22", "Pilot report, defect closure"],
             ["M6 Go-live and hypercare", "24", "Production cutover, 4-week hypercare"],
         ], [62, 16, 96]),
         "<b>Team:</b> 1 programme manager, 1 solution architect, 2 integration engineers (SAP certified), "
         "3 platform engineers, 1 security lead, 2 QA, 1 change-management lead (11 FTE)."),
        ("4. Commercial Proposal",
         ("table", [
             ["Item", "Basis", "Amount (INR)"],
             ["Platform licence (350 agents)", "Rs 2,600 per agent/month x 12", "1,09,20,000"],
             ["Festive burst licences (250 agents x 3 months)", "Rs 2,600 per agent/month", "19,50,000"],
             ["Implementation & integration services", "Fixed price", "86,00,000"],
             ["Data migration", "Fixed price", "14,00,000"],
             ["Premium support (24x7, named TAM)", "Annual", "22,00,000"],
             ["<b>Total Year 1</b>", "", "<b>2,50,70,000</b>"],
             ["<b>Estimated Year 2 and 3 (each)</b>", "Licences + support, 5% uplift cap", "<b>1,58,23,500</b>"],
         ], [70, 60, 44], True),
         "<b>Assumptions:</b> prices exclude GST; Meridian supplies SAP and Salesforce sandboxes; WhatsApp "
         "conversation charges billed at Meta cost with no markup; travel included for Mumbai and Bengaluru "
         "only. Three-year total cost of ownership: approximately Rs 5.67 crore."),
        ("5. Security, Compliance and Risk Controls",
         ("bullets", [
             "ISO/IEC 27001:2022 and ISO/IEC 27701 certified (certificates valid to 2028); SOC 2 Type II report "
             "for FY2025-26 available under NDA.",
             "All data stored and processed in India; encryption AES-256 at rest, TLS 1.3 in transit; "
             "customer-managed keys via AWS KMS optional.",
             "DPDP Act 2023: consent logging, data principal request workflow, configurable retention and "
             "automated purge; breach notification runbook within 72 hours of detection.",
             "Role-based access, SSO via Azure AD/SAML, immutable audit log retained 7 years.",
             "Quarterly external penetration test (CERT-In empanelled auditor); RPO 15 minutes, RTO 2 hours.",
         ]),
         ("table", [
             ["Risk", "Likelihood", "Mitigation"],
             ["SAP sandbox delayed", "Medium", "Mock services from Week 2; escalation at steering committee"],
             ["Festive peak overload", "Low", "Pre-scaling, load test at 1.5x expected peak"],
             ["Agent adoption", "Medium", "Train-the-trainer, 30 super-users, in-app guides"],
         ], [52, 24, 98])),
        ("6. Support Model, Experience and References",
         "24x7 L1/L2 support with a named Technical Account Manager; P1 response 15 minutes, resolution "
         "target 4 hours; 99.95% monthly uptime SLA with service credits. Apex has delivered 9 contact-centre "
         "platforms since 2019, including 3 in retail.",
         ("bullets", [
             "<b>Kavya Fashion Retail</b> (fictional) - 420 agents, SAP integration, live 2024.",
             "<b>Northline Electronics</b> (fictional) - 260 agents, WhatsApp + voice, live 2025.",
             "References available on request after shortlisting.",
         ])),
    ]))

# ---------------------------------------------------------------- 2. BrightPath
suppliers.append(dict(
    file="02_BrightPath_Tech_Proposal.pdf", name="BrightPath Tech LLP", date="2026-09-25",
    validity="60 days", contact="Sneha Kulkarni, Founder & CEO (sneha@brightpath.example)",
    sections=[
        ("1. Executive Summary",
         "BrightPath Tech is a fast-growing start-up founded in 2023. We understand Meridian wants to move "
         "away from email-only support to a modern omnichannel helpdesk. We offer the <b>lowest-cost and "
         "fastest</b> route: our SaaS product <b>HelpLoop</b> can be live in <b>10 weeks</b>, saving you "
         "months of effort and lakhs of rupees."),
        ("2. Proposed Solution",
         "HelpLoop is a multi-tenant SaaS helpdesk with email, chat and WhatsApp in one inbox. Voice "
         "callback is on our roadmap for Q2 2027; in the interim agents can log calls manually.",
         ("bullets", [
             "Pre-built Salesforce app available on AppExchange (basic contact sync).",
             "SAP S/4HANA: we will build a custom REST integration during the project. Specific approach "
             "to be finalised after discovery.",
             "Hosted on a public cloud; region selection to be confirmed.",
             "Supports 'hundreds of agents'; our largest current customer has 85 agents.",
         ])),
        ("3. Implementation Approach and Timeline",
         "We use an agile, sprint-based approach with two-week sprints and a lean team.",
         ("table", [
             ["Sprint", "Weeks", "Scope"],
             ["Sprint 1", "1-2", "Setup, email and chat"],
             ["Sprint 2", "3-4", "WhatsApp, Salesforce app"],
             ["Sprint 3", "5-6", "SAP integration (custom)"],
             ["Sprint 4", "7-8", "Testing and training"],
             ["Go-live", "9-10", "Cutover"],
         ], [40, 30, 104]),
         "<b>Team:</b> 1 project lead (also acts as solution architect), 2 developers, 1 support engineer "
         "(4 FTE). Data migration of legacy tickets is not included; historical tickets can be exported "
         "to CSV for reference."),
        ("4. Commercial Proposal",
         ("table", [
             ["Item", "Basis", "Amount (INR)"],
             ["HelpLoop licence (350 agents)", "Rs 950 per agent/month x 12", "39,90,000"],
             ["Implementation services", "Fixed price", "12,00,000"],
             ["Standard support", "Included", "0"],
             ["<b>Total Year 1</b>", "", "<b>51,90,000</b>"],
         ], [70, 60, 44], True),
         "<b>Assumptions:</b> prices exclude GST; festive-season additional agents billed at the same rate "
         "pro-rata; WhatsApp charges extra; SAP integration scope capped at 3 APIs, beyond which "
         "change requests apply at Rs 6,500 per developer-hour. Year 2 pricing subject to revision."),
        ("5. Security and Compliance",
         "We take security seriously. HelpLoop uses HTTPS and encrypted databases, and we follow industry "
         "best practices. We are planning to begin ISO 27001 certification in 2027. We will cooperate with "
         "Meridian on DPDP requirements as they are clarified. Backups are taken daily.",
         "<b>Risks:</b> tight timeline depends on fast decisions from Meridian; SAP integration complexity "
         "is not yet known."),
        ("6. Support and Experience",
         "Support is available Monday to Saturday, 9 am to 7 pm IST by email and chat. Target first "
         "response for critical issues is 4 business hours. Uptime target 99.5%.",
         "BrightPath has 11 customers, mostly D2C brands with 10-85 agents. This would be our first "
         "deployment with SAP and our largest deployment to date.",
         ("bullets", [
             "<b>UrbanSip Beverages</b> (fictional) - 22 agents, live 2025.",
             "<b>Leafy Home</b> (fictional) - 85 agents, live 2026.",
         ])),
    ]))

# ---------------------------------------------------------------- 3. NexaWorks
suppliers.append(dict(
    file="03_NexaWorks_Proposal.pdf", name="NexaWorks Solutions Ltd.", date="2026-09-22",
    validity="90 days", contact="Arvind Iyer, Head of Pre-sales (arvind.iyer@nexaworks.example)",
    sections=[
        ("1. Executive Summary and Understanding of Requirement",
         f"{REQ}",
         "NexaWorks proposes <b>NexaDesk</b>, a proven cloud contact-centre suite, delivered through a "
         "structured, low-risk implementation and backed by a local 24x7 support centre in Pune. Our "
         "proposal is balanced: competitive pricing, solid security credentials and a plan designed to "
         "absorb delays without moving go-live."),
        ("2. Proposed Solution",
         ("bullets", [
             "Cloud SaaS hosted on Microsoft Azure Central India with DR in South India; all data resident in India.",
             "Channels: email, web chat, WhatsApp, voice callback (native CPaaS integration).",
             "SAP S/4HANA integration through SAP Integration Suite using standard order and returns APIs; "
             "pre-built adapter used at two prior clients.",
             "Salesforce integration via managed package: loyalty tier, case history and NPS synced every 60 seconds.",
             "Validated capacity: 800 concurrent agents in production at an existing client.",
         ])),
        ("3. Implementation Plan",
         "Delivery uses a hybrid waterfall-agile model with formal stage gates, a joint steering committee "
         "meeting every two weeks, and RAID logs shared weekly. Total duration <b>22 weeks</b> including "
         "<b>2 weeks of built-in contingency</b>, so the plan absorbs slippage without breaching the 6-month "
         "deadline.",
         ("table", [
             ["Phase / Milestone", "Weeks", "Exit criteria"],
             ["P0 Mobilisation", "1-2", "Project charter, RACI, governance signed"],
             ["P1 Discovery & design", "3-5", "Signed design; data migration mapping approved"],
             ["P2 Build & configure", "6-11", "All channels configured; integrations unit-tested"],
             ["P3 Data migration (3 trial loads)", "8-13", "Reconciliation at 99.9% record match"],
             ["P4 SIT and UAT", "12-16", "Zero open Sev-1/Sev-2 defects"],
             ["P5 Pilot in 15 stores + training", "17-18", "Pilot KPIs met; 350 agents trained"],
             ["P6 Phased go-live (3 waves)", "19-20", "All stores live"],
             ["Contingency buffer", "21-22", "Reserved for slippage"],
             ["Hypercare", "Go-live + 6 weeks", "Stability sign-off"],
         ], [62, 30, 82]),
         "<b>Team (14 FTE):</b> engagement director, PMP-certified project manager, solution architect, "
         "SAP integration lead, Salesforce consultant, 3 configuration engineers, data migration lead, "
         "2 QA engineers, OCM/training lead, 2 support transition engineers. Key personnel CVs in Annex B; "
         "named staff will not be replaced without Meridian's approval.",
         "<b>Risk plan:</b> top risks (SAP sandbox availability, migration data quality, festive freeze "
         "window from October) each have an owner, trigger and mitigation; go-live is scheduled before the "
         "festive freeze."),
        ("4. Commercial Proposal",
         ("table", [
             ["Item", "Basis", "Amount (INR)"],
             ["NexaDesk licence (350 agents)", "Rs 1,750 per agent/month x 12", "73,50,000"],
             ["Festive burst (250 agents x 3 months)", "Rs 1,400 per agent/month (discounted)", "10,50,000"],
             ["Implementation (fixed price)", "Milestone-linked payments", "58,00,000"],
             ["Data migration (3 trial loads)", "Fixed price", "9,00,000"],
             ["24x7 support and success management", "Annual", "12,00,000"],
             ["<b>Total Year 1</b>", "", "<b>1,63,00,000</b>"],
             ["<b>Year 2 and 3 (each)</b>", "Licences + burst + support, 4% uplift cap", "<b>99,84,000</b>"],
         ], [70, 60, 44], True),
         "<b>Assumptions:</b> excludes GST; 20% of implementation fee withheld until hypercare sign-off; "
         "WhatsApp and telephony usage at pass-through cost. Three-year TCO approximately Rs 3.63 crore."),
        ("5. Security and Compliance",
         ("bullets", [
             "ISO/IEC 27001:2022 certified; SOC 2 Type II report (2025) available.",
             "AES-256 encryption at rest, TLS 1.2+ in transit; SSO via SAML 2.0; MFA enforced for admins.",
             "DPDP Act 2023 controls: consent records, data principal rights requests, retention policies.",
             "Annual third-party penetration test; audit logs retained 3 years (extendable).",
         ])),
        ("6. Support Model, Experience and References",
         "<b>Support:</b> 24x7 multilingual service desk (English, Hindi, Marathi, Tamil) in Pune; P1 response "
         "15 minutes, P1 resolution 4 hours, P2 resolution 8 hours; 99.9% uptime SLA with service credits; "
         "named Customer Success Manager with quarterly business reviews; monthly release notes and "
         "admin training; 6-week hypercare with on-site presence in week 1.",
         "<b>Experience:</b> 14 contact-centre deployments since 2017, 5 in retail.",
         ("bullets", [
             "<b>Sahyadri Supermarkets</b> (fictional) - 500 agents, SAP S/4HANA, live 2023.",
             "<b>TrendKart Online</b> (fictional) - 800 agents peak, Salesforce, live 2024.",
             "<b>Coastal Home Appliances</b> (fictional) - 180 agents, live 2025.",
             "Reference contacts for all three provided in Annex C.",
         ])),
    ]))

# ---------------------------------------------------------------- 4. Orbit
suppliers.append(dict(
    file="04_Orbit_Digital_Proposal.pdf", name="Orbit Digital Services Pvt. Ltd.", date="2026-09-20",
    validity="90 days", contact="Meera Chandra, Client Partner (meera.chandra@orbitdigital.example)",
    sections=[
        ("1. Executive Summary",
         f"{REQ}",
         "Orbit Digital brings <b>18 years of customer-experience delivery</b> and more than 40 contact-centre "
         "programmes across retail, banking and telecom. We propose <b>OrbitCX</b>, our configurable "
         "service platform, supported by a seasoned delivery team that has seen every festive-season "
         "challenge Indian retail can produce."),
        ("2. Proposed Solution",
         "OrbitCX provides email, chat, WhatsApp and voice callback in a unified agent desktop with "
         "knowledge base, SLA management and analytics. Hosting is in an India data centre.",
         "<b>Integrations:</b> OrbitCX has a flexible integration layer and has integrated with many ERP and "
         "CRM systems over the years. Integration with SAP and Salesforce will be designed during the "
         "discovery phase, depending on Meridian's landscape, and may use middleware, APIs or batch "
         "files as appropriate. Details of the integration architecture will be shared after discovery.",
         "Scalability: the platform is used by large enterprises and will scale to Meridian's volumes."),
        ("3. Implementation Approach and Timeline",
         "Orbit uses its <b>OrbitWay</b> delivery methodology refined over 40+ programmes.",
         ("table", [
             ["Stage", "Indicative duration"],
             ["Discovery & integration design", "6 weeks"],
             ["Build and configuration", "8 weeks"],
             ["Testing and UAT", "5 weeks"],
             ["Rollout and stabilisation", "5 weeks"],
             ["<b>Total</b>", "<b>24-26 weeks</b>"],
         ], [100, 74], True),
         "Note: timeline for integrations will be confirmed after discovery and could extend the plan. "
         "<b>Team:</b> delivery director, project manager, 2 functional consultants, 3 technical "
         "consultants, QA lead, trainer (9 FTE)."),
        ("4. Commercial Proposal",
         ("table", [
             ["Item", "Basis", "Amount (INR)"],
             ["OrbitCX licence (350 agents)", "Rs 2,100 per agent/month x 12", "88,20,000"],
             ["Festive burst (250 agents x 3 months)", "Rs 2,100 per agent/month", "15,75,000"],
             ["Implementation services", "Time & material estimate", "65,00,000"],
             ["Integration services", "Estimate, to be confirmed after discovery", "18,00,000"],
             ["Support (business hours + P1 24x7)", "Annual", "15,00,000"],
             ["<b>Total Year 1 (indicative)</b>", "", "<b>2,01,95,000</b>"],
         ], [70, 60, 44], True),
         "<b>Assumptions:</b> excludes GST and travel; implementation on time-and-material basis with "
         "+/- 15% variance; integration estimate may change after discovery; Year 2+ licence at prevailing "
         "list price."),
        ("5. Security, Compliance and Risk",
         ("bullets", [
             "ISO/IEC 27001:2013 certified (transition to 2022 version in progress).",
             "Data hosted in India; encryption at rest and in transit; role-based access.",
             "DPDP Act 2023 compliance programme under way across all Orbit products.",
             "Annual penetration testing; disaster recovery site available (RTO 8 hours).",
         ]),
         "<b>Key risk:</b> integration scope is not yet defined; Orbit will manage this through change "
         "control."),
        ("6. Support Model, Experience and References",
         "Support from our Chennai service centre: business hours for P2-P4, 24x7 for P1 with 30-minute "
         "response; 99.9% uptime target. Dedicated account manager.",
         "<b>Experience:</b> 18 years; 40+ contact-centre programmes; 12 retail clients; 2,500+ agents "
         "currently supported on OrbitCX.",
         ("bullets", [
             "<b>Dhanlaxmi Department Stores</b> (fictional) - 600 agents, live since 2019; reference: Head of CX.",
             "<b>Pinnacle Bank</b> (fictional) - 1,100 agents, live since 2021; reference: VP Service Operations.",
             "<b>Swift Telecom</b> (fictional) - 900 agents, live since 2022; reference: CIO.",
             "<b>GreenBasket Grocery</b> (fictional) - 300 agents, live since 2024; reference: COO.",
             "Customer satisfaction across our install base: average CSAT 4.5/5 (2025 survey).",
         ])),
    ]))

# ---------------------------------------------------------------- 5. Zenith (edge case)
suppliers.append(dict(
    file="05_Zenith_CloudWorks_Proposal.pdf", name="Zenith CloudWorks", date="2026-09-25",
    validity="Not stated", contact="info@zenithcloud.example",
    sections=[
        ("1. Introduction",
         "Zenith CloudWorks is pleased to respond to Meridian's requirement for a customer service "
         "platform. Zenith is an AI-first company that believes chatbots will handle the majority of "
         "customer queries in the near future."),
        ("2. Our Solution",
         "<b>ZenBot</b> is a generative-AI chatbot that can answer customer questions on websites and "
         "WhatsApp, reducing the need for human agents. Human hand-off to agents is possible using a "
         "third-party helpdesk of the customer's choice.",
         ("bullets", [
             "Trains on your FAQs and policy documents within days.",
             "Supports 12 Indian languages.",
             "Can connect to any system through APIs.",
             "Email and voice channels are not part of ZenBot.",
         ]),
         "We believe Meridian can reduce its agent headcount significantly with ZenBot. Our solution "
         "will be configured according to Meridian's needs."),
        ("3. Approach",
         "We will start with a proof of concept, then expand. Exact timeline will depend on the "
         "proof-of-concept results. Team details will be shared at the time of contracting."),
        ("4. Pricing",
         "Pricing is usage-based and will be shared on request after understanding Meridian's "
         "monthly conversation volume. A free 30-day proof of concept is offered."),
        ("5. Security",
         "ZenBot runs on secure cloud infrastructure."),
        ("6. About Us",
         "Zenith CloudWorks was founded in 2025 and has a passionate team of AI engineers. We are "
         "currently working with early-adopter customers. Customer names cannot be disclosed. "
         "Support is provided by email."),
    ]))

for s in suppliers:
    print(build(s))
