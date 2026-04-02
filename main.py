from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
import random
import string

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB mock (solo per test rapidi locale)
VEHICLES = {
    1001: {"id": 1001, "brand": "Fiat", "model": "500X", "year": 2022, "fuel": "Benzina"},
    1002: {"id": 1002, "brand": "VW", "model": "Golf", "year": 2023, "fuel": "Diesel"},
}
WORK_ORDERS = []
PARTS = []
NEXT_WO_ID = 1


def get_vehicle(vehicle_id: int) -> Dict[str, Any]:
    v = VEHICLES.get(vehicle_id)
    if not v:
        raise HTTPException(404, "Vehicle not found")
    return v


def query(sql: str, params=None):
    # stub per test - restituisce valori fittizi
    if sql.lower().startswith("select count(*"):
        return [{"count": 0}]
    if sql.lower().startswith("select sum"):
        return [{"sum": 0}]
    return []


class DiagnosticRequest(BaseModel):
    vehicle_id: int
    dtc_codes: List[str]
    symptoms: str = ""


class WorkOrderRequest(BaseModel):
    vehicle_id: int
    dtc_codes: List[str]
    symptoms: str = ""


# Simulazione LLM locale (usa OpenAI o Llama se disponibile)
def mock_llm_prompt(prompt):
    # In produzione: usa openai.ChatCompletion.create o llama-cpp-python
    if "P0100" in prompt:
        return "Il codice P0100 indica un problema al sensore MAF. Suggerisco: 1. Controllare fili e connettori. 2. Pulire o sostituire sensore MAF. 3. Verificare filtro aria intasato."
    elif "P0171" in prompt:
        return "Miscela troppo magra (P0171). Possibili cause: iniettori sporchi, sensore O2 guasto, perdita aspirazione. Azioni: test iniettori, sostituzione O2, controllo tubi."
    else:
        return "Codice DTC non riconosciuto. Consigli: consultare manuale costruttore, eseguire scansione completa OBD-II, verificare aggiornamenti ECU."

@app.post("/diagnostics/llm")
def llm_diagnosis(req: DiagnosticRequest):
    vehicle = get_vehicle(req.vehicle_id)
    prompt = f"""
    Veicolo: {vehicle['brand']} {vehicle['model']} ({vehicle['year']}) - Fuel: {vehicle['fuel']}
    DTC: {', '.join(req.dtc_codes)}
    Sintomi: {req.symptoms or 'nessuno specificato'}
    Fornisci diagnosi dettagliata e piano riparazione step-by-step.
    """
    diagnosis = mock_llm_prompt(prompt)
    return {"vehicle_id": req.vehicle_id, "diagnosis": diagnosis}

