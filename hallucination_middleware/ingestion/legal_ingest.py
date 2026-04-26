"""Legal Data Ingestion — Caselaw Access Project (CAP) API + static legal facts."""
import logging
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

CAP_API_BASE = "https://api.case.law/v1"


class LegalIngestor:
    """Ingests legal cases from the Caselaw Access Project and static legal facts."""

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key
        self._headers = {"Authorization": f"Token {api_key}"} if api_key else {}

    async def search_cases(self, query: str, max_results: int = 5) -> List[dict]:
        """Search CAP for relevant legal cases. Returns [] without API key."""
        if not self._api_key:
            logger.debug("[LegalIngestor] No CAP API key — skipping live search")
            return []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{CAP_API_BASE}/cases/",
                    params={"search": query, "page_size": max_results},
                    headers=self._headers,
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                results = []
                for case in data.get("results", []):
                    name = case.get("name_abbreviation", case.get("name", "Unknown"))
                    date = case.get("decision_date", "N/A")
                    court = case.get("court", {}).get("name", "")
                    cite = (case.get("citations") or [{}])[0].get("cite", "")
                    results.append({
                        "source": f"CAP: {name} ({date})",
                        "text": f"{name}. Court: {court}. Citation: {cite}.",
                        "type": "legal",
                    })
                return results
        except Exception as exc:
            logger.warning("[LegalIngestor] CAP API error: %s", exc)
            return []

    async def get_text_for_kb(self, query: str) -> Optional[str]:
        """Retrieve legal text for KB ingestion."""
        cases = await self.search_cases(query)
        if not cases:
            return None
        return "\n\n".join(f"{c['source']}\n{c['text']}" for c in cases)

    def get_static_facts(self) -> str:
        """High-quality static legal facts for KB seeding."""
        return """
GDPR (General Data Protection Regulation): The GDPR became effective on 25 May 2018.
It applies to all organizations processing personal data of EU residents. Maximum fines:
€20 million or 4% of annual global turnover, whichever is higher.

GDPR Data Breach Notification: Under Article 33 GDPR, data breaches must be reported
to the supervisory authority within 72 hours of discovery (not 24 hours). Article 34
requires notification to affected individuals without undue delay for high-risk breaches.

GDPR Data Protection Officer (DPO): A DPO is required only for: (1) public authorities,
(2) organizations systematically monitoring individuals at large scale, and (3) organizations
processing special categories of data at large scale. Not all companies need a DPO.

GDPR Right to Erasure (Article 17): Also known as the "right to be forgotten." Individuals
can request deletion of their personal data under specific circumstances, including when
the data is no longer necessary for its original purpose.

Fourth Amendment (US): Protects citizens from unreasonable searches and seizures.
Requires law enforcement to obtain a warrant based on probable cause before searching
property. The exclusionary rule prevents illegally obtained evidence from being used.

Miranda Rights (US): Established by Miranda v. Arizona (1966). Police must inform suspects
of their rights before custodial interrogation: right to remain silent, anything said can
be used against them, right to an attorney, right to appointed counsel if unable to afford one.

First Amendment (US): Prohibits Congress from making laws respecting establishment of
religion, prohibiting free exercise of religion, abridging freedom of speech or press,
or the right to petition the government. Does not protect all speech (e.g., incitement).

ADA (Americans with Disabilities Act, 1990): Prohibits discrimination against people with
disabilities in employment (Title I), government services (Title II), and public accommodations
(Title III). Employers with 15+ employees must provide reasonable accommodations.

HIPAA (Health Insurance Portability and Accountability Act, 1996): Protects the privacy
and security of protected health information (PHI). The Privacy Rule, Security Rule, and
Breach Notification Rule are its main components. Fines range from $100 to $50,000 per violation.

Contract Law — Consideration: For a contract to be enforceable, there must be offer,
acceptance, consideration (something of value exchanged), and mutual assent. Consideration
distinguishes a contract from a gift.
""".strip()
