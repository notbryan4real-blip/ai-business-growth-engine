"""Read-only LuckPool Verus miner snapshot. No device commands or secrets."""
from datetime import datetime, timezone
import os
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/mining", tags=["mining"])
WALLET = os.getenv("VERUS_MINER_WALLET", "RGr99tkfNxYHhSxikyjqg9JSJFtsTCoSZC")
POOL_BASE = "https://luckpool.net/verus"
TIMEOUT = 8.0

@router.get("/status")
async def mining_status():
    """Pool-derived snapshot; unavailable is not zero and not proof of offline status."""
    if not (WALLET.startswith("R") and WALLET.isalnum() and len(WALLET) <= 64):
        raise HTTPException(status_code=503, detail="Miner wallet configuration invalid")
    endpoint = f"{POOL_BASE}/miner/{WALLET}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            response = await client.get(endpoint, headers={"Accept": "application/json"})
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Unexpected pool response")
    except (httpx.HTTPError, ValueError):
        return {"status": "unavailable", "source": "luckpool", "checked_at": datetime.now(timezone.utc).isoformat(), "wallet": WALLET, "worker": "moto", "metrics": None}
    # Do not guess undocumented keys or turn missing values into zero.
    fields = ("hashrate", "hashrate1h", "hashrate24h", "workers", "balance", "immature", "paid", "shares", "validShares", "invalidShares")
    return {"status": "reported", "source": "luckpool", "checked_at": datetime.now(timezone.utc).isoformat(), "wallet": WALLET, "worker": "moto", "metrics": {key: data[key] for key in fields if key in data}}