@app.post("/work_orders/auto_generate")
def auto_generate_work_order(req: WorkOrderRequest):
    global NEXT_WO_ID
    vehicle = get_vehicle(req.vehicle_id)
    title = f"Riparazione DTC: {', '.join(req.dtc_codes[:3])}"
    description = f"Diagnosi automatica per veicolo {vehicle['brand']} {vehicle['model']} ({vehicle['year']}). Sintomi: {req.symptoms}"

    wo_id = NEXT_WO_ID
    NEXT_WO_ID += 1
    new_wo = {
        "id": wo_id,
        "vehicle_id": req.vehicle_id,
        "title": title,
        "description": description,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    WORK_ORDERS.append(new_wo)

    parts = []
    for code in req.dtc_codes:
        if code == "P0100":
            parts.append(("Sensore MAF", 1, 120.0))
        elif code == "P0171":
            parts.append(("Sensore O2", 1, 80.0))
            parts.append(("Iniettore carburante", 4, 25.0))
        elif code == "P0300":
            parts.append(("Candele", 4, 15.0))
            parts.append(("Bobine accensione", 4, 40.0))
        elif code == "P0401":
            parts.append(("Valvola EGR", 1, 150.0))
        elif code == "P0420":
            parts.append(("Catalizzatore", 1, 500.0))
        elif code == "P2459":
            parts.append(("Filtro particolato DPF", 1, 800.0))
    
    # Inserisci parts
    for name, qty, price in parts:
        PARTS.append({
            "work_order_id": wo_id,
            "name": name,
            "quantity": qty,
            "unit_price": price,
        })

    return {"work_order_id": wo_id, "title": title, "parts": parts}

@app.get("/work_orders/{wo_id}/details")
def work_order_details(wo_id: int):
    wo = next((w for w in WORK_ORDERS if w["id"] == wo_id), None)
    if not wo:
        raise HTTPException(404, "work order not found")
    parts = [p for p in PARTS if p["work_order_id"] == wo_id]
    return {"work_order": wo, "parts": parts}
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
import io
from fastapi.responses import StreamingResponse

@app.put("/work_orders/{wo_id}/status")
def update_work_order_status(wo_id: int, status: str):
    valid_statuses = ["open", "in_progress", "completed", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(400, f"Status must be one of: {', '.join(valid_statuses)}")
    wo = next((w for w in WORK_ORDERS if w["id"] == wo_id), None)
    if not wo:
        raise HTTPException(404, "work order not found")
    wo["status"] = status
    wo["updated_at"] = datetime.now().isoformat()
    return {"message": f"Work order {wo_id} status updated to {status}"}

@app.get("/work_orders/{wo_id}/pdf")
def generate_work_order_pdf(wo_id: int):
    wo = query("SELECT * FROM work_orders WHERE id = %s", [wo_id])
    if not wo:
        raise HTTPException(404, "Work order not found")
    wo = wo[0]
    vehicle = query("SELECT b.name AS brand, m.name AS model, v.year FROM vehicles v JOIN engines e ON e.id=v.engine_id JOIN models m ON m.id=e.model_id JOIN brands b ON b.id=m.brand_id WHERE v.id = %s", [wo['vehicle_id']])[0]
    parts = query("SELECT * FROM parts WHERE work_order_id = %s", [wo_id])
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    story.append(Paragraph("Officina AI - Work Order Report", styles['Title']))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph(f"Work Order ID: {wo['id']}", styles['Heading2']))
    story.append(Paragraph(f"Title: {wo['title']}", styles['Normal']))
    story.append(Paragraph(f"Description: {wo['description']}", styles['Normal']))
    story.append(Paragraph(f"Status: {wo['status']}", styles['Normal']))
    story.append(Paragraph(f"Created: {wo['created_at']}", styles['Normal']))
    story.append(Paragraph(f"Vehicle: {vehicle['brand']} {vehicle['model']} ({vehicle['year']})", styles['Normal']))
    story.append(Spacer(1, 12))
    
    if parts:
        story.append(Paragraph("Parts Required:", styles['Heading3']))
        data = [['Part Name', 'Quantity', 'Unit Price', 'Total']]
        total = 0
        for p in parts:
            subtotal = p['quantity'] * p['unit_price']
            total += subtotal
            data.append([p['name'], str(p['quantity']), f"€{p['unit_price']:.2f}", f"€{subtotal:.2f}"])
        data.append(['', '', 'Total:', f"€{total:.2f}"])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
    
    doc.build(story)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type='application/pdf', headers={"Content-Disposition": f"attachment; filename=work_order_{wo_id}.pdf"})
from datetime import datetime, timedelta

