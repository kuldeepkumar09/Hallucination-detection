"""Medical Data Ingestion — PubMed E-utilities (free, no API key) + static facts."""
import logging
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


class MedicalIngestor:
    """Ingests medical literature from PubMed and static medical facts."""

    async def search_pubmed(self, query: str, max_results: int = 5) -> List[str]:
        """Search PubMed and return PMIDs."""
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    PUBMED_SEARCH,
                    params={
                        "db": "pubmed",
                        "term": query,
                        "retmax": max_results,
                        "retmode": "json",
                        "sort": "relevance",
                    },
                )
                if resp.status_code != 200:
                    return []
                return resp.json().get("esearchresult", {}).get("idlist", [])
        except Exception as exc:
            logger.warning("[MedicalIngestor] PubMed search failed: %s", exc)
            return []

    async def fetch_summaries(self, pmids: List[str]) -> List[dict]:
        """Fetch article summaries for given PMIDs."""
        if not pmids:
            return []
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    PUBMED_SUMMARY,
                    params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
                )
                if resp.status_code != 200:
                    return []
                result = resp.json().get("result", {})
                docs = []
                for pmid in pmids:
                    article = result.get(pmid)
                    if not article or pmid == "uids":
                        continue
                    title = article.get("title", "")
                    source = article.get("source", "PubMed")
                    pub_date = article.get("pubdate", "")
                    authors = article.get("authors", [])
                    first_author = authors[0].get("name", "") if authors else ""
                    docs.append({
                        "pmid": pmid,
                        "source": f"PubMed PMID:{pmid} — {source} ({pub_date})",
                        "text": f"{title}. {first_author}. {source}, {pub_date}.",
                    })
                return docs
        except Exception as exc:
            logger.warning("[MedicalIngestor] PubMed fetch failed: %s", exc)
            return []

    async def get_text_for_kb(self, query: str, max_results: int = 5) -> Optional[str]:
        """Get medical literature text for KB ingestion."""
        pmids = await self.search_pubmed(query, max_results)
        if not pmids:
            return None
        docs = await self.fetch_summaries(pmids)
        if not docs:
            return None
        return "\n\n".join(f"{d['source']}\n{d['text']}" for d in docs)

    def get_static_facts(self) -> str:
        """High-quality static medical facts for KB seeding."""
        return """
Penicillin Discovery: Alexander Fleming discovered penicillin in 1928 when he observed
that the mold Penicillium notatum inhibited bacterial growth. It was developed into a
usable antibiotic by Howard Florey and Ernst Chain in 1940.

COVID-19 mRNA Vaccines: The Pfizer-BioNTech (BNT162b2) COVID-19 vaccine received FDA
Emergency Use Authorization on December 11, 2020. The Moderna (mRNA-1273) vaccine was
authorized on December 18, 2020. Both use mRNA technology to produce the SARS-CoV-2 spike protein.

DNA Structure: James Watson and Francis Crick described the double helix structure of DNA
in 1953, building on X-ray crystallography data from Rosalind Franklin. DNA contains four
bases: adenine (A), thymine (T), guanine (G), and cytosine (C). A pairs with T; G pairs with C.

Type 1 Diabetes: An autoimmune disease where the immune system destroys insulin-producing
beta cells in the pancreas. Requires lifelong insulin therapy. Not caused by diet or lifestyle.
Distinct from Type 2 diabetes (insulin resistance).

Type 2 Diabetes: The most common form of diabetes (~90-95% of cases). Global prevalence
approximately 422 million people (WHO 2016 estimate, not 500 million). Managed through
lifestyle changes, oral medications, and sometimes insulin.

Aspirin and Children: Aspirin is contraindicated in children and teenagers with viral
infections due to the risk of Reye's syndrome — a rare but serious condition causing
liver and brain damage. Acetaminophen or ibuprofen are preferred.

Ibuprofen in Pregnancy: Ibuprofen (an NSAID) is generally NOT recommended during
pregnancy, especially after 20 weeks gestation. It can cause premature closure of the
ductus arteriosus and fetal renal complications. Acetaminophen is the preferred analgesic.

HIV/AIDS: HIV (Human Immunodeficiency Virus) causes AIDS. There is currently NO cure
for HIV, but antiretroviral therapy (ART) can suppress viral load to undetectable levels.
People on effective ART can live near-normal lifespans and cannot transmit the virus sexually.

Blood Pressure Classification (ACC/AHA 2017):
  Normal: <120/<80 mmHg
  Elevated: 120-129/<80 mmHg
  High Stage 1: 130-139 or 80-89 mmHg
  High Stage 2: ≥140 or ≥90 mmHg
  Crisis: >180/>120 mmHg (requires immediate medical attention)

Cancer Screening Guidelines (US Preventive Services Task Force):
  Breast cancer: Mammography every 2 years for women 50-74 (biennial screening)
  Colorectal: Colonoscopy every 10 years starting at age 45 (updated from 50 in 2021)
  Cervical: Pap smear every 3 years (ages 21-65) or Pap + HPV test every 5 years (ages 30-65)

Antibiotic Resistance: The WHO lists antimicrobial resistance as one of the greatest
threats to global health. Antibiotics do not treat viral infections (e.g., common cold, flu).
Misuse and overuse of antibiotics accelerates resistance development.

Insulin Types:
  Rapid-acting (e.g., lispro): onset 15 min, peak 1-2 hr, duration 3-5 hr
  Regular (short-acting): onset 30-60 min, peak 2-4 hr, duration 5-8 hr
  NPH (intermediate): onset 2-4 hr, peak 4-12 hr, duration 12-18 hr
  Glargine (long-acting): onset 2-4 hr, no pronounced peak, duration ~24 hr
""".strip()
