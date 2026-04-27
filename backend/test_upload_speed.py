import io
import csv
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fast_csv_parse(raw_text: str):
    extracted_data = None
    try:
        reader = csv.DictReader(io.StringIO(raw_text))
        if reader.fieldnames:
            reader.fieldnames = [str(f).strip().lower() for f in reader.fieldnames]
            symbol_keys = {"symbol", "ticker", "asset_symbol", "asset"}
            qty_keys = {"quantity", "qty", "shares", "units"}
            price_keys = {"average_buy_price", "price", "avg_price", "buy_price", "cost"}
            
            if set(reader.fieldnames).intersection(symbol_keys):
                extracted_data = []
                for row in reader:
                    sym = next((row[k] for k in symbol_keys if k in row and row[k]), None)
                    qty = next((row[k] for k in qty_keys if k in row and row[k]), 0)
                    prc = next((row[k] for k in price_keys if k in row and row[k]), 0)
                    
                    if sym:
                        extracted_data.append({
                            "asset_symbol": str(sym).strip().upper(),
                            "asset_type": row.get("asset_type", row.get("type", "equity")).strip().lower(),
                            "quantity": float(qty) if qty else 0,
                            "average_buy_price": float(prc) if prc else 0
                        })
                logger.info("Successfully used deterministic CSV fast-path. Bypassing LLM.")
    except Exception as e:
        logger.warning("Deterministic CSV parsing failed: %s", e)
        extracted_data = None
    return extracted_data

# Test data
csv_content = """Symbol,Quantity,Price
AAPL,10,150.0
MSFT,5,300.0
GOOG,2,2800.0
"""

start_time = time.time()
result = fast_csv_parse(csv_content)
end_time = time.time()

print(f"Time taken: {(end_time - start_time) * 1000:.2f} ms")
print(f"Extracted rows: {len(result) if result else 0}")
if result:
    print(f"Sample: {result[0]}")