@app.get("/kpi/summary")
def get_kpi_summary():
    # Totale veicoli
    total_vehicles = query("SELECT count(*) FROM vehicles")[0]['count']
    
    # Work orders completate
    completed_wo = query("SELECT count(*) FROM work_orders WHERE status = 'completed'")[0]['count']
    
    # Ricavi totali (da parts)
    revenue = query("SELECT sum(p.quantity * p.unit_price) FROM parts p JOIN work_orders wo ON wo.id = p.work_order_id WHERE wo.status = 'completed'")[0]['sum'] or 0
    
    # Work orders questo mese
    month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    wo_this_month = query("SELECT count(*) FROM work_orders WHERE created_at >= %s", [month_start])[0]['count']
    
    # DTC più comuni
    common_dtc = query("""
        SELECT d.code, d.description, count(*) as freq
        FROM dtc_codes d
        JOIN work_orders wo ON wo.title LIKE '%' || d.code || '%'
        GROUP BY d.code, d.description
        ORDER BY freq DESC
        LIMIT 5
    """)
    
    return {
        "total_vehicles": total_vehicles,
        "completed_work_orders": completed_wo,
        "total_revenue": round(float(revenue), 2),
        "work_orders_this_month": wo_this_month,
        "common_dtc": common_dtc
    }

@app.get("/kpi/revenue_chart")
def get_revenue_chart():
    # Ricavi per mese ultimi 6 mesi
    data = []
    for i in range(5, -1, -1):
        month = (datetime.now() - timedelta(days=30*i)).strftime('%Y-%m')
        revenue = query("""
            SELECT sum(p.quantity * p.unit_price) 
            FROM parts p 
            JOIN work_orders wo ON wo.id = p.work_order_id 
            WHERE wo.status = 'completed' AND to_char(wo.updated_at, 'YYYY-MM') = %s
        """, [month])[0]['sum'] or 0
        data.append({"month": month, "revenue": round(float(revenue), 2)})
    return data

@app.get("/kpi/work_orders_status")
def get_work_orders_status():
    statuses = query("SELECT status, count(*) FROM work_orders GROUP BY status")
    return {s['status']: s['count'] for s in statuses}
import random
import time

# Simulazione connessione OBD-II
obd_connections = {}  # vehicle_id -> connection_status

@app.post("/obd/connect/{vehicle_id}")
def obd_connect(vehicle_id: int):
    # Simula connessione (delay 2 secondi)
    time.sleep(2)
    obd_connections[vehicle_id] = True
    return {"message": f"Connected to vehicle {vehicle_id} via OBD-II", "status": "connected"}

@app.get("/obd/{vehicle_id}/read_dtc")
def obd_read_dtc(vehicle_id: int):
    if vehicle_id not in obd_connections or not obd_connections[vehicle_id]:
        raise HTTPException(400, "Vehicle not connected via OBD-II")
    
    # Simula lettura DTC casuali dal DB esistente
    dtc_list = query("SELECT code FROM dtc_codes ORDER BY random() LIMIT %s", [random.randint(1, 3)])
    codes = [d['code'] for d in dtc_list]
    
    # Simula anche parametri live (RPM, temp, etc.)
    live_data = {
        "rpm": random.randint(800, 3000),
        "coolant_temp": random.randint(80, 110),
        "battery_voltage": round(random.uniform(12.0, 14.5), 1),
        "fuel_level": random.randint(20, 100)
    }
    
    return {"dtc_codes": codes, "live_data": live_data}

@app.post("/obd/{vehicle_id}/clear_dtc")
def obd_clear_dtc(vehicle_id: int):
    if vehicle_id not in obd_connections or not obd_connections[vehicle_id]:
        raise HTTPException(400, "Vehicle not connected via OBD-II")
    
    # Simula clear DTC
    time.sleep(1)
    return {"message": f"DTC cleared for vehicle {vehicle_id}", "cleared_codes": []}

@app.post("/obd/disconnect/{vehicle_id}")
def obd_disconnect(vehicle_id: int):
    if vehicle_id in obd_connections:
        del obd_connections[vehicle_id]
    return {"message": f"Disconnected from vehicle {vehicle_id}"}
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configurazione email (sostituisci con credenziali reali)
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your_email@gmail.com",  # Sostituisci
    "password": "your_app_password",     # Sostituisci con app password
    "from_email": "officina_ai@example.com",
    "to_emails": ["mechanic@example.com", "customer@example.com"]  # Lista destinatari
}

