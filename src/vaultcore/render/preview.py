"""HTML-предпросмотр документа (резервный путь, если QtPdf недоступен).

Основной предпросмотр в интерфейсе — настоящий PDF (``QPdfView``). Этот модуль
нужен, чтобы приложение не осталось без визуализации на сборках без QtPdf, а
также чтобы можно было «показать документ» в текстовом окружении (например,
в отчёте тестов).
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from .. import canonical, codec, crypto
from ..fmt import local_label
from .template import Template, load_template


def _fmt_local(payload: canonical.Payload) -> str:
    return local_label(payload)


def render_html(
    payload: canonical.Payload,
    *,
    code: str | None = None,
    template: Template | None = None,
    key_fingerprint: str | None = None,
    valid: bool | None = None,
) -> str:
    """Возвращает самодостаточный HTML-документ (A4-пропорции, без внешних ресурсов)."""
    tpl = template or load_template()
    code_text = code or codec.encode(payload)
    ink = tpl.color("ink", "#1f2733")
    muted = tpl.color("muted", "#5a6472")
    rule = tpl.color("rule", "#1f3a5f")
    block_bg = tpl.color("blockBg", "#f5f7fa")
    border = tpl.color("blockBorder", "#9aa7b6")
    stamp = tpl.color("stamp", "#7b1f2b")

    paragraphs = []
    for block in payload.text.split("\n\n"):
        block = block.strip("\n")
        if not block.strip():
            continue
        paragraphs.append("<p>" + "<br/>".join(escape(line) for line in block.split("\n")) + "</p>")

    status_chip = ""
    if valid is True:
        status_chip = (
            '<div style="background:#e7f4ec;border:1px solid #1d6b3a;color:#14512c;'
            'padding:8px 12px;border-radius:6px;margin-bottom:14px;font-family:sans-serif;'
            'font-size:12px">Документ подлинный, содержимое не изменялось</div>'
        )
    elif valid is False:
        status_chip = (
            '<div style="background:#fbeaea;border:1px solid #8c1d1d;color:#8c1d1d;'
            'padding:8px 12px;border-radius:6px;margin-bottom:14px;font-family:sans-serif;'
            'font-size:12px">Документ изменён или подпись недействительна</div>'
        )

    key_fp = escape(key_fingerprint or crypto.fingerprint(payload.public_key))
    body = "\n".join(paragraphs)

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{escape(payload.title)}</title></head>
<body style="margin:0;background:#eceff3;padding:18px;">
<div style="max-width:760px;margin:0 auto;background:#fff;border:1px solid #d6dbe2;
            box-shadow:0 2px 10px rgba(0,0,0,.08);padding:40px 46px;position:relative;">
  <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
              transform:rotate(-24deg);color:{stamp};opacity:.12;font-family:sans-serif;
              font-weight:700;font-size:64px;pointer-events:none;user-select:none;">ОБРАЗЕЦ</div>
  {status_chip}
  <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;
         border-bottom:2px solid {rule};padding-bottom:10px;">
    <tr>
      <td style="font-family:sans-serif;font-size:16px;font-weight:700;color:{ink};">
        {escape(tpl.app('name', 'VaultCore'))}
        <div style="font-size:11px;font-weight:400;color:{muted};margin-top:2px;">
          {escape(tpl.app('subtitle', ''))}</div>
      </td>
      <td align="right" style="font-family:sans-serif;font-size:10px;color:{muted};">
        {escape(tpl.app('tagline', ''))}</td>
    </tr>
  </table>
  <h1 style="font-family:Georgia,'Times New Roman',serif;font-size:24px;text-align:center;
             margin:26px 0 6px;color:{ink};">{escape(payload.title)}</h1>
  <div style="font-family:sans-serif;font-size:11px;color:{muted};text-align:center;">
    {escape(tpl.text('idLabel', 'Документ №'))} {payload.document_id} ·
    {escape(tpl.text('formatLabel', 'формат кода VC1 v'))}{payload.version}
  </div>
  <div style="font-family:Georgia,'Times New Roman',serif;font-size:13px;text-align:center;
              margin:14px 0 4px;color:{ink};">
    <b>{escape(tpl.text('dateLabel', 'Дата и время создания (UTC)'))}:</b> {escape(payload.ts)}
  </div>
  <div style="font-family:sans-serif;font-size:10px;color:{muted};text-align:center;
              margin-bottom:18px;">
    {escape(tpl.text('localDateLabel', ''))}: {escape(_fmt_local(payload))}
  </div>
  <div style="font-family:Georgia,'Times New Roman',serif;font-size:13.5px;line-height:1.5;
              text-align:justify;color:{ink};">{body}</div>
  <div style="margin-top:26px;border:1px solid {border};background:{block_bg};padding:14px 16px;
              font-family:sans-serif;font-size:10.5px;color:{ink};">
    <div style="font-weight:700;font-size:12px;margin-bottom:6px;">
      {escape(tpl.text('certifyHeading', ''))}</div>
    <div style="color:{muted};margin-bottom:8px;">{escape(tpl.text('certifyIntro', ''))}</div>
    <div style="font-weight:700;color:{muted};margin-bottom:2px;">
      {escape(tpl.text('publicKeyLabel', ''))}</div>
    <div style="font-family:Consolas,monospace;font-size:9.5px;word-break:break-all;margin-bottom:6px;">
      {escape(payload.public_key_b64)}</div>
    <div style="font-size:9.5px;color:{muted};margin-bottom:6px;">
      {escape(tpl.text('fingerprintShortLabel', ''))}: {crypto.fingerprint_short(payload.public_key)} ·
      {escape(tpl.text('keyFingerprintLabel', ''))}: {key_fp}</div>
    <div style="font-weight:700;color:{muted};margin-bottom:2px;">
      {escape(tpl.text('signatureLabel', ''))}</div>
    <div style="font-family:Consolas,monospace;font-size:9.5px;word-break:break-all;margin-bottom:6px;">
      {escape(payload.signature_b64)}</div>
    <div style="font-size:9.5px;color:{muted};margin-bottom:6px;">
      {escape(tpl.text('signatureFingerprintLabel', ''))}: {crypto.signature_short(payload.signature)}</div>
    <div style="font-family:Consolas,monospace;font-size:9px;word-break:break-all;color:{muted};
                margin-bottom:8px;">{escape(tpl.text('digestLabel', ''))}: {payload.digest.hex()}</div>
    <div style="color:{stamp};font-weight:700;margin-bottom:6px;">
      {escape(tpl.text('disclaimer', ''))}</div>
    <div style="color:{muted};font-size:9px;">{escape(tpl.text('tsaNote', ''))}</div>
  </div>
  <div style="margin-top:14px;font-family:Consolas,monospace;font-size:8px;color:{muted};
              word-break:break-all;border-top:1px solid {border};padding-top:8px;">
    {escape(code_text)}</div>
</div>
</body></html>"""
