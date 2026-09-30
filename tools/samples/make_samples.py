"""Generate the fictional sample attachments used on the Triage page.

cd tools/samples && uv run --with pillow --with matplotlib python make_samples.py

Everything shown is invented for Meridian Logistics (fictional). The customer email carries a
fake email address and 555 phone number on purpose, to exercise sensitive-data flagging.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "apps" / "web" / "public" / "samples"


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def scanner_screen() -> None:
    """A handheld scanner's WMS app after it lost its connection."""
    img = Image.new("RGB", (480, 800), "#f4f4f4")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 480, 64], fill="#1f3b57")
    d.text((20, 18), "WMS Mobile 4.2", font=font(26), fill="white")
    d.text((360, 22), "05:58", font=font(22), fill="white")
    d.rectangle([20, 96, 460, 196], fill="#c62828")
    d.text((40, 112), "Host not reachable", font=font(30), fill="white")
    d.text((40, 156), "Cannot connect to wms-prod-02:8443", font=font(20), fill="white")
    lines = [
        ("Device", "HH-MEM-015"),
        ("Location", "Receiving, dock 4"),
        ("Scans pending upload", "37"),
        ("Last successful sync", "05:42"),
        ("Wi-Fi", "MERIDIAN-WH (connected, no access)"),
        ("802.1X certificate", "EXPIRED 2026-08-17"),
    ]
    y = 232
    for label, value in lines:
        d.text((24, y), label, font=font(18), fill="#555555")
        d.text((24, y + 24), value, font=font(24), fill="#111111")
        y += 72
    d.rounded_rectangle([24, 690, 456, 760], radius=10, fill="#1f3b57")
    d.text((180, 710), "RETRY", font=font(28), fill="white")
    img.save(OUT / "scanner-screen.png", optimize=True)


def vpn_error() -> None:
    """A VPN client dialog on a remote laptop."""
    img = Image.new("RGB", (760, 380), "#e9e9e9")
    d = ImageDraw.Draw(img)
    d.rectangle([40, 30, 720, 350], fill="white", outline="#9a9a9a")
    d.rectangle([40, 30, 720, 72], fill="#dadada")
    d.text((58, 42), "VPN Client", font=font(20), fill="#222222")
    d.ellipse([70, 105, 130, 165], fill="#d32f2f")
    d.text((92, 112), "!", font=font(40), fill="white")
    d.text((160, 102), "Unable to connect to the portal", font=font(26), fill="#111111")
    body = [
        "The portal configuration could not be read. The cached",
        "configuration may be corrupted.",
        "",
        "Portal: vpn.meridian-logistics.example",
        "Client version: 6.3.0 (updated this morning)",
        "Error code: PORTAL_CFG_READ (0x2041)",
    ]
    for i, line in enumerate(body):
        d.text((160, 148 + i * 26), line, font=font(18), fill="#333333")
    d.rounded_rectangle([600, 300, 700, 336], radius=6, fill="#1565c0")
    d.text((636, 307), "OK", font=font(20), fill="white")
    img.save(OUT / "vpn-error.png", optimize=True)


def customer_email() -> None:
    """A customer's email about a certificate warning, saved as a PDF."""
    text = [
        ("From: Dana Ortiz <dana.ortiz@bluehaven-freight.example>", 10, "normal"),
        ("To: Meridian Logistics Carrier Support", 10, "normal"),
        ("Date: 15 July 2026, 06:41", 10, "normal"),
        ("Subject: Security warning on your carrier booking portal", 10, "bold"),
        ("", 10, "normal"),
        ("Hello,", 11, "normal"),
        ("", 11, "normal"),
        ("Since about 06:10 this morning every dispatcher on our team gets a browser warning", 11, "normal"),
        ("when opening your carrier booking portal (booking.meridian-logistics.example):", 11, "normal"),
        ("", 11, "normal"),
        ('    "Your connection is not private   NET::ERR_CERT_DATE_INVALID"', 11, "normal"),
        ("", 11, "normal"),
        ("It happens in Chrome and Edge, on the office network and on phones. We can't book", 11, "normal"),
        ("today's pickups for the Dallas and Atlanta DCs until this is fixed, and two other", 11, "normal"),
        ("carriers we work with told us they see the same thing.", 11, "normal"),
        ("", 11, "normal"),
        ("Please call me when it is resolved: (555) 010-4477.", 11, "normal"),
        ("", 11, "normal"),
        ("Dana Ortiz", 11, "normal"),
        ("Dispatch Manager, Bluehaven Freight", 11, "normal"),
    ]
    fig = plt.figure(figsize=(8.5, 11))
    y = 0.93
    for line, size, weight in text:
        fig.text(0.08, y, line, fontsize=size, fontweight=weight, family="DejaVu Sans")
        y -= 0.028
    fig.savefig(OUT / "customer-email.pdf", metadata={"Title": "Carrier portal security warning"})
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    scanner_screen()
    vpn_error()
    customer_email()
    for f in sorted(OUT.iterdir()):
        print(f.name, f.stat().st_size)
