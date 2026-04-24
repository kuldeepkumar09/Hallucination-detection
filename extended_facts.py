"""
Extended authoritative facts for the hallucination detection KB.
60+ entries across MEDICAL, FINANCIAL, LEGAL, and GENERAL domains.
Run: python ingest_extended_facts.py
"""

EXTENDED_FACTS = [

    # ── MEDICAL ─────────────────────────────────────────────────────────────

    {
        "source": "medical_aspirin_reye",
        "category": "MEDICAL",
        "fact": (
            "Aspirin (acetylsalicylic acid) must NOT be given to children under 16 due to the "
            "risk of Reye's syndrome — a rare, potentially fatal condition causing acute liver "
            "failure and brain swelling. The NHS and CDC both advise paracetamol or ibuprofen "
            "as safer alternatives for fever and pain in children."
        ),
    },
    {
        "source": "medical_ibuprofen_pregnancy",
        "category": "MEDICAL",
        "fact": (
            "Ibuprofen is NOT safe throughout all trimesters of pregnancy. It is generally "
            "avoided in the third trimester because it can cause premature closure of the "
            "ductus arteriosus (a fetal heart vessel) and reduce amniotic fluid. Paracetamol "
            "is the preferred analgesic during pregnancy in the UK and most countries."
        ),
    },
    {
        "source": "medical_penicillin_discovery",
        "category": "MEDICAL",
        "fact": (
            "Penicillin was discovered by Alexander Fleming in 1928 when he observed mould "
            "(Penicillium notatum) inhibiting bacterial growth on a culture plate. It was "
            "not mass-produced until the 1940s. Fleming, Florey, and Chain shared the Nobel "
            "Prize in Physiology or Medicine in 1945 for this work."
        ),
    },
    {
        "source": "medical_covid_vaccine_pfizer",
        "category": "MEDICAL",
        "fact": (
            "The first COVID-19 vaccine authorised for emergency use was the Pfizer-BioNTech "
            "BNT162b2 vaccine, approved by the UK's MHRA on 2 December 2020. The US FDA "
            "granted Emergency Use Authorisation on 11 December 2020. It uses mRNA technology "
            "to instruct cells to produce the SARS-CoV-2 spike protein."
        ),
    },
    {
        "source": "medical_vaccines_autism_debunked",
        "category": "MEDICAL",
        "fact": (
            "Vaccines do NOT cause autism. The 1998 Lancet paper by Andrew Wakefield claiming "
            "a link between the MMR vaccine and autism was fully retracted in 2010 due to "
            "ethical violations and fabricated data. Wakefield lost his medical licence. "
            "Studies involving over 1.2 million children have found no causal link between "
            "any vaccine and autism spectrum disorder."
        ),
    },
    {
        "source": "medical_diabetes_stats_2021",
        "category": "MEDICAL",
        "fact": (
            "According to the International Diabetes Federation (IDF) Diabetes Atlas 2021, "
            "537 million adults aged 20-79 were living with diabetes worldwide — NOT 2 billion. "
            "This is projected to rise to 643 million by 2030 and 783 million by 2045. "
            "Type 2 diabetes accounts for approximately 90-95% of all diabetes cases."
        ),
    },
    {
        "source": "medical_blood_types",
        "category": "MEDICAL",
        "fact": (
            "The ABO blood group system has four main types: A, B, AB, and O. Type O negative "
            "is considered the universal donor for red blood cells. Type AB positive is the "
            "universal recipient. The Rh factor (positive or negative) is determined by the "
            "presence of the RhD antigen on red blood cells."
        ),
    },
    {
        "source": "medical_heart_disease_leading_cause",
        "category": "MEDICAL",
        "fact": (
            "Cardiovascular disease (heart disease and stroke) is the leading cause of death "
            "globally, responsible for approximately 17.9 million deaths per year according "
            "to the World Health Organization (WHO) — representing 32% of all global deaths. "
            "Ischaemic heart disease and stroke are the two biggest killers."
        ),
    },
    {
        "source": "medical_hiv_aids_distinction",
        "category": "MEDICAL",
        "fact": (
            "HIV (Human Immunodeficiency Virus) is the virus that causes AIDS (Acquired "
            "Immunodeficiency Syndrome). HIV destroys CD4+ T cells, weakening the immune "
            "system. AIDS is the late stage of HIV infection when the CD4 count drops below "
            "200 cells/mm³ or when AIDS-defining illnesses occur. Not everyone with HIV "
            "develops AIDS — antiretroviral therapy (ART) can prevent progression."
        ),
    },
    {
        "source": "medical_smoking_cancer_link",
        "category": "MEDICAL",
        "fact": (
            "Smoking is the single largest preventable cause of cancer in the world. "
            "It causes at least 15 types of cancer including lung, mouth, throat, oesophagus, "
            "stomach, pancreas, kidney, bladder, and cervix. Smoking causes approximately "
            "70% of lung cancer cases. The link between smoking and lung cancer was "
            "established in studies by Richard Doll and Austin Bradford Hill in the 1950s."
        ),
    },
    {
        "source": "medical_malaria_plasmodium",
        "category": "MEDICAL",
        "fact": (
            "Malaria is caused by Plasmodium parasites transmitted through the bites of "
            "infected female Anopheles mosquitoes — NOT by bacteria or viruses. There are "
            "five species that infect humans; Plasmodium falciparum is the most deadly. "
            "WHO reported 249 million malaria cases and 608,000 deaths globally in 2022, "
            "with over 90% of deaths occurring in sub-Saharan Africa."
        ),
    },
    {
        "source": "medical_antibiotic_resistance",
        "category": "MEDICAL",
        "fact": (
            "Antibiotics treat bacterial infections — they do NOT work against viral infections "
            "such as the common cold, influenza, or COVID-19. Overuse and misuse of antibiotics "
            "is the primary driver of antimicrobial resistance (AMR). The WHO classifies AMR "
            "as one of the top 10 global public health threats. In 2019, AMR was directly "
            "responsible for 1.27 million deaths worldwide."
        ),
    },

    # ── FINANCIAL ───────────────────────────────────────────────────────────

    {
        "source": "financial_inflation_definition",
        "category": "FINANCIAL",
        "fact": (
            "Inflation is the rate at which the general level of prices for goods and services "
            "rises over time, eroding purchasing power. Central banks typically target an "
            "inflation rate of around 2% per year as a sign of a healthy economy. It is "
            "measured by indices such as the Consumer Price Index (CPI) and the Producer "
            "Price Index (PPI). Hyperinflation occurs when inflation exceeds 50% per month."
        ),
    },
    {
        "source": "financial_sp500_index",
        "category": "FINANCIAL",
        "fact": (
            "The S&P 500 (Standard & Poor's 500) is a stock market index tracking the "
            "performance of 500 large companies listed on US stock exchanges. It is widely "
            "regarded as the best single gauge of large-cap US equities. The index is "
            "market-capitalisation weighted, meaning larger companies have a bigger influence "
            "on the index value. It was introduced in its current 500-stock form in 1957."
        ),
    },
    {
        "source": "financial_gdp_definition",
        "category": "FINANCIAL",
        "fact": (
            "Gross Domestic Product (GDP) is the total monetary value of all goods and services "
            "produced within a country's borders in a specific time period. It is the broadest "
            "measure of economic output and activity. GDP can be measured three ways: "
            "expenditure approach (C+I+G+NX), income approach, and production/output approach. "
            "The US has the world's largest GDP by nominal value; China has the largest by "
            "purchasing power parity (PPP)."
        ),
    },
    {
        "source": "financial_compound_interest",
        "category": "FINANCIAL",
        "fact": (
            "Compound interest is interest calculated on both the initial principal and the "
            "accumulated interest from previous periods. The formula is A = P(1 + r/n)^(nt), "
            "where P is principal, r is annual interest rate, n is compounding periods per "
            "year, and t is time in years. The more frequently interest compounds (daily vs "
            "annually), the greater the effective annual return. Simple interest calculates "
            "interest only on the original principal."
        ),
    },
    {
        "source": "financial_bitcoin_creation",
        "category": "FINANCIAL",
        "fact": (
            "Bitcoin was created in 2009 by an anonymous person or group using the pseudonym "
            "Satoshi Nakamoto. The maximum supply of Bitcoin is capped at 21 million coins. "
            "Bitcoin uses blockchain technology — a distributed ledger maintained by a "
            "decentralised network of computers (nodes). Bitcoin is NOT legal tender in most "
            "countries, though El Salvador adopted it as legal tender in 2021."
        ),
    },
    {
        "source": "financial_interest_rates_central_banks",
        "category": "FINANCIAL",
        "fact": (
            "Central banks use interest rates as a primary monetary policy tool. Raising "
            "interest rates makes borrowing more expensive, slowing economic activity and "
            "reducing inflation. Lowering rates stimulates borrowing and spending. The US "
            "Federal Reserve's key rate is the federal funds rate. The Bank of England sets "
            "the base rate. The European Central Bank sets the main refinancing operations rate."
        ),
    },
    {
        "source": "financial_diversification",
        "category": "FINANCIAL",
        "fact": (
            "Portfolio diversification is an investment strategy that reduces risk by spreading "
            "investments across different asset classes, sectors, and geographies. Harry "
            "Markowitz introduced Modern Portfolio Theory (MPT) in 1952, demonstrating "
            "mathematically that a diversified portfolio offers better risk-adjusted returns "
            "than individual assets. The principle: 'Don't put all your eggs in one basket.' "
            "Diversification reduces unsystematic (company-specific) risk but not systematic "
            "(market-wide) risk."
        ),
    },
    {
        "source": "financial_recession_definition",
        "category": "FINANCIAL",
        "fact": (
            "A recession is commonly defined as two consecutive quarters of negative GDP growth. "
            "However, the National Bureau of Economic Research (NBER) in the US uses a broader "
            "definition based on depth, duration, and diffusion of economic decline across "
            "sectors. A depression is a severe, prolonged recession. The Great Depression "
            "(1929-1939) was the worst economic downturn in modern history, with US GDP "
            "falling by about 30% and unemployment reaching 25%."
        ),
    },
    {
        "source": "financial_etf_definition",
        "category": "FINANCIAL",
        "fact": (
            "An Exchange-Traded Fund (ETF) is an investment fund that tracks an index, "
            "commodity, bond, or basket of assets and trades on a stock exchange like a "
            "regular stock. ETFs typically have lower expense ratios than actively managed "
            "mutual funds. The first ETF, the SPDR S&P 500 ETF Trust (SPY), was launched "
            "in 1993. ETFs provide intraday liquidity, unlike mutual funds which trade at "
            "end-of-day net asset value (NAV)."
        ),
    },
    {
        "source": "financial_quantitative_easing",
        "category": "FINANCIAL",
        "fact": (
            "Quantitative Easing (QE) is an unconventional monetary policy where a central "
            "bank purchases government bonds or other financial assets to inject money into "
            "the economy and stimulate lending. It is used when conventional interest-rate "
            "cuts are insufficient (near the zero lower bound). The US Federal Reserve used "
            "QE extensively after the 2008 financial crisis and again during COVID-19. "
            "Critics argue QE can cause asset price inflation and wealth inequality."
        ),
    },

    # ── LEGAL ────────────────────────────────────────────────────────────────

    {
        "source": "legal_gdpr_entry_into_force",
        "category": "LEGAL",
        "fact": (
            "The EU General Data Protection Regulation (GDPR) entered into force on "
            "25 May 2018 — NOT 1 June 2019. It replaced the 1995 Data Protection Directive. "
            "GDPR applies to all organisations processing personal data of EU residents, "
            "regardless of where the organisation is based. Maximum fines are €20 million "
            "or 4% of global annual turnover, whichever is higher — NOT 2%."
        ),
    },
    {
        "source": "legal_gdpr_breach_notification",
        "category": "LEGAL",
        "fact": (
            "Under GDPR Article 33, personal data breaches must be reported to the relevant "
            "supervisory authority within 72 hours of becoming aware of the breach — NOT "
            "24 hours. If the breach is unlikely to result in a risk to individuals' rights "
            "and freedoms, notification may not be required. Breaches posing high risk to "
            "individuals must also be communicated directly to those affected (Article 34)."
        ),
    },
    {
        "source": "legal_gdpr_dpo_requirement",
        "category": "LEGAL",
        "fact": (
            "Not all organisations must appoint a Data Protection Officer (DPO) under GDPR. "
            "A DPO is required for: public authorities and bodies; organisations whose core "
            "activities involve large-scale systematic monitoring of individuals; and "
            "organisations processing special categories of data at large scale. "
            "The DPO must have expert knowledge of data protection law and practice."
        ),
    },
    {
        "source": "legal_us_constitution_first_amendment",
        "category": "LEGAL",
        "fact": (
            "The First Amendment to the US Constitution protects freedom of speech, religion, "
            "press, assembly, and the right to petition the government. It prohibits Congress "
            "from making laws that abridge these freedoms. However, free speech is not "
            "absolute — exceptions include incitement to imminent lawless action, defamation, "
            "obscenity, and true threats. The First Amendment restricts government action, "
            "not private entities."
        ),
    },
    {
        "source": "legal_contract_elements",
        "category": "LEGAL",
        "fact": (
            "A legally binding contract requires four essential elements: offer (a clear "
            "proposal), acceptance (unambiguous agreement to all terms), consideration "
            "(something of value exchanged by both parties), and intention to create legal "
            "relations. In common law jurisdictions, contracts need not be in writing to "
            "be enforceable, with some exceptions (e.g., real estate transfers, contracts "
            "exceeding one year under the Statute of Frauds)."
        ),
    },
    {
        "source": "legal_presumption_of_innocence",
        "category": "LEGAL",
        "fact": (
            "The presumption of innocence — 'innocent until proven guilty' — is a fundamental "
            "principle of criminal law in most countries. The prosecution bears the burden of "
            "proof to establish guilt 'beyond a reasonable doubt' in criminal cases. In civil "
            "cases, the standard of proof is typically 'balance of probabilities' (more likely "
            "than not — over 50%). This is enshrined in Article 6(2) of the European "
            "Convention on Human Rights."
        ),
    },
    {
        "source": "legal_intellectual_property_types",
        "category": "LEGAL",
        "fact": (
            "Intellectual property (IP) law protects creations of the mind. The main types "
            "are: patents (inventions, typically 20 years); copyright (original works — "
            "literary, artistic, musical — typically life + 70 years in most jurisdictions); "
            "trademarks (brand identifiers, renewable indefinitely with use); and trade secrets "
            "(confidential business information with no expiry). IP rights are territorial — "
            "protection in one country does not automatically extend globally."
        ),
    },
    {
        "source": "legal_habeas_corpus",
        "category": "LEGAL",
        "fact": (
            "Habeas corpus (Latin: 'you shall have the body') is a legal writ requiring a "
            "person under arrest to be brought before a judge. It protects against unlawful "
            "detention and is one of the oldest legal protections in common law, originating "
            "in the Magna Carta (1215) and codified in England's Habeas Corpus Act 1679. "
            "It can be suspended in extraordinary circumstances — in the US, only by Congress "
            "in cases of rebellion or invasion."
        ),
    },
    {
        "source": "legal_gdpr_lawful_basis",
        "category": "LEGAL",
        "fact": (
            "Under GDPR Article 6, processing of personal data is only lawful if at least "
            "one of six lawful bases applies: (1) consent, (2) contract performance, "
            "(3) legal obligation, (4) vital interests, (5) public task, or (6) legitimate "
            "interests. Consent under GDPR must be freely given, specific, informed, and "
            "unambiguous — pre-ticked boxes do not constitute valid consent."
        ),
    },

    # ── GENERAL ─────────────────────────────────────────────────────────────

    {
        "source": "general_great_wall_moon",
        "category": "GENERAL",
        "fact": (
            "The Great Wall of China is NOT visible from the Moon with the naked eye. "
            "The wall is approximately 15-30 metres wide — far too narrow to be seen from "
            "384,400 km away. NASA and multiple astronauts have confirmed this. The myth "
            "predates the Moon landings, appearing in print as early as 1932. From low "
            "Earth orbit (~400 km), it is theoretically possible under perfect conditions "
            "but extremely difficult in practice."
        ),
    },
    {
        "source": "general_einstein_nobel",
        "category": "GENERAL",
        "fact": (
            "Albert Einstein won the Nobel Prize in Physics in 1921 — NOT for his Theory "
            "of Relativity but for the discovery of the law of the photoelectric effect. "
            "Einstein was born on 14 March 1879 in Ulm, Germany (not Berlin). He did NOT "
            "fail mathematics in school; he was exceptional at mathematics and physics. "
            "He published his Special Theory of Relativity in 1905 and General Relativity "
            "in 1915."
        ),
    },
    {
        "source": "general_speed_of_light",
        "category": "GENERAL",
        "fact": (
            "The speed of light in a vacuum is exactly 299,792,458 metres per second "
            "(approximately 300,000 km/s or 186,282 miles per second). This is not an "
            "approximation — it is a defined constant since 1983, used to define the metre. "
            "Nothing with mass can reach or exceed the speed of light. Light takes "
            "approximately 8 minutes and 20 seconds to travel from the Sun to Earth."
        ),
    },
    {
        "source": "general_ww2_dates",
        "category": "GENERAL",
        "fact": (
            "World War II began on 1 September 1939 when Germany invaded Poland, and ended "
            "in 1945. Germany surrendered unconditionally on 8 May 1945 (V-E Day). Japan "
            "formally surrendered on 2 September 1945 aboard USS Missouri, following atomic "
            "bombings of Hiroshima (6 August 1945, 'Little Boy') and Nagasaki (9 August 1945, "
            "'Fat Man'). The war caused an estimated 70-85 million deaths."
        ),
    },
    {
        "source": "general_india_population_2023",
        "category": "GENERAL",
        "fact": (
            "India surpassed China to become the world's most populous country in 2023, "
            "with a population of approximately 1.43 billion people — NOT 2.5 billion. "
            "The global population reached 8 billion in November 2022. China's population "
            "began declining in 2022 for the first time since the 1960s Great Famine. "
            "India's population is projected to continue growing until approximately 2064."
        ),
    },
    {
        "source": "general_napoleon_height",
        "category": "GENERAL",
        "fact": (
            "Napoleon Bonaparte was NOT unusually short. He stood approximately 5 feet 7 "
            "inches (170 cm), which was average or slightly above average for a Frenchman "
            "of his era. The myth arose from a misunderstanding between French and English "
            "measurement units (French 'pouces' vs English inches) and deliberate British "
            "propaganda, particularly caricatures by James Gillray. Napoleon was born "
            "15 August 1769 in Ajaccio, Corsica."
        ),
    },
    {
        "source": "general_columbus_flat_earth",
        "category": "GENERAL",
        "fact": (
            "Christopher Columbus did NOT set out to prove the Earth was round — medieval "
            "Europeans already knew the Earth was spherical, a fact established by ancient "
            "Greek scholars including Pythagoras and Eratosthenes (who accurately calculated "
            "Earth's circumference around 240 BC). Columbus's dispute with Spanish scholars "
            "was about the SIZE of the Earth. Columbus reached the Caribbean on 12 October "
            "1492, NOT the North American mainland."
        ),
    },
    {
        "source": "general_human_dna",
        "category": "GENERAL",
        "fact": (
            "Human DNA consists of approximately 3 billion base pairs organised into 23 pairs "
            "of chromosomes (46 total), contained in the nucleus of almost every cell. "
            "The human genome contains approximately 20,000-25,000 protein-coding genes. "
            "Humans share about 98.7% of their DNA with chimpanzees and about 60% with "
            "banana plants (shared genes, not whole genomes). DNA was first described as "
            "a double helix by Watson and Crick in 1953."
        ),
    },
    {
        "source": "general_moon_landing",
        "category": "GENERAL",
        "fact": (
            "Apollo 11 landed on the Moon on 20 July 1969. Neil Armstrong became the first "
            "human to walk on the Moon at 02:56 UTC on 21 July 1969, followed by Buzz Aldrin. "
            "Michael Collins orbited the Moon in the Command Module. The mission used Saturn V "
            "rockets and took approximately 8 days total. Six Apollo missions successfully "
            "landed on the Moon between 1969 and 1972 (Apollo 11, 12, 14, 15, 16, 17)."
        ),
    },
    {
        "source": "general_climate_change_co2",
        "category": "GENERAL",
        "fact": (
            "Carbon dioxide (CO2) concentration in Earth's atmosphere reached 421 parts per "
            "million (ppm) in 2023 — the highest level in at least 800,000 years. "
            "Pre-industrial levels were approximately 280 ppm. The Intergovernmental Panel "
            "on Climate Change (IPCC) has concluded with high scientific confidence that "
            "human activities (primarily burning fossil fuels) are the dominant cause of "
            "observed warming since the mid-20th century."
        ),
    },
    {
        "source": "general_internet_creation",
        "category": "GENERAL",
        "fact": (
            "The Internet evolved from ARPANET, a US Department of Defense project from the "
            "late 1960s. The World Wide Web (WWW) was invented by Sir Tim Berners-Lee in "
            "1989-1991 at CERN — the web is not the same as the internet. The internet is "
            "the global network infrastructure; the web is a service running on it. "
            "The first website went live on 6 August 1991. As of 2023, approximately "
            "5.4 billion people use the internet globally."
        ),
    },
    {
        "source": "general_einstein_relativity",
        "category": "GENERAL",
        "fact": (
            "Einstein's Special Theory of Relativity (1905) introduced two postulates: "
            "(1) the laws of physics are the same in all inertial reference frames, and "
            "(2) the speed of light is constant regardless of the motion of the source or "
            "observer. It produced the famous equation E=mc² (energy equals mass times the "
            "speed of light squared). General Relativity (1915) extended this to include "
            "gravity, describing it as the curvature of spacetime caused by mass."
        ),
    },
    {
        "source": "general_periodic_table",
        "category": "GENERAL",
        "fact": (
            "The periodic table organises chemical elements by atomic number (number of "
            "protons). Dmitri Mendeleev published the first widely recognised periodic table "
            "in 1869, leaving gaps for undiscovered elements. As of 2024, there are 118 "
            "confirmed elements. Element 1 is Hydrogen (lightest), Element 79 is Gold (Au), "
            "Element 26 is Iron (Fe). Water (H2O) is composed of two hydrogen atoms and "
            "one oxygen atom — NOT H3O."
        ),
    },
    {
        "source": "general_black_holes",
        "category": "GENERAL",
        "fact": (
            "A black hole is a region of spacetime where gravity is so strong that nothing — "
            "not even light — can escape once it crosses the event horizon. They form when "
            "massive stars collapse at the end of their lives. Stephen Hawking theorised that "
            "black holes emit radiation (Hawking radiation) and slowly evaporate. The first "
            "direct image of a black hole (M87*) was captured by the Event Horizon Telescope "
            "in April 2019. The supermassive black hole at the Milky Way's centre is "
            "Sagittarius A*."
        ),
    },
    {
        "source": "general_evolution_darwin",
        "category": "GENERAL",
        "fact": (
            "Charles Darwin published 'On the Origin of Species' in 1859, presenting the "
            "theory of evolution by natural selection. The core idea: organisms with "
            "heritable traits better suited to their environment survive and reproduce more "
            "successfully. Darwin did NOT say humans evolved from chimpanzees — rather, "
            "humans and chimps share a common ancestor. Alfred Russel Wallace independently "
            "developed a similar theory, which prompted Darwin to publish his work."
        ),
    },
    {
        "source": "general_magna_carta",
        "category": "GENERAL",
        "fact": (
            "Magna Carta (Great Charter) was signed by King John of England on 15 June 1215 "
            "at Runnymede. It was the first document to limit royal power and establish that "
            "the king was subject to the rule of law. It established the principle of habeas "
            "corpus (protection against unlawful detention). Only three of the original 63 "
            "clauses remain in English law today. It is considered a foundational document "
            "for democracy and human rights."
        ),
    },
    {
        "source": "general_solar_system",
        "category": "GENERAL",
        "fact": (
            "The Solar System has 8 planets (Pluto was reclassified as a dwarf planet in 2006 "
            "by the International Astronomical Union): Mercury, Venus, Earth, Mars, Jupiter, "
            "Saturn, Uranus, Neptune. Jupiter is the largest planet — it could fit all other "
            "planets inside it. The Sun contains 99.86% of the Solar System's total mass. "
            "Earth is the only known planet to harbour life. The Sun is approximately "
            "4.6 billion years old."
        ),
    },
    {
        "source": "general_french_revolution",
        "category": "GENERAL",
        "fact": (
            "The French Revolution began in 1789 with the storming of the Bastille on "
            "14 July 1789 — now celebrated as Bastille Day. It overthrew the monarchy of "
            "King Louis XVI, who was guillotined on 21 January 1793. The Revolution produced "
            "the Declaration of the Rights of Man and of the Citizen (1789) and gave rise "
            "to the ideals of liberty, equality, and fraternity. Napoleon Bonaparte rose "
            "to power in the aftermath, becoming Emperor in 1804."
        ),
    },
    {
        "source": "general_hiroshima_bomb",
        "category": "GENERAL",
        "fact": (
            "The atomic bomb dropped on Hiroshima on 6 August 1945 was codenamed 'Little Boy' "
            "and used uranium-235. The bomb dropped on Nagasaki on 9 August 1945 was "
            "codenamed 'Fat Man' and used plutonium-239. Hiroshima and Nagasaki are in Japan. "
            "The Hiroshima bomb killed an estimated 70,000-80,000 people immediately, with "
            "total deaths (including radiation effects) estimated at 90,000-166,000. "
            "Japan surrendered on 15 August 1945."
        ),
    },
    {
        "source": "general_dna_watson_crick",
        "category": "GENERAL",
        "fact": (
            "The double helix structure of DNA was described by James Watson and Francis Crick "
            "in 1953, based on X-ray crystallography data from Rosalind Franklin and Raymond "
            "Gosling. Watson, Crick, and Maurice Wilkins received the Nobel Prize in Physiology "
            "or Medicine in 1962. Franklin died in 1958 and was not eligible for the Nobel "
            "Prize (which is not awarded posthumously). DNA stands for "
            "Deoxyribonucleic Acid."
        ),
    },

    # ── FINANCIAL (additional — common LLM claim phrasings) ─────────────────

    {
        "source": "financial_capital_gains_tax",
        "category": "FINANCIAL",
        "fact": (
            "In the United States, capital gains tax rates depend on the holding period. "
            "Short-term capital gains (assets held one year or less) are taxed as ordinary "
            "income at rates up to 37%. Long-term capital gains (assets held more than one "
            "year) are taxed at preferential rates of 0%, 15%, or 20% depending on taxable "
            "income. The 3.8% Net Investment Income Tax (NIIT) may apply to high earners. "
            "Capital gains are NOT taxed at a flat 20% for all investors."
        ),
    },
    {
        "source": "financial_federal_reserve_mandate",
        "category": "FINANCIAL",
        "fact": (
            "The Federal Reserve has a dual mandate established by Congress: maximum employment "
            "and stable prices (price stability). The Fed targets 2% inflation as measured by "
            "the Personal Consumption Expenditures (PCE) price index. The Federal Reserve is "
            "NOT a government agency — it is an independent central bank. The Fed funds rate "
            "is the interest rate at which banks lend reserve balances to each other overnight."
        ),
    },
    {
        "source": "financial_stock_market_crash_1929",
        "category": "FINANCIAL",
        "fact": (
            "The Wall Street Crash of 1929 began on Black Thursday (24 October 1929) and "
            "reached its worst on Black Tuesday (29 October 1929). The Dow Jones Industrial "
            "Average fell approximately 12% on Black Tuesday alone and lost nearly 90% of its "
            "value by 1932. The crash triggered the Great Depression, the worst economic "
            "downturn of the 20th century, lasting until about 1939. The crash was NOT caused "
            "by a single day event — it was a series of declines over several weeks."
        ),
    },
    {
        "source": "financial_fdic_insurance",
        "category": "FINANCIAL",
        "fact": (
            "The Federal Deposit Insurance Corporation (FDIC) insures deposits up to $250,000 "
            "per depositor, per FDIC-insured bank, per ownership category. Created in 1933 "
            "after the Great Depression bank failures, the FDIC covers checking accounts, "
            "savings accounts, money market deposit accounts, and CDs. Investment products "
            "such as stocks, bonds, mutual funds, and crypto are NOT FDIC-insured. The FDIC "
            "limit is $250,000, NOT $100,000 (which was the limit before 2008)."
        ),
    },
    {
        "source": "financial_401k_limits_2024",
        "category": "FINANCIAL",
        "fact": (
            "For 2024, the IRS contribution limit for 401(k) plans is $23,000 per year for "
            "employees under age 50. Workers aged 50 and over may make an additional catch-up "
            "contribution of $7,500, bringing the total to $30,500. Employer contributions "
            "do not count toward the employee elective deferral limit but are subject to the "
            "combined limit of $69,000 (or $76,500 with catch-up). 401(k) contributions "
            "reduce taxable income in the year of contribution (traditional 401k)."
        ),
    },
    {
        "source": "financial_us_debt_ceiling",
        "category": "FINANCIAL",
        "fact": (
            "The United States debt ceiling is a statutory limit set by Congress on the total "
            "amount of money the federal government is authorized to borrow to meet its "
            "existing legal obligations. Reaching the debt ceiling does NOT prevent the "
            "government from spending more than it takes in — it prevents the Treasury from "
            "issuing new debt to pay for spending already approved by Congress. Failure to "
            "raise the ceiling can lead to a technical default on US Treasury obligations."
        ),
    },
    {
        "source": "financial_margin_trading",
        "category": "FINANCIAL",
        "fact": (
            "Margin trading allows investors to borrow money from a broker to purchase "
            "securities. The initial margin requirement set by Regulation T is 50% — meaning "
            "investors can borrow up to 50% of the purchase price. A margin call occurs when "
            "the account equity falls below the maintenance margin (typically 25% of market "
            "value), requiring the investor to deposit more funds or sell assets. Margin "
            "trading amplifies both gains and losses."
        ),
    },
    {
        "source": "financial_options_call_put",
        "category": "FINANCIAL",
        "fact": (
            "An options contract gives the buyer the right, but NOT the obligation, to buy "
            "or sell an underlying asset at a specified price (strike price) on or before a "
            "specified date (expiration). A call option gives the right to BUY the asset. "
            "A put option gives the right to SELL the asset. The buyer pays a premium for "
            "this right. Options are used for hedging, speculation, and income generation. "
            "The seller (writer) of the option is obligated to fulfill the contract if exercised."
        ),
    },
    {
        "source": "financial_yield_curve",
        "category": "FINANCIAL",
        "fact": (
            "The yield curve plots interest rates of bonds with equal credit quality but "
            "different maturity dates. A normal yield curve slopes upward (longer maturities "
            "have higher yields). An inverted yield curve occurs when short-term rates exceed "
            "long-term rates and has historically preceded US recessions. The 2-year/10-year "
            "Treasury spread is the most watched recession indicator. The yield curve is NOT "
            "controlled by the Federal Reserve — the Fed controls only short-term rates directly."
        ),
    },
    {
        "source": "financial_dodd_frank_act",
        "category": "FINANCIAL",
        "fact": (
            "The Dodd-Frank Wall Street Reform and Consumer Protection Act was signed into law "
            "by President Obama on 21 July 2010 in response to the 2008 financial crisis. "
            "It created the Consumer Financial Protection Bureau (CFPB), established the "
            "Financial Stability Oversight Council (FSOC), introduced the Volcker Rule "
            "(restricting proprietary trading by banks), and required more derivatives to "
            "be traded on exchanges. Dodd-Frank is NOT the same as the Glass-Steagall Act "
            "(which was repealed in 1999)."
        ),
    },
    {
        "source": "financial_fico_credit_score",
        "category": "FINANCIAL",
        "fact": (
            "FICO credit scores range from 300 to 850. Scores are categorized as: "
            "Poor (300-579), Fair (580-669), Good (670-739), Very Good (740-799), "
            "and Exceptional (800-850). A score of 670 or above is generally considered "
            "good by most lenders. FICO scores are calculated using five factors: payment "
            "history (35%), amounts owed (30%), length of credit history (15%), new credit "
            "(10%), and credit mix (10%). A score of 850 is perfect but extremely rare."
        ),
    },
    {
        "source": "financial_hedge_fund_vs_mutual_fund",
        "category": "FINANCIAL",
        "fact": (
            "Hedge funds are private investment vehicles open only to accredited investors "
            "(individuals with net worth over $1 million excluding primary residence, or "
            "annual income over $200,000). Hedge funds face fewer SEC regulations than "
            "mutual funds, can use leverage and short selling, and typically charge '2 and 20' "
            "(2% management fee + 20% of profits). Mutual funds are registered with the SEC, "
            "open to all investors, cannot use unlimited leverage, and must disclose holdings "
            "quarterly. Hedge funds are NOT regulated like mutual funds."
        ),
    },
    {
        "source": "financial_us_tax_brackets_2024",
        "category": "FINANCIAL",
        "fact": (
            "For 2024, the US federal income tax brackets for single filers are: 10% on income "
            "up to $11,600; 12% from $11,601 to $47,150; 22% from $47,151 to $100,525; "
            "24% from $100,526 to $191,950; 32% from $191,951 to $243,725; "
            "35% from $243,726 to $609,350; 37% over $609,350. The US uses a progressive "
            "tax system where each bracket rate applies ONLY to income within that bracket, "
            "NOT to total income."
        ),
    },
    {
        "source": "financial_basel_iii",
        "category": "FINANCIAL",
        "fact": (
            "Basel III is an international regulatory framework developed by the Basel Committee "
            "on Banking Supervision (BCBS) after the 2008 financial crisis. It requires banks "
            "to maintain minimum capital ratios: Common Equity Tier 1 (CET1) of at least 4.5% "
            "of risk-weighted assets, Tier 1 capital of 6%, and total capital of 8%. Basel III "
            "also introduced liquidity requirements (Liquidity Coverage Ratio and Net Stable "
            "Funding Ratio) and a leverage ratio of 3%. Basel III strengthened requirements "
            "compared to Basel II."
        ),
    },
    {
        "source": "financial_fixed_vs_arm_mortgage",
        "category": "FINANCIAL",
        "fact": (
            "A fixed-rate mortgage has an interest rate that remains constant for the entire "
            "loan term (typically 15 or 30 years), providing predictable monthly payments. "
            "An adjustable-rate mortgage (ARM) has an initial fixed period (e.g., 5/1 ARM "
            "means fixed for 5 years) after which the rate adjusts annually based on a "
            "benchmark index plus a margin. ARMs typically start with lower rates than "
            "fixed mortgages but carry interest rate risk. The most common mortgage term "
            "in the US is 30 years."
        ),
    },

    # ── LEGAL (additional — common LLM claim phrasings) ─────────────────────

    {
        "source": "legal_gdpr_right_to_erasure",
        "category": "LEGAL",
        "fact": (
            "Article 17 of the GDPR grants individuals the 'right to erasure' (also called "
            "the 'right to be forgotten'). Individuals can request deletion of their personal "
            "data when it is no longer necessary for the original purpose, consent is withdrawn "
            "and there is no other legal basis, or the data was unlawfully processed. The right "
            "is NOT absolute — exceptions include exercising freedom of expression, compliance "
            "with legal obligations, and archiving in the public interest. Controllers must "
            "respond within one month."
        ),
    },
    {
        "source": "legal_gdpr_data_portability",
        "category": "LEGAL",
        "fact": (
            "Article 20 of the GDPR grants the right to data portability. Individuals have the "
            "right to receive their personal data in a structured, commonly used, and "
            "machine-readable format (such as JSON or CSV), and to transmit that data to "
            "another controller. This right applies when processing is based on consent or "
            "contract and is carried out by automated means. Controllers are NOT required to "
            "adopt compatible systems with other controllers, but must provide data in an "
            "interoperable format where technically feasible."
        ),
    },
    {
        "source": "legal_gdpr_fine_calculation",
        "category": "LEGAL",
        "fact": (
            "GDPR fines can reach up to €20 million or 4% of the company's total global annual "
            "turnover of the preceding financial year, whichever is higher (for serious "
            "violations under Article 83(5)). Lower-tier violations (Article 83(4)) carry "
            "fines up to €10 million or 2% of global annual turnover. The maximum GDPR fine "
            "is €20 million or 4% of global turnover — NOT a flat €20 million for all "
            "violations. The supervisory authority has discretion in setting the actual fine."
        ),
    },
    {
        "source": "legal_uk_gdpr_post_brexit",
        "category": "LEGAL",
        "fact": (
            "After Brexit, the United Kingdom retained data protection rules through the UK "
            "GDPR, which mirrors the EU GDPR but is a separate legal framework applying to "
            "UK-based organisations. The Information Commissioner's Office (ICO) is the UK's "
            "supervisory authority for data protection. The UK GDPR maximum fines are £17.5 "
            "million or 4% of global annual turnover (whichever is higher). UK organisations "
            "processing EU residents' data must still comply with the EU GDPR."
        ),
    },
    {
        "source": "legal_ccpa_california",
        "category": "LEGAL",
        "fact": (
            "The California Consumer Privacy Act (CCPA), effective January 1, 2020, grants "
            "California residents rights over their personal information held by businesses. "
            "Rights include: knowing what data is collected, deleting personal data, opting "
            "out of the sale of personal data, and non-discrimination for exercising rights. "
            "CCPA applies to for-profit businesses that meet certain thresholds (e.g., annual "
            "gross revenue over $25 million, or buy/sell/share data of 100,000+ consumers). "
            "The California Privacy Rights Act (CPRA) expanded CCPA rights from January 2023."
        ),
    },
    {
        "source": "legal_miranda_rights",
        "category": "LEGAL",
        "fact": (
            "Miranda rights (Miranda warning) are required in the United States before "
            "custodial interrogation. They inform suspects of their Fifth Amendment right "
            "against self-incrimination and Sixth Amendment right to counsel. The warning "
            "typically states: 'You have the right to remain silent. Anything you say can "
            "and will be used against you in a court of law. You have the right to an "
            "attorney.' Miranda rights stem from Miranda v. Arizona (1966). They are required "
            "during custodial interrogation, NOT simply upon arrest."
        ),
    },
    {
        "source": "legal_attorney_client_privilege",
        "category": "LEGAL",
        "fact": (
            "Attorney-client privilege protects confidential communications between a client "
            "and their attorney made for the purpose of seeking or providing legal advice. "
            "The privilege belongs to the client, not the attorney, and can only be waived "
            "by the client. Exceptions include the crime-fraud exception (communications "
            "made to further a crime or fraud are not protected). The privilege does NOT "
            "extend to communications with non-attorney legal staff in all jurisdictions, "
            "nor does it protect facts the attorney observes independently."
        ),
    },
    {
        "source": "legal_statute_of_limitations",
        "category": "LEGAL",
        "fact": (
            "A statute of limitations is the maximum time period after an event within which "
            "legal proceedings may be initiated. Time limits vary by jurisdiction and type of "
            "claim: in the US, personal injury claims are typically 2-3 years; contract "
            "disputes 3-6 years; written contracts up to 10 years in some states. There is "
            "NO general statute of limitations for murder in most jurisdictions. The clock "
            "typically starts from the date the cause of action accrues, though the discovery "
            "rule may delay the start in some cases."
        ),
    },
    {
        "source": "legal_double_jeopardy",
        "category": "LEGAL",
        "fact": (
            "The Double Jeopardy Clause of the Fifth Amendment to the US Constitution provides "
            "that no person shall 'be subject for the same offence to be twice put in jeopardy "
            "of life or limb.' This means a defendant acquitted or convicted of a crime cannot "
            "be tried again for the same offense in the same jurisdiction. However, the dual "
            "sovereignty doctrine allows prosecution by both state and federal governments for "
            "the same conduct. Double jeopardy attaches when the jury is sworn in (jury trial) "
            "or the first witness is sworn (bench trial)."
        ),
    },
    {
        "source": "legal_defamation_libel_slander",
        "category": "LEGAL",
        "fact": (
            "Defamation is a false statement of fact presented as true that damages a person's "
            "reputation. Libel refers to written or published defamation (including broadcast "
            "media in most jurisdictions). Slander refers to spoken defamation. To succeed in "
            "a defamation claim, the plaintiff must generally prove: the statement was false, "
            "it was published to a third party, it caused harm, and the defendant was at fault. "
            "Public figures must prove 'actual malice' (knowledge of falsity or reckless "
            "disregard for truth) under New York Times v. Sullivan (1964)."
        ),
    },
    {
        "source": "legal_employment_at_will",
        "category": "LEGAL",
        "fact": (
            "Employment at-will is the default employment doctrine in the United States "
            "(except Montana), allowing either the employer or employee to terminate the "
            "employment relationship at any time, for any reason (or no reason), without "
            "prior notice. Exceptions include terminations that violate anti-discrimination "
            "laws (Title VII, ADA, ADEA), breach an employment contract, violate public "
            "policy, or constitute unlawful retaliation. Most EU countries and the UK do NOT "
            "follow at-will employment — they require just cause for dismissal."
        ),
    },
    {
        "source": "legal_force_majeure",
        "category": "LEGAL",
        "fact": (
            "A force majeure clause in a contract excuses a party from performing contractual "
            "obligations when extraordinary events beyond their control make performance "
            "impossible or impractical. Common force majeure events include natural disasters, "
            "wars, government actions, pandemics, and strikes. Force majeure is NOT implied in "
            "contracts under English law — it must be expressly included. Courts interpret "
            "force majeure clauses narrowly. The COVID-19 pandemic prompted many force majeure "
            "claims, with courts examining whether contracts explicitly included pandemics."
        ),
    },
    {
        "source": "legal_nda_trade_secrets",
        "category": "LEGAL",
        "fact": (
            "A Non-Disclosure Agreement (NDA), also called a confidentiality agreement, is a "
            "legal contract protecting confidential information shared between parties. NDAs "
            "can be unilateral (one party discloses) or mutual (both parties share confidential "
            "information). Trade secrets are a category of intellectual property protected "
            "without registration for as long as secrecy is maintained. In the US, the "
            "Defend Trade Secrets Act (DTSA) of 2016 provides federal civil remedies for "
            "trade secret misappropriation. An NDA cannot protect information that is already "
            "publicly known."
        ),
    },
    {
        "source": "legal_class_action_lawsuit",
        "category": "LEGAL",
        "fact": (
            "A class action lawsuit allows one or more plaintiffs to sue on behalf of a larger "
            "group (class) of people who have suffered similar harm. In the US federal courts, "
            "class actions must meet requirements under Rule 23 of the Federal Rules of Civil "
            "Procedure: numerosity (enough class members), commonality (common legal questions), "
            "typicality, and adequate representation. Class members receive notice and can "
            "opt out. Settlements must be approved by the court. Class members who don't opt "
            "out are bound by the judgment and cannot sue separately."
        ),
    },
    {
        "source": "legal_shareholder_derivative_suit",
        "category": "LEGAL",
        "fact": (
            "A shareholder derivative suit is a lawsuit brought by a shareholder on behalf of "
            "the corporation against officers, directors, or third parties who have harmed the "
            "corporation. The shareholder sues in the corporation's name because the board "
            "has refused to take action. Any recovery goes to the corporation, not directly "
            "to the shareholder. Requirements typically include: the shareholder owned shares "
            "at the time of the alleged wrong, demand was made on the board (or demand is "
            "excused as futile), and the shareholder fairly represents the corporation's "
            "interests."
        ),
    },
]
