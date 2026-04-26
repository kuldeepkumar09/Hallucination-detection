"""Financial Data Ingestion — SEC EDGAR via edgartools + free financial APIs."""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class FinancialIngestor:
    """Ingests SEC EDGAR financial filings and free financial facts."""

    def __init__(self) -> None:
        self._edgar_ok = False
        try:
            import edgar
            edgar.set_identity("HalluCheck research@hallucheck.ai")
            self._edgar_ok = True
            logger.info("[FinancialIngestor] edgartools ready")
        except ImportError:
            logger.info("[FinancialIngestor] edgartools not installed — skipping SEC EDGAR")

    def get_company_text(self, ticker: str) -> Optional[str]:
        """Fetch 10-K filing text snippet for a ticker. Returns None on failure."""
        if not self._edgar_ok:
            return None
        try:
            import edgar
            company = edgar.Company(ticker)
            filings = company.get_filings(form="10-K").latest(1)
            if not filings:
                return None
            f = filings[0]
            lines = [
                f"SEC 10-K Filing: {ticker}",
                f"Company: {f.company_name if hasattr(f, 'company_name') else ticker}",
                f"Filed: {f.filing_date}",
                f"Description: {f.description or 'Annual Report'}",
            ]
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("[FinancialIngestor] EDGAR error for %s: %s", ticker, exc)
            return None

    def get_static_facts(self) -> str:
        """Return hard-coded high-quality financial facts for KB seeding."""
        return """
Federal Reserve Dual Mandate: The Federal Reserve Act mandates the Fed to promote
maximum employment and stable prices (2% inflation target). The Fed uses the federal
funds rate as its primary monetary policy tool.

FDIC Insurance: The Federal Deposit Insurance Corporation (FDIC) insures deposits up
to $250,000 per depositor, per insured bank, per ownership category. This limit was
permanently set at $250,000 by the Dodd-Frank Act in 2010.

Capital Gains Tax (US): Long-term capital gains (assets held > 1 year) are taxed at
0%, 15%, or 20% depending on income. Short-term gains are taxed as ordinary income.

401(k) Contribution Limits (2024): The annual employee contribution limit is $23,000
($30,500 for those age 50+). Employer + employee total limit is $69,000.

Dodd-Frank Act: The Dodd-Frank Wall Street Reform and Consumer Protection Act (2010)
established the Consumer Financial Protection Bureau (CFPB) and the Financial Stability
Oversight Council (FSOC) in response to the 2008 financial crisis.

Basel III Capital Requirements: Basel III requires banks to maintain a minimum
Common Equity Tier 1 (CET1) ratio of 4.5%, Tier 1 capital ratio of 6%, and total
capital ratio of 8%. Plus a 2.5% capital conservation buffer.

FICO Credit Scores: FICO scores range from 300 to 850.
  Poor: 300-579 | Fair: 580-669 | Good: 670-739 | Very Good: 740-799 | Exceptional: 800-850
Payment history (35%) is the largest factor, followed by amounts owed (30%).

S&P 500 Index: The S&P 500 tracks 500 large US publicly traded companies. It is
widely considered the best gauge of large-cap US equity performance. Created in 1957.

SEC Registration: Companies must register securities with the SEC under the Securities
Act of 1933 before offering them to the public. The Securities Exchange Act of 1934
established the SEC and regulates secondary market trading.
""".strip()
