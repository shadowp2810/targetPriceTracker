"""
Stock universe definitions.
US: S&P 500 Information Technology sector + Nasdaq-100 (~138 unique tickers).
"""

# ---------------------------------------------------------------------------
# US — S&P 500 Information Technology
# ---------------------------------------------------------------------------
SP500_IT = [
    "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "QCOM", "TXN", "AMAT",
    "ACN", "IBM", "INTU", "MU", "LRCX", "ADI", "KLAC", "SNPS", "CDNS", "MRVL",
    "MSI", "FTNT", "ADSK", "TEL", "APH", "MPWR", "GEN", "CTSH", "IT",
    "KEYS", "AKAM", "ZBRA", "TDY", "ENPH", "TER", "SWKS", "QRVO", "FFIV", "EPAM",
    "NTAP", "HPE", "GLW", "STX", "WDC", "CSCO", "ANET", "PANW", "FSLR",
    "NOW", "TTWO", "EA", "PAYC", "VRSN", "LDOS", "SAIC", "DXC", "HPQ",
    "CDW", "GDDY", "PTC", "JKHY", "TRMB", "PCTY", "NSIT",
]

# ---------------------------------------------------------------------------
# US — Nasdaq-100
# ---------------------------------------------------------------------------
NASDAQ_100 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST",
    "NFLX", "AMD", "PEP", "ADBE", "CSCO", "QCOM", "LIN", "TMUS", "INTU", "AMGN",
    "TXN", "AMAT", "CMCSA", "HON", "ISRG", "BKNG", "VRTX", "REGN", "ADI", "PANW",
    "SBUX", "GILD", "MU", "LRCX", "MDLZ", "INTC", "KLAC", "SNPS", "CDNS", "ASML",
    "MELI", "ADP", "MAR", "CTAS", "ABNB", "MNST", "FTNT", "MRVL", "PYPL", "ORLY",
    "PCAR", "CPRT", "ROST", "PAYX", "NXPI", "DXCM", "ODFL", "KDP", "WDAY", "FAST",
    "VRSK", "CRWD", "TEAM", "ZS", "ADSK", "MCHP", "CSX", "EA", "CEG", "BIIB",
    "WBD", "IDXX", "FANG", "EXC", "XEL", "GEHC", "KHC", "TTWO", "ON", "GFS",
    "DLTR", "ILMN", "SIRI", "ZM", "LCID", "DDOG", "OKTA", "RIVN", "RGEN", "NTES",
    "ALGN", "CDW", "HOLX", "MTCH", "SWKS", "INCY", "PDD", "NET",
]


def get_universe() -> list[str]:
    """Return deduplicated US tickers (S&P 500 IT + Nasdaq-100), sorted."""
    return sorted(set(SP500_IT + NASDAQ_100))


if __name__ == "__main__":
    tickers = get_universe()
    print(f"US tickers: {len(tickers)}")
    print(tickers)
