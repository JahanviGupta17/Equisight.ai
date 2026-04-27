"""
app/api/endpoints/upload.py
POST /api/v1/portfolio/upload

Accepts any CSV, PDF, or TXT holdings export.
Fast-path: deterministic CSV parser handles all major Indian brokerage formats
  (Zerodha, Groww, HDFC Securities, ICICI Direct, Upstox, Angel One, etc.)
Slow-path: Gemini LLM extraction for PDFs and unrecognised formats.
"""
import io
import logging
import re
import string
import uuid

import pypdf
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.holding import Holding
from app.schemas.holding import BulkInsertResponse, HoldingCSVRow
from app.services.llm import extract_holdings_from_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# ── Column name normaliser ────────────────────────────────────────────────────

def _norm(s: str) -> str:
    """Lowercase, strip punctuation and whitespace — makes header matching robust."""
    return str(s).strip().lower().translate(str.maketrans("", "", string.punctuation + " "))


# ── Column alias sets (order = priority; first match wins) ───────────────────

SYMBOL_KEYS = {
    # Generic
    "symbol", "ticker", "tickersymbol",
    # ISIN / instrument
    "isin", "instrument", "instrumentname", "instrumenttype",
    # NSE/BSE
    "tradingsymbol", "scripcode", "scrip", "scripname",
    # Broker-specific
    "stockname", "stock", "company", "companyname", "securityname",
    "asset", "assetsymbol", "name",
    # Zerodha
    "tradingsymbolinstrument",
    # Groww
    "schemename", "fundname",
    # HDFC Sec
    "sharesymbol",
}

QTY_KEYS = {
    "quantity", "qty", "shares", "units", "volume",
    "holdingqty", "availableqty", "netqty", "balance",
    "noofsharesheld", "noshares", "noofshares",
    # Zerodha
    "totalquantity", "t1quantity",
    # Groww
    "currentunits", "units",
}

PRICE_KEYS = {
    "averagebuyprice", "avgbuyprice", "avgprice", "averageprice",
    "buyprice", "purchaseprice", "costprice", "avgcostprice",
    "price", "avgcost", "cost",
    # Broker-specific
    "avgbuycost", "purchaserate", "buyavg",
    # Groww
    "averagecost", "averagecostprice", "navpurchased",
    # Angel One / HDFC
    "purchasepriceinr", "buypriceinr",
    # Value / fallback (used when price col absent)
    "currentnavvalue", "nav",
}

TYPE_KEYS = {
    "assettype", "type", "instrumenttype", "category",
    "securitytype", "holdingtype",
}


# ── ISIN → NSE ticker ────────────────────────────────────────────────────────

