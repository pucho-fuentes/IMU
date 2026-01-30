from flask import Flask, jsonify, render_template, request, send_file
from flask_sock import Sock
import json
from datetime import datetime, timedelta
import csv
import io
import os

app = Flask(__name__)
sock = Sock(app)

# Últimos datos IMU
latest_data = {
    "ax": 0.0,
    "ay": 0.0,
    "az": 0.0,
    "time": ""
}

# ✅ Lista para almacenar TODOS los datos históricos
data_history = []

# ✅ Archivo CSV para persistencia
DATA_FILE = "imu_data_history.csv"

# =========================
# Cargar datos previos al iniciar
# =========================
def load_history():
    """Carga el historial de datos desde el archivo CSV si existe"""
    global data_history
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data_history.append({
                        "ax": float(row["ax"]),
                        "ay": float(row["ay"]),
                        "az": float(row["az"]),
                        "time": row["time"]
                    })
            print(f"✅ Cargados {len(data_history)} registros históricos")
        except Exception as e:
            print(f"⚠️ Error al cargar historial: {e}")

# =========================
# Guardar datos en archivo
# =========================
def save_to_file(data):
    """Guarda un registro nuevo en el archivo CSV"""
    file_exists = os.path.exists(DATA_FILE)
    
    try:
        with open(DATA_FILE, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ["time", "ax", "ay", "az"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            # Escribir encabezado solo si el archivo es nuevo
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(data)
    except Exception as e:
        print(f"⚠️ Error al guardar en archivo: {e}")

# =========================
# WebSocket en "/"
# =========================
@sock.route("/")
def imu_ws(ws):
    print("🟢 ESP32 conectada por WebSocket")

    while True:
        data = ws.receive()
        if data is None:
            print("🔴 ESP32 desconectada")
            break

        print("📥 Mensaje crudo:", data)

        try:
            imu = json.loads(data)

            timestamp = datetime.now().isoformat()
            
            latest_data["ax"] = imu["ax"]
            latest_data["ay"] = imu["ay"]
            latest_data["az"] = imu["az"]
            latest_data["time"] = timestamp

            # ✅ Guardar en historial
            record = {
                "ax": imu["ax"],
                "ay": imu["ay"],
                "az": imu["az"],
                "time": timestamp
            }
            
            data_history.append(record)
            save_to_file(record)

            print("✅ IMU guardado:", latest_data)

        except Exception as e:
            print("⚠️ Error JSON:", e)

# =========================
# HTML
# =========================
@app.route("/monitor")
def monitor():
    return render_template("monitor.html")

# =========================
# API para el HTML
# =========================
@app.route("/data")
def data():
    return jsonify(latest_data)

# =========================
# ✅ API para obtener estadísticas
# =========================
@app.route("/api/stats")
def stats():
    """Devuelve estadísticas del historial completo"""
    return jsonify({
        "total_records": len(data_history),
        "first_record": data_history[0]["time"] if data_history else None,
        "last_record": data_history[-1]["time"] if data_history else None
    })

# =========================
# ✅ API para filtrar datos por rango de tiempo
# =========================
@app.route("/api/filter")
def filter_data():
    """Filtra datos por rango de fecha/hora"""
    start_time = request.args.get('start')
    end_time = request.args.get('end')
    
    if not start_time or not end_time:
        return jsonify({"error": "Se requieren parámetros 'start' y 'end'"}), 400
    
    try:
        # Convertir strings a datetime y remover timezone info para comparación
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        # Remover timezone info si existe para comparación consistente
        if start_dt.tzinfo:
            start_dt = start_dt.replace(tzinfo=None)
        if end_dt.tzinfo:
            end_dt = end_dt.replace(tzinfo=None)
        
        # Filtrar datos en el rango
        filtered = []
        for record in data_history:
            record_dt = datetime.fromisoformat(record["time"])
            # Remover timezone info del registro también
            if record_dt.tzinfo:
                record_dt = record_dt.replace(tzinfo=None)
            
            if start_dt <= record_dt <= end_dt:
                filtered.append(record)
        
        return jsonify({
            "total": len(filtered),
            "data": filtered
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# =========================
# ✅ Descargar CSV filtrado por rango
# =========================
@app.route("/api/download")
def download_csv():
    """Descarga datos en formato CSV según el rango de tiempo especificado"""
    start_time = request.args.get('start')
    end_time = request.args.get('end')
    
    if not start_time or not end_time:
        return jsonify({"error": "Se requieren parámetros 'start' y 'end'"}), 400
    
    try:
        # Convertir strings a datetime y remover timezone info para comparación
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        # Remover timezone info si existe para comparación consistente
        if start_dt.tzinfo:
            start_dt = start_dt.replace(tzinfo=None)
        if end_dt.tzinfo:
            end_dt = end_dt.replace(tzinfo=None)
        
        # Filtrar datos en el rango
        filtered = []
        for record in data_history:
            record_dt = datetime.fromisoformat(record["time"])
            # Remover timezone info del registro también
            if record_dt.tzinfo:
                record_dt = record_dt.replace(tzinfo=None)
            
            if start_dt <= record_dt <= end_dt:
                filtered.append(record)
        
        # Crear CSV en memoria
        output = io.StringIO()
        fieldnames = ["time", "ax", "ay", "az"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        
        writer.writeheader()
        for record in filtered:
            writer.writerow(record)
        
        # Convertir a bytes
        output.seek(0)
        csv_bytes = io.BytesIO(output.getvalue().encode('utf-8'))
        
        # Nombre del archivo con el rango de fechas
        filename = f"imu_data_{start_dt.strftime('%Y%m%d_%H%M')}_{end_dt.strftime('%Y%m%d_%H%M')}.csv"
        
        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# =========================
# ✅ Descargar TODO el historial
# =========================
@app.route("/api/download/all")
def download_all():
    """Descarga todos los datos históricos en CSV"""
    try:
        # Crear CSV en memoria
        output = io.StringIO()
        fieldnames = ["time", "ax", "ay", "az"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        
        writer.writeheader()
        for record in data_history:
            writer.writerow(record)
        
        # Convertir a bytes
        output.seek(0)
        csv_bytes = io.BytesIO(output.getvalue().encode('utf-8'))
        
        # Nombre del archivo con timestamp
        filename = f"imu_data_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# =========================
# ✅ Borrar historial (opcional)
# =========================
@app.route("/api/clear", methods=['POST'])
def clear_history():
    """Borra todo el historial de datos"""
    global data_history
    try:
        data_history = []
        
        # Eliminar archivo
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)
        
        return jsonify({"success": True, "message": "Historial borrado"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================
if __name__ == "__main__":
    print("🚀 Cargando historial de datos...")
    load_history()
    print(f"🚀 Servidor en http://0.0.0.0:5000")
    print(f"📊 Monitor: http://0.0.0.0:5000/monitor")
    app.run(host="0.0.0.0", port=5000)