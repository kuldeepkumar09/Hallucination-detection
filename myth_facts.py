"""
Myth-busting fact pairs for the hallucination detection KB.

Each entry has:
  - myth:   A common false belief (what the KB should CONTRADICT)
  - fact:   The authoritative correction (what the KB stores as truth)
  - source: A label for the KB entry
  - category: MEDICAL | LEGAL | FINANCIAL | GENERAL

Ingested via ingest_myths.py
"""

MYTH_FACTS = [
    {
        "source": "myth_great_wall",
        "category": "GENERAL",
        "fact": (
            "The Great Wall of China is NOT visible from the Moon with the naked eye. "
            "The wall is only about 15-30 metres wide, far too narrow to be seen from "
            "a distance of 384,400 km. NASA has confirmed this. It is one of the most "
            "widely repeated myths about the wall."
        ),
    },
    {
        "source": "myth_einstein_failed_school",
        "category": "GENERAL",
        "fact": (
            "Albert Einstein did NOT fail mathematics in school. He was an excellent student "
            "in mathematics and physics. He was born on 14 March 1879 in Ulm, Germany (not Berlin). "
            "He won the Nobel Prize in Physics in 1921 for the discovery of the law of the "
            "photoelectric effect — NOT for his Theory of Relativity."
        ),
    },
    {
        "source": "myth_gdpr_dates",
        "category": "LEGAL",
        "fact": (
            "The EU GDPR (General Data Protection Regulation) entered into force on 25 May 2018, "
            "NOT 1 June 2019. Data breaches must be reported to the supervisory authority within "
            "72 hours, NOT 24 hours. Maximum fines are €20 million or 4% of global annual turnover, "
            "NOT 2%. Not all organisations must appoint a Data Protection Officer — only public "
            "authorities and certain private organisations that process personal data at scale."
        ),
    },
    {
        "source": "myth_aspirin_children",
        "category": "MEDICAL",
        "fact": (
            "Aspirin (acetylsalicylic acid) should NOT be given to children under 16 years of age "
            "due to the risk of Reye's syndrome, a rare but potentially fatal condition causing "
            "liver and brain damage. Ibuprofen is NOT safe to use throughout all trimesters of "
            "pregnancy. It is generally avoided in the third trimester due to risks to the foetus "
            "including premature closure of the ductus arteriosus."
        ),
    },
    {
        "source": "myth_india_population",
        "category": "GENERAL",
        "fact": (
            "The population of India is approximately 1.4 billion people (as of 2023), "
            "NOT 2.5 billion. India surpassed China in 2023 to become the world's most "
            "populous country. The global population reached 8 billion in November 2022."
        ),
    },
    {
        "source": "myth_ww2_end",
        "category": "GENERAL",
        "fact": (
            "World War II ended in 1945. Germany surrendered unconditionally on 8 May 1945 "
            "(Victory in Europe Day, V-E Day). Japan formally surrendered on 2 September 1945 "
            "aboard the USS Missouri, following the atomic bombings of Hiroshima (6 August 1945) "
            "and Nagasaki (9 August 1945). The war began on 1 September 1939."
        ),
    },
    {
        "source": "myth_speed_of_light",
        "category": "GENERAL",
        "fact": (
            "The speed of light in a vacuum is exactly 299,792,458 metres per second "
            "(approximately 300,000 km/s or 186,000 miles per second), NOT 250,000 km/s. "
            "Einstein's Special Theory of Relativity was published in 1905, not 1912. "
            "Nothing with mass can reach or exceed the speed of light."
        ),
    },
    {
        "source": "myth_diabetes_prevalence",
        "category": "MEDICAL",
        "fact": (
            "According to the International Diabetes Federation (IDF), approximately 537 million "
            "adults (20-79 years) were living with diabetes in 2021. This number is projected to "
            "rise to 643 million by 2030. The figure of 500 million is a close approximation "
            "but the IDF reported 537 million. A figure of '2 billion' would be wildly incorrect."
        ),
    },
    {
        "source": "myth_napoleon_height",
        "category": "GENERAL",
        "fact": (
            "Napoleon Bonaparte was NOT unusually short. He was approximately 5 feet 7 inches "
            "(170 cm) tall, which was average for a Frenchman of his era. The myth arose partly "
            "from a misunderstanding of French and English measurement units and British propaganda. "
            "He was born on 15 August 1769 in Ajaccio, Corsica."
        ),
    },
    {
        "source": "myth_vaccines_autism",
        "category": "MEDICAL",
        "fact": (
            "Vaccines do NOT cause autism. The 1998 study that claimed a link between the MMR "
            "vaccine and autism was retracted by The Lancet in 2010 due to serious ethical "
            "violations and data manipulation. The lead author Andrew Wakefield lost his medical "
            "licence. Decades of research involving millions of children have found no causal "
            "link between any vaccine and autism spectrum disorder."
        ),
    },
    {
        "source": "myth_columbus_flat_earth",
        "category": "GENERAL",
        "fact": (
            "Christopher Columbus did NOT set out to prove the Earth was round. Medieval Europeans "
            "already knew the Earth was spherical — this had been understood since ancient Greece. "
            "Columbus's dispute with Spanish scholars was about the SIZE of the Earth, not its shape. "
            "Columbus reached the Caribbean on 12 October 1492, NOT the North American mainland."
        ),
    },
    {
        "source": "myth_compound_interest",
        "category": "FINANCIAL",
        "fact": (
            "The quote 'Compound interest is the eighth wonder of the world' is often attributed "
            "to Albert Einstein, but there is no verified historical source for this attribution. "
            "Compound interest grows exponentially: principal × (1 + rate)^time. Annual compounding "
            "differs from monthly or daily compounding — the more frequent the compounding, the "
            "greater the effective annual rate. Simple interest does NOT compound."
        ),
    },
]
