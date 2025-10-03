"""Consulta el estado de una CPE automotor y guarda la respuesta en la base de datos."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import xml.etree.ElementTree as ET

# Configurar Django para poder guardar los datos en la base de datos
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "count.settings")

import django  # noqa: E402

django.setup()

from django.utils import timezone  # noqa: E402
from django.utils.dateparse import parse_datetime  # noqa: E402

from trips.models import CPEAutomotor  # noqa: E402

# ==============================
# CONFIGURACIÓN
# ==============================
URL_PROD = "https://cpea-ws.afip.gob.ar/wscpe/services/soap"

CUIT = "30716004720"   # tu CUIT

# Datos de la CPE a consultar
TIPO_CPE = 74          # Automotor
SUCURSAL = 1           # sucursal sin ceros a la izquierda
NRO_ORDEN = 25209      # número de orden sin ceros a la izquierda
NRO_CTG = "010225047780"  # CTG con 12 dígitos


def element_to_dict(element: ET.Element) -> Any:
    """Convierte un elemento XML en un diccionario anidado."""

    children = list(element)
    if not children:
        return (element.text or "").strip()

    data: dict[str, Any] = {}
    for child in children:
        key = child.tag.split("}")[-1]
        value = element_to_dict(child)
        if key in data:
            if not isinstance(data[key], list):
                data[key] = [data[key]]
            data[key].append(value)
        else:
            data[key] = value
    return data


def parse_iso_datetime(value: str | None):
    """Parsea fechas ISO y las convierte a zona horaria configurada en Django."""

    if not value:
        return None

    parsed = parse_datetime(value)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None

    if parsed and timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def guardar_cpe(datos_cpe: dict[str, Any]) -> None:
    """Guarda o actualiza la información de la CPE en la base de datos."""

    cabecera = datos_cpe.get("cabecera", {}) or {}
    nro_ctg = str(cabecera.get("nroCTG") or NRO_CTG).strip()

    defaults = {
        "tipo_carta_porte": cabecera.get("tipoCartaPorte"),
        "sucursal": cabecera.get("sucursal"),
        "nro_orden": cabecera.get("nroOrden"),
        "estado": cabecera.get("estado"),
        "fecha_emision": parse_iso_datetime(cabecera.get("fechaEmision")),
        "fecha_inicio_estado": parse_iso_datetime(cabecera.get("fechaInicioEstado")),
        "fecha_vencimiento": parse_iso_datetime(cabecera.get("fechaVencimiento")),
        "observaciones": cabecera.get("observaciones"),
        "raw_response": datos_cpe,
    }

    registro, creado = CPEAutomotor.objects.update_or_create(
        nro_ctg=nro_ctg,
        defaults=defaults,
    )

    accion = "creado" if creado else "actualizado"
    print(f"Registro {accion} en la base de datos para el CTG {registro.nro_ctg}.")


def main() -> None:
    """Ejecuta el flujo de consulta de CPE y persiste la respuesta."""

    # Leer token y sign desde archivos generados por WSAA
    with open("token.txt", "r", encoding="utf-8") as ft:
        token = ft.read().strip()

    with open("sign.txt", "r", encoding="utf-8") as fs:
        sign = fs.read().strip()

    # ==============================
    # ARMAR REQUEST SOAP
    # ==============================
    soap_body = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\"
                  xmlns:wsc=\"https://serviciosjava.afip.gob.ar/wscpe/\">
  <soapenv:Header/>
  <soapenv:Body>
    <wsc:ConsultarCPEAutomotorReq>
      <auth>
        <token>{token}</token>
        <sign>{sign}</sign>
        <cuitRepresentada>{CUIT}</cuitRepresentada>
      </auth>
      <solicitud>
        <nroCTG>{NRO_CTG}</nroCTG>
      </solicitud>
    </wsc:ConsultarCPEAutomotorReq>
  </soapenv:Body>
</soapenv:Envelope>
"""

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "https://serviciosjava.afip.gob.ar/wscpe/consultarCPEAutomotor",
    }

    # Guardar request
    with open("request.xml", "w", encoding="utf-8") as f:
        f.write(soap_body)

    # ==============================
    # ENVIAR REQUEST
    # ==============================
    resp = requests.post(URL_PROD, data=soap_body.encode("utf-8"), headers=headers, timeout=60)

    # Guardar response
    with open("response.xml", "w", encoding="utf-8") as f:
        f.write(resp.text)

    print("=== Archivos generados ===")
    print("request.xml  → XML enviado al WS")
    print("response.xml → XML recibido del WS")

    # ==============================
    # PROCESAR RESPUESTA EN DICCIONARIO
    # ==============================
    if resp.status_code == 200:
        root = ET.fromstring(resp.text)
        respuesta = root.find(".//respuesta")
        if respuesta is not None:
            datos_cpe = element_to_dict(respuesta)

            print("\n=== DATOS DE LA CPE (formato JSON) ===")
            print(json.dumps(datos_cpe, indent=2, ensure_ascii=False))

            guardar_cpe(datos_cpe)
        else:
            print("No se encontró el bloque <respuesta> en la respuesta del WS")
            print(resp.text)
    else:
        print("Error HTTP:", resp.status_code)
        print(resp.text)


if __name__ == "__main__":
    main()