ISIN_TO_TICKER: dict[str, str] = {
    "INE467B01029": "RELIANCE.NS",
    "INE009A01021": "INFY.NS",
    "INE040A01034": "HDFCBANK.NS",
    "INE062A01020": "SBIN.NS",
    "INE397D01024": "HDFCLIFE.NS",
    "INE238A01034": "AXISBANK.NS",
    "INE090A01021": "ICICIBANK.NS",
    "INE356A01018": "WIPRO.NS",
    "INE155A01022": "TCS.NS",
    "INE040A01026": "HDFCBANK.NS",
    "INE001A01036": "ADANIENT.NS",
    "INE117A01022": "ABB.NS",
    "INE214T01019": "ADANIPORTS.NS",
    "INE669E01016": "ADANIGREEN.NS",
    "INE423A01024": "AMBUJACEM.NS",
    "INE079A01024": "APOLLOHOSP.NS",
    "INE406A01037": "ASHOKLEY.NS",
    "INE208A01029": "AXISBANK.NS",
    "INE034A01011": "BAJAJ-AUTO.NS",
    "INE296A01024": "BAJAJFINSV.NS",
    "INE021F01012": "BAJFINANCE.NS",
    "INE176A01028": "BHARTIARTL.NS",
    "INE028A01039": "BPCL.NS",
    "INE010B01027": "CANBK.NS",
    "INE059A01026": "CIPLA.NS",
    "INE522F01014": "COFORGE.NS",
    "INE694A01020": "COALINDIA.NS",
    "INE121J01017": "CHOLAFIN.NS",
    "INE114A01011": "DIVISLAB.NS",
    "INE171A01029": "DIXON.NS",
    "INE010A01006": "DRREDDY.NS",
    "INE081A01020": "EICHERMOT.NS",
    "INE242A01010": "EXIDEIND.NS",
    "INE075A01022": "GRASIM.NS",
    "INE047A01021": "HEROMOTOCO.NS",
    "INE030A01027": "HINDALCO.NS",
    "INE031A01017": "HINDUNILVR.NS",
    "INE095A01012": "ICICIBANK.NS",
    "INE154A01025": "ITC.NS",
    "INE002A01018": "INFY.NS",
    "INE669C01036": "INDUSINDBK.NS",
    "INE237A01028": "JSWSTEEL.NS",
    "INE500L01026": "KOTAKBANK.NS",
    "INE018A01030": "LT.NS",
    "INE101A01026": "MARUTI.NS",
    "INE414G01012": "MUTHOOTFIN.NS",
    "INE733E01010": "NTPC.NS",
    "INE213A01029": "NMDC.NS",
    "INE274J01014": "NYKAA.NS",
    "INE742F01042": "ONGC.NS",
    "INE523B01011": "PAYTM.NS",
    "INE318A01026": "POWERGRID.NS",
    "INE160A01022": "PFC.NS",
    "INE020B01018": "PNB.NS",
    "INE585B01010": "RECLTD.NS",
    "INE364U01010": "POLICYBZR.NS",
    "INE647O01011": "IRCTC.NS",
    "INE192R01011": "ZOMATO.NS",
    "INE044A01036": "SUNPHARMA.NS",
    "INE467B01029": "RELIANCE.NS",
    "INE585B01010": "RECLTD.NS",
    "INE070A01015": "SAIL.NS",
    "INE089A01023": "TATAMOTORS.NS",
    "INE081A01020": "EICHERMOT.NS",
    "INE081A01012": "TATASTEEL.NS",
    "INE467B01029": "RELIANCE.NS",
    "INE467B01029": "RELIANCE.NS",
    "INE114A01011": "DIVISLAB.NS",
    "INE303R01014": "TRENT.NS",
    "INE192A01025": "ULTRACEMCO.NS",
    "INE397D01024": "HDFCLIFE.NS",
    "INE860A01027": "HCL.NS",
    "INE860A01027": "HCLTECH.NS",
    "INE397D01024": "HDFCLIFE.NS",
    "INE296A01024": "BAJAJFINSV.NS",
    "INE040A01034": "HDFCBANK.NS",
    "INE765G01017": "BEL.NS",
}

# ── Company name → NSE ticker (for brokers that export full names, e.g. Groww) ─
# Keys are uppercased, spaces/punctuation-normalised versions of company names.
# Used when no clean ticker/ISIN column exists.

