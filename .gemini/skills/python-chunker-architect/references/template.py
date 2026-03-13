"""
GOLDEN TEMPLATE: Markdown Semantic Chunker (AST Data Structure)
Logic: Builds a formal Semantic Tree, merges/splits sibling nodes, aggregates stats, and exports.
"""
import uuid
import re
from typing import List, Dict, Any, Optional, Tuple
import marko
from marko.block import Heading, Paragraph, List as MDList, Quote, FencedCode, HTMLBlock
from marko.ext.gfm import gfm
from marko.md_renderer import MarkdownRenderer

class SemanticSection:
    """Core AST Node representing either a structural heading or a content leaf."""
    def __init__(self, title: str, level: int, content: str = ""):
        self.node_id: str = str(uuid.uuid4())
        self.title: str = title
        self.level: int = level
        self.own_content: str = content
        
        # Bi-directional pointers
        self.parent: Optional['SemanticSection'] = None
        self.children: List['SemanticSection'] = []
        self.next_sibling: Optional['SemanticSection'] = None
        self.prev_sibling: Optional['SemanticSection'] = None
        
        # Local Inventory
        self.image_count: int = 0
        self.table_count: int = 0
        self.code_block_count: int = 0
        self.token_count: int = 0  # Approximated by word count in this template
        
        # Aggregated Statistics
        self.total_descendants: int = 0
        self.total_token_count: int = 0
        self.has_tables_in_subtree: bool = False
        self.has_images_in_subtree: bool = False

    def add_child(self, child: 'SemanticSection') -> None:
        child.parent = self
        if self.children:
            last_child = self.children[-1]
            last_child.next_sibling = child
            child.prev_sibling = last_child
        self.children.append(child)

    def aggregate_statistics(self) -> None:
        self.total_token_count = self.token_count
        self.total_descendants = len(self.children)
        self.has_tables_in_subtree = self.table_count > 0
        self.has_images_in_subtree = self.image_count > 0

        for child in self.children:
            child.aggregate_statistics()
            self.total_token_count += child.total_token_count
            self.total_descendants += child.total_descendants
            self.has_tables_in_subtree |= child.has_tables_in_subtree
            self.has_images_in_subtree |= child.has_images_in_subtree

    def get_ancestors(self) -> List['SemanticSection']:
        ancestors, current = [], self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors[::-1]

    def get_breadcrumb_path(self) -> str:
        path = [node.title for node in self.get_ancestors() if node.title]
        if self.title: path.append(self.title)
        return " > ".join(path)

    def to_rag_document(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "text": self.own_content,
            "metadata": {
                "title": self.title,
                "breadcrumb": self.get_breadcrumb_path(),
                "level": self.level,
                "total_tokens": self.total_token_count,
                "has_tables": self.has_tables_in_subtree,
                "has_images": self.has_images_in_subtree,
            }
        }


