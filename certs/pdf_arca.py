from fact_arca import emitir_factura, cargar_ta, ta_vigente
import xmltodict
from datetime import datetime
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import os

CUIT_EMISOR = 20431255570 

def generar_qr(cuit_emisor, tipo_cbte, pto_vta, cbte_nro, imp_total, cae, cae_vto):
    data = {
        "ver": 1,
        "fecha": datetime.now().strftime('%Y-%m-%d'),
        "cuit": cuit_emisor,
        "ptoVta": pto_vta,
        "tipoCmp": tipo_cbte,
        "nroCmp": cbte_nro,
        "importe": round(imp_total, 2),
        "moneda": "PES",
        "ctz": 1.0,
        "tipoDocRec": 99,
        "nroDocRec": 0,
        "tipoCodAut": "E",
        "codAut": int(cae)
    }

    import json, base64
    json_str = json.dumps(data)
    base64_data = base64.urlsafe_b64encode(json_str.encode()).decode()
    url = f"https://www.afip.gob.ar/fe/qr/?p={base64_data}"
    qr = qrcode.make(url)
    qr_path = "qr_afip.png"
    qr.save(qr_path)
    return qr_path

def tipo_cbte_letra(tipo_cbte):
    return {
        1: 'A',
        6: 'B',
        11: 'C'
    }.get(tipo_cbte, 'X')  # 'X' si tipo no reconocido

def generar_pdf(datos):
    letra = tipo_cbte_letra(datos['tipo_cbte'])
    nombre_pdf = f"factura_{letra}_{datos['pto_vta']:04d}-{datos['cbte_nro']:08d}.pdf"

    c = canvas.Canvas(nombre_pdf, pagesize=A4)
    c.setFont("Helvetica", 12)

    c.drawString(100, 800, f"Factura {letra} - N° {datos['pto_vta']:04d}-{datos['cbte_nro']:08d}")
    c.drawString(100, 780, f"CUIT Emisor: {datos['cuit_emisor']}")
    c.drawString(100, 760, f"Fecha: {datos['fecha_cbte']}")
    c.drawString(100, 740, f"Importe Total: ${datos['imp_total']}")
    c.drawString(100, 720, f"CAE: {datos['cae']}")
    c.drawString(100, 700, f"Vencimiento CAE: {datos['cae_vto']}")

    qr_path = generar_qr(
        cuit_emisor=datos['cuit_emisor'],
        tipo_cbte=datos['tipo_cbte'],
        pto_vta=datos['pto_vta'],
        cbte_nro=datos['cbte_nro'],
        imp_total=datos['imp_total'],
        cae=datos['cae'],
        cae_vto=datos['cae_vto']
    )
    c.drawImage(qr_path, 100, 600, width=150, height=150)
    c.save()

    print(f"✅ PDF generado: {nombre_pdf}")
    return nombre_pdf

def main():
    ta_dict = cargar_ta()
    if not ta_dict or not ta_vigente(ta_dict):
        raise Exception("TA vencido o inexistente. Ejecutá primero fact_arca.py para emitir una factura válida.")

    token = ta_dict["credentials"]["token"]
    sign = ta_dict["credentials"]["sign"]

    print("Emitiendo factura nueva para generar PDF...")
    resultado, imp_total = emitir_factura(token, sign)
    detalle = resultado['FeDetResp']['FECAEDetResponse'][0]

    datos_factura = {
        'tipo_cbte': resultado['FeCabResp']['CbteTipo'],
        'pto_vta': resultado['FeCabResp']['PtoVta'],
        'cbte_nro': detalle['CbteDesde'],
        'fecha_cbte': detalle['CbteFch'],
        'cae': detalle['CAE'],
        'cae_vto': detalle['CAEFchVto'],
        'cuit_emisor': CUIT_EMISOR,
        'imp_total': imp_total  # <- ya no falla porque lo recibimos de la función
    }

    print("Generando PDF con QR...")
    generar_pdf(datos_factura)

if __name__ == "__main__":
    main()
