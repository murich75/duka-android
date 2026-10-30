"""
main.py - Interface ya DUKA ya Android (Flet). Logic yose iri muri core.py
"""
import time
from datetime import date

import flet as ft

import core

MONO = "monospace"
GREY, RED_BG, ORANGE_BG = ft.Colors.GREY_200, ft.Colors.RED_100, ft.Colors.ORANGE_100
RED, GREEN = ft.Colors.RED_700, ft.Colors.GREEN_700


def main(page: ft.Page):
    page.title = core.SHOP_NAME
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0

    fp = ft.FilePicker()
    page.services.append(fp)

    msg = ft.Text("", size=13, weight=ft.FontWeight.BOLD)
    body = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=8)
    nav = ft.Row(wrap=True, spacing=4, run_spacing=4)

    # ------------------------------------------------------------ ibikoresho
    def say(text="", ok=True):
        msg.value = text
        msg.color = GREEN if ok else RED
        page.update()

    def err(ex):
        say(str(ex), False)

    def tf(label, value="", num=False, **kw):
        return ft.TextField(label=label, value=value, dense=True,
                            keyboard_type=ft.KeyboardType.NUMBER if num else ft.KeyboardType.TEXT, **kw)

    def pw(label):
        return ft.TextField(label=label, dense=True, password=True, can_reveal_password=True)

    def h(text):
        return ft.Text(text, size=18, weight=ft.FontWeight.BOLD)

    def show(*controls):
        msg.value = ""
        body.controls = list(controls)
        page.update()

    def row(*controls):
        return ft.Row(list(controls), wrap=True, spacing=6, run_spacing=6)

    def mono_box(lines):
        return ft.Container(
            content=ft.Row([ft.Text("\n".join(lines), font_family=MONO, size=9, selectable=True)],
                           scroll=ft.ScrollMode.AUTO),
            padding=8, bgcolor=GREY, border_radius=8)

    async def save_bytes(name, data):
        try:
            await fp.save_file(file_name=name, src_bytes=data)
            say(f"Dosiye '{name}' yoherejwe kubikwa. Niba wayibitse, uyisanga muri Files / Downloads.")
        except Exception as ex:
            err(f"Ntibyabashije kubikwa: {ex}")

    # ------------------------------------------------------------ kwinjira
    def go_setup():
        nav.controls = []
        p1, p2 = pw("Password nshya (nibura inyuguti 4)"), pw("Subiramo password")

        def ok(e):
            if p1.value != p2.value:
                return err("Ibyo wanditse ntibihuye.")
            try:
                core.set_password(p1.value)
            except Exception as ex:
                return err(ex)
            start()

        show(h(core.SHOP_NAME), ft.Text("Ni ubwa mbere ukoresheje porogaramu. Shyiraho password."),
             p1, p2, ft.Button("Bika password", on_click=ok))

    def go_login():
        nav.controls = []
        p = pw("Password")

        def ok(e):
            if core.check_password(p.value):
                start()
            else:
                time.sleep(1)
                err("Password si yo.")

        show(h(core.SHOP_NAME), p, ft.Button("Injira", on_click=ok))

    def build_nav():
        nav.controls = [ft.Button("Stock", on_click=lambda e: go_stock()),
                        ft.Button("Kugurisha", on_click=lambda e: go_sales()),
                        ft.Button("Abakiriya", on_click=lambda e: go_customers()),
                        ft.Button("Raporo", on_click=lambda e: go_report()),
                        ft.Button("Ibindi", on_click=lambda e: go_settings())]

    def start():
        build_nav()
        go_stock()
        n = len(core.low_stock_items())
        if n:
            say(f"⚠ Ibicuruzwa {n} bigiye gushira.", False)

    # ------------------------------------------------------------ Stock
    def go_stock():
        sel = {"id": None, "del": False}
        keys = [("name", "Igicuruzwa (Designation)"), ("qty", "Umubare winjiye"),
                ("buy", "Igiciro cyo kurangura"), ("sell", "Igiciro cyo kugurisha"),
                ("min", "Ntarengwa (alert) - 5 arizo zisigaye")]
        f = {k: tf(l, num=(k != "name")) for k, l in keys}
        search = tf("Shakisha muri stock", on_change=lambda e: refresh())
        only_low = ft.Checkbox(label="Ibigiye gushira gusa", value=False, on_change=lambda e: refresh())
        lst = ft.Column(spacing=4)
        low_lbl = ft.Text("", color=RED, weight=ft.FontWeight.BOLD)
        tot_lbl = ft.Text("", weight=ft.FontWeight.BOLD)

        def refresh():
            lst.controls = []
            total = 0
            for r in core.list_products(search.value, only_low.value):
                total += r["qty"] * r["buy_price"]
                bg = RED_BG if r["qty"] <= 0 else (ORANGE_BG if r["qty"] <= r["min_qty"] else GREY)
                lst.controls.append(ft.Container(
                    content=ft.Column([
                        ft.Text(r["name"], weight=ft.FontWeight.BOLD),
                        ft.Text(f"Usigaye: {r['qty']:g}  |  Kurangura: {core.fmt(r['buy_price'])}  |  "
                                f"Kugurisha: {core.fmt(r['sell_price'])}  |  {core.stock_status(r)}", size=12)],
                        spacing=2),
                    padding=8, border_radius=8, bgcolor=bg, on_click=lambda e, r=r: pick(r)))
            n = len(core.low_stock_items())
            low_lbl.value = f"⚠ Bigiye gushira: {n}" if n else ""
            tot_lbl.value = f"Agaciro k'ibiri muri stock: {core.fmt(total)} {core.CURRENCY}"
            page.update()

        def pick(r):
            sel["id"], sel["del"] = r["id"], False
            f["name"].value = r["name"]
            f["qty"].value = f"{r['qty']:g}"
            f["buy"].value = f"{r['buy_price']:g}"
            f["sell"].value = f"{r['sell_price']:g}"
            f["min"].value = f"{r['min_qty']:g}"
            say(f"Wahisemo: {r['name']}. Ushobora 'Kosora' cyangwa 'Siba'.")

        def vals():
            return [f[k].value for k in ("name", "qty", "buy", "sell", "min")]

        def add(e):
            try:
                core.add_product(*vals())
            except Exception as ex:
                return err(ex)
            go_stock()
            say("Byabitswe muri stock.")

        def update(e):
            if not sel["id"]:
                return err("Hitamo igicuruzwa mu rutonde mbere.")
            try:
                core.update_product(sel["id"], *vals())
            except Exception as ex:
                return err(ex)
            go_stock()
            say("Byakosowe.")

        def delete(e):
            if not sel["id"]:
                return err("Hitamo igicuruzwa mu rutonde mbere.")
            if not sel["del"]:
                sel["del"] = True
                return err("Kanda 'Siba' nanone kugira ngo wemeze gusiba.")
            core.delete_product(sel["id"])
            go_stock()
            say("Cyasibwe.")

        async def export(e):
            rows = core.stock_export_rows(search.value, only_low.value)
            if not rows:
                return err("Nta gicuruzwa cyo kohereza.")
            await save_bytes(f"stock_{core.today()}.xlsx",
                             core.xlsx_bytes(core.STOCK_HEADER, rows, "Stock"))

        show(h("Stock"), *f.values(),
             row(ft.Button("Ongera muri stock", on_click=add), ft.Button("Kosora", on_click=update),
                 ft.Button("Siba", on_click=delete), ft.Button("Sukura", on_click=lambda e: go_stock())),
             ft.Text("'Ongera' yongera umubare ku wari uhari (iyo izina ririho). 'Kosora' isimbuza "
                     "ibyo wanditse byose (iyo wibeshye). Kanda igicuruzwa mu rutonde ngo ugikosore.", size=11),
             ft.Divider(), search, row(only_low, ft.Button("Excel", on_click=export)),
             low_lbl, lst, tot_lbl)
        refresh()

    # ------------------------------------------------------------ Kugurisha
    S = {"cart": [], "sel": None, "customer": "", "phone": "", "date": None,
         "ideni": False, "paid": "", "psearch": ""}

    def go_sales():
        if not S["date"]:
            S["date"] = core.today()

        def setv(key):
            def h_(e):
                S[key] = e.control.value
            return h_

        sug, res = ft.Column(spacing=2), ft.Column(spacing=2)
        t_cust = tf("Izina ry'umukiriya", S["customer"])
        t_phone = tf("Telefone (si ngombwa)", S["phone"], on_change=setv("phone"))
        t_date = tf("Italiki (YYYY-MM-DD)", S["date"], on_change=setv("date"))
        t_paid = tf("Yishyuye (ku ideni)", S["paid"], num=True, on_change=setv("paid"))
        c_ideni = ft.Checkbox(label="IDENI (si CASH)", value=S["ideni"], on_change=lambda e: set_ideni(e))
        t_ps = tf("Shakisha igicuruzwa", S["psearch"])
        t_qty = tf("Ingano", "1", num=True)
        t_price = tf("Igiciro cya kimwe", num=True)
        lbl_sel = ft.Text("", weight=ft.FontWeight.BOLD)
        cart_col = ft.Column(spacing=2)
        lbl_total = ft.Text("", size=16, weight=ft.FontWeight.BOLD)

        def set_ideni(e):
            S["ideni"] = e.control.value

        def pick_customer(c):
            S["customer"], S["phone"] = c["name"], c["phone"] or ""
            t_cust.value, t_phone.value = S["customer"], S["phone"]
            sug.controls = []
            page.update()

        def on_cust(e):
            S["customer"] = e.control.value
            sug.controls = ([ft.Button(f"{c['name']}  {c['phone'] or ''}", on_click=lambda ev, c=c: pick_customer(c))
                             for c in core.customer_names(S["customer"])] if S["customer"].strip() else [])
            page.update()

        t_cust.on_change = on_cust

        def pick_product(p):
            S["sel"] = {"id": p["id"], "name": p["name"]}
            lbl_sel.value = f"Wahisemo: {p['name']} (hasigaye {p['qty']:g})"
            t_price.value = f"{p['sell_price']:g}"
            res.controls = []
            page.update()

        def on_ps(e):
            S["psearch"] = e.control.value
            res.controls = []
            if S["psearch"].strip():
                for p in core.list_products(S["psearch"])[:8]:
                    if p["qty"] > 0:
                        res.controls.append(ft.Button(
                            f"{p['name']} - hasigaye {p['qty']:g} - {core.fmt(p['sell_price'])}",
                            on_click=lambda ev, p=p: pick_product(p)))
            page.update()

        t_ps.on_change = on_ps

        def add_line(e):
            try:
                p = S["sel"]
                if not p:
                    raise ValueError("Hitamo igicuruzwa.")
                q = core.num(t_qty.value, "Ingano")
                pr = core.num(t_price.value, "Igiciro cya kimwe")
                fresh = core.get_product(p["id"])
                in_cart = sum(l["qty"] for l in S["cart"] if l["pid"] == p["id"])
                if not fresh or q + in_cart > fresh["qty"]:
                    raise ValueError(f"Muri stock hasigaye {fresh['qty'] if fresh else 0:g} gusa.")
                S["cart"].append({"pid": p["id"], "name": p["name"], "qty": q, "price": pr})
            except Exception as ex:
                return err(ex)
            S["sel"], S["psearch"] = None, ""
            go_sales()

        def remove(i):
            del S["cart"][i]
            go_sales()

        def confirm(e):
            sold = {l["pid"] for l in S["cart"]}
            try:
                sid = core.create_sale(S["customer"], S["phone"], S["date"],
                                       core.IDENI if S["ideni"] else core.CASH, S["paid"], S["cart"])
            except Exception as ex:
                return err(ex)
            S.update(cart=[], sel=None, psearch="", customer="", phone="", paid="", ideni=False)
            low = [r["name"] for r in core.low_stock_items() if r["id"] in sold]
            go_invoice(sid, go_sales, "⚠ Bigiye gushira: " + ", ".join(low) if low else "")

        total = 0
        for i, l in enumerate(S["cart"]):
            t = l["qty"] * l["price"]
            total += t
            cart_col.controls.append(ft.Row([
                ft.Text(f"{l['name']}: {l['qty']:g} × {core.fmt(l['price'])} = {core.fmt(t)}", expand=True, size=13),
                ft.Button("X", on_click=lambda ev, i=i: remove(i))]))
        lbl_total.value = f"TOTAL: {core.fmt(total)} {core.CURRENCY}"

        show(h("Kugurisha"), t_cust, sug, t_phone, t_date, c_ideni, t_paid, ft.Divider(),
             t_ps, res, lbl_sel, row(t_qty, t_price), ft.Button("Ongeraho", on_click=add_line),
             ft.Divider(), cart_col, lbl_total,
             row(ft.Button("EMEZA IGURISHA", on_click=confirm),
                 ft.Button("Hanagura byose", on_click=lambda e: (S.update(cart=[]), go_sales()))))

    def go_invoice(sid, back, note=""):
        lines = core.invoice_lines(sid)

        async def pdf(e):
            await save_bytes(f"facture_{sid:05d}.pdf", core.pdf_bytes(lines))

        show(h("Facture"), ft.Text(note, color=RED), mono_box(lines),
             row(ft.Button("Bika PDF (print / WhatsApp)", on_click=pdf),
                 ft.Button("Subira", on_click=lambda e: back())))
        say(f"Igurisha ryabitswe (Facture {sid:05d}).")

    # ------------------------------------------------------------ Abakiriya
    def go_customers(search=""):
        lst = ft.Column(spacing=4)
        s = tf("Shakisha umukiriya", search)

        def fill():
            lst.controls = []
            for c in core.customers_with_debt(s.value):
                lst.controls.append(ft.Container(
                    content=ft.Column([
                        ft.Text(c["name"], weight=ft.FontWeight.BOLD),
                        ft.Text(f"Ideni: {core.fmt(c['debt'])} {core.CURRENCY}   {c['phone'] or ''}", size=12)],
                        spacing=2),
                    padding=8, border_radius=8, bgcolor=RED_BG if c["debt"] > 0 else GREY,
                    on_click=lambda e, c=c: go_statement(c["id"])))
            page.update()

        s.on_change = lambda e: fill()
        show(h("Abakiriya / Ideni"), s, ft.Text("Kanda umukiriya urebe konti ye yose.", size=11), lst)
        fill()

    def go_statement(cid):
        c = core.get_customer(cid)
        lines = core.statement_lines(cid)
        debt = core.customer_debt(cid)
        pay = tf("Amafaranga yishyuwe", num=True)

        def do_pay(e):
            try:
                core.pay_debt(cid, pay.value)
            except Exception as ex:
                return err(ex)
            go_statement(cid)
            say("Ubwishyu bwabitswe.")

        async def pdf(e):
            await save_bytes(f"konti_{c['name']}.pdf", core.pdf_bytes(lines))

        async def xl(e):
            await save_bytes(f"konti_{c['name']}.xlsx",
                             core.xlsx_bytes(core.STATEMENT_HEADER, core.statement_export_rows(cid), "Konti"))

        items = [h(f"Konti: {c['name']}"), mono_box(lines),
                 ft.Text(f"IDENI RISIGAYE: {core.fmt(debt)} {core.CURRENCY}", size=16, weight=ft.FontWeight.BOLD,
                         color=RED if debt > 0 else GREEN)]
        if debt > 0:
            items += [pay, ft.Button("Kwishyura ideni", on_click=do_pay)]
        items.append(row(ft.Button("Bika PDF", on_click=pdf), ft.Button("Excel", on_click=xl),
                         ft.Button("Subira", on_click=lambda e: go_customers())))
        show(*items)

    # ------------------------------------------------------------ Raporo
    R = {"day": None, "last": None, "title": ""}

    def go_report():
        if not R["day"]:
            R["day"] = core.today()
        t_day = tf("Italiki (YYYY-MM-DD)", R["day"], on_change=lambda e: R.update(day=e.control.value))
        lst = ft.Column(spacing=4)
        summary = ft.Text("", weight=ft.FontWeight.BOLD)

        def run(daily):
            try:
                rows, totals = core.report(R["day"] if daily else None)
            except Exception as ex:
                return err(ex)
            R["last"] = (rows, totals)
            R["title"] = f"UMUNSI WA {R['day']}" if daily else "BYOSE"
            go_report()

        async def export(e):
            if not R["last"]:
                return err("Banza ukore raporo, hanyuma uyohereze.")
            rows, totals = R["last"]
            await save_bytes(f"raporo_{R['title'].replace(' ', '_')}.xlsx",
                             core.xlsx_bytes(core.REPORT_HEADER, core.report_export_rows(rows, totals), "Raporo"))

        if R["last"]:
            rows, t = R["last"]
            for r in rows[:200]:
                lst.controls.append(ft.Container(
                    content=ft.Column([
                        ft.Text(f"{r[0]}  #{r[1]}  {r[2]}  ({r[8]})", size=12, weight=ft.FontWeight.BOLD),
                        ft.Text(f"{r[3]}: {r[4]:g} × {core.fmt(r[5])} = {core.fmt(r[6])}  |  inyungu {core.fmt(r[7])}",
                                size=12)], spacing=2),
                    padding=6, border_radius=6, bgcolor=GREY))
            if len(rows) > 200:
                lst.controls.append(ft.Text(f"... n'indi mirongo {len(rows) - 200} (iboneka muri Excel).", size=11))
            summary.value = (f"RAPORO {R['title']}\nIbyagurishijwe: {core.fmt(t['total'])} {core.CURRENCY}\n"
                             f"INYUNGU: {core.fmt(t['profit'])} {core.CURRENCY}\n"
                             f"CASH: {core.fmt(t['cash'])}  |  IDENI: {core.fmt(t['credit'])}")
        show(h("Raporo & Inyungu"), t_day,
             row(ft.Button("Raporo y'umunsi", on_click=lambda e: run(True)),
                 ft.Button("Raporo ya byose", on_click=lambda e: run(False)),
                 ft.Button("Excel", on_click=export)),
             summary, lst)

    # ------------------------------------------------------------ Ibindi
    def go_settings():
        old, n1, n2 = pw("Password isanzwe"), pw("Password nshya"), pw("Subiramo password nshya")

        def change(e):
            if not core.check_password(old.value):
                return err("Password isanzwe si yo.")
            if n1.value != n2.value:
                return err("Password nshya ntihuye.")
            try:
                core.set_password(n1.value)
            except Exception as ex:
                return err(ex)
            go_settings()
            say("Password nshya yabitswe.")

        async def backup(e):
            await save_bytes(f"duka_backup_{core.today()}.db", core.backup_bytes())

        low = core.low_stock_items()
        low_col = ft.Column([ft.Text(f"• {r['name']}: hasigaye {r['qty']:g} (ntarengwa {r['min_qty']:g})", size=13)
                             for r in low] or [ft.Text("Nta gicuruzwa kigiye gushira.")], spacing=2)
        show(h("Ibicuruzwa bigiye gushira"), low_col, ft.Divider(),
             h("Hindura password"), old, n1, n2, ft.Button("Bika password nshya", on_click=change),
             ft.Divider(), h("Backup"),
             ft.Text("Bika kopi y'amakuru yose (duka.db) kugira ngo adahomba telefone ihindutse cyangwa "
                     "app isibwe.", size=12),
             ft.Button("Bika backup", on_click=backup), ft.Divider(),
             ft.Button("Funga (Lock)", on_click=lambda e: go_login()))

    # ------------------------------------------------------------ itangira
    page.add(ft.SafeArea(content=ft.Container(content=ft.Column([nav, msg, body], expand=True),
                                              padding=8, expand=True), expand=True))
    go_login() if core.has_password() else go_setup()


ft.run(main)
