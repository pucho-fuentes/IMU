from flask import Flask, jsonify, render_template, request, send_file
from flask_sock import Sock
import json
import os
import io
import csv
import mysql.connector
from datetime import datetime

# =========================
# CONFIG
# =========================
app = Flask(__name__)
sock = Sock(app)

# =========================
# MYSQL (Railway ENV VARS)
# =========================
DB_CONFIG = {
    "host": os.environ.get("MYSQLHOST"),
    "user": os.environ.get("MYSQLUSER"),
    "password": os.environ.get("MYSQLPASSWORD"),
    "database": os.environ.get("MYSQLDATABASE"),
    "port": int(os.environ.get("MYSQLPORT", 3306))
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

# =========================
# ÚLTIMO DATO (TIEMPO REAL)
# =========================
latest_data = {
    "ax": 0.0,
    "ay": 0.0,
    "az": 0.0,
    "time": ""
}

# =========================
# CREAR TABLA SI NO EXISTE
# =========================
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS imu_data (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            ax FLOAT,
            ay FLOAT,
            az FLOAT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ MySQL listo")

# =========================
# WEBSOCKET ESP32
# =========================
@sock.route("/")
def imu_ws(ws):
    print("🟢 ESP32 conectada")

    conn = get_db()
    cur = conn.cursor()

    while True:
        msg = ws.receive()
        if msg is None:
            print("🔴 ESP32 desconectada")
            break

        try:
            imu = json.loads(msg)
            timestamp = datetime.now().isoformat()

            latest_data.update({
                "ax": imu["ax"],
                "ay": imu["ay"],
                "az": imu["az"],
                "time": timestamp
            })

            cur.execute(
                "INSERT INTO imu_data (ax, ay, az) VALUES (%s, %s, %s)",
                (imu["ax"], imu["ay"], imu["az"])
            )
            conn.commit()

        except Exception as e:
            print("⚠️ Error:", e)

    cur.close()
    conn.close()

# =========================
# MONITOR HTML
# =========================
@app.route("/monitor")
def monitor():
    return render_template("monitor.html")

# =========================
# DATA EN TIEMPO REAL
# =========================
@app.route("/data")
def data():
    return jsonify(latest_data)

# =========================
# FILTRAR POR RANGO HORARIO
# =========================
@app.route("/api/filter")
def filter_data():
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return jsonify({"error": "start y end requeridos"}), 400

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT ax, ay, az, created_at
        FROM imu_data
        WHERE created_at BETWEEN %s AND %s
        ORDER BY created_at ASC
    """, (start, end))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        "total": len(rows),
        "data": rows
    })

# =========================
# DESCARGAR CSV POR RANGO
# =========================
@app.route("/api/download")
def download_csv():
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        return jsonify({"error": "start y end requeridos"}), 400

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT ax, ay, az, created_at
        FROM imu_data
        WHERE created_at BETWEEN %s AND %s
        ORDER BY created_at ASC
    """, (start, end))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["time", "ax", "ay", "az"])

    for r in rows:
        writer.writerow([r["created_at"], r["ax"], r["ay"], r["az"]])

    output.seek(0)
    csv_bytes = io.BytesIO(output.getvalue().encode("utf-8"))

    filename = f"imu_{start}_{end}.csv"

    return send_file(
        csv_bytes,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename
    )

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print("🚀 Servidor listo")
    app.run(host="0.0.0.0", port=port)