class ASTSemanticChunker:
    def __init__(self, chunk_size_limit: int = 500):
        self.chunk_size_limit = chunk_size_limit
        self.md = marko.Markdown(extensions=['gfm'], renderer=MarkdownRenderer)

    def process_document(self, markdown_text: str) -> List[Dict[str, Any]]:
        """Main pipeline: Parse -> Build AST -> Prune/Chunk -> Aggregate -> Export."""
        # 1. Parse markdown
        marko_ast = self.md.parse(markdown_text)
        
        # 2. Build the structural tree
        root_node = self._build_tree(marko_ast)
        
        # 3. Smart chunking (Merge & Split leaf nodes)
        self._prune_and_chunk(root_node)
        
        # 4. Bubble up RAG statistics
        root_node.aggregate_statistics()
        
        # 5. Export only the content leaf nodes
        rag_docs = []
        for node in self._get_leaf_nodes(root_node):
            if node.own_content.strip():
                rag_docs.append(node.to_rag_document())
                
        return rag_docs

    def _build_tree(self, marko_ast: Any) -> SemanticSection:
        """Infers hierarchy from flat markdown and attaches content as leaf children."""
        root = SemanticSection(title="Document Root", level=0)
        active_headings = {0: root}

        for child in marko_ast.children:
            if isinstance(child, Heading):
                level = child.level
                title = self.md.render(child).strip('#').strip()
                new_section = SemanticSection(title=title, level=level)
                
                # Find closest structural parent
                parent_level = level - 1
                while parent_level > 0 and parent_level not in active_headings:
                    parent_level -= 1
                
                active_headings[parent_level].add_child(new_section)
                active_headings[level] = new_section
                
                # Clear deeper transient headings
                for k in list(active_headings.keys()):
                    if k > level: del active_headings[k]
            else:
                # It's a content block -> Treat as a Leaf Node
                content = self.md.render(child).strip()
                if not content: continue
                
                deepest_level = max(active_headings.keys())
                parent = active_headings[deepest_level]
                
                leaf_node = SemanticSection(title="", level=parent.level + 1, content=content)
                leaf_node.token_count = len(content.split()) # Proxy for token count
                
                node_type = type(child).__name__
                if node_type == 'Table': leaf_node.table_count = 1
                elif "<IMAGE_" in content or node_type == 'Image': leaf_node.image_count = 1
                elif "<CODE_" in content or node_type == 'FencedCode': leaf_node.code_block_count = 1
                    
                parent.add_child(leaf_node)
                
        return root

    def _prune_and_chunk(self, node: SemanticSection) -> None:
        """Post-order traversal to merge small siblings and split oversized ones."""
        new_children = []
        current_merged_leaf = None

        for child in node.children:
            if child.title: # It's a structural branch, recurse into it
                if current_merged_leaf:
                    new_children.append(current_merged_leaf)
                    current_merged_leaf = None
                self._prune_and_chunk(child)
                new_children.append(child)
            else: # It's a content leaf
                if current_merged_leaf is None:
                    current_merged_leaf = child
                else:
                    # Merge Condition
                    if current_merged_leaf.token_count + child.token_count <= self.chunk_size_limit:
                        current_merged_leaf.own_content += "\n\n" + child.own_content
                        current_merged_leaf.token_count += child.token_count
                        current_merged_leaf.table_count += child.table_count
                        current_merged_leaf.image_count += child.image_count
                        current_merged_leaf.code_block_count += child.code_block_count
                    else:
                        # Flush current and start a new merged block
                        new_children.append(current_merged_leaf)
                        current_merged_leaf = child

        if current_merged_leaf:
            new_children.append(current_merged_leaf)

        # Split Condition for oversized leaf nodes
        final_children = []
        for child in new_children:
            is_atomic = child.table_count > 0 or child.image_count > 0 or child.code_block_count > 0
            if child.title == "" and child.token_count > self.chunk_size_limit and not is_atomic:
                # Naive sentence split for oversized blocks
                sentences = re.split(r'(?<=[.!?]) +', child.own_content)
                temp_content = ""
                for s in sentences:
                    if len(temp_content.split()) + len(s.split()) > self.chunk_size_limit and temp_content:
                        split_leaf = SemanticSection(title="", level=child.level, content=temp_content.strip())
                        split_leaf.token_count = len(temp_content.split())
                        final_children.append(split_leaf)
                        temp_content = s
                    else:
                        temp_content += (" " if temp_content else "") + s
                if temp_content:
                    split_leaf = SemanticSection(title="", level=child.level, content=temp_content.strip())
                    split_leaf.token_count = len(temp_content.split())
                    final_children.append(split_leaf)
            else:
                final_children.append(child)

        # Re-attach the pruned/split children ensuring sibling links are re-calculated
        node.children = []
        for child in final_children:
            node.add_child(child)

    def _get_leaf_nodes(self, node: SemanticSection) -> List[SemanticSection]:
        """Utility to extract purely content-bearing nodes."""
        leaves = []
        if node.title == "": leaves.append(node)
        for child in node.children:
            leaves.extend(self._get_leaf_nodes(child))
        return leaves