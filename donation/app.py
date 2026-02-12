import io
import os
import smtplib
from pathlib import Path
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import quote
from uuid import uuid4

import pymysql
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.json.ensure_ascii = False
default_receipt_dir = f"/tmp/donation_receipts_{os.geteuid()}"
RECEIPT_DIR = Path(os.getenv("RECEIPT_DIR", default_receipt_dir))
RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
BASE_DIR = Path(__file__).resolve().parent
SEAL_IMAGE_PATH = Path(os.getenv("SEAL_IMAGE_PATH", str(BASE_DIR / "assets/seals/issuer_seal.png")))
SIGNATURE_IMAGE_PATH = Path(
    os.getenv("SIGNATURE_IMAGE_PATH", str(BASE_DIR / "assets/seals/issuer_signature.png"))
)


# ===== メール設定（環境変数） =====
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "").replace(" ", "")
FROM_MAIL = os.getenv("FROM_MAIL", SMTP_USER)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "kifukin_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "donation")
CREDIT_CARD_INPUT_URL = os.getenv("CREDIT_CARD_INPUT_URL", "").strip()


def parse_multiline_env(value: str) -> str:
    normalized = (
        (value or "")
        .replace("\r\n", "\n")
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("¥n", "\n")
        .strip()
    )
    # Fallback for values like "支店n普通 1234n口座名義..." (missing backslash).
    if "\n" not in normalized and "n" in normalized:
        parts = [part.strip() for part in normalized.split("n")]
        if len(parts) >= 2 and all(parts):
            normalized = "\n".join(parts)
    return normalized


BANK_TRANSFER_INFO = parse_multiline_env(os.getenv("BANK_TRANSFER_INFO", ""))


@app.route("/", methods=["GET"])
def form_page():
    return send_from_directory(".", "index.html")


def build_receipt_pdf(
    name: str,
    address: str,
    amount: str,
    payment_method: str,
    donated_at: datetime,
    certificate_no: str,
) -> bytes:
    """Create receipt PDF bytes (Japanese compatible)."""
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("HeiseiKakuGo-W5", 12)

    text = c.beginText(50, 800)
    text.setFont("HeiseiKakuGo-W5", 12)
    text.textLine("寄付受領書")
    text.textLine("")
    text.textLine(f"証明書番号：{certificate_no}")
    text.textLine("")
    text.textLine(f"{name} 様")
    text.textLine(f"住所：{address}")
    text.textLine("")
    text.textLine(f"寄附金額：{amount} 円")
    text.textLine(f"支払方法：{payment_method}")
    text.textLine(f"日付：{donated_at.strftime('%Y年%m月%d日 %H:%M:%S')}")
    text.textLine("")
    text.textLine("受け入れ団体：NPO法人ほっこり サポートホーム／ほっこりくろちゃん")
    text.textLine("所在地：〒612-8403 京都市伏見区深草ヲカヤ町23-6 サポートホーム")

    c.drawText(text)
    draw_issuer_assets(c)
    c.showPage()
    c.save()

    return buffer.getvalue()


def draw_issuer_assets(c: canvas.Canvas) -> None:
    c.setFont("HeiseiKakuGo-W5", 10)
    y_label = 140
    c.drawString(60, y_label, "発行者印")
    c.drawString(250, y_label, "代表者署名")

    try:
        if SEAL_IMAGE_PATH.exists():
            c.drawImage(
                str(SEAL_IMAGE_PATH),
                x=60,
                y=55,
                width=130,
                height=75,
                preserveAspectRatio=True,
                mask="auto",
            )
    except Exception:
        pass

    try:
        if SIGNATURE_IMAGE_PATH.exists():
            c.drawImage(
                str(SIGNATURE_IMAGE_PATH),
                x=250,
                y=55,
                width=220,
                height=75,
                preserveAspectRatio=True,
                mask="auto",
            )
    except Exception:
        pass


def normalize_payment_method(payment_method: str) -> str:
    value = payment_method.strip()
    if value in {"銀行振込", "振込", "振り込み"}:
        return "bank_transfer"
    if value in {"クレジットカード"}:
        return "credit_card"
    return "cash"


