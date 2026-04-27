import pypdf

reader = pypdf.PdfReader("final-proejct-plan.pdf")
text = ""
for page in reader.pages:
    text += page.extract_text() + "\n"

print(text)
