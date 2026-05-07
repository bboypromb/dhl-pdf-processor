from http.server import BaseHTTPRequestHandler
import fitz
import json
import os
import requests
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            body = json.loads(self.rfile.read(content_length))

            pdf_url = body.get("pdf_url")
            pdf_name = body.get("pdf_name", "document").replace(" ", "_")

            # Download PDF
            response = requests.get(pdf_url)
            pdf_bytes = response.content

            # Open with PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            sb = create_client(SUPABASE_URL, SUPABASE_KEY)

            results = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text().strip()
                image_urls = []

                # Extract images from this page
                for img in page.get_images():
                    xref = img[0]
                    try:
                        image_data = doc.extract_image(xref)
                        img_bytes = image_data["image"]
                        img_ext = image_data["ext"]

                        filename = f"{pdf_name}_p{page_num+1}_{xref}.{img_ext}"

                        # Upload to Supabase Storage
                        sb.storage.from_("screenshots").upload(
                            filename,
                            img_bytes,
                            {"content-type": f"image/{img_ext}"}
                        )

                        public_url = sb.storage.from_("screenshots").get_public_url(filename)
                        image_urls.append(public_url)

                    except Exception as img_error:
                        print(f"Image error on page {page_num+1}: {img_error}")
                        continue

                if text:
                    results.append({
                        "page": page_num + 1,
                        "text": text,
                        "images": image_urls
                    })

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({ "pages": results }).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({ "error": str(e) }).encode())
