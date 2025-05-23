import os
import markdown2

def convert_md_to_html(md_file_path):
    with open(md_file_path, 'r', encoding='utf-8') as md_file:
        md_content = md_file.read()
    
    html_content = markdown2.markdown(md_content)
    
    html_file_path = md_file_path.replace('.md', '.html')
    with open(html_file_path, 'w', encoding='utf-8') as html_file:
        html_file.write(html_content)
    
    print(f"Converted {md_file_path} to {html_file_path}")

def convert_all_md_to_html(docs_dir):
    for root, _, files in os.walk(docs_dir):
        for file in files:
            if file.endswith('.md'):
                md_file_path = os.path.join(root, file)
                convert_md_to_html(md_file_path)

if __name__ == "__main__":
    docs_dir = 'docs'
    convert_all_md_to_html(docs_dir)
