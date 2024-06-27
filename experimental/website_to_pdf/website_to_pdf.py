import pdfkit

def convert_website_to_pdf(url: str, output_path: str):
    config = pdfkit.configuration()

    # Options to disable local file access
    options = {
        '--disable-local-file-access': ''
    }

    # Convert website to PDF
    pdfkit.from_url(url, output_path, configuration=config, options=options)
    print(f"Website {url} has been converted to {output_path}")

if __name__ == "__main__":
    website_url = "https://medium.com/google-cloud/unravelling-gemini-multimodal-llms-on-vertex-ai-6e4d64499473"
    output_pdf_path = "output.pdf"
    convert_website_to_pdf(website_url, output_pdf_path)
