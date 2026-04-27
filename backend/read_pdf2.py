import pypdf

reader = pypdf.PdfReader("final-proejct-plan.pdf")
text = ""
for page in reader.pages:
    text += page.extract_text() + "\n"

with open("plan_text_utf8.txt", "w", encoding="utf-8") as f:
    f.write(text)