_COMPANY_NAME_TO_TICKER: dict[str, str] = {
    "BHARATELECTRONICSLIMITED": "BEL.NS",
    "BHARATELECTRONICSLTD": "BEL.NS",
    "BHARATELECTRONICS": "BEL.NS",
    "RELIANCEINDUSTRIESLIMITED": "RELIANCE.NS",
    "RELIANCEINDUSTRIES": "RELIANCE.NS",
    "TATACONSULTANCYSERVICES": "TCS.NS",
    "TATACONSULTANCY": "TCS.NS",
    "HDFCBANKLIMITED": "HDFCBANK.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "INFOSYSLIMITED": "INFY.NS",
    "INFOSYS": "INFY.NS",
    "ICICIBANKLIMITED": "ICICIBANK.NS",
    "ICICIBANKLTD": "ICICIBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "NTPCLIMITED": "NTPC.NS",
    "NTPC": "NTPC.NS",
    "STATEBANKOFINDIA": "SBIN.NS",
    "AXISBANKLIMITED": "AXISBANK.NS",
    "AXISBANKLTD": "AXISBANK.NS",
    "AXISBANK": "AXISBANK.NS",
    "KOTAKMAHINDRABAN": "KOTAKBANK.NS",
    "KOTAKMAHINDRABANK": "KOTAKBANK.NS",
    "HINDUSTANUNILEVER": "HINDUNILVR.NS",
    "HINDUSTANUTANLIMITED": "HINDUNILVR.NS",
    "LARSENANDTOUBRO": "LT.NS",
    "LARSENNTOUBRO": "LT.NS",
    "MARUTISUZUKI": "MARUTI.NS",
    "MARUTISUZUKILIMITED": "MARUTI.NS",
    "SUNPHARMACEUTICAL": "SUNPHARMA.NS",
    "SUNPHARMA": "SUNPHARMA.NS",
    "WIPROLIMITED": "WIPRO.NS",
    "WIPRO": "WIPRO.NS",
    "HCLTECH": "HCLTECH.NS",
    "HCLTECHNOLOGIES": "HCLTECH.NS",
    "BAJAJFINANCE": "BAJFINANCE.NS",
    "BAJAJFINANCELIMITED": "BAJFINANCE.NS",
    "BAJAJFINSERVLIMITED": "BAJAJFINSV.NS",
    "BAJAJFINSERV": "BAJAJFINSV.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "TATAMOTORSLIMITED": "TATAMOTORS.NS",
    "BHARTIAIRTEL": "BHARTIARTL.NS",
    "BHARTIAIRTEL": "BHARTIARTL.NS",
    "ITCLIMITED": "ITC.NS",
    "ADANIENTERPRISES": "ADANIENT.NS",
    "ADANIPORTS": "ADANIPORTS.NS",
    "POWERGRIDCORPORATION": "POWERGRID.NS",
    "POWERGRID": "POWERGRID.NS",
    "COALINDIA": "COALINDIA.NS",
    "COALINDIALIMITED": "COALINDIA.NS",
    "TITANCOMPANY": "TITAN.NS",
    "TITAN": "TITAN.NS",
    "ULTRATECHCEMENT": "ULTRACEMCO.NS",
    "GRESIMLIMITED": "GRASIM.NS",
    "ASIAPAINTSLTD": "ASIANPAINT.NS",
    "ASIANPAINTS": "ASIANPAINT.NS",
    "NESTLEINDIALIMITED": "NESTLEIND.NS",
    "NESTLEINDIA": "NESTLEIND.NS",
    "DRREDDY": "DRREDDY.NS",
    "DRREDDYSLABORATORIES": "DRREDDY.NS",
    "CIPLA": "CIPLA.NS",
    "CIPLTD": "CIPLA.NS",
    "HINDALCOINDUSTRIES": "HINDALCO.NS",
    "HINDALCO": "HINDALCO.NS",
    "JSWS": "JSWSTEEL.NS",
    "JSWSTEELLIMITED": "JSWSTEEL.NS",
    "JSWSTEEL": "JSWSTEEL.NS",
    "TATASTEEL": "TATASTEEL.NS",
    "TATASTEELLIMITED": "TATASTEEL.NS",
    "ONLIMITED": "ONGC.NS",
    "OILNATURALGASCORPORATION": "ONGC.NS",
    "ONGC": "ONGC.NS",
    "BPCL": "BPCL.NS",
    "BHARATPETROLEUMCORPORATION": "BPCL.NS",
    "TECHNOLOGIESMAHINDRA": "TECHM.NS",
    "TECHMAHINDRA": "TECHM.NS",
    "HDFCLIFEINSURANCE": "HDFCLIFE.NS",
    "HDFCLIFE": "HDFCLIFE.NS",
    "HDFCLIFEINSURANCECOMPANY": "HDFCLIFE.NS",
    "SBILIFEINSURANC": "SBILIFE.NS",
    "SBILIFE": "SBILIFE.NS",
    "INDUSINDBANKLTD": "INDUSINDBK.NS",
    "INDUSINDBANK": "INDUSINDBK.NS",
    "DIVISLABORATORIES": "DIVISLAB.NS",
    "DIVISLAB": "DIVISLAB.NS",
    "EICHERMOTORS": "EICHERMOT.NS",
    "EICHERMOTORS": "EICHERMOT.NS",
    "HEROMOTOCORPLIMITED": "HEROMOTOCO.NS",
    "HEROMOTOCORP": "HEROMOTOCO.NS",
    "APOLLOHOSPITALS": "APOLLOHOSP.NS",
    "APOLLOHOSPITALSENTERPR": "APOLLOHOSP.NS",
    "MUTHOOTFINANCE": "MUTHOOTFIN.NS",
    "ZOMATOLIMITED": "ZOMATO.NS",
    "ZOMATO": "ZOMATO.NS",
    "IRCTC": "IRCTC.NS",
    "INDIANRAILWAYCATERING": "IRCTC.NS",
    "PAYTM": "PAYTM.NS",
    "ONEMOBIKWIKSYSTEMS": "PAYTM.NS",
    "NYKAA": "NYKAA.NS",
    "FSNNECOMMER": "NYKAA.NS",
    "POLICYBAZAAR": "POLICYBZR.NS",
    "PBFINTECH": "POLICYBZR.NS",
    "COFORGELIMITED": "COFORGE.NS",
    "COFORGE": "COFORGE.NS",
    "NIPPONAMC": "NAM-INDIA.NS",
    "NIPPONAMCNETFSILVER": "SILVERIETF.NS",
    "NIPPONINDINETFSILVER": "SILVERIETF.NS",
    "NIPPONAMC-NETFSILVER": "SILVERIETF.NS",
    "NIIPPONNIFTY": "NIFTYBEES.NS",
    "NIPPONINDIANIFTY50": "NIFTYBEES.NS",
    "NIPPONINDIANIFTYBEES": "NIFTYBEES.NS",
    "TRENTLIMITED": "TRENT.NS",
    "TRENT": "TRENT.NS",
    "PERSISTENTSYSTEMS": "PERSISTENT.NS",
    "LTIMINDTREE": "LTIM.NS",
    "MINDTREETECHNO": "LTIM.NS",
    "KPITTECH": "KPIT.NS",
    "KPITTECHNOLOGIES": "KPIT.NS",
    "TATAELXSILIMITED": "TATAELXSI.NS",
    "TATAELXSI": "TATAELXSI.NS",
    "POLYCABINDIA": "POLYCAB.NS",
    "POLYCAB": "POLYCAB.NS",
    "DMART": "DMART.NS",
    "AVENUESSUPERMARTS": "DMART.NS",
    "SHREECEMENT": "SHREECEM.NS",
    "SHREECEMLIMITED": "SHREECEM.NS",
    "BRITANNIAINDUSTRIES": "BRITANNIA.NS",
    "BRITANNIA": "BRITANNIA.NS",
    "PIDILITEINDUSTRIES": "PIDILITIND.NS",
    "PIDILITE": "PIDILITIND.NS",
    "DABUR": "DABUR.NS",
    "DABURINDIA": "DABUR.NS",
    "MARICO": "MARICO.NS",
    "MARICOLIMITED": "MARICO.NS",
    "GODREJCONSUMER": "GODREJCP.NS",
    "GODREJCONSUMERPRODUCTS": "GODREJCP.NS",
    "COLGATEPALMOLIVE": "COLPAL.NS",
    "COLGATE": "COLPAL.NS",
    "PAGEDINDUSTRIES": "PAGEIND.NS",
    "HAVELLSINDIA": "HAVELLS.NS",
    "HAVELLS": "HAVELLS.NS",
    "SIEMENS": "SIEMENS.NS",
    "SIEMENSINDIA": "SIEMENS.NS",
    "ABBINDIA": "ABB.NS",
    "ABB": "ABB.NS",
    "BOSCHLIMITED": "BOSCHLTD.NS",
    "BOSCH": "BOSCHLTD.NS",
    "CUMMINS": "CUMMINSIND.NS",
    "CUMMINSINDIA": "CUMMINSIND.NS",
    "FEDERALBANK": "FEDERALBNK.NS",
    "BANKOFINDIA": "BANKBARODA.NS",
    "BANKOFBARODA": "BANKBARODA.NS",
    "PUNJABNATIONALBANK": "PNB.NS",
    "CANARABANK": "CANBK.NS",
    "UNIONBANKOFINDIA": "UNIONBANK.NS",
    "IDFC": "IDFCFIRSTB.NS",
    "IDFCFIRSTBANK": "IDFCFIRSTB.NS",
    "ICICILOMBARD": "ICICIGI.NS",
    "ICICILOMBARDINSURANC": "ICICIGI.NS",
    "STARHEALTHINSURANCE": "STARHEALTH.NS",
    "ASTRALLTD": "ASTRAL.NS",
    "ASTRALPIPES": "ASTRAL.NS",
    "SUPREMEIND": "SUPREMEIND.NS",
    "SUPREMEINDUSTRIES": "SUPREMEIND.NS",
    "BALKRISHNAIND": "BALKRISIND.NS",
    "BALKRISHNAINDUSTRIES": "BALKRISIND.NS",
    "APOLLOTYRES": "APOLLOTYRE.NS",
    "APOLLOTYRE": "APOLLOTYRE.NS",
    "MPHASIS": "MPHASIS.NS",
    "CYIENT": "CYIENT.NS",
    "LTTS": "LTTS.NS",
    "LTIMINDTREE": "LTIM.NS",
    "AMBUJACEMENT": "AMBUJACEM.NS",
    "AMBUJA": "AMBUJACEM.NS",
    "ACCLIMITED": "ACC.NS",
    "ACC": "ACC.NS",
    "ALKEM": "ALKEM.NS",
    "ALKEMLABORATORIES": "ALKEM.NS",
    "TORNTPHARMACEUTICALS": "TORNTPHARM.NS",
    "TORNTPHARMA": "TORNTPHARM.NS",
    "AUROBINDAPHARMA": "AUROPHARMA.NS",
    "AUROPHARMA": "AUROPHARMA.NS",
    "NATCOPHARM": "NATCOPHARM.NS",
    "NHPCLIMITED": "NHPC.NS",
    "NHPC": "NHPC.NS",
    "RECLTD": "RECLTD.NS",
    "RURELECTRIFICATIONCORP": "RECLTD.NS",
    "PFCLIMITED": "PFC.NS",
    "POWERFINCORPORATION": "PFC.NS",
    "MOTHERSONSUMIWR": "MOTHERSON.NS",
    "MOTHERSON": "MOTHERSON.NS",
    "BERGERPAINTS": "BERGEPAINT.NS",
    "BERGERPAINTSIND": "BERGEPAINT.NS",
    "INFOBEANS": "INFOBEAN.NS",
    "INDIANHOTEL": "INDHOTEL.NS",
    "TATAPOWER": "TATAPOWER.NS",
    "TATAPOWERLIMITED": "TATAPOWER.NS",
    "INOXWIND": "INOXWIND.NS",
    "ADANITRANSMISSION": "ADANITRANS.NS",
    "VEDANTA": "VEDL.NS",
    "VEDANTALIMITED": "VEDL.NS",
    "MAHANAGAR": "MTNL.NS",
    "CHOLAMANDALAMIN": "CHOLAFIN.NS",
    "CHOLAMANDALAM": "CHOLAFIN.NS",
    "INFORMATICA": "INFTC.NS",
    "TATACHEM": "TATACHEM.NS",
    "TATACHEMICALS": "TATACHEM.NS",
    "TATACONSUMERPRODUCTS": "TATACONSUM.NS",
    "TATACONSUMER": "TATACONSUM.NS",
    "SAILIINDUSTRIES": "SAIL.NS",
    "NMDC": "NMDC.NS",
    "NMTLIMITED": "NMDC.NS",
    "MOIL": "MOIL.NS",
    "RADICOKHAITANLIMITED": "RADICO.NS",
    "RADICO": "RADICO.NS",
    "MCDOWELLINDIA": "MCDOWELL.NS",
    "UNITEDBREW": "UBL.NS",
    "UNITEDSPIRITS": "MCDOWELL.NS",
    "NAUKRI": "NAUKRI.NS",
    "INFOEDGE": "NAUKRI.NS",
    "INFOEDGEINDIA": "NAUKRI.NS",
    "VARUNBEVERAGES": "VBL.NS",
    "VARUN": "VBL.NS",
    "DELHIVERY": "DELHIVERY.NS",
    "INDIGO": "INDIGO.NS",
    "INTERGLOBE": "INDIGO.NS",
    "SPICEJET": "SPICEJET.NS",
    "UFLEX": "UFLEX.NS",
}


