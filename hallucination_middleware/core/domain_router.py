"""Domain Router — classifies text/claims into MEDICAL | LEGAL | FINANCIAL | GENERAL."""
from typing import Literal

DomainType = Literal["MEDICAL", "LEGAL", "FINANCIAL", "GENERAL"]

_MEDICAL = {
    "drug", "dose", "dosage", "treatment", "diagnosis", "symptom", "disease",
    "virus", "bacteria", "vaccine", "vaccination", "medication", "therapy",
    "patient", "hospital", "surgery", "clinical", "trial", "fda", "who",
    "cancer", "diabetes", "covid", "pandemic", "mortality", "prescription",
    "side effect", "allergy", "antibiotic", "insulin", "blood pressure",
    "cholesterol", "chemotherapy", "antiretroviral", "hiv", "aids",
    "placebo", "randomized", "contraindication", "pharmacokinetics",
    "pubmed", "cochrane", "medline", "lancet", "nejm",
}

_LEGAL = {
    "law", "act", "regulation", "court", "judge", "ruling", "statute",
    "legal", "illegal", "criminal", "civil", "lawsuit", "liability",
    "contract", "gdpr", "fine", "penalty", "compliance", "right",
    "amendment", "constitution", "federal", "jurisdiction", "verdict",
    "attorney", "plaintiff", "defendant", "precedent", "supreme court",
    "legislature", "ordinance", "treaty", "indictment", "habeas corpus",
    "due process", "fifth amendment", "sec", "ftc", "doj", "legislation",
}

_FINANCIAL = {
    "stock", "market", "price", "revenue", "profit", "loss", "gdp",
    "inflation", "interest rate", "bond", "equity", "dividend", "earnings",
    "fiscal", "federal reserve", "tax", "budget", "debt", "deficit",
    "ipo", "trading", "investment", "portfolio", "hedge fund", "etf",
    "cryptocurrency", "bitcoin", "dollar", "nasdaq", "s&p", "dow jones",
    "balance sheet", "eps", "pe ratio", "market cap", "acquisition",
    "quarterly", "annual report", "10-k", "10-q", "sec filing",
}


def route_domain(text: str) -> DomainType:
    """Classify text into domain. Returns GENERAL if no strong signal."""
    lower = text.lower()

    med = sum(1 for t in _MEDICAL if t in lower)
    leg = sum(1 for t in _LEGAL if t in lower)
    fin = sum(1 for t in _FINANCIAL if t in lower)

    if med == 0 and leg == 0 and fin == 0:
        return "GENERAL"

    best = max(("MEDICAL", med), ("LEGAL", leg), ("FINANCIAL", fin), key=lambda x: x[1])
    return best[0]
