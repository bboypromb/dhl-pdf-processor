from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import fitz
import os
import re
import requests
from supabase import create_client

app = FastAPI()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

def clean_text(text):
    # Remove Chapman Bright header/footer
    patterns = [
        r'COMPANY:.*?(?=\n|$)',
        r'ADDRESS:.*?(?=\n|$)',
        r'WEBSITE:.*?(?=\n|$)',
        r'EMAIL:.*?(?=\n|$)',
        r'PHONE:.*?(?=\n|$)',
        r'BREDASEWEG.*?NL63INGB\d+',
        r'COC:.*?VAT:.*?(?=\n|$)',
    ]
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text

@app.post("/api/extract")
async def extract(request: Request):
    try:
        body = await request.json()
        pdf_url = body.get("pdf_url")
        pdf_name = body.get("pdf_name", "document").replace(" ", "_")

        response = requests.get(pdf_url)
        pdf_bytes = response.content

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)

        results = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = clean_text(page.get_text())
            image_urls = []

            for img in page.get_images():
                xref = img[0]
                try:
                    image_data = doc.extract_image(xref)
                    img_bytes = image_data["image"]
                    img_ext = image_data["ext"]
                    filename = f"{pdf_name}_p{page_num+1}_{xref}.{img_ext}"

                    sb.storage.from_("screenshots").upload(
                        filename,
                        img_bytes,
                        {"content-type": f"image/{img_ext}"}
                    )

                    public_url = sb.storage.from_("screenshots").get_public_url(filename)
                    image_urls.append(public_url)

                except Exception as img_error:
                    print(f"Image error page {page_num+1}: {img_error}")
                    continue

            if text and len(text) > 50:
                results.append({
                    "page": page_num + 1,
                    "text": text,
                    "images": image_urls
                })

        return JSONResponse({"pages": results})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