def _company_name_to_ticker(name: str) -> str | None:
    """Resolve a full company name (like Groww exports) to a Yahoo Finance ticker.
    Strips spaces, punctuation, common suffixes for fuzzy matching."""
    # Normalise: uppercase, remove spaces/punctuation
    key = re.sub(r"[^A-Z0-9]", "", name.upper())
    if key in _COMPANY_NAME_TO_TICKER:
        return _COMPANY_NAME_TO_TICKER[key]
    # Try stripping common suffixes and retry
    for suffix in ["LIMITED", "LTD", "CORPORATION", "CORP", "INDUSTRIES", "INDUSTRY",
                   "INDIA", "INDIN", "PRIVATE", "PVT", "PUBLIC"]:
        if key.endswith(suffix):
            shorter = key[: -len(suffix)]
            if shorter in _COMPANY_NAME_TO_TICKER:
                return _COMPANY_NAME_TO_TICKER[shorter]
    return None


def _symbol_to_yf_ticker(raw: str) -> str:
    """
    Canonicalise a raw symbol from any brokerage to a Yahoo Finance ticker.

    Rules (applied in order):
    1. ISIN (12-char alphanum starting with IN) → lookup table, else keep as-is
    2. Already has a recognised suffix (.NS, .BO, .BSE) → keep
    3. Exchange-prefixed (e.g. "NSE:RELIANCE") → strip prefix
    4. Multi-word → try company-name lookup table; keep as-is if not found
    5. Bare NSE symbol → append .NS
    """
    sym = str(raw).strip().upper().strip('"').strip("'")
    # ISIN detection
    if re.match(r"^IN[A-Z0-9]{10}$", sym):
        return ISIN_TO_TICKER.get(sym, sym)
    # Already has suffix
    if re.search(r"\.(NS|BO|BSE|MCX|CDS)$", sym, re.IGNORECASE):
        return sym
    # Strip any exchange prefix that brokers prepend (e.g. "NSE:RELIANCE")
    if ":" in sym:
        sym = sym.split(":")[-1].strip()
    # Multi-word → company name lookup
    if " " in sym or "-" in sym and len(sym) > 12:
        resolved = _company_name_to_ticker(sym)
        if resolved:
            return resolved
        # Cannot resolve — return as-is so caller can skip it
        return sym
    # Append .NS for Indian equities/ETFs
    return f"{sym}.NS"


