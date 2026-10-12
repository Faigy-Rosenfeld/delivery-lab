from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()

# מסד נתונים בזיכרון (dict)
deliveries_db = {}
id_counter = 1


# מודל Pydantic עבור הבקשות (POST) - מונע שדות מיותרים
class DeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient: str
    address: str


# טיפול בשגיאות ולידציה של הבקשה (החזרת status 400 במקום 422)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid request payload"})


# טיפול בשגיאות HTTP בפורמט הנדרש: {"error": "..."}
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail)},
    )


# 1. GET /health
@app.get("/health")
def health():
    return {"status": "ok"}


# 2. POST /deliveries - יצירת משלוח חדש
@app.post("/deliveries", status_code=status.HTTP_201_CREATED)
def create_delivery(delivery: DeliveryCreate):
    global id_counter

    # בדיקת מחרוזות שאינן ריקות
    if not delivery.recipient.strip() or not delivery.address.strip():
        raise HTTPException(
            status_code=400, detail="Recipient and address must be non-empty strings"
        )

    new_delivery = {
        "id": id_counter,
        "recipient": delivery.recipient,
        "address": delivery.address,
        "status": "created",
    }

    deliveries_db[id_counter] = new_delivery
    id_counter += 1

    return new_delivery


# 3. GET /deliveries - קבלת רשימת משלוחים (עם אופציה לסינון לפי status)
@app.get("/deliveries")
def get_deliveries(status: Optional[str] = None):
    valid_statuses = ["created", "in_transit", "delivered"]
    if status is not None and status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status filter")

    results = list(deliveries_db.values())

    if status:
        results = [d for d in results if d["status"] == status]

    return results


# 4. GET /deliveries/{delivery_id} - קבלת משלוח לפי מזהה
@app.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: int):
    if delivery_id not in deliveries_db:
        raise HTTPException(status_code=404, detail="Delivery not found")

    return deliveries_db[delivery_id]


# 5. PATCH /deliveries/{delivery_id}/status - עדכון סטטוס משלוח
@app.patch("/deliveries/{delivery_id}/status")
def update_delivery_status(delivery_id: int, payload: dict):
    if delivery_id not in deliveries_db:
        raise HTTPException(status_code=404, detail="Delivery not found")

    if "status" not in payload:
        raise HTTPException(status_code=400, detail="Status is required")

    new_status = payload["status"]
    valid_statuses = ["created", "in_transit", "delivered"]

    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")

    current_status = deliveries_db[delivery_id]["status"]

    # כללי מעבר סטטוס: מותר רק צעד אחד קדימה (created -> in_transit -> delivered)
    allowed_transitions = {
        "created": "in_transit",
        "in_transit": "delivered",
        "delivered": None,
    }

    if allowed_transitions.get(current_status) != new_status:
        raise HTTPException(
            status_code=409, detail="Invalid status transition"
        )

    deliveries_db[delivery_id]["status"] = new_status
    return deliveries_db[delivery_id]


# 6. DELETE /deliveries/{delivery_id} - מחיקת משלוח
@app.delete("/deliveries/{delivery_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_delivery(delivery_id: int):
    if delivery_id not in deliveries_db:
        raise HTTPException(status_code=404, detail="Delivery not found")

    # מותר למחוק רק משלוח בסטטוס created
    if deliveries_db[delivery_id]["status"] != "created":
        raise HTTPException(
            status_code=409, detail="Cannot delete delivery that is not in created status"
        )

    del deliveries_db[delivery_id]
    return Response(status_code=status.HTTP_204_NO_CONTENT)