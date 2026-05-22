---
name: pdf-generator
description: Generate PDFs from Markdown, HTML, or URLs
trigger: pdf
model: claude-opus-4-7
---

# PDF Generator

Convert documents and web content to PDF format. Supports multiple input types:
- **Markdown files** → PDF (via Pandoc)
- **HTML content** → PDF (via wkhtmltopdf)
- **Web URLs** → PDF (via wkhtmltopdf)

## Available Commands

### Convert Markdown to PDF
```bash
pandoc input.md -o output.pdf
```

### Convert HTML File to PDF
```bash
wkhtmltopdf input.html output.pdf
```

### Convert Web URL to PDF
```bash
wkhtmltopdf https://example.com output.pdf
```

### Convert with Options
Pandoc supports many options:
```bash
pandoc input.md -o output.pdf --pdf-engine=xvfb-run --pdf-engine-opt=--enable-local-file-access
```

wkhtmltopdf supports:
```bash
wkhtmltopdf --page-size A4 --margin-top 0.75in input.html output.pdf
```

## Usage Examples

When a user asks you to generate a PDF:

1. **Markdown to PDF**: If you have a Markdown file at `/workspace/group/document.md`, run:
   ```bash
   pandoc /workspace/group/document.md -o /workspace/group/output.pdf
   ```

2. **HTML to PDF**: If you have HTML content, save it and convert:
   ```bash
   cat > /workspace/group/temp.html << 'EOF'
   <html>
   <body>
   <h1>My PDF Document</h1>
   <p>This is the content.</p>
   </body>
   </html>
   EOF
   wkhtmltopdf /workspace/group/temp.html /workspace/group/output.pdf
   ```

3. **Web Content to PDF**: Convert a website directly:
   ```bash
   wkhtmltopdf https://example.com /workspace/group/webpage.pdf
   ```

## File Locations

- **Input files**: Read from `/workspace/group/` or any accessible directory
- **Output PDFs**: Write to `/workspace/group/` so the user can access them
- **Temporary files**: Use `/tmp/` for intermediate files

## Notes

- Pandoc works best with well-formed Markdown
- wkhtmltopdf may have issues with JavaScript-heavy websites (use Chromium via agent-browser for those)
- Ensure output paths are writable (`/workspace/group/` is always writable)
- Large PDFs may take time; consider adding `2>/dev/null` to suppress verbose output