# ── CSV fast-path ─────────────────────────────────────────────────────────────

def _parse_csv(raw_text: str) -> list[dict]:
    """
    Robust CSV parser that handles:
    - Any delimiter (comma, tab, semicolon, pipe)
    - Leading metadata rows before the real header (common in Zerodha, HDFC)
    - Extra columns (current value, P&L, etc.) — ignored safely
    - Quoted fields with embedded commas
    - BOM characters
    - Windows and Unix line endings
    - Zero or missing quantity/price — accepted, flagged as 0
    - ISIN-only exports (no trading symbol column)
    """
    import csv as _csv

    # Strip BOM if present
    raw_text = raw_text.lstrip("﻿")

    lines = raw_text.splitlines()
    non_empty = [l for l in lines if l.strip() and not l.strip().startswith("#")]

    if not non_empty:
        raise ValueError("File appears to be empty after removing blank/comment lines.")

    # ── Auto-detect delimiter ─────────────────────────────────────────────────
    delimiter = ","
    try:
        sample = "\n".join(non_empty[:50])
        dialect = _csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except _csv.Error:
        for d in [",", "\t", ";", "|"]:
            if sum(l.count(d) for l in non_empty[:10]) > 3:
                delimiter = d
                break
    logger.info("CSV parser: delimiter=%r", delimiter)

    # ── Find the real header row ──────────────────────────────────────────────
    # Scan top 50 lines; first line where any field matches a known column set is the header.
    header_idx = None
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        fields = [_norm(f) for f in line.split(delimiter)]
        # Must contain a symbol-like column OR at least 3 of our known keys
        has_symbol = any(f in SYMBOL_KEYS for f in fields)
        has_qty    = any(f in QTY_KEYS    for f in fields)
        has_price  = any(f in PRICE_KEYS  for f in fields)
        # A real header must have a symbol column AND at least one of qty or price.
        # This prevents matching metadata rows like "Name,Jahanvi Gupta" which have
        # "name" in SYMBOL_KEYS but no numeric columns.
        if has_symbol and (has_qty or has_price):
            header_idx = i
            logger.info("CSV parser: header at line %d — %s", i, fields[:8])
            break

    if header_idx is None:
        preview = "\n".join(f"  L{i}: {l[:120]}" for i, l in enumerate(lines[:30]))
        logger.warning("CSV parser: no header found.\n%s", preview)
        raise ValueError(
            "Could not find a column header row. "
            "Ensure your CSV has a header with columns like: "
            "Symbol/Ticker, Quantity/Units, AverageBuyPrice/Price."
        )

    # ── Parse rows from header line onwards ──────────────────────────────────
    block = "\n".join(lines[header_idx:])
    reader = _csv.DictReader(io.StringIO(block), delimiter=delimiter)

    # Normalise the field names once
    raw_fields = reader.fieldnames or []
    norm_fields = [_norm(f) for f in raw_fields]
    reader.fieldnames = norm_fields

    records: list[dict] = []

    for row in reader:
        # DictReader with normed keys
        r = {_norm(k): (v or "").strip() for k, v in row.items()}

        # ── Extract symbol ────────────────────────────────────────────────────
        sym_raw = next((r[k] for k in SYMBOL_KEYS if k in r and r[k]), None)
        if not sym_raw:
            continue  # blank row

        # Skip obvious metadata / summary rows (these appear in Groww, HDFC exports)
        sl = sym_raw.strip().lower()
        if any(sl == w or sl.startswith(w + " ") for w in [
            "total", "grand total", "summary", "subtotal", "invested value",
            "closing value", "unrealised", "net p&l", "name", "unique client",
            "holdings statement", "as on", "portfolio value",
        ]):
            continue

        symbol = _symbol_to_yf_ticker(sym_raw)

        # If company-name lookup failed (symbol still has spaces), skip the row
        if " " in symbol:
            logger.debug("Skipping unresolved name row: %r", sym_raw)
            continue

        # ── Extract quantity ──────────────────────────────────────────────────
        qty_raw = next((r[k] for k in QTY_KEYS if k in r and r[k]), "0")
        try:
            qty = float(str(qty_raw).replace(",", "").replace("₹", "").strip() or "0")
        except ValueError:
            qty = 0.0

        # ── Extract average buy price ─────────────────────────────────────────
        prc_raw = next((r[k] for k in PRICE_KEYS if k in r and r[k]), "0")
        try:
            prc = float(str(prc_raw).replace(",", "").replace("₹", "").strip() or "0")
        except ValueError:
            prc = 0.0

        # ── Extract asset type ────────────────────────────────────────────────
        type_raw = next((r[k] for k in TYPE_KEYS if k in r and r[k]), "")
        tl = type_raw.lower()
        if "etf" in tl:
            asset_type = "ETF"
        elif "mutual" in tl or "mf" in tl or "fund" in tl:
            asset_type = "MutualFund"
        else:
            asset_type = "Stock"

        records.append({
            "asset_symbol":     symbol,
            "asset_type":       asset_type,
            "quantity":         qty,
            "average_buy_price": prc,
        })

    if not records:
        raise ValueError(
            "Header row was found but no data rows could be parsed. "
            "Check that the file has holdings below the header."
        )

    return records


