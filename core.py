"""
core.py - Logic yose ya DUKA (database, ibarwa, PDF, Excel, password).
Ikoresha Python standard library gusa, nta kintu cyo kwinjizamo.
"""
import hashlib
import io
import os
import secrets
import sqlite3
import threading
import zipfile
from datetime import date, datetime
from xml.sax.saxutils import escape as xml_escape

# ---- Hindura hano ----
SHOP_NAME = "KWA KAZUNGU"
SHOP_INFO = "Kigali, Rwanda"
CURRENCY = "RWF"
# ----------------------

CASH, IDENI = "CASH", "IDENI"
W = 54  # ubugari bw'inyandiko ya facture (inyuguti)

_data_dir = os.getenv("FLET_APP_STORAGE_DATA") or os.path.dirname(os.path.abspath(__file__))
os.makedirs(_data_dir, exist_ok=True)
DB_FILE = os.path.join(_data_dir, "duka.db")

LOCK = threading.RLock()
db = sqlite3.connect(DB_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS products(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    qty REAL NOT NULL DEFAULT 0,
    buy_price REAL NOT NULL DEFAULT 0,
    sell_price REAL NOT NULL DEFAULT 0,
    min_qty REAL NOT NULL DEFAULT 5);
CREATE TABLE IF NOT EXISTS customers(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    phone TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS sales(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    date TEXT NOT NULL,
    pay_type TEXT NOT NULL,
    paid REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sale_items(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id),
    product_id INTEGER,
    designation TEXT NOT NULL,
    qty REAL NOT NULL,
    unit_price REAL NOT NULL,
    buy_price REAL NOT NULL);
CREATE TABLE IF NOT EXISTS payments(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id),
    date TEXT NOT NULL,
    amount REAL NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
""")
db.commit()


def locked(fn):
    def wrapper(*a, **k):
        with LOCK:
            return fn(*a, **k)
    wrapper.__name__ = fn.__name__
    return wrapper


# ------------------------------------------------------------- Ibikoresho bito
def today():
    return date.today().isoformat()


def fmt(n):
    n = float(n or 0)
    return f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"


def num(s, what, allow_zero=False):
    try:
        v = float(str(s if s is not None else "").replace(",", "").strip())
    except ValueError:
        raise ValueError(f"{what}: andika umubare nyawo.")
    if v < 0 or (v == 0 and not allow_zero):
        raise ValueError(f"{what}: umubare ugomba kuba urenze 0.")
    return v


def check_date(s):
    try:
        datetime.strptime((s or "").strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError("Italiki igomba kuba: YYYY-MM-DD (urugero 2026-10-21).")
    return s.strip()


# ------------------------------------------------------------- Password
def _hash(pw, salt):
    h = (salt + pw).encode("utf-8")
    for _ in range(100_000):
        h = hashlib.sha256(h + salt.encode()).digest()
    return h.hex()


def get_setting(key):
    r = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else None


@locked
def set_setting(key, value):
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    db.commit()


def has_password():
    return get_setting("pw_hash") is not None


def set_password(pw):
    if len(pw or "") < 4:
        raise ValueError("Password igomba kuba ifite nibura inyuguti 4.")
    salt = secrets.token_hex(16)
    set_setting("pw_salt", salt)
    set_setting("pw_hash", _hash(pw, salt))


def check_password(pw):
    stored, salt = get_setting("pw_hash"), get_setting("pw_salt")
    return bool(stored and salt) and secrets.compare_digest(_hash(pw or "", salt), stored)


# ------------------------------------------------------------- Stock
def list_products(search="", only_low=False):
    sql = "SELECT * FROM products WHERE name LIKE ?"
    if only_low:
        sql += " AND qty<=min_qty"
    return db.execute(sql + " ORDER BY name", (f"%{(search or '').strip()}%",)).fetchall()


def get_product(pid):
    return db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()


def low_stock_items():
    return db.execute("SELECT * FROM products WHERE qty<=min_qty ORDER BY qty, name").fetchall()


def stock_status(r):
    if r["qty"] <= 0:
        return "BYASHIZE"
    return "BIGIYE GUSHIRA" if r["qty"] <= r["min_qty"] else "BIRIMO"


def _parse_product(name, qty, buy, sell, mn):
    name = (name or "").strip()
    if not name:
        raise ValueError("Andika izina ry'igicuruzwa.")
    return (name, num(qty, "Umubare", True), num(buy, "Igiciro cyo kurangura", True),
            num(sell, "Igiciro cyo kugurisha", True), num(mn or "5", "Ntarengwa", True))


@locked
def add_product(name, qty, buy, sell, mn):
    name, qty, buy, sell, mn = _parse_product(name, qty, buy, sell, mn)
    r = db.execute("SELECT id FROM products WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    if r:
        db.execute("UPDATE products SET qty=qty+?, buy_price=?, sell_price=?, min_qty=? WHERE id=?",
                   (qty, buy, sell, mn, r["id"]))
    else:
        db.execute("INSERT INTO products(name,qty,buy_price,sell_price,min_qty) VALUES(?,?,?,?,?)",
                   (name, qty, buy, sell, mn))
    db.commit()


@locked
def update_product(pid, name, qty, buy, sell, mn):
    name, qty, buy, sell, mn = _parse_product(name, qty, buy, sell, mn)
    try:
        db.execute("UPDATE products SET name=?, qty=?, buy_price=?, sell_price=?, min_qty=? WHERE id=?",
                   (name, qty, buy, sell, mn, pid))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise ValueError("Hari igicuruzwa gisanzwe gifite iryo zina.")


@locked
def delete_product(pid):
    db.execute("DELETE FROM products WHERE id=?", (pid,))
    db.commit()


STOCK_HEADER = ["Id", "Igicuruzwa", "Usigaye", "Ntarengwa", "Kurangura", "Kugurisha",
                "Agaciro (kurangura)", "Muri Stock"]


def stock_export_rows(search="", only_low=False):
    return [[r["id"], r["name"], r["qty"], r["min_qty"], r["buy_price"], r["sell_price"],
             r["qty"] * r["buy_price"], stock_status(r)] for r in list_products(search, only_low)]


# ------------------------------------------------------------- Abakiriya & igurisha
def customer_names(prefix="", limit=5):
    return db.execute("SELECT * FROM customers WHERE name LIKE ? ORDER BY name LIMIT ?",
                      (f"%{(prefix or '').strip()}%", limit)).fetchall()


def get_customer(cid):
    return db.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()


def customers_with_debt(search=""):
    rows = db.execute("""
        SELECT c.id, c.name, c.phone,
          COALESCE((SELECT SUM(i.qty*i.unit_price) FROM sales s JOIN sale_items i ON i.sale_id=s.id
                    WHERE s.customer_id=c.id),0) AS total,
          COALESCE((SELECT SUM(paid) FROM sales WHERE customer_id=c.id),0) AS paid
        FROM customers c WHERE c.name LIKE ? ORDER BY c.name""",
        (f"%{(search or '').strip()}%",)).fetchall()
    return [dict(r, debt=r["total"] - r["paid"]) for r in rows]


def customer_debt(cid):
    for r in customers_with_debt():
        if r["id"] == cid:
            return r["debt"]
    return 0


def sale_total(sale_id):
    return db.execute("SELECT COALESCE(SUM(qty*unit_price),0) t FROM sale_items WHERE sale_id=?",
                      (sale_id,)).fetchone()["t"]


@locked
def create_sale(customer, phone, day, pay_type, paid_str, cart):
    name = (customer or "").strip()
    if not name:
        raise ValueError("Andika izina ry'umukiriya.")
    if not cart:
        raise ValueError("Nta gicuruzwa kiri ku rutonde.")
    d = check_date(day)
    total = sum(l["qty"] * l["price"] for l in cart)
    if pay_type == CASH:
        paid = total
    else:
        paid = num(paid_str or "0", "Yishyuye", True)
        if paid > total:
            raise ValueError("Yishyuye ntishobora kurenga total.")
    need = {}
    for l in cart:
        need[l["pid"]] = need.get(l["pid"], 0) + l["qty"]
    for pid, q in need.items():
        p = get_product(pid)
        if not p or p["qty"] < q:
            raise ValueError(f"Stock ya '{p['name'] if p else '?'}' ntihagije.")
    try:
        row = db.execute("SELECT id FROM customers WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if row:
            cid = row["id"]
            if (phone or "").strip():
                db.execute("UPDATE customers SET phone=? WHERE id=?", (phone.strip(), cid))
        else:
            cid = db.execute("INSERT INTO customers(name, phone) VALUES(?,?)",
                             (name, (phone or "").strip())).lastrowid
        sid = db.execute("INSERT INTO sales(customer_id,date,pay_type,paid) VALUES(?,?,?,?)",
                         (cid, d, pay_type, paid)).lastrowid
        for l in cart:
            bp = get_product(l["pid"])["buy_price"]
            db.execute("INSERT INTO sale_items(sale_id,product_id,designation,qty,unit_price,buy_price) "
                       "VALUES(?,?,?,?,?,?)", (sid, l["pid"], l["name"], l["qty"], l["price"], bp))
            db.execute("UPDATE products SET qty=qty-? WHERE id=?", (l["qty"], l["pid"]))
        if pay_type == IDENI and paid > 0:
            db.execute("INSERT INTO payments(sale_id,date,amount) VALUES(?,?,?)", (sid, d, paid))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return sid


@locked
def pay_debt(cid, amount_str):
    amount = num(amount_str, "Amafaranga")
    if amount > customer_debt(cid) + 1e-9:
        raise ValueError("Amafaranga arenze ideni risigaye.")
    left, day = amount, today()
    try:
        for s in db.execute("SELECT * FROM sales WHERE customer_id=? ORDER BY date,id", (cid,)).fetchall():
            owed = sale_total(s["id"]) - s["paid"]
            if owed > 0 and left > 0:
                x = min(owed, left)
                db.execute("UPDATE sales SET paid=paid+? WHERE id=?", (x, s["id"]))
                db.execute("INSERT INTO payments(sale_id,date,amount) VALUES(?,?,?)", (s["id"], day, x))
                left -= x
        db.commit()
    except Exception:
        db.rollback()
        raise


# ------------------------------------------------------------- Raporo
REPORT_HEADER = ["Italiki", "Facture", "Umukiriya", "Designation", "Quantity", "Unity price",
                 "Total", "Inyungu", "Uburyo"]


def report(day=None):
    """Isubiza (imirongo, totals). day=None => raporo ya byose."""
    sql = """SELECT s.id sid, s.date, s.pay_type, c.name cname, i.*
             FROM sale_items i JOIN sales s ON s.id=i.sale_id
             JOIN customers c ON c.id=s.customer_id"""
    args = ()
    if day:
        args = (check_date(day),)
        sql += " WHERE s.date=?"
    rows, tot, profit, cash, credit = [], 0, 0, 0, 0
    for r in db.execute(sql + " ORDER BY s.date, s.id", args):
        t = r["qty"] * r["unit_price"]
        p = r["qty"] * (r["unit_price"] - r["buy_price"])
        tot += t
        profit += p
        if r["pay_type"] == CASH:
            cash += t
        else:
            credit += t
        rows.append([r["date"], f"{r['sid']:05d}", r["cname"], r["designation"], r["qty"],
                     r["unit_price"], t, p, r["pay_type"]])
    return rows, {"total": tot, "profit": profit, "cash": cash, "credit": credit}


def report_export_rows(rows, totals):
    return rows + [[""] * 9,
                   ["", "", "", "TOTAL", "", "", totals["total"], totals["profit"], ""],
                   ["", "", "", "CASH", "", "", totals["cash"], "", ""],
                   ["", "", "", "IDENI", "", "", totals["credit"], "", ""]]


# ------------------------------------------------------------- Inyandiko ya facture / konti
def _wrap(s, n):
    s = str(s)
    return [s[i:i + n] for i in range(0, len(s), n)] or [""]


def _center(s):
    return s.center(W).rstrip()


def invoice_lines(sale_id):
    s = db.execute("""SELECT s.*, c.name cname, c.phone FROM sales s
                      JOIN customers c ON c.id=s.customer_id WHERE s.id=?""", (sale_id,)).fetchone()
    items = db.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,)).fetchall()
    total = sale_total(sale_id)
    sep = "-" * W
    L = [_center(SHOP_NAME), _center(SHOP_INFO), sep, f"FACTURE No {s['id']:05d}",
         f"Italiki   : {s['date']}", f"Umukiriya : {s['cname']} {s['phone'] or ''}".rstrip(),
         f"Uburyo    : {'CASH (Yishyuwe)' if s['pay_type'] == CASH else 'IDENI (Ideni)'}", sep,
         "Designation".ljust(22) + " " + "Qty".rjust(6) + " " + "U.price".rjust(10) + " " + "Total".rjust(12), sep]
    for i in items:
        parts = _wrap(i["designation"], 22)
        L.append(parts[0].ljust(22) + " " + f"{i['qty']:g}".rjust(6) + " " +
                 fmt(i["unit_price"]).rjust(10) + " " + fmt(i["qty"] * i["unit_price"]).rjust(12))
        L += ["  " + p for p in parts[1:]]
    L += [sep, "TOTAL".ljust(20) + fmt(total).rjust(W - 20),
          "Yishyuwe".ljust(20) + fmt(s["paid"]).rjust(W - 20),
          "ASIGAYE (Ideni)".ljust(20) + fmt(total - s["paid"]).rjust(W - 20), sep, "",
          "Umugurisha: ________      Umukiriya: ________"]
    return L


def statement_data(cid):
    c = get_customer(cid)
    sales = db.execute("SELECT * FROM sales WHERE customer_id=? ORDER BY date,id", (cid,)).fetchall()
    blocks, grand, paid = [], 0, 0
    for s in sales:
        items = db.execute("SELECT * FROM sale_items WHERE sale_id=?", (s["id"],)).fetchall()
        blocks.append((s, items))
        grand += sale_total(s["id"])
        paid += s["paid"]
    return c, blocks, grand, paid


def statement_lines(cid):
    c, blocks, grand, paid = statement_data(cid)
    sep = "-" * W
    L = [_center(SHOP_NAME), _center(SHOP_INFO), sep, f"KONTI Y'UMUKIRIYA: {c['name']}"]
    if c["phone"]:
        L.append(f"Telefone: {c['phone']}")
    L.append(sep)
    for s, items in blocks:
        L.append(f"Facture {s['id']:05d}  {s['date']}  {s['pay_type']}")
        for i in items:
            parts = _wrap(i["designation"], 20)
            L.append("  " + parts[0].ljust(20) + " " + f"{i['qty']:g}".rjust(5) + " " +
                     fmt(i["unit_price"]).rjust(9) + " " + fmt(i["qty"] * i["unit_price"]).rjust(11))
            L += ["    " + p for p in parts[1:]]
        L.append("")
    L += [sep, "TOTAL YOSE".ljust(20) + fmt(grand).rjust(W - 20),
          "Yishyuwe".ljust(20) + fmt(paid).rjust(W - 20),
          "IDENI RISIGAYE".ljust(20) + fmt(grand - paid).rjust(W - 20), sep]
    return L


STATEMENT_HEADER = ["Italiki", "Facture", "Designation", "Quantity", "Unity price", "Total", "Uburyo"]


def statement_export_rows(cid):
    c, blocks, grand, paid = statement_data(cid)
    rows = []
    for s, items in blocks:
        for i in items:
            rows.append([s["date"], f"{s['id']:05d}", i["designation"], i["qty"], i["unit_price"],
                         i["qty"] * i["unit_price"], s["pay_type"]])
    rows += [[""] * 7, ["", "", "TOTAL YOSE", "", "", grand, ""], ["", "", "Yishyuwe", "", "", paid, ""],
             ["", "", "IDENI RISIGAYE", "", "", grand - paid, ""]]
    return rows


# ------------------------------------------------------------- PDF (nta library)
def pdf_bytes(lines, size=11):
    lead = size + 3
    per_page = 50
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[""]]
    kids = " ".join(f"{4 + 2 * k} 0 R" for k in range(len(pages)))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    for k, pl in enumerate(pages):
        st = ["BT", f"/F1 {size} Tf", f"{lead} TL", "40 800 Td"]
        for ln in pl:
            t = ln.encode("latin-1", "replace").decode("latin-1")
            t = t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            st.append(f"({t}) '")
        st.append("ET")
        data = "\n".join(st).encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {5 + 2 * k} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


# ------------------------------------------------------------- Excel (.xlsx) nta library
def _col(i):
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def xlsx_bytes(header, rows, sheet="Raporo"):
    def cell(r, c, v, style):
        ref = f"{_col(c)}{r}"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f'<c r="{ref}" s="{style}"><v>{v}</v></c>'
        return (f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">'
                f'{xml_escape("" if v is None else str(v))}</t></is></c>')

    allrows = [header] + rows
    body = "".join(
        f'<row r="{ri}">' + "".join(cell(ri, ci, v, 1 if ri == 1 else 0) for ci, v in enumerate(row)) + "</row>"
        for ri, row in enumerate(allrows, start=1))
    widths = [max(len(str(r[i])) if i < len(r) and r[i] is not None else 0 for r in allrows)
              for i in range(len(header))]
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{min(max(w + 3, 10), 45)}" customWidth="1"/>'
                   for i, w in enumerate(widths))
    X = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    parts = {
        "[Content_Types].xml": X + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>',
        "_rels/.rels": X + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{RT}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": X + f'<workbook xmlns="{NS}" xmlns:r="{RT}"><sheets>'
            f'<sheet name="{xml_escape(sheet)}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": X + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{RT}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{RT}/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": X + f'<styleSheet xmlns="{NS}">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        "xl/worksheets/sheet1.xml": X + f'<worksheet xmlns="{NS}"><cols>{cols}</cols><sheetData>{body}</sheetData></worksheet>',
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return buf.getvalue()


@locked
def backup_bytes():
    db.commit()
    with open(DB_FILE, "rb") as f:
        return f.read()
