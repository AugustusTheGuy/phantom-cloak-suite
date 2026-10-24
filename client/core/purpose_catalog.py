"""Purpose-based country recommendations for PhantomCloak."""

PURPOSES = {
    "streaming": {
        "label": "Streaming",
        "icon": "🎬",
        "description": "Full Netflix, Hulu, and Prime Video libraries",
        "countries": [
            {"code": "US", "name": "United States", "score": 100, "note": "Largest combined catalog"},
            {"code": "GB", "name": "United Kingdom", "score": 96, "note": "Strong BBC + US overlap"},
            {"code": "CA", "name": "Canada", "score": 94, "note": "Full Hulu region + strong Netflix"},
            {"code": "AU", "name": "Australia", "score": 91, "note": "Prime + Netflix AU originals"},
            {"code": "DE", "name": "Germany", "score": 89, "note": "EU licensing hub"},
            {"code": "FR", "name": "France", "score": 88, "note": "Canal+ overlap + Prime FR"},
            {"code": "JP", "name": "Japan", "score": 87, "note": "Anime + exclusive Netflix JP"},
            {"code": "BR", "name": "Brazil", "score": 85, "note": "Large LATAM catalog"},
            {"code": "IN", "name": "India", "score": 83, "note": "Massive Prime + Netflix IN"},
            {"code": "NL", "name": "Netherlands", "score": 82, "note": "EU English-friendly library"},
        ],
    },
    "crypto": {
        "label": "Crypto",
        "icon": "₿",
        "description": "Top legally lenient cryptocurrency jurisdictions",
        "countries": [
            {"code": "AE", "name": "UAE (Dubai)", "score": 100, "note": "VARA/FSRA, 0% tax zones"},
            {"code": "SG", "name": "Singapore", "score": 98, "note": "MAS clarity, no CGT individuals"},
            {"code": "CH", "name": "Switzerland", "score": 96, "note": "Crypto Valley, FINMA"},
            {"code": "HK", "name": "Hong Kong", "score": 94, "note": "Web3 + stablecoin push"},
            {"code": "KY", "name": "Cayman Islands", "score": 92, "note": "Offshore fund domicile"},
            {"code": "DE", "name": "Germany", "score": 90, "note": "1yr+ hold tax-free individuals"},
            {"code": "EE", "name": "Estonia", "score": 88, "note": "E-residency + licenses"},
            {"code": "BS", "name": "Bahamas", "score": 86, "note": "DARE Act framework"},
            {"code": "SC", "name": "Seychelles", "score": 84, "note": "Offshore licensing"},
            {"code": "MU", "name": "Mauritius", "score": 82, "note": "Low-tax treaties"},
        ],
    },
    "browsing": {
        "label": "Browsing",
        "icon": "🌐",
        "description": "Least content-restrictive jurisdictions",
        "countries": [
            {"code": "IS", "name": "Iceland", "score": 100, "note": "Strong press + access freedom"},
            {"code": "CH", "name": "Switzerland", "score": 98, "note": "Privacy-first legal culture"},
            {"code": "NL", "name": "Netherlands", "score": 96, "note": "Open internet norms"},
            {"code": "CA", "name": "Canada", "score": 94, "note": "Balanced access laws"},
            {"code": "DE", "name": "Germany", "score": 92, "note": "EU baseline + strong privacy"},
            {"code": "SE", "name": "Sweden", "score": 90, "note": "Minimal filtering"},
            {"code": "JP", "name": "Japan", "score": 88, "note": "Low censorship index"},
            {"code": "US", "name": "United States", "score": 86, "note": "Broad access (state variance)"},
            {"code": "PT", "name": "Portugal", "score": 84, "note": "EU open-access culture"},
            {"code": "RO", "name": "Romania", "score": 82, "note": "Low restriction enforcement"},
        ],
    },
    "digital_nomad": {
        "label": "Digital Nomad",
        "icon": "✈️",
        "description": "Top 20 countries for remote work + connectivity",
        "countries": [
            {"code": "PT", "name": "Portugal", "score": 100, "note": "D7 visa, coworking, EU access"},
            {"code": "ES", "name": "Spain", "score": 98, "note": "Digital nomad visa, timezone EU"},
            {"code": "TH", "name": "Thailand", "score": 96, "note": "LTR visa, low cost, fast net"},
            {"code": "MX", "name": "Mexico", "score": 94, "note": "US timezone overlap"},
            {"code": "CO", "name": "Colombia", "score": 92, "note": "Medellín hub, affordable"},
            {"code": "EE", "name": "Estonia", "score": 90, "note": "E-residency + digital infra"},
            {"code": "GE", "name": "Georgia", "score": 88, "note": "Remotely from Georgia program"},
            {"code": "CR", "name": "Costa Rica", "score": 86, "note": "Rentista visa, stable"},
            {"code": "MY", "name": "Malaysia", "score": 84, "note": "DE Rantau, strong infra"},
            {"code": "ID", "name": "Indonesia (Bali)", "score": 82, "note": "B211A, coworking density"},
            {"code": "VN", "name": "Vietnam", "score": 80, "note": "Low cost, fast fiber cities"},
            {"code": "AE", "name": "UAE", "score": 78, "note": "0% income tax, global hub"},
            {"code": "SG", "name": "Singapore", "score": 76, "note": "Connectivity + banking"},
            {"code": "DE", "name": "Germany", "score": 74, "note": "Freelance visa paths"},
            {"code": "CZ", "name": "Czech Republic", "score": 72, "note": "Zivno, central EU"},
            {"code": "PL", "name": "Poland", "score": 70, "note": "Affordable EU base"},
            {"code": "HR", "name": "Croatia", "score": 68, "note": "Digital nomad permit"},
            {"code": "GR", "name": "Greece", "score": 66, "note": "EU lifestyle + islands"},
            {"code": "JP", "name": "Japan", "score": 64, "note": "Reliable infra, safety"},
            {"code": "CA", "name": "Canada", "score": 62, "note": "Stable, US-adjacent TZ"},
        ],
    },
    "other": {
        "label": "Other",
        "icon": "⚙️",
        "description": "General-purpose protection profiles",
        "countries": [
            {"code": "CA", "name": "Vancouver, Canada", "score": 100, "note": "Default base location"},
            {"code": "CH", "name": "Zurich, Switzerland", "score": 95, "note": "Privacy + banking"},
            {"code": "SG", "name": "Singapore", "score": 93, "note": "Asia-Pacific hub"},
            {"code": "DE", "name": "Frankfurt, Germany", "score": 91, "note": "EU central routing"},
            {"code": "AE", "name": "Dubai, UAE", "score": 89, "note": "Middle East hub"},
            {"code": "HK", "name": "Hong Kong", "score": 87, "note": "Asia finance gateway"},
            {"code": "GB", "name": "London, UK", "score": 85, "note": "English + EU adjacency"},
            {"code": "NL", "name": "Amsterdam", "score": 83, "note": "IX density"},
            {"code": "US", "name": "United States", "score": 81, "note": "Broad service access"},
            {"code": "JP", "name": "Tokyo, Japan", "score": 79, "note": "Low latency Asia"},
        ],
    },
}


def get_purposes():
    return {k: {"label": v["label"], "icon": v["icon"], "description": v["description"]} for k, v in PURPOSES.items()}


def get_countries_for_purpose(purpose: str):
    return PURPOSES.get(purpose, PURPOSES["other"])["countries"]