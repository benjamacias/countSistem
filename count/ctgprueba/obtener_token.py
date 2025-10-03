import subprocess
import base64
import datetime as dt
import requests
import xml.etree.ElementTree as ET
import uuid

# ==============================
# CONFIGURACIÓN
# ==============================
CERT = "certificado.pem"  # tu cert convertido a PEM
KEY = "jdmkey.key"        # tu clave privada
TRA_FILE = "login_ticket_request.xml"
CMS_FILE = "login.cms.der"
SERVICE = "wscpe"
WSAA_URL = "https://wsaa.afip.gov.ar/ws/services/LoginCms"

# ==============================
# CONSTRUIR TRA
# ==============================
now = dt.datetime.now(dt.timezone.utc)
generation = (now - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
expiration = (now + dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
uid = int(uuid.uuid4().int % 1e10)

tra = f"""<loginTicketRequest version="1.0">
  <header>
    <uniqueId>{uid}</uniqueId>
    <generationTime>{generation}Z</generationTime>
    <expirationTime>{expiration}Z</expirationTime>
  </header>
  <service>{SERVICE}</service>
</loginTicketRequest>"""

with open(TRA_FILE, "w", encoding="utf-8") as f:
    f.write(tra)

print("=== TRA generado ===")
print(tra)

# ==============================
# FIRMAR TRA con OpenSSL
# ==============================
subprocess.run([
    "openssl", "smime", "-sign",
    "-in", TRA_FILE,
    "-signer", CERT,
    "-inkey", KEY,
    "-out", CMS_FILE,
    "-outform", "DER",
    "-nodetach"
], check=True)

with open(CMS_FILE, "rb") as f:
    cms_der = f.read()

cms_b64 = base64.b64encode(cms_der).decode("ascii")

# ==============================
# ENVIAR A WSAA
# ==============================
envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Header/>
  <soapenv:Body>
    <loginCms xmlns="http://wsaa.view.sua.dvadac.desein.afip.gov.ar">
      <in0>{cms_b64}</in0>
    </loginCms>
  </soapenv:Body>
</soapenv:Envelope>"""

headers = {
    "Content-Type": "text/xml; charset=utf-8",
    "SOAPAction": "loginCms"
}

resp = requests.post(WSAA_URL, data=envelope.encode("utf-8"), headers=headers, timeout=60)

print("=== Respuesta WSAA ===")
print("HTTP:", resp.status_code)

if resp.status_code == 200:
    root = ET.fromstring(resp.text)
    login_return = None
    for elem in root.iter():
        if elem.tag.endswith("loginCmsReturn"):
            login_return = elem
            break
    if login_return is not None and login_return.text:
        ta_xml = ET.fromstring(login_return.text)
        token = ta_xml.findtext(".//token")
        sign = ta_xml.findtext(".//sign")
        expiration = ta_xml.findtext(".//expirationTime")

        print("\n=== CREDENCIALES WSAA ===")
        print("TOKEN:", token[:80], "...")
        print("SIGN :", sign[:80], "...")
        print("Expira:", expiration)

        # Guardar en archivos
        with open("token.txt", "w", encoding="utf-8") as ft:
            ft.write(token)

        with open("sign.txt", "w", encoding="utf-8") as fs:
            fs.write(sign)

        with open("ta.xml", "w", encoding="utf-8") as fx:
            fx.write(login_return.text)

        print("\n=== Archivos generados ===")
        print("token.txt → contiene el TOKEN")
        print("sign.txt  → contiene el SIGN")
        print("ta.xml    → contiene el TA completo (Ticket de Acceso)")
    else:
        print("No se encontró loginCmsReturn en la respuesta.")
else:
    print(resp.text)
