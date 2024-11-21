import argparse
import re

from typing import List, Optional
from datetime import datetime
from pathlib import Path

from sql import Database, Paper


class MarkdownExporter:
    def __init__(self, db: Database):
        self.db = db

    def generate_markdown(self, papers: List[Paper], title: str = "Research Paper Summaries") -> str:
        """Generate markdown content from a list of papers."""
        # Sort papers by title
        papers = sorted(papers, key=lambda x: x.title.lower())
        
        md_content = f"# {title}\n\n"
        md_content += f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by [PubSummarizer](https://github.com/Logan-Lin/PubSummarizer)*\n\n"

        for paper in papers:
            md_content += self._format_paper(paper)

        return md_content

    def _format_paper(self, paper: Paper) -> str:
        """Format a single paper into markdown."""
        md_text = f"## {paper.title}\n\n"
        
        if paper.summary:
            # Split summary into topics and main summary
            clean_summary = paper.summary.replace('**', '').replace('__', '')
            
            # Extract topics, TL;DR, and summary sections
            sections = clean_summary.split('[')
            for section in sections:
                section_lower = section.lower()
                if section_lower.startswith('topics:]'):
                    topics = re.sub(r'(?i)Topics:]', '', section).strip()
                    md_text += "### Topics\n\n"
                    md_text += f"{topics}\n\n"
                elif section_lower.startswith('tl;dr:]'):
                    tldr = re.sub(r'(?i)TL;DR:]', '', section).strip()
                    md_text += "### TL;DR\n\n"
                    md_text += f"{tldr}\n\n"
                elif section_lower.startswith('summary:]'):
                    summary = re.sub(r'(?i)Summary:]', '', section).strip()
                    md_text += "### Summary\n\n"
                    md_text += f"{summary}\n\n"

        if paper.pdf_url:
            md_text += f"**Paper URL**: [{paper.pdf_url}]({paper.pdf_url})\n\n"
        
        md_text += "---\n\n"
        return md_text

    def export_to_file(self, output_path: str, filters: Optional[dict] = None, title: str = "Research Paper Summaries") -> None:
        """
        Export papers from database to a markdown file.
        
        Args:
            output_path: Path where the markdown file will be saved
            filters: Optional filters to apply when querying papers
            title: Custom title for the markdown document
        """
        papers = self.db.get_papers(filters)
        
        if not papers:
            raise ValueError("No papers found in the database with the given filters")

        # Generate markdown content with custom title
        md_content = self.generate_markdown(papers, title)

        # Ensure the output directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)


class WebExporter:
    def __init__(self, db: Database):
        self.db = db
        
    def generate_html(self, papers: List[Paper], title: str = "Research Paper Summaries") -> str:
        """Generate HTML content from a list of papers."""
        # Sort papers by title
        papers = sorted(papers, key=lambda x: x.title.lower())
        
        html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>PubSummarizer - {title}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://unpkg.com/masonry-layout@4/dist/masonry.pkgd.min.js"></script>
</head>
<body>
    <div class="container py-4">
        <h1 class="mb-4">{title}</h1>
        <p class="text-muted"><em>Generated on {date} by <a href="https://github.com/Logan-Lin/PubSummarizer">PubSummarizer</a></em></p>
        <div class="row" data-masonry='{{"percentPosition": true }}'>
            {papers_content}
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
        papers_content = "\n".join(self._format_paper(paper) for paper in papers)
        return html_content.format(
            title=title,
            date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            papers_content=papers_content
        )

    def _format_paper(self, paper: Paper) -> str:
        """Format a single paper into HTML using Bootstrap components."""
        html_text = '<div class="col-sm-12 col-lg-6 col-xl-4 mb-4">\n'
        html_text += '<div class="card shadow-sm">\n<div class="card-body">\n'
        html_text += f'<h3 class="card-title h4">{paper.title}</h3>\n'
        
        if paper.summary:
            # Sometimes, LLM apply special formatting to the title of the sections. Remove for consistency.
            clean_summary = paper.summary.replace('**', '').replace('__', '')
            sections = clean_summary.split('[')
            
            for section in sections:
                section_lower = section.lower()
                if section_lower.startswith('topics:]'):
                    topics = re.sub(r'(?i)Topics:]', '', section).strip()
                    topic_list = [t.strip() for t in topics.split(',')]
                    html_text += '<div class="mb-3">\n'
                    html_text += '<div class="d-flex gap-2 flex-wrap">\n'
                    for topic in topic_list:
                        html_text += f'<span class="badge bg-primary">{topic}</span>\n'
                    html_text += '</div>\n'
                    html_text += '</div>\n'
                elif section_lower.startswith('tl;dr:]'):
                    tldr = re.sub(r'(?i)TL;DR:]', '', section).strip()
                    html_text += '<div class="mb-3">\n'
                    html_text += '<h3 class="h5">TL;DR</h3>\n'
                    html_text += f'<p class="card-text">{tldr}</p>\n'
                    html_text += '</div>\n'
                elif section_lower.startswith('summary:]'):
                    summary = re.sub(r'(?i)Summary:]', '', section).strip()
                    html_text += '<div class="mb-3">\n'
                    html_text += '<h3 class="h5">Summary</h3>\n'
                    html_text += f'<p class="card-text">{summary}</p>\n'
                    html_text += '</div>\n'

        if paper.pdf_url:
            html_text += f'<p class="card-text"><strong>Paper URL:</strong> <a href="{paper.pdf_url}" class="link-primary">{paper.pdf_url}</a></p>\n'
        
        html_text += '</div>\n</div>\n</div>\n'
        return html_text

    def export_to_file(self, output_path: str, filters: Optional[dict] = None, title: str = "Research Paper Summaries") -> None:
        """
        Export papers from database to an HTML file.
        
        Args:
            output_path: Path where the HTML file will be saved
            filters: Optional filters to apply when querying papers
            title: Custom title for the HTML page
        """
        papers = self.db.get_papers(filters)
        
        if not papers:
            raise ValueError("No papers found in the database with the given filters")

        html_content = self.generate_html(papers, title)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)


def export_papers(db_url: str, output_path: str, format: str = 'markdown', filters: Optional[dict] = None, title: str = "Research Paper Summaries") -> None:
    """
    Convenience function to export papers from a database to either markdown or HTML format.
    
    Args:
        db_url: Database URL to connect to
        output_path: Path where the output file will be saved
        format: Output format - either 'markdown' or 'html' (default: 'markdown')
        filters: Optional filters to apply when querying papers
        title: Custom title for the output document
    """
    db = Database(db_url)
    
    if format.lower() == 'markdown':
        exporter = MarkdownExporter(db)
    elif format.lower() == 'html':
        exporter = WebExporter(db)
    else:
        raise ValueError(f"Unsupported format: {format}. Use 'markdown' or 'html'")
        
    exporter.export_to_file(output_path, filters, title)
    print(f"Exported papers to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export papers from a database")
    parser.add_argument("--db_url", type=str, required=True, help="Database URL")
    parser.add_argument("--output_path", type=str, required=True, help="Output path for the file")
    parser.add_argument("--format", type=str, choices=['markdown', 'html'], default='markdown', 
                      help="Output format (markdown or html)")
    parser.add_argument("--filters", type=dict, help="Filters to apply when querying papers", default={})
    parser.add_argument("--title", type=str, default="Research Paper Summaries",
                      help="Custom title for the output document")
    args = parser.parse_args()

    export_papers(args.db_url, args.output_path, args.format, args.filters, args.title)