def build_credit_card_input_url(certificate_no: str) -> str:
    base_url = CREDIT_CARD_INPUT_URL or f"{request.url_root.rstrip('/')}/donation/payment/credit-card"
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}certificate_no={quote(certificate_no)}"


def send_receipt_email(
    name: str,
    email: str,
    pdf_bytes: bytes,
    payment_method: str,
    credit_card_input_url: str,
) -> None:
    if not SMTP_USER or not SMTP_PASS or not FROM_MAIL:
        raise RuntimeError("SMTP設定が未完了です。SMTP_USER / SMTP_PASS / FROM_MAIL を設定してください。")

    payment_kind = normalize_payment_method(payment_method)
    body_lines = [
        f"{name} 様",
        "",
        "この度はご寄附ありがとうございます。",
        "受領書をPDFにてお送りいたします。",
        "",
    ]
    if payment_kind == "bank_transfer":
        body_lines.extend(
            [
                "【お振込先情報】",
                BANK_TRANSFER_INFO or "振込先情報が未設定です。運営までお問い合わせください。",
                "",
            ]
        )
    elif payment_kind == "credit_card":
        body_lines.extend(
            [
                "【クレジットカード情報入力】",
                "以下のページからカード情報をご入力ください。",
                credit_card_input_url,
                "",
            ]
        )
    body_lines.extend(["NPO法人ほっこり"])

    msg = EmailMessage()
    msg["Subject"] = "【NPO法人ほっこり】寄付受領書"
    msg["From"] = FROM_MAIL
    msg["To"] = email
    msg.set_content("\n".join(body_lines))
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename="寄付受領書.pdf",
    )

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def get_db_connection():
    if not DB_HOST or not DB_USER or not DB_NAME:
        raise RuntimeError("DB設定が未完了です。DB_HOST / DB_USER / DB_NAME を設定してください。")

    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def ensure_receipts_table(conn) -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS donation_receipts (
        id BIGINT NOT NULL AUTO_INCREMENT,
        certificate_no VARCHAR(32) NOT NULL,
        donor_name VARCHAR(255) NOT NULL,
        donor_address VARCHAR(255) NOT NULL,
        donor_email VARCHAR(255) NOT NULL,
        amount_yen VARCHAR(64) NOT NULL,
        payment_method VARCHAR(64) NOT NULL,
        donated_at DATETIME NOT NULL,
        download_token VARCHAR(64) DEFAULT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'created',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uk_certificate_no (certificate_no),
        UNIQUE KEY uk_download_token (download_token)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def create_receipt_record(
    conn,
    name: str,
    address: str,
    email: str,
    amount: str,
    payment_method: str,
    donated_at: datetime,
) -> tuple[int, str]:
    with conn.cursor() as cur:
        # certificate_no is VARCHAR(32), so keep temporary value within 32 chars.
        temp_certificate_no = f"TEMP-{uuid4().hex[:27]}"
        cur.execute(
            """
            INSERT INTO donation_receipts (
                certificate_no, donor_name, donor_address, donor_email, amount_yen,
                payment_method, donated_at, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'created')
            """,
            (temp_certificate_no, name, address, email, amount, payment_method, donated_at),
        )
        receipt_id = cur.lastrowid
        certificate_no = f"RCPT-{donated_at.year}-{receipt_id:06d}"
        cur.execute(
            "UPDATE donation_receipts SET certificate_no=%s WHERE id=%s",
            (certificate_no, receipt_id),
        )
    conn.commit()
    return receipt_id, certificate_no


def update_receipt_status(conn, receipt_id: int, status: str, token: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE donation_receipts
            SET status=%s, download_token=COALESCE(%s, download_token)
            WHERE id=%s
            """,
            (status, token, receipt_id),
        )
    conn.commit()


def save_receipt(pdf_bytes: bytes) -> str:
    # Keep files for a day and clean older ones opportunistically.
    now_ts = datetime.now().timestamp()
    for path in RECEIPT_DIR.glob("*.pdf"):
        try:
            if now_ts - path.stat().st_mtime > 24 * 60 * 60:
                path.unlink(missing_ok=True)
        except OSError:
            continue

    token = uuid4().hex
    (RECEIPT_DIR / f"{token}.pdf").write_bytes(pdf_bytes)
    return token


@app.route("/download/<token>", methods=["GET"])
def download_receipt(token: str):
    receipt_path = RECEIPT_DIR / f"{token}.pdf"
    if not receipt_path.exists():
        abort(404, description="受領書PDFが見つかりません。再度寄付フォームからお試しください。")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        receipt_path,
        as_attachment=True,
        download_name=f"寄付受領書_{timestamp}.pdf",
        mimetype="application/pdf",
    )


@app.route("/db-check", methods=["GET"])
def db_check():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok, DATABASE() AS db, CURRENT_USER() AS user")
            row = cur.fetchone()

            cur.execute("SHOW TABLES LIKE 'donation_receipts'")
            table_exists = cur.fetchone() is not None

        return jsonify(
            {
                "ok": True,
                "db_result": row,
                "donation_receipts_exists": table_exists,
            }
        ), 200
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/db-check/receipts", methods=["GET"])
def db_check_receipts():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM donation_receipts")
            total = cur.fetchone()["total"]

            cur.execute(
                """
                SELECT
                    id,
                    certificate_no,
                    donor_name,
                    donor_email,
                    amount_yen,
                    payment_method,
                    status,
                    donated_at,
                    created_at
                FROM donation_receipts
                ORDER BY id DESC
                LIMIT 20
                """
            )
            rows = cur.fetchall()

        return jsonify({"ok": True, "total": total, "rows": rows}), 200
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/submit", methods=["POST"])
@app.route("/submit/", methods=["POST"])
def submit():
    name = request.form.get("name", "匿名").strip() or "匿名"
    address = request.form.get("address", "").strip()
    email = request.form.get("email", "").strip()
    amount = request.form.get("amount", "").strip()
    payment_method = request.form.get("payment_method", "未指定").strip() or "未指定"

    if not address or not email or not amount:
        abort(400, description="address / email / amount は必須です。")

    donated_at = datetime.now()

    conn = None
    try:
        conn = get_db_connection()
        ensure_receipts_table(conn)
        receipt_id, certificate_no = create_receipt_record(
            conn=conn,
            name=name,
            address=address,
            email=email,
            amount=amount,
            payment_method=payment_method,
            donated_at=donated_at,
        )
    except Exception as exc:
        app.logger.exception("Failed to create receipt record")
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    pdf_bytes = build_receipt_pdf(
        name=name,
        address=address,
        amount=amount,
        payment_method=payment_method,
        donated_at=donated_at,
        certificate_no=certificate_no,
    )

    credit_card_input_url = build_credit_card_input_url(certificate_no)

    try:
        send_receipt_email(
            name=name,
            email=email,
            pdf_bytes=pdf_bytes,
            payment_method=payment_method,
            credit_card_input_url=credit_card_input_url,
        )
    except Exception as exc:
        app.logger.exception("Failed to send receipt email")
        conn = None
        try:
            conn = get_db_connection()
            update_receipt_status(conn, receipt_id=receipt_id, status="mail_failed")
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        return jsonify({"ok": False, "error": str(exc)}), 502

    token = save_receipt(pdf_bytes)
    conn = None
    try:
        conn = get_db_connection()
        update_receipt_status(conn, receipt_id=receipt_id, status="issued", token=token)
    except Exception:
        app.logger.exception("Failed to update receipt status")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    payment_kind = normalize_payment_method(payment_method)
    if payment_kind == "credit_card":
        return redirect(credit_card_input_url)

    return render_template(
        "thanks.html",
        name=name,
        token=token,
        certificate_no=certificate_no,
        payment_method=payment_method,
        payment_kind=payment_kind,
        bank_transfer_info=BANK_TRANSFER_INFO,
    )


@app.route("/payment/credit-card", methods=["GET"])
def credit_card_input_page():
    certificate_no = request.args.get("certificate_no", "").strip()
    return render_template("credit_card.html", certificate_no=certificate_no)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