def send_email_notification(subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['from_email']
        msg['To'] = ', '.join(EMAIL_CONFIG['to_emails'])
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
        text = msg.as_string()
        server.sendmail(EMAIL_CONFIG['from_email'], EMAIL_CONFIG['to_emails'], text)
        server.quit()
        return True
    except Exception as e:
        print(f"Email send failed: {e}")
        return False

@app.put("/work_orders/{wo_id}/status")
def update_work_order_status(wo_id: int, status: str):
    valid_statuses = ["open", "in_progress", "completed", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(400, f"Status must be one of: {', '.join(valid_statuses)}")
    
    old_status = query("SELECT status, title FROM work_orders WHERE id = %s", [wo_id])
    if not old_status:
        raise HTTPException(404, "Work order not found")
    old_status = old_status[0]['status']
    
    query("UPDATE work_orders SET status = %s, updated_at = NOW() WHERE id = %s", [status, wo_id])
    
    # Invia notifica email se status cambiato
    if old_status != status:
        subject = f"Work Order {wo_id} Status Changed"
        body = f"""
        Work Order ID: {wo_id}
        Title: {old_status[0]['title']}
        Status changed from '{old_status}' to '{status}'
        
        Please check the system for details.
        """
        send_email_notification(subject, body)
    
    return {"message": f"Work order {wo_id} status updated to {status}"}
from datetime import datetime

# Aggiungi tabella appointments se non esiste
try:
    query("""
    CREATE TABLE IF NOT EXISTS appointments (
        id SERIAL PRIMARY KEY,
        vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
        title TEXT NOT NULL,
        description TEXT,
        start_time TIMESTAMPTZ NOT NULL,
        end_time TIMESTAMPTZ NOT NULL,
        status TEXT DEFAULT 'scheduled'
    )
    """)
except:
    pass

@app.get("/appointments")
def get_appointments(start: str = None, end: str = None):
    q = "SELECT id, vehicle_id, title, description, start_time, end_time, status FROM appointments"
    params = []
    if start and end:
        q += " WHERE start_time >= %s AND end_time <= %s"
        params = [start, end]
    q += " ORDER BY start_time"
    return query(q, params)

@app.post("/appointments")
def create_appointment(vehicle_id: int, title: str, description: str = "", start_time: str = "", end_time: str = ""):
    if not all([vehicle_id, title, start_time, end_time]):
        raise HTTPException(400, "Missing required fields")
    app_id = query("INSERT INTO appointments (vehicle_id, title, description, start_time, end_time) VALUES (%s, %s, %s, %s, %s) RETURNING id", 
                   [vehicle_id, title, description, start_time, end_time])[0]['id']
    return {"id": app_id, "message": "Appointment created"}

@app.put("/appointments/{app_id}")
def update_appointment(app_id: int, title: str = None, description: str = None, start_time: str = None, end_time: str = None, status: str = None):
    updates = []
    params = []
    if title:
        updates.append("title = %s"); params.append(title)
    if description is not None:
        updates.append("description = %s"); params.append(description)
    if start_time:
        updates.append("start_time = %s"); params.append(start_time)
    if end_time:
        updates.append("end_time = %s"); params.append(end_time)
    if status:
        updates.append("status = %s"); params.append(status)
    if not updates:
        raise HTTPException(400, "No fields to update")
    q = f"UPDATE appointments SET {', '.join(updates)} WHERE id = %s"
    params.append(app_id)
    query(q, params)
    return {"message": f"Appointment {app_id} updated"}

@app.delete("/appointments/{app_id}")
def delete_appointment(app_id: int):
    query("DELETE FROM appointments WHERE id = %s", [app_id])
    return {"message": f"Appointment {app_id} deleted"}
