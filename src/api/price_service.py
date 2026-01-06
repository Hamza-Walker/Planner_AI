
import math
import time
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class EnergyStatus(BaseModel):
    electricity_price_eur: float
    solar_available: int

@app.get("/")
def get_status():
    # Simulate varying price
    t = time.time()
    variation = math.sin(t / 10.0) 
    price = 0.50 + (0.40 * variation)
    solar = 1 if price < 0.40 else 0
    
    return {
        "electricity_price_eur": round(price, 2),
        "solar_available": solar
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