# ── Upload endpoint ───────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=BulkInsertResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload holdings (CSV, PDF, TXT — any brokerage format)",
    description=(
        "Accepts portfolio exports from Zerodha, Groww, HDFC Sec, ICICI Direct, "
        "Upstox, Angel One, and any CSV with Symbol + Quantity columns. "
        "PDF/TXT files use Gemini AI extraction."
    ),
)
async def upload_holdings(
    portfolio_id: uuid.UUID = Query(..., description="UUID of the target portfolio."),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> BulkInsertResponse:

    filename = (file.filename or "").lower()

    # ── 1. Content-type / extension guard ─────────────────────────────────────
    ct = (file.content_type or "").lower()
    is_csv = (
        "csv" in ct
        or "excel" in ct
        or "spreadsheet" in ct
        or "octet-stream" in ct        # browsers sometimes send this for .csv
        or "plain" in ct               # text/plain
        or filename.endswith(".csv")
        or filename.endswith(".tsv")
        or filename.endswith(".txt")
    )
    is_pdf = "pdf" in ct or filename.endswith(".pdf")

    if not (is_csv or is_pdf):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{file.content_type}'. Upload a CSV or PDF.",
        )

    # ── 2. Read + size check ──────────────────────────────────────────────────
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 10 MB limit.",
        )

    # ── 3. Decode text ────────────────────────────────────────────────────────
    raw_text = ""
    if is_pdf:
        try:
            import asyncio
            def _read_pdf(b: bytes) -> str:
                r = pypdf.PdfReader(io.BytesIO(b))
                return "\n".join(p.extract_text() or "" for p in r.pages)
            raw_text = await asyncio.to_thread(_read_pdf, content)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"PDF read failed: {exc}")
    else:
        # Try UTF-8, fall back to latin-1 (covers Windows-1252 Zerodha exports)
        try:
            raw_text = content.decode("utf-8-sig")  # strips BOM automatically
        except UnicodeDecodeError:
            raw_text = content.decode("latin-1", errors="replace")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="File is empty.")

    # ── 4. Extract holdings ───────────────────────────────────────────────────
    extracted: list[dict] = []

    if is_csv:
        try:
            extracted = _parse_csv(raw_text)
            logger.info("CSV fast-path: %d rows extracted from '%s'", len(extracted), file.filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            logger.warning("CSV fast-path exception: %s", exc)
            raise HTTPException(status_code=400, detail=f"CSV parsing failed: {exc}")
    else:
        # PDF → Gemini LLM extraction
        try:
            extracted = await extract_holdings_from_text(raw_text)
        except Exception as exc:
            err = str(exc)
            if "503" in err or "UNAVAILABLE" in err:
                raise HTTPException(status_code=503, detail="AI service overloaded. Try again in a minute.")
            raise HTTPException(status_code=500, detail=f"AI extraction failed: {exc}")

    if not extracted:
        raise HTTPException(status_code=400, detail="No holdings found in the file.")

    # ── 5. Row-level Pydantic validation ──────────────────────────────────────
    valid_holdings: list[Holding] = []
    errors: list[dict] = []

    for idx, row in enumerate(extracted):
        try:
            validated = HoldingCSVRow.model_validate(row)
            # Skip rows where both quantity and price are zero (likely header leftovers)
            if validated.quantity == 0 and validated.average_buy_price == 0:
                logger.debug("Row %d skipped (zero qty + zero price): %s", idx, row)
                continue
            valid_holdings.append(
                Holding(
                    portfolio_id=portfolio_id,
                    asset_symbol=validated.asset_symbol,
                    asset_type=validated.asset_type,
                    quantity=validated.quantity,
                    average_buy_price=validated.average_buy_price,
                )
            )
        except ValidationError as exc:
            errors.append({"row": idx + 1, "data": row, "error": exc.errors(include_url=False)})

    if not valid_holdings:
        detail = "No valid holdings could be inserted."
        if errors:
            detail += f" {len(errors)} row(s) had validation errors: " + \
                      "; ".join(str(e["error"]) for e in errors[:3])
        raise HTTPException(status_code=400, detail=detail)

    # ── 6. Bulk DB insert ─────────────────────────────────────────────────────
    try:
        db.add_all(valid_holdings)
        await db.flush()
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="Database temporarily unavailable.") from exc
    except Exception as exc:
        logger.error("Bulk insert error: %s", exc)
        raise HTTPException(status_code=500, detail="Unexpected error during insertion.") from exc

    logger.info(
        "Upload portfolio %s: %d inserted, %d errors.", portfolio_id, len(valid_holdings), len(errors)
    )
    return BulkInsertResponse(inserted=len(valid_holdings), errors=errors)
