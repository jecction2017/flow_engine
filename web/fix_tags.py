from pathlib import Path

tag = "div"
p = Path(r"e:\cursor\flow_engine\web\src\components\SecretManagerPanel.vue")
text = p.read_text(encoding="utf-8")
text = text.replace("<motion", f"<{tag}")
text = text.replace("</motion>", f"</{tag}>")
p.write_text(text, encoding="utf-8", newline="\n")
