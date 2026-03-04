from typing import List, Optional, Dict
import re
from markdown_it import MarkdownIt

class SemanticSection:
    def __init__(
        self,
        title: str,
        level: int,
        start_index: int,
        end_index: int = -1,
        content: str = "",
    ):
        self.title = title
        self.level = level
        self.start_index = start_index
        self.end_index = end_index
        self.own_content = content  # Text strictly within this section (before next heading)
        self.children: List['SemanticSection'] = []
        
        # Content Inventory
        self.image_count = 0
        self.table_count = 0
        self.code_block_count = 0
        
        # Summaries
        self.own_summary: str = ""
        self.context_summary: str = ""
        
    def add_child(self, child: 'SemanticSection'):
        self.children.append(child)

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "level": self.level,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "image_count": self.image_count,
            "table_count": self.table_count,
            "code_block_count": self.code_block_count,
            "own_summary": self.own_summary,
            "context_summary": self.context_summary,
            "children": [child.to_dict() for child in self.children]
        }

class MarkdownParser:
    def __init__(self):
        self.md = MarkdownIt()

    def parse(self, markdown_text: str) -> SemanticSection:
        tokens = self.md.parse(markdown_text)
        
        root = SemanticSection(title="Root", level=0, start_index=0, end_index=len(markdown_text), content="")
        stack: List[SemanticSection] = [root]
        
        headings = []
        for i, token in enumerate(tokens):
            if token.type == "heading_open":
                level = int(token.tag[1])
                title = ""
                if i + 1 < len(tokens) and tokens[i+1].type == "inline":
                    title = tokens[i+1].content
                
                headings.append({
                    "level": level,
                    "title": title,
                    "map": token.map
                })

        lines = markdown_text.splitlines(keepends=True)
        
        def get_pos(line_idx):
            if line_idx >= len(lines):
                return len(markdown_text)
            return sum(len(l) for l in lines[:line_idx])

        for h in headings:
            start_pos = get_pos(h["map"][0])
            section = SemanticSection(
                title=h["title"],
                level=h["level"],
                start_index=start_pos
            )
            
            while len(stack) > 1 and stack[-1].level >= h["level"]:
                stack.pop()
            
            stack[-1].add_child(section)
            stack.append(section)

        self._fill_section_details(root, markdown_text)
        
        return root

    def _fill_section_details(self, section: SemanticSection, full_text: str):
        # Determine the end of "own content" (until first child starts or section ends)
        if section.children:
            own_content_end = section.children[0].start_index
        else:
            own_content_end = section.end_index

        section.own_content = full_text[section.start_index:own_content_end]
        
        # Content Inventory using robust Regex
        # 1. Images: ![]() or ![alt]()
        section.image_count = len(re.findall(r"!\[.*?\]\(.*?\)", section.own_content))
        
        # 2. Tables: Look for separator line | --- | or |:---| etc.
        # This is a reliable way to detect Markdown tables without a full AST plugin
        section.table_count = len(re.findall(r"^\s*\|[:\s-]*\|[\s-]*.*$", section.own_content, re.MULTILINE))
        
        # 3. Code Blocks: count occurrences of ``` and divide by 2
        section.code_block_count = len(re.findall(r"```", section.own_content)) // 2

        for child in section.children:
            child_idx = section.children.index(child)
            if child_idx + 1 < len(section.children):
                child.end_index = section.children[child_idx+1].start_index
            else:
                child.end_index = section.end_index
                
            self._fill_section_details(child, full_text)
